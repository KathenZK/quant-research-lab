from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[4]
FAMILY_DIR = (
    ROOT / "research/asset-portfolios/1d-ma7-quantile-utility-meta-label"
)
BASE_SCRIPT = ROOT / (
    "research/asset-portfolios/1d-ma7-rsi6-direction-aligned-pooled-ml/"
    "scripts/sync_binance_pooled_p0_data.py"
)
CUTOFF = pd.Timestamp("2025-05-31T00:00:00Z")
SYMBOLS = {
    "BCHUSDT": ("BCH", "BCH/USDT:USDT", "bchusdt"),
    "ETCUSDT": ("ETC", "ETC/USDT:USDT", "etcusdt"),
    "XLMUSDT": ("XLM", "XLM/USDT:USDT", "xlmusdt"),
    "ATOMUSDT": ("ATOM", "ATOM/USDT:USDT", "atomusdt"),
    "VETUSDT": ("VET", "VET/USDT:USDT", "vetusdt"),
    "NEARUSDT": ("NEAR", "NEAR/USDT:USDT", "nearusdt"),
    "AAVEUSDT": ("AAVE", "AAVE/USDT:USDT", "aaveusdt"),
    "FILUSDT": ("FIL", "FIL/USDT:USDT", "filusdt"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument(
        "--symbols",
        nargs="+",
        choices=sorted(SYMBOLS),
        default=list(SYMBOLS),
    )
    parser.add_argument("--finalize-only", action="store_true")
    return parser.parse_args()


def load_base_module():
    spec = importlib.util.spec_from_file_location(
        "binance_1d_ma7_quml_p0_price_base",
        BASE_SCRIPT,
    )
    if spec is None or spec.loader is None:
        raise ImportError(BASE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(item) for item in value]
    if isinstance(value, (pd.Timestamp, datetime)):
        return pd.Timestamp(value).isoformat()
    return value


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit_feature_set() -> tuple[dict[str, Any], int]:
    feature_dir = ROOT / "data/features/binance_1d_ma7_quml_p0"
    audits: dict[str, Any] = {}
    total_blockers = 0
    for symbol, (_, _, slug) in SYMBOLS.items():
        paths = {
            "hourly": feature_dir / f"{slug}_perp_1h.parquet",
            "daily": feature_dir / f"{slug}_perp_1d.parquet",
            "funding": feature_dir / f"{slug}_perp_funding_mark.parquet",
        }
        missing = [
            str(path.relative_to(ROOT))
            for path in paths.values()
            if not path.exists()
        ]
        if missing:
            audits[symbol] = {"missing_files": missing, "blocker_count": len(missing)}
            total_blockers += len(missing)
            continue
        hourly = pd.read_parquet(paths["hourly"])
        daily = pd.read_parquet(paths["daily"])
        funding = pd.read_parquet(paths["funding"])
        for frame in (hourly, daily, funding):
            frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
        hourly = hourly.loc[hourly["ts"].lt(CUTOFF)].sort_values("ts")
        daily = daily.loc[daily["ts"].lt(CUTOFF)].sort_values("ts")
        funding = funding.loc[funding["ts"].lt(CUTOFF)].sort_values("ts")

        hourly_ts = pd.DatetimeIndex(hourly["ts"])
        expected_hourly = pd.date_range(
            hourly_ts.min(), CUTOFF - pd.Timedelta(hours=1), freq="1h"
        )
        missing_hourly = expected_hourly.difference(hourly_ts)
        hourly_nulls = int(
            hourly[
                [
                    "ts",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "quote_volume",
                    "trade_count",
                ]
            ]
            .isna()
            .sum()
            .sum()
        )
        invalid_hourly_ohlc = int(
            (
                hourly["high"].lt(
                    hourly[["open", "close", "low"]].max(axis=1)
                )
                | hourly["low"].gt(
                    hourly[["open", "close", "high"]].min(axis=1)
                )
            ).sum()
        )

        rebuilt = hourly.copy()
        rebuilt["day"] = rebuilt["ts"].dt.floor("1D")
        complete_days = rebuilt.groupby("day", sort=True).filter(
            lambda rows: len(rows) == 24
            and rows["ts"].min() == rows["day"].iloc[0]
            and rows["ts"].max()
            == rows["day"].iloc[0] + pd.Timedelta(hours=23)
        )
        grouped = complete_days.groupby("day", sort=True)
        derived = pd.DataFrame(
            {
                "ts": grouped["ts"].first().index,
                "open": grouped["open"].first().to_numpy(),
                "high": grouped["high"].max().to_numpy(),
                "low": grouped["low"].min().to_numpy(),
                "close": grouped["close"].last().to_numpy(),
                "volume": grouped["volume"].sum().to_numpy(),
                "quote_volume": grouped["quote_volume"].sum().to_numpy(),
                "trade_count": grouped["trade_count"].sum().to_numpy(),
            }
        )
        daily_compare = daily.merge(
            derived,
            on="ts",
            how="outer",
            suffixes=("_stored", "_derived"),
            indicator=True,
        )
        daily_join_mismatch = int(daily_compare["_merge"].ne("both").sum())
        daily_field_mismatch: dict[str, int] = {}
        both = daily_compare["_merge"].eq("both")
        for column in (
            "open",
            "high",
            "low",
            "close",
            "volume",
            "quote_volume",
            "trade_count",
        ):
            daily_field_mismatch[column] = int(
                (
                    ~np.isclose(
                        daily_compare.loc[
                            both, f"{column}_stored"
                        ].to_numpy(dtype="float64"),
                        daily_compare.loc[
                            both, f"{column}_derived"
                        ].to_numpy(dtype="float64"),
                        rtol=1e-12,
                        atol=1e-12,
                    )
                ).sum()
            )

        funding_ts = pd.DatetimeIndex(funding["ts"])
        funding_grid_ts = pd.DatetimeIndex(
            pd.to_datetime(
                funding.get("funding_nominal_ts", funding["ts"]),
                utc=True,
            )
        )
        funding_gaps = (
            pd.Series(funding_grid_ts).diff().dt.total_seconds().div(3600.0)
        )
        invalid_funding_gaps = int(
            (
                funding_gaps.dropna().le(0.0)
                | funding_gaps.dropna().gt(8.0)
                | np.mod(funding_gaps.dropna(), 1.0).ne(0.0)
            ).sum()
        )
        funding_nulls = int(
            funding[["ts", "funding_rate", "mark_price"]]
            .isna()
            .sum()
            .sum()
        )
        blockers = (
            len(missing_hourly)
            + int(hourly_ts.duplicated().sum())
            + hourly_nulls
            + invalid_hourly_ohlc
            + daily_join_mismatch
            + sum(daily_field_mismatch.values())
            + int(pd.DatetimeIndex(daily["ts"]).duplicated().sum())
            + int(funding_ts.duplicated().sum())
            + int(funding_grid_ts.duplicated().sum())
            + invalid_funding_gaps
            + funding_nulls
            + int((funding["mark_price"] <= 0.0).sum())
        )
        total_blockers += int(blockers)
        audits[symbol] = {
            "rows": {
                "hourly": int(len(hourly)),
                "daily": int(len(daily)),
                "funding": int(len(funding)),
            },
            "range": {
                "hourly": [hourly["ts"].min(), hourly["ts"].max()],
                "daily": [daily["ts"].min(), daily["ts"].max()],
                "funding": [funding["ts"].min(), funding["ts"].max()],
            },
            "source_values": {
                "hourly": sorted(map(str, hourly["source"].dropna().unique())),
                "daily": sorted(map(str, daily["source"].dropna().unique())),
                "funding": sorted(map(str, funding["source"].dropna().unique())),
            },
            "missing_hourly": int(len(missing_hourly)),
            "hourly_nulls": hourly_nulls,
            "invalid_hourly_ohlc": invalid_hourly_ohlc,
            "daily_join_mismatch": daily_join_mismatch,
            "daily_field_mismatch": daily_field_mismatch,
            "invalid_funding_gaps": invalid_funding_gaps,
            "max_funding_gap_hours": float(funding_gaps.max()),
            "funding_nulls": funding_nulls,
            "feature_sha256": {
                key: sha256_path(path) for key, path in paths.items()
            },
            "blocker_count": int(blockers),
        }
    return audits, int(total_blockers)


def finalize_artifact(generated_at: str) -> dict[str, Any]:
    audits, blocker_count = audit_feature_set()
    summary = {
        "schema_version": "binance-1d-ma7-quml-p0-price-v1",
        "generated_at_utc": generated_at,
        "family": "BIN-1D-MA7-QUML",
        "contract": "specs/binance-1d-ma7-quml-p0-p1-contract-2026-08-10.md",
        "cutoff_exclusive": CUTOFF,
        "symbols": list(SYMBOLS),
        "offline_feature_audit": audits,
        "blocker_count": blocker_count,
        "hype_rows_consumed": 0,
        "hype_files_opened": 0,
        "hype_requests_sent": 0,
    }
    if blocker_count:
        raise RuntimeError(f"P0 data blockers remain: {blocker_count}")
    artifact_dir = FAMILY_DIR / "artifacts/p0_price_data_2026-08-10"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact = artifact_dir / "p0_data_quality_manifest.json"
    artifact.write_text(
        json.dumps(json_ready(summary), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    args = parse_args()
    if args.max_workers < 1 or args.max_workers > 8:
        raise ValueError("--max-workers must be in [1, 8]")
    if any("HYPE" in symbol for symbol in SYMBOLS):
        raise RuntimeError("HYPE source is forbidden")
    generated_at = datetime.now(UTC).isoformat()
    if args.finalize_only:
        print(
            json.dumps(
                json_ready(finalize_artifact(generated_at)),
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    base = load_base_module()
    base.SYMBOLS = SYMBOLS
    base.FEATURE_DIR = ROOT / "data/features/binance_1d_ma7_quml_p0"
    base.ARTIFACT_DIR = FAMILY_DIR / "artifacts/p0_price_data_2026-08-10"
    base.SEALED_START = CUTOFF
    base.SEALED_END_EXCLUSIVE = CUTOFF
    base.USER_AGENT = "quant-research-lab-bin-1d-ma7-quml-p0/1.0"
    base.REQUEST_PAGE_DELAY_SECONDS = 1.0
    cutoff_ms = int(CUTOFF.timestamp() * 1_000)
    contracts = base.fetch_contracts(args.timeout)
    layout = base.DataLakeLayout.from_settings(base.load_settings(None))
    layout.ensure_directories()
    results: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = {
            executor.submit(
                base.process_symbol,
                symbol,
                contract=contracts[symbol],
                cutoff_ms=cutoff_ms,
                generated_at=generated_at,
                timeout=args.timeout,
                no_write=False,
                layout=layout,
            ): symbol
            for symbol in args.symbols
        }
        for future in as_completed(futures):
            symbol = futures[future]
            results[symbol] = future.result()
    results = {symbol: results[symbol] for symbol in args.symbols}
    blocker_count = int(
        sum(
            row["hourly_quality"]["blocker_count"]
            + int(not row["daily_quality"]["audit"]["trusted"])
            + row["funding_quality"]["blocker_count"]
            + row["mark_quality"]["blocker_count"]
            for row in results.values()
        )
    )
    feature_identity: dict[str, Any] = {}
    missing_feature_files: list[str] = []
    for symbol, (_, _, slug) in SYMBOLS.items():
        paths = {
            "hourly": base.FEATURE_DIR / f"{slug}_perp_1h.parquet",
            "daily": base.FEATURE_DIR / f"{slug}_perp_1d.parquet",
            "funding": base.FEATURE_DIR / f"{slug}_perp_funding_mark.parquet",
        }
        for name, path in paths.items():
            if not path.exists():
                missing_feature_files.append(str(path.relative_to(ROOT)))
                continue
            frame = pd.read_parquet(path, columns=["ts"])
            feature_identity[f"{symbol}:{name}"] = {
                "path": str(path.relative_to(ROOT)),
                "rows": int(len(frame)),
                "start": pd.to_datetime(frame["ts"], utc=True).min(),
                "end": pd.to_datetime(frame["ts"], utc=True).max(),
                "sha256": sha256_path(path),
            }
    blocker_count += len(missing_feature_files)
    summary = {
        "schema_version": "binance-1d-ma7-quml-p0-price-v1",
        "generated_at_utc": generated_at,
        "family": "BIN-1D-MA7-QUML",
        "contract": (
            "specs/binance-1d-ma7-quml-p0-p1-contract-2026-08-10.md"
        ),
        "cutoff_exclusive": CUTOFF,
        "symbols": list(SYMBOLS),
        "processed_symbols": list(args.symbols),
        "results": results,
        "feature_identity": feature_identity,
        "missing_feature_files": missing_feature_files,
        "blocker_count": blocker_count,
        "hype_rows_consumed": 0,
        "hype_files_opened": 0,
        "hype_requests_sent": 0,
    }
    if blocker_count:
        raise RuntimeError(f"P0 data blockers remain: {blocker_count}")
    base.ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    artifact = base.ARTIFACT_DIR / "p0_data_quality_manifest.json"
    base.atomic_write_path(
        artifact,
        lambda temporary: temporary.write_text(
            json.dumps(json_ready(summary), ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        ),
    )
    print(json.dumps(json_ready(summary), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
