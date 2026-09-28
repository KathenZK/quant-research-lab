#!/usr/bin/env python3
"""BIN-4H-MA7-RC P0R-DATA data-scope rerun.

Reuses frozen P0 mechanism/statistics without retuning. Replaces OHLCV inputs
with catalog dataset_ids. Does not overwrite P0 artifacts. Does not fix the
known P0 statistical blockers.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

from strategy_lab.data.catalog import (
    BINANCE_PERP_1H_FROM_15M_V1,
    BINANCE_PERP_1H_NORMALIZED_LEGACY,
    BINANCE_PERP_4H_FROM_15M_V1,
    DatasetScope,
    load_trusted_dataset,
    read_published_manifest,
    require_passing_trusted,
)
from strategy_lab.data.lake import DataLakeLayout
from strategy_lab.data.settings import default_settings

ROOT = Path(__file__).resolve().parents[4]
FAMILY_DIR = ROOT / "research/asset-portfolios/4h-ma7-regime-continuation"
P0_SCRIPT_PATH = FAMILY_DIR / "scripts/research_binance_4h_ma7_regime_continuation_p0.py"
CONFIG_PATH = FAMILY_DIR / "configs/binance-4h-ma7-regime-continuation-p0r-data.json"
ARTIFACT_DIR = FAMILY_DIR / "artifacts"
DIAGNOSTIC_DIR = FAMILY_DIR / "diagnostics"
REPORT_PATH = DIAGNOSTIC_DIR / "binance-4h-ma7-regime-continuation-p0r-data-results-2026-09-03.md"

EXPECTED_CONFIG_SHA256 = "4b4ceadcffea866a2783f4acfc06ecc445c4ad533c130a8ce94447bad5b55ff5"
EXPECTED_MANIFEST_SHA256 = "651bd88b5e349091c36b0de74b2a480b3f44383c22a1f58e11177e33dc9155ae"
RUN_DATE = "2026-09-03"
NATIVE_4H_COMPONENTS = 16
PATH_1H_COMPONENTS = 4

KNOWN_STATISTICAL_BLOCKERS = [
    "完整年度窗口仍只统计 2023–2025 三个日历年，PASS 却要求至少四个正年度，故 SUPPORTED_WEAK_CONTINUATION 在现口径下不可达。",
    "horizon 表先写 bootstrap p_value，随后 cluster 用同名 p_value 覆盖，导致 CI 与 p/q-value 检验对象不一致。本轮未修复。",
]

OHLCV_COLUMNS = [
    "ts",
    "exchange",
    "symbol",
    "market_type",
    "timeframe",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "quote_volume",
    "trade_count",
    "vwap",
    "is_closed",
    "source",
    "component_count",
]

OUTPUTS = {
    "data_audit": ARTIFACT_DIR / f"binance_4h_ma7_rc_p0r_data_data_audit_{RUN_DATE}.json",
    "universe": ARTIFACT_DIR / f"binance_4h_ma7_rc_p0r_data_universe_summary_{RUN_DATE}.csv",
    "events": ARTIFACT_DIR / f"binance_4h_ma7_rc_p0r_data_events_{RUN_DATE}.parquet",
    "metrics": ARTIFACT_DIR / f"binance_4h_ma7_rc_p0r_data_metrics_{RUN_DATE}.csv",
    "first_hit": ARTIFACT_DIR / f"binance_4h_ma7_rc_p0r_data_first_hit_{RUN_DATE}.csv",
    "horizon": ARTIFACT_DIR / f"binance_4h_ma7_rc_p0r_data_horizon_returns_{RUN_DATE}.csv",
    "survival": ARTIFACT_DIR / f"binance_4h_ma7_rc_p0r_data_survival_{RUN_DATE}.csv",
    "yearly": ARTIFACT_DIR / f"binance_4h_ma7_rc_p0r_data_yearly_{RUN_DATE}.csv",
    "concentration": ARTIFACT_DIR / f"binance_4h_ma7_rc_p0r_data_symbol_concentration_{RUN_DATE}.csv",
    "phase": ARTIFACT_DIR / f"binance_4h_ma7_rc_p0r_data_phase_{RUN_DATE}.csv",
    "controls": ARTIFACT_DIR / f"binance_4h_ma7_rc_p0r_data_controls_{RUN_DATE}.csv",
    "recent": ARTIFACT_DIR / f"binance_4h_ma7_rc_p0r_data_recent_slices_{RUN_DATE}.csv",
    "summary": ARTIFACT_DIR / f"binance_4h_ma7_rc_p0r_data_summary_{RUN_DATE}.json",
}


def load_p0_module():
    name = "binance_4h_ma7_rc_p0"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, P0_SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load P0 script {P0_SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


P0 = load_p0_module()

EIGHT_HOURS_NS = 8 * 3600 * 1_000_000_000
ONE_SECOND_NS = 1_000_000_000
_FUNDING_NS: dict[str, dict[int, float]] = {}


def expected_funding_times_ns(entry_ts: pd.Timestamp, exit_ts: pd.Timestamp) -> list[int]:
    """Same schedule as P0.expected_funding_times, without Timestamp.floor."""
    entry_ns = int(pd.Timestamp(entry_ts).value)
    exit_ns = int(pd.Timestamp(exit_ts).value)
    start_ns = (entry_ns // EIGHT_HOURS_NS + 1) * EIGHT_HOURS_NS
    if start_ns > exit_ns:
        return []
    end_ns = (exit_ns // ONE_SECOND_NS) * ONE_SECOND_NS
    if start_ns > end_ns:
        return []
    return list(range(start_ns, end_ns + 1, EIGHT_HOURS_NS))


def expected_funding_times_fast(entry_ts: pd.Timestamp, exit_ts: pd.Timestamp) -> list[pd.Timestamp]:
    return [pd.Timestamp(ts_ns, tz="UTC") for ts_ns in expected_funding_times_ns(entry_ts, exit_ts)]


def fast_funding_cost_for_window(
    lookup: dict[str, Any],
    symbol: str,
    entry_ts: pd.Timestamp,
    exit_ts: pd.Timestamp,
    side: int,
) -> tuple[float, bool, int, int]:
    expected = expected_funding_times_ns(entry_ts, exit_ts)
    if not expected:
        return 0.0, True, 0, 0
    table_ns = _FUNDING_NS.get(symbol)
    if table_ns is None:
        table = lookup.get(symbol)
        if table is None:
            return math.nan, False, len(expected), len(expected)
        table_ns = {
            int(pd.Timestamp(ts).value): float(rate) for ts, rate in table.by_second.items()
        }
        _FUNDING_NS[symbol] = table_ns
    rates: list[float] = []
    missing = 0
    for ts_ns in expected:
        rate = table_ns.get(ts_ns)
        if rate is None:
            missing += 1
        else:
            rates.append(rate)
    if missing:
        return math.nan, False, len(expected), missing
    return float(side * np.sum(rates)), True, len(expected), 0


def install_fast_funding(lookup: dict[str, Any]) -> None:
    """Replace P0 Timestamp.floor funding path with equivalent integer arithmetic."""
    global _FUNDING_NS
    _FUNDING_NS = {
        str(symbol): {
            int(pd.Timestamp(ts).value): float(rate) for ts, rate in table.by_second.items()
        }
        for symbol, table in lookup.items()
    }
    P0.expected_funding_times = expected_funding_times_fast
    P0.funding_cost_for_window = fast_funding_cost_for_window


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run frozen BIN-4H-MA7-RC P0R-DATA.")
    parser.add_argument("--run", action="store_true", help="Acknowledge outcome read.")
    parser.add_argument("--force", action="store_true", help="Replace existing P0R-DATA outputs only.")
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_sidecar(path: Path) -> str:
    digest = sha256_file(path)
    rel_path = path.relative_to(ROOT).as_posix()
    path.with_suffix(path.suffix + ".sha256").write_text(
        f"{digest}  {rel_path}\n", encoding="utf-8"
    )
    return digest


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def lake_layout() -> DataLakeLayout:
    return DataLakeLayout.from_settings(default_settings(ROOT))


def p0_protected_paths() -> list[Path]:
    paths = [
        P0.CONFIG_PATH,
        P0.CONFIG_PATH.with_suffix(P0.CONFIG_PATH.suffix + ".sha256"),
        P0.REPORT_PATH,
        P0.REPORT_PATH.with_suffix(P0.REPORT_PATH.suffix + ".sha256"),
        ARTIFACT_DIR / "binance_4h_ma7_rc_p0_dataset_manifest_2026-09-02.json",
        ARTIFACT_DIR / "binance_4h_ma7_rc_p0_dataset_manifest_2026-09-02.json.sha256",
        DIAGNOSTIC_DIR / "binance-4h-ma7-regime-continuation-p0-data-scope-correction-2026-09-02.md",
    ]
    paths.extend(P0.OUTPUTS.values())
    for path in [*P0.OUTPUTS.values(), P0.REPORT_PATH]:
        paths.append(path.with_suffix(path.suffix + ".sha256"))
    return [path for path in dict.fromkeys(paths)]


def assert_no_p0_collision() -> None:
    protected = {path.resolve() for path in p0_protected_paths()}
    planned = {path.resolve() for path in [*OUTPUTS.values(), REPORT_PATH]}
    overlap = protected & planned
    if overlap:
        names = ", ".join(rel(path) for path in sorted(overlap))
        raise RuntimeError(f"P0R-DATA outputs collide with protected P0 files: {names}")


def assert_p0_artifacts_intact() -> None:
    for path in p0_protected_paths():
        sidecar = path.with_suffix(path.suffix + ".sha256") if path.suffix != ".sha256" else path
        if path.suffix == ".sha256":
            continue
        if not path.exists() or not sidecar.exists():
            continue
        recorded = sidecar.read_text(encoding="utf-8").split()[0]
        actual = sha256_file(path)
        if actual != recorded:
            raise RuntimeError(
                f"protected P0 artifact changed before P0R-DATA: {rel(path)}"
            )


def prepare_outputs(force: bool) -> None:
    assert_no_p0_collision()
    assert_p0_artifacts_intact()
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    DIAGNOSTIC_DIR.mkdir(parents=True, exist_ok=True)
    existing = [path for path in [*OUTPUTS.values(), REPORT_PATH] if path.exists()]
    if existing and not force:
        names = ", ".join(rel(path) for path in existing[:3])
        raise RuntimeError(f"P0R-DATA outputs already exist; pass --force. Existing: {names}")


def validate_frozen_config() -> dict[str, Any]:
    actual = sha256_file(CONFIG_PATH)
    if actual != EXPECTED_CONFIG_SHA256:
        raise RuntimeError(
            f"frozen P0R-DATA config hash mismatch: {actual} != {EXPECTED_CONFIG_SHA256}"
        )
    config = load_json(CONFIG_PATH)
    if config["study_id"] != "BIN-4H-MA7-RC-P0R-DATA":
        raise RuntimeError("unexpected study_id")
    if config["data"]["native_4h_dataset_id"] != BINANCE_PERP_4H_FROM_15M_V1:
        raise RuntimeError("native 4h dataset_id is not frozen derived 4h")
    if config["data"]["path_1h_dataset_id"] != BINANCE_PERP_1H_FROM_15M_V1:
        raise RuntimeError("path 1h dataset_id is not frozen derived 1h")
    if BINANCE_PERP_1H_NORMALIZED_LEGACY not in config["data"]["forbidden_dataset_ids"]:
        raise RuntimeError("legacy 1h is not forbidden")
    if "ohlcv_1h_globs" in config["data"]:
        raise RuntimeError("P0R-DATA config must not contain legacy 1h globs")
    manifest_path = ROOT / config["data"]["dataset_manifest"]
    if sha256_file(manifest_path) != EXPECTED_MANIFEST_SHA256:
        raise RuntimeError("pre-outcome dataset manifest hash mismatch")
    manifest = load_json(manifest_path)
    if manifest.get("outcome_read") is not False:
        raise RuntimeError("dataset manifest is not marked pre-outcome")
    return config


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("SET TimeZone='UTC'")
    con.execute("SET enable_progress_bar=false")
    return con


def slim_coverage(coverage: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in coverage.items() if key != "per_symbol"}


def assert_allowed_dataset(dataset_id: str, record_root: Path) -> None:
    if dataset_id == BINANCE_PERP_1H_NORMALIZED_LEGACY:
        raise RuntimeError("P0R-DATA forbids binance.perp.ohlcv.1h.normalized.legacy")
    if dataset_id not in {BINANCE_PERP_4H_FROM_15M_V1, BINANCE_PERP_1H_FROM_15M_V1}:
        raise RuntimeError(f"unexpected dataset_id {dataset_id}")
    resolved = record_root.resolve()
    derived_root = (ROOT / "data/derived/datasets").resolve()
    if derived_root not in resolved.parents and resolved != derived_root:
        raise RuntimeError(f"dataset root is not under derived/datasets: {resolved}")
    text = str(resolved)
    if "normalized/ohlcv" in text and "timeframe=1h" in text:
        raise RuntimeError(f"refusing normalized legacy 1h path: {resolved}")


def catalog_trusted_load(dataset_id: str, cutoff: pd.Timestamp):
    layout = lake_layout()
    loaded = require_passing_trusted(
        load_trusted_dataset(
            dataset_id,
            layout=layout,
            requested_scope=DatasetScope.FULL_MARKET,
            end=cutoff,
            require_contiguous=False,
            require_closed=True,
            allow_full_scan=False,
            max_materialize_rows=0,
        )
    )
    assert_allowed_dataset(dataset_id, loaded.record.absolute_root(layout))
    if loaded.audit.get("quality_status") != "PASS":
        raise RuntimeError(f"{dataset_id} trusted load did not pass SQL quality audit")
    published = read_published_manifest(loaded.record, layout) or {}
    return loaded, {
        "dataset_id": dataset_id,
        "materialized": loaded.materialized,
        "status": loaded.record.status.value,
        "declared_scope": loaded.record.declared_scope.value,
        "requested_scope": DatasetScope.FULL_MARKET.value,
        "physical_root": rel(loaded.record.absolute_root(layout))
        if loaded.record.absolute_root(layout).is_relative_to(ROOT)
        else str(loaded.record.absolute_root(layout)),
        "coverage": slim_coverage(loaded.coverage),
        "union_stats": loaded.manifest.get("union_stats", {}),
        "quality_status": loaded.audit.get("quality_status"),
        "sql_audit": {
            key: loaded.audit.get(key)
            for key in (
                "rows",
                "duplicate_business_key_rows",
                "critical_null_rows",
                "illegal_ohlc_rows",
                "unverified_source_rows",
                "open_rows",
                "internal_missing_bars",
                "unaligned_gap_transitions",
                "cutoff_unclosed_excluded_rows",
                "gap_policy",
            )
        },
        "published_manifest_sha256": sha256_file(
            loaded.record.absolute_root(layout) / "_MANIFEST.json"
        )
        if (loaded.record.absolute_root(layout) / "_MANIFEST.json").exists()
        else None,
        "published_content_fingerprint": published.get("content_fingerprint"),
        "published_rows": published.get("rows"),
        "published_symbol_count": published.get("symbol_count"),
        "parquet_inventory_fingerprint": loaded.verified_identity.get(
            "parquet_inventory_fingerprint"
        ),
    }


def catalog_scope_gate(dataset_id: str, cutoff: pd.Timestamp) -> dict[str, Any]:
    _loaded, summary = catalog_trusted_load(dataset_id, cutoff)
    return summary


def load_derived_ohlcv(
    dataset_id: str,
    cutoff: pd.Timestamp,
    *,
    expected_timeframe: str,
    expected_components: int,
    symbols: list[str] | None = None,
    trusted=None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    layout = lake_layout()
    if trusted is None:
        trusted, _summary = catalog_trusted_load(dataset_id, cutoff)
    require_passing_trusted(trusted)
    root = trusted.record.absolute_root(layout)
    assert_allowed_dataset(dataset_id, root)
    files = list(trusted.verified_parquet_files)
    if not files:
        raise RuntimeError(f"{dataset_id} trusted load returned no verified parquet files")
    cols = ", ".join(OHLCV_COLUMNS)
    sql = f"""
        SELECT {cols}
        FROM read_parquet(?, hive_partitioning=false, union_by_name=true)
        WHERE ts < ?
          AND timeframe = ?
    """
    params: list[Any] = [[str(path) for path in files], cutoff.to_pydatetime(), expected_timeframe]
    if symbols is not None:
        sql += " AND symbol = ANY(?)"
        params.append(list(symbols))
    sql += " ORDER BY symbol, ts"
    con = connect()
    raw = con.execute(
        """
        SELECT
            count(*) AS raw_rows,
            count(DISTINCT symbol) AS raw_symbols,
            min(ts) AS min_ts,
            max(ts) AS max_ts,
            count(*) FILTER (
                WHERE symbol IS NULL OR ts IS NULL OR exchange IS NULL
                   OR market_type IS NULL OR open IS NULL OR high IS NULL
                   OR low IS NULL OR close IS NULL OR volume IS NULL
                   OR quote_volume IS NULL OR trade_count IS NULL
                   OR vwap IS NULL OR is_closed IS NULL OR source IS NULL
            ) AS critical_null_rows,
            count(*) FILTER (WHERE NOT is_closed) AS open_bar_rows,
            count(*) FILTER (
                WHERE open <= 0 OR high <= 0 OR low <= 0 OR close <= 0
                   OR volume < 0 OR quote_volume < 0 OR trade_count < 0
                   OR high < greatest(open, close, low)
                   OR low > least(open, close, high)
            ) AS invalid_ohlc_rows,
            count(*) FILTER (
                WHERE exchange != 'binance' OR market_type != 'perp'
                   OR timeframe != ?
            ) AS identity_mismatch_rows,
            count(*) FILTER (WHERE component_count IS NULL OR component_count != ?) AS wrong_component_rows
        FROM read_parquet(?, hive_partitioning=false, union_by_name=true)
        WHERE ts < ?
        """
        + (" AND symbol = ANY(?)" if symbols is not None else ""),
        (
            [expected_timeframe, expected_components, [str(path) for path in files], cutoff.to_pydatetime()]
            + ([list(symbols)] if symbols is not None else [])
        ),
    ).fetch_df().iloc[0]
    frame = con.execute(sql, params).fetch_df()
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
    frame["base_asset"] = frame["symbol"].str.replace("/USDT:USDT", "", regex=False)
    frame["quote_asset"] = "USDT"
    if "taker_buy_volume" not in frame.columns:
        frame["taker_buy_volume"] = 0.0
    if "taker_buy_quote_volume" not in frame.columns:
        frame["taker_buy_quote_volume"] = 0.0
    duplicate_selected = int(frame.duplicated(["symbol", "ts"]).sum())
    by_source = (
        frame.groupby("source", dropna=False)
        .agg(row_count=("symbol", "size"), symbols=("symbol", "nunique"))
        .reset_index()
        .to_dict("records")
        if not frame.empty
        else []
    )
    audit = {
        "dataset_id": dataset_id,
        "timeframe": expected_timeframe,
        "ohlcv_raw_rows_before_cutoff": int(raw["raw_rows"]),
        "ohlcv_selected_rows_before_cutoff": int(len(frame)),
        "ohlcv_raw_symbols_before_cutoff": int(raw["raw_symbols"]),
        "ohlcv_selected_symbols_before_cutoff": int(frame["symbol"].nunique()) if not frame.empty else 0,
        "ohlcv_min_ts_utc": P0._iso(raw["min_ts"]),
        "ohlcv_max_ts_utc": P0._iso(raw["max_ts"]),
        "ohlcv_critical_null_rows": int(raw["critical_null_rows"]),
        "ohlcv_open_bar_rows": int(raw["open_bar_rows"]),
        "ohlcv_invalid_ohlc_rows": int(raw["invalid_ohlc_rows"]),
        "ohlcv_identity_mismatch_rows": int(raw["identity_mismatch_rows"]),
        "ohlcv_wrong_component_rows": int(raw["wrong_component_rows"]),
        "ohlcv_duplicate_selected_symbol_ts_rows": duplicate_selected,
        "symbol_filter_count": None if symbols is None else int(len(symbols)),
        "ohlcv_selected_by_source": [
            {
                "source": str(row["source"]),
                "row_count": int(row["row_count"]),
                "symbols": int(row["symbols"]),
            }
            for row in by_source
        ],
    }
    blockers = [
        key
        for key in (
            "ohlcv_critical_null_rows",
            "ohlcv_open_bar_rows",
            "ohlcv_invalid_ohlc_rows",
            "ohlcv_identity_mismatch_rows",
            "ohlcv_wrong_component_rows",
            "ohlcv_duplicate_selected_symbol_ts_rows",
        )
        if audit[key] != 0
    ]
    if blockers:
        raise RuntimeError(f"{dataset_id} data-quality blockers: {blockers}")
    if frame.empty:
        raise RuntimeError(f"{dataset_id} selected union is empty before cutoff")
    return frame, audit


def prepare_native_4h(frame: pd.DataFrame, last_complete_4h: pd.Timestamp) -> pd.DataFrame:
    out = frame.loc[frame["ts"] <= last_complete_4h].copy()
    if out.empty:
        raise RuntimeError("native derived 4h is empty after last-complete-4h filter")
    if not out["timeframe"].eq("4h").all():
        raise RuntimeError("native panel contains non-4h rows")
    out["phase_hour"] = 0
    return out.reset_index(drop=True)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )


def write_report(summary: dict[str, Any], tables: dict[str, pd.DataFrame]) -> None:
    verdict = summary["decision"]["side_verdicts"]
    event_counts = summary["events"]
    audit = summary["data_audit"]

    def md_table(frame: pd.DataFrame, columns: list[str], n: int = 8) -> str:
        if frame.empty:
            return "_无数据_"
        view = frame.loc[:, columns].head(n).copy()

        def fmt(value: Any) -> str:
            if pd.isna(value):
                return ""
            if isinstance(value, float):
                return f"{value:.6f}"
            return str(value)

        header = "| " + " | ".join(columns) + " |"
        sep = "| " + " | ".join(["---"] * len(columns)) + " |"
        body = [
            "| " + " | ".join(fmt(value) for value in row) + " |"
            for row in view.to_numpy(dtype=object)
        ]
        return "\n".join([header, sep, *body])

    blockers_md = "\n".join(f"- {item}" for item in KNOWN_STATISTICAL_BLOCKERS)
    report = f"""# BIN-4H-MA7-RC P0R-DATA 结果报告（2026-09-03）

## 结论先行

P0R-DATA 最终裁决：long = `{verdict['long']['verdict']}`；short = `{verdict['short']['verdict']}`。本次仍保持 `explore / diagnostic-only / not promoted / not live-ready`，明确不登记 `V1`、不 promotion、不 live-ready、不创建 runner / live spec，也不得写入 `quant-runner`。

这是数据范围重跑，不是调参。机制仍只回答无条件 `4h SMA7` strict cross 后是否存在趋势延续。结果不得被用来事后选择 `MA5/MA10/SMA42`、方向、持仓期、币种或过滤器。

是否允许进入 P1：`{summary['decision']['p1_allowed']}`。理由：{summary['decision']['p1_reason']}

P0 六资产 `NO-GO` 仍只解释为 `DATA_SCOPE_INCOMPLETE / six-asset diagnostic-only`。本观察替换输入后，全市场结论以本报告为准，但不覆盖任何 P0 artifact。

## 数据与 PIT 币池审计

- 市场：Binance USD-M USDT perpetual，24/7 UTC。
- 原生 `4h`：`{audit['catalog_4h']['dataset_id']}`，`requested_scope=FULL_MARKET`。
- `1h` 路径：`{audit['catalog_1h']['dataset_id']}`，仅用于 first-hit 与 phase 1/2/3。
- 禁止读取：`binance.perp.ohlcv.1h.normalized.legacy` 与 normalized `1h` glob。
- `audit_as_of`：`{summary['config']['data']['audit_as_of_utc']}`。
- 数据截止：`{summary['config']['data']['cutoff_exclusive_utc']}`；最后允许完整原生 `4h`：`{summary['config']['data']['last_allowed_complete_4h_open_utc']}`。
- 配置 SHA256：`{summary['input_lineage']['config_sha256']}`；输入 manifest SHA256：`{summary['input_lineage']['dataset_manifest_sha256']}`。
- 原生 4h selected rows：`{audit['ohlcv_4h']['ohlcv_selected_rows_before_cutoff']}`，symbols：`{audit['ohlcv_4h']['ohlcv_selected_symbols_before_cutoff']}`，范围 `{audit['ohlcv_4h']['ohlcv_min_ts_utc']}` 至 `{audit['ohlcv_4h']['ohlcv_max_ts_utc']}`。
- 路径 1h selected rows：`{audit['ohlcv_1h']['ohlcv_selected_rows_before_cutoff']}`，symbols：`{audit['ohlcv_1h']['ohlcv_selected_symbols_before_cutoff']}`，范围 `{audit['ohlcv_1h']['ohlcv_min_ts_utc']}` 至 `{audit['ohlcv_1h']['ohlcv_max_ts_utc']}`。
- 4h FULL_MARKET coverage symbols：`{audit['catalog_4h']['coverage'].get('symbol_count')}`，long-history：`{audit['catalog_4h']['coverage'].get('long_history_symbols')}`，short-snapshot share：`{audit['catalog_4h']['coverage'].get('short_snapshot_share')}`。
- Funding selected rows：`{audit['funding_selected_rows_before_or_at_cutoff']}`，symbols：`{audit['funding_selected_symbols_before_or_at_cutoff']}`，范围 `{audit['funding_min_ts_utc']}` 至 `{audit['funding_max_ts_utc']}`。
- PIT 交易池规则：上市龄 `>=30` 天、30 日 trailing ADV `>=10,000,000 USDT`、30 日覆盖率 `>=95%`、每日最多 ADV 前 `120`；ADV 只用衍生 4h `quote_volume`。

关键数据 blocker：`{summary['blockers']}`。

## 明确不修复的统计 blocker

{blockers_md}

## 事件数量

- 主相位 `0h` / `SMA7`：总事件 `{event_counts['primary_ma7_phase0_total']}`，long `{event_counts['primary_ma7_phase0_long']}`，short `{event_counts['primary_ma7_phase0_short']}`，symbols `{event_counts['primary_ma7_phase0_symbols']}`。
- 全相位/全 MA 输出事件行：`{event_counts['all_event_rows']}`。
- 同侧非穿越对照行：`{event_counts['non_cross_control_rows']}`。

## Long / Short 无条件结果

{md_table(tables['first_hit'], ['direction', 'event_count', 'control_count', 'event_favorable_rate', 'control_favorable_rate', 'diff', 'ci_low', 'ci_high', 'p_value', 'q_value_bh'])}

## First-Hit 与生存曲线

first-hit 使用 `+2 ATR / -1 ATR / 30 bars`，`ATR_scale = ATR20[t-1]`；同一 `1h` 双障碍触发按 adverse-first。`1h` 路径来自 `binance.perp.ohlcv.1h.from_15m.v1`。

{md_table(tables['survival'], ['direction', 'metric', 'event_mean', 'control_mean', 'incremental_diff', 'ci_low', 'ci_high', 'p_value', 'q_value_bh'])}

## 固定期限收益

固定期限收益以 `open[t+1]` 入场，在期限结束后的可执行 `4h` open 平仓；下表为主相位 `SMA7`。horizon 表的 `p_value` 仍是 P0 同名覆盖后的 cluster p 值，不能当作 bootstrap p 值阅读。

{md_table(tables['horizon'], ['direction', 'horizon_4h_bars', 'cost_case', 'event_count', 'event_mean', 'control_mean', 'incremental_diff', 'ci_low', 'ci_high', 'q_value_bh'], n=36)}

## 成本与 Funding

成本列同时输出 gross、fee + 4bps、fee + 8bps 与 full net。Funding 按真实事件时间和方向累计，缺失不会填 0；`funding_complete_30_rate` 见年度表。若任一侧因 funding 缺失无法覆盖完整净收益，该侧不得给出可交易通过。

## 同侧非穿越基准

同侧非穿越基准按 `symbol × calendar_year × side × causal ATR quintile` 确定性加权，使对照分层权重与穿越事件一致；未使用随机时点或当前 TopN 回填。

## MA5/7/10/42 对照

{md_table(tables['controls'].loc[tables['controls']['control_type'].eq('ma_period')], ['ma_period', 'direction', 'events', 'first_hit_favorable_rate', 'net_return_4bps_30_mean', 'net_return_8bps_30_mean', 'mfe_30_mean', 'mae_30_mean'])}

## 年度、币种、流动性与集中度

年度结果。完整年度闸门仍只数 `2023–2025`，即使样本已覆盖更多年份：

{md_table(tables['yearly'], ['direction', 'calendar_year', 'events', 'first_hit_favorable_rate', 'net_return_4bps_30_mean', 'net_return_8bps_30_mean', 'funding_complete_30_rate'], n=20)}

集中度与 leave-one-out：

{md_table(tables['concentration'], ['direction', 'stress_case', 'stress_events', 'mean_net_return_30', 'stress_mean_net_return_30', 'max_symbol', 'max_symbol_contribution_share', 'top5_symbol_contribution_share', 'max_year', 'max_year_contribution_share', 'top1pct_event_contribution_share'], n=12)}

## Phase 检查

原生 `0h` 使用 `4h.from_15m.v1`；phase `1/2/3` 从 `1h.from_15m.v1` 按 P0 的四根连续 `1h` 公式重聚合。主结果只用原生 `0h`；非原生相位不替换主相位。

{md_table(tables['phase'], ['phase_hour', 'direction', 'events', 'first_hit_favorable_rate', 'net_return_4bps_30_mean', 'net_return_8bps_30_mean', 'mfe_30_mean', 'mae_30_mean', 'positive_phase_share', 'native_vs_phase_median_deviation'])}

## 最近切片

最近切片锚定本次可用主样本末尾，仅作审计，不参与选择。

{md_table(tables['recent'], ['slice', 'anchor_end_utc', 'direction', 'events', 'first_hit_favorable_rate', 'net_return_4bps_30_mean', 'net_return_8bps_30_mean'], n=20)}

## 数据或执行 Blocker

- P0R-DATA 未发现可绕过的执行入口：信号 bar 收盘后下一根 `4h` open 入场，未使用信号 close 成交。
- Funding 缺失事件只阻断对应净收益，不以 0 填充。
- 这不是策略回测；first-hit 障碍不是实际止盈止损。
- Live blocker：没有 runner 规格、没有账户组合、没有线上 open/close 对账，因此不允许 promotion 或 live-ready 声明。
- 本轮未修复上述两项统计口径 blocker。

## 是否进入 P1

`{summary['decision']['p1_allowed']}`。{summary['decision']['p1_reason']}

无论 P1 建议如何，本次不得自动晋升，也不得写入 `quant-runner`。

## 证据文件

- [P0R-DATA 合同](../specs/binance-4h-ma7-regime-continuation-p0r-data-contract-2026-09-03.md)
- [P0R-DATA 配置](../configs/binance-4h-ma7-regime-continuation-p0r-data.json)
- [P0 合同（机制父本）](../specs/binance-4h-ma7-regime-continuation-p0-contract-2026-09-02.md)
- [数据审计](../artifacts/binance_4h_ma7_rc_p0r_data_data_audit_2026-09-03.json)
- [事件表](../artifacts/binance_4h_ma7_rc_p0r_data_events_2026-09-03.parquet)
- [summary](../artifacts/binance_4h_ma7_rc_p0r_data_summary_2026-09-03.json)
- [脚本](../scripts/research_binance_4h_ma7_regime_continuation_p0r_data.py)
- [P0 结果（未覆盖）](binance-4h-ma7-regime-continuation-p0-results-2026-09-02.md)
"""
    REPORT_PATH.write_text(report, encoding="utf-8")


def main() -> None:
    args = parse_args()
    if not args.run:
        raise SystemExit("pass --run to acknowledge frozen historical outcome read")
    config = validate_frozen_config()
    prepare_outputs(args.force)
    rng = np.random.default_rng(P0.SEED)
    cutoff = pd.Timestamp(config["data"]["cutoff_exclusive_utc"])
    last_complete_4h = pd.Timestamp(config["data"]["last_allowed_complete_4h_open_utc"])
    last_closed_1h = pd.Timestamp(config["data"]["last_allowed_closed_1h_open_utc"])

    print("stage: catalog FULL_MARKET trusted loads", flush=True)
    trusted_4h, catalog_4h = catalog_trusted_load(config["data"]["native_4h_dataset_id"], cutoff)
    trusted_1h, catalog_1h = catalog_trusted_load(config["data"]["path_1h_dataset_id"], cutoff)
    print(
        f"  4h symbols={catalog_4h['coverage'].get('symbol_count')} "
        f"long_history={catalog_4h['coverage'].get('long_history_symbols')}",
        flush=True,
    )
    print(
        f"  1h symbols={catalog_1h['coverage'].get('symbol_count')} "
        f"long_history={catalog_1h['coverage'].get('long_history_symbols')}",
        flush=True,
    )

    print("stage: load derived 4h via dataset_id", flush=True)
    native_4h_raw, audit_4h = load_derived_ohlcv(
        config["data"]["native_4h_dataset_id"],
        cutoff,
        expected_timeframe="4h",
        expected_components=NATIVE_4H_COMPONENTS,
        trusted=trusted_4h,
    )
    native_4h = prepare_native_4h(native_4h_raw, last_complete_4h)
    print(f"  native 4h bars={len(native_4h)} symbols={native_4h['symbol'].nunique()}", flush=True)

    print("stage: load funding (same lake as P0)", flush=True)
    funding, funding_audit = P0.load_selected_funding(config)
    funding_lookup = P0.build_funding_lookup(funding)
    install_fast_funding(funding_lookup)

    print("stage: indicators and PIT universe on native 4h", flush=True)
    native_4h = P0.add_indicators(native_4h)
    eligibility, universe_summary = P0.build_universe(native_4h)
    pool_symbols = sorted(
        eligibility.loc[eligibility["in_trading_pool"].fillna(False), "symbol"].astype(str).unique()
    )
    print(
        f"  eligible symbol-days={int(eligibility['eligible'].sum())} "
        f"pool symbol-days={int(eligibility['in_trading_pool'].fillna(False).sum())} "
        f"ever-pool symbols={len(pool_symbols)}",
        flush=True,
    )
    if not pool_symbols:
        raise RuntimeError("PIT trading pool is empty")

    print("stage: load derived 1h via dataset_id for pool symbols", flush=True)
    ohlcv_1h, audit_1h = load_derived_ohlcv(
        config["data"]["path_1h_dataset_id"],
        cutoff,
        expected_timeframe="1h",
        expected_components=PATH_1H_COMPONENTS,
        symbols=pool_symbols,
        trusted=trusted_1h,
    )
    ohlcv_1h = ohlcv_1h.loc[ohlcv_1h["ts"] <= last_closed_1h].copy()
    hourly_by_sym = P0.hourly_maps(ohlcv_1h)
    print(f"  1h bars={len(ohlcv_1h)} symbols={ohlcv_1h['symbol'].nunique()}", flush=True)

    print("stage: aggregate phase 1/2/3 from derived 1h", flush=True)
    phase_panels = [native_4h]
    phase_audits: list[dict[str, Any]] = [
        {
            "phase_hour": 0,
            "source": BINANCE_PERP_4H_FROM_15M_V1,
            "symbols": int(native_4h["symbol"].nunique()),
            "complete_4h_bars": int(len(native_4h)),
            "incomplete_or_illegal_4h_groups": 0,
            "first_complete_4h_utc": P0._iso(native_4h["ts"].min()),
            "last_complete_4h_utc": P0._iso(native_4h["ts"].max()),
        }
    ]
    for phase in (1, 2, 3):
        bars, audit = P0.aggregate_4h(ohlcv_1h, int(phase))
        bars = bars.loc[bars["ts"] < cutoff].copy()
        bars = P0.add_indicators(bars)
        phase_panels.append(bars)
        phase_audits.append(audit)
        print(f"  phase {phase}: {audit['complete_4h_bars']} complete 4h bars", flush=True)
    panel = pd.concat(phase_panels, ignore_index=True)
    panel = P0.attach_universe(panel, eligibility)
    fourh_by_sym_phase = P0.panel_maps(panel)

    print("stage: extract strict-cross events", flush=True)
    event_frames = [P0.build_event_candidates(panel, period) for period in P0.MA_PERIODS]
    events = pd.concat([frame for frame in event_frames if not frame.empty], ignore_index=True)
    print(f"  event rows before outcome enrichment: {len(events)}", flush=True)
    print("stage: label event outcomes", flush=True)
    events = P0.enrich_outcomes(events, hourly_by_sym, fourh_by_sym_phase, funding_lookup)

    print("stage: build and label same-side non-cross controls", flush=True)
    controls_raw = P0.build_non_cross_controls(panel)
    print(f"  control rows before outcome enrichment: {len(controls_raw)}", flush=True)
    controls = P0.enrich_outcomes(controls_raw, hourly_by_sym, fourh_by_sym_phase, funding_lookup)
    controls = P0.apply_control_weights(
        events.loc[events["phase_hour"].eq(0) & events["ma_period"].eq(7)],
        controls,
    )

    print("stage: aggregate statistics and bootstrap confidence intervals", flush=True)
    first_hit = P0.build_first_hit_stats(events, controls, rng)
    horizon = P0.build_horizon_stats(events, controls, rng)
    survival = P0.build_survival_stats(events, controls, rng)
    yearly = P0.summarize_by_year(events)
    concentration = P0.concentration_rows(events)
    phase = P0.phase_stats(events)
    ma_controls = P0.ma_control_stats(events)
    recent = P0.recent_slices(events)
    metrics = P0.build_metrics_table(events)

    controls_summary = ma_controls.copy()
    controls_summary["control_weighted_rows"] = np.nan
    strata_coverage = (
        controls.groupby(["direction", "control_stratum_has_event"], dropna=False)
        .size()
        .reset_index(name="rows")
    )
    strata_coverage["control_type"] = "same_side_non_cross_coverage"
    strata_coverage["ma_period"] = 7
    for col in (
        "events",
        "first_hit_favorable_rate",
        "net_return_4bps_30_mean",
        "net_return_8bps_30_mean",
        "mfe_30_mean",
        "mae_30_mean",
        "survival_bars_mean",
        "control_weighted_rows",
    ):
        if col not in strata_coverage:
            strata_coverage[col] = np.nan
    controls_out = pd.concat(
        [controls_summary, strata_coverage[controls_summary.columns]],
        ignore_index=True,
    )

    verdicts = P0.side_verdicts(first_hit, horizon, survival, yearly, concentration, ma_controls)
    p1_allowed = any(
        item["verdict"] in {"SUPPORTED_WEAK_CONTINUATION", "PARTIAL_STRUCTURAL_SEPARATION"}
        for item in verdicts.values()
    )
    p1_reason = (
        "至少一侧存在可继续画 P1 状态地图的结构性分离；P1 仍须另行冻结。本次不得自动晋升。"
        if p1_allowed
        else "两侧均为 NO-GO；不应进入 P1，也不得用过滤器营救已揭示历史。"
    )

    data_audit = {
        "catalog_4h": catalog_4h,
        "catalog_1h": catalog_1h,
        "ohlcv_4h": audit_4h,
        "ohlcv_1h": audit_1h,
        **funding_audit,
        "aggregation_4h": phase_audits,
        "universe_days": int(eligibility["day"].nunique()),
        "universe_eligible_symbol_days": int(eligibility["eligible"].sum()),
        "universe_pool_symbol_days": int(eligibility["in_trading_pool"].fillna(False).sum()),
        "universe_ever_pool_symbols": int(len(pool_symbols)),
        "fail_closed_passed": True,
        "legacy_1h_read": False,
        "known_statistical_blockers": KNOWN_STATISTICAL_BLOCKERS,
    }
    primary_events = events.loc[events["phase_hour"].eq(0) & events["ma_period"].eq(7)]
    summary = {
        "family": "Binance-4H-MA7-Regime-Continuation",
        "alias": "BIN-4H-MA7-RC",
        "stage": "P0R-DATA",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "status": "explore / diagnostic-only / not promoted / not live-ready",
        "config": config,
        "input_lineage": {
            "config_path": rel(CONFIG_PATH),
            "config_sha256": EXPECTED_CONFIG_SHA256,
            "dataset_manifest_path": config["data"]["dataset_manifest"],
            "dataset_manifest_sha256": EXPECTED_MANIFEST_SHA256,
            "native_4h_dataset_id": BINANCE_PERP_4H_FROM_15M_V1,
            "path_1h_dataset_id": BINANCE_PERP_1H_FROM_15M_V1,
            "legacy_1h_forbidden": True,
        },
        "data_audit": data_audit,
        "events": {
            "all_event_rows": int(len(events)),
            "primary_ma7_phase0_total": int(len(primary_events)),
            "primary_ma7_phase0_long": int(primary_events["direction"].eq("long").sum()),
            "primary_ma7_phase0_short": int(primary_events["direction"].eq("short").sum()),
            "primary_ma7_phase0_symbols": int(primary_events["symbol"].nunique()),
            "non_cross_control_rows": int(len(controls)),
        },
        "blockers": list(KNOWN_STATISTICAL_BLOCKERS),
        "decision": {
            "side_verdicts": verdicts,
            "p1_allowed": "YES" if p1_allowed else "NO",
            "p1_reason": p1_reason,
            "no_registration": True,
            "no_promotion": True,
            "not_live_ready": True,
            "no_quant_runner_write": True,
        },
    }

    write_json(OUTPUTS["data_audit"], data_audit)
    universe_summary.to_csv(OUTPUTS["universe"], index=False)
    events.to_parquet(OUTPUTS["events"], index=False, compression="zstd")
    metrics.to_csv(OUTPUTS["metrics"], index=False)
    first_hit.to_csv(OUTPUTS["first_hit"], index=False)
    horizon.to_csv(OUTPUTS["horizon"], index=False)
    survival.to_csv(OUTPUTS["survival"], index=False)
    yearly.to_csv(OUTPUTS["yearly"], index=False)
    concentration.to_csv(OUTPUTS["concentration"], index=False)
    phase.to_csv(OUTPUTS["phase"], index=False)
    controls_out.to_csv(OUTPUTS["controls"], index=False)
    recent.to_csv(OUTPUTS["recent"], index=False)

    tables = {
        "first_hit": first_hit,
        "horizon": horizon,
        "survival": survival,
        "yearly": yearly,
        "concentration": concentration,
        "phase": phase,
        "controls": controls_out,
        "recent": recent,
    }
    write_report(summary, tables)
    artifact_hashes = {}
    for name, path in OUTPUTS.items():
        if name == "summary":
            continue
        artifact_hashes[rel(path)] = write_sidecar(path)
    artifact_hashes[rel(REPORT_PATH)] = write_sidecar(REPORT_PATH)
    summary["artifact_hashes"] = artifact_hashes
    write_json(OUTPUTS["summary"], summary)
    write_sidecar(OUTPUTS["summary"])
    assert_p0_artifacts_intact()

    print(
        json.dumps(
            {
                "events": summary["events"],
                "decision": summary["decision"],
                "summary": rel(OUTPUTS["summary"]),
                "report": rel(REPORT_PATH),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
