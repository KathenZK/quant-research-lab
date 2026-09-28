#!/usr/bin/env python3
"""Verify that governed research entry points consume trusted OHLCV.

The registry is intentionally explicit.  It defines the active dependency
chains covered by this gate and separately classifies producers, archived
projects, frozen artifacts, and auxiliary non-trusted audit inputs.
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True, slots=True)
class ConsumerSpec:
    path: str
    entrypoints: tuple[str, ...]
    required_calls: tuple[str, ...] = ("load_trusted_ohlcv",)
    classification: str = "active-trusted-consumer"


@dataclass(frozen=True, slots=True)
class AuxiliaryClassification:
    path: str
    symbol: str
    classification: str
    rationale: str


ACTIVE_TRUSTED_CONSUMERS: tuple[ConsumerSpec, ...] = (
    # 已留证的独立审计在模块顶层运行；保留其字节，只登记精确读取入口。
    # 原生资金费通过固定 manifest 的 load_funding_v2 读取，其余仅为本家族保留产物。
    ConsumerSpec(
        "research/asset-portfolios/1d-medium-term-trend-capture/scripts/audit_funding_independent.py",
        ("<module>",), ("load_funding_v2",),
        "verified-funding-and-retained-family-artifacts-audit",
    ),
    ConsumerSpec(
        "research/asset-portfolios/1d-medium-term-trend-capture/scripts/audit_funding.py",
        ("load_coverage",), ("load_funding_v2",),
    ),
    ConsumerSpec(
        "research/asset-portfolios/1d-medium-term-trend-capture/scripts/audit_inputs.py",
        ("load_inputs",), ("require_research_startup",),
    ),
    ConsumerSpec(
        "research/asset-portfolios/1d-trend-strength-pullback-restart/scripts/audit_inputs.py",
        ("load_inputs",), ("require_research_startup",),
    ),
    ConsumerSpec(
        "research/asset-portfolios/1d-medium-term-continuation-state/scripts/audit_inputs.py",
        ("load_inputs",), ("require_research_startup",),
    ),
    ConsumerSpec(
        "research/asset-portfolios/1d-ma7-bidirectional-trend-generalization/scripts/audit_funding_scope.py",
        ("load_coverage",), ("load_funding_v2",),
    ),
    ConsumerSpec(
        "research/asset-portfolios/1d-ma7-bidirectional-trend-generalization/scripts/audit_funding_scope.py",
        ("attempt_net_startup",), ("require_research_startup",),
    ),
    ConsumerSpec(
        "research/asset-portfolios/1d-ma7-bidirectional-trend-generalization/scripts/audit_inputs.py",
        ("load_inputs",),
        ("require_research_startup",),
    ),
    # PBTR
    ConsumerSpec(
        "research/hype/5m-pullback-trail/scripts/"
        "research_hype_5m_positive_payoff_search.py",
        ("load_all_hype_5m",),
    ),
    ConsumerSpec(
        "research/hype/5m-pullback-trail/scripts/"
        "research_hype_5m_indicator_search.py",
        ("load_hype_5m",),
    ),
    ConsumerSpec(
        "research/hype/5m-pullback-trail/scripts/"
        "research_hype_5m_ensemble_forward_oos.py",
        ("load_hype_5m",),
    ),
    ConsumerSpec(
        "research/hype/5m-pullback-trail/scripts/"
        "research_hype_5m_pbtr_v33_retry_arm.py",
        ("load_hype_1m",),
    ),
    # EMA-TB
    ConsumerSpec(
        "research/hype/15m-ema-trend-breakout/scripts/"
        "research_hype_ema_tb_v35_profit_floor.py",
        ("load_data",),
    ),
    ConsumerSpec(
        "research/hype/15m-ema-trend-breakout/scripts/"
        "research_hype_ema_tb_v35_h4_rsi6_entry_filter.py",
        ("load_data",),
    ),
    ConsumerSpec(
        "research/hype/15m-ema-trend-breakout/scripts/"
        "hype_multi_timeframe_trend_search.py",
        ("_load_data",),
    ),
    # EMA-X
    ConsumerSpec(
        "research/hype/15m-ema-crossover/scripts/"
        "research_hype_ema_cross_strategy.py",
        ("load_trusted_klines",),
    ),
    ConsumerSpec(
        "research/hype/15m-ema-crossover/scripts/"
        "research_hype_ema_regime_hold_v5.py",
        ("load_hype_data_lake",),
    ),
    ConsumerSpec(
        "research/hype/15m-ema-crossover/scripts/"
        "research_hype_v16_indicator_expansion.py",
        ("load_ohlcv",),
    ),
    # Candle-Count
    ConsumerSpec(
        "research/hype/15m-candle-count-reversal/scripts/"
        "research_hype_cc_v35_dual_ema_filter.py",
        ("load_and_audit_frame",),
    ),
    ConsumerSpec(
        "research/hype/15m-candle-count-reversal/scripts/"
        "replay_hype_cc_v35_oos_proxy_2026_06_29.py",
        ("_load_ohlcv_proxy_frame",),
    ),
    # MII
    ConsumerSpec(
        "research/hype/15m-multi-indicator-intraday/scripts/"
        "research_hype_15m_mii_search.py",
        ("load_data",),
    ),
    ConsumerSpec(
        "research/hype/15m-multi-indicator-intraday/scripts/"
        "research_hype_15m_mii_v1_full_ablation.py",
        ("load_data_lake",),
    ),
    # AR component families and the frozen-kernel HYPE wrapper.
    ConsumerSpec(
        "research/trx/1h-adaptive-regime/scripts/"
        "research_trx_1h_adaptive_regime_search.py",
        ("load_data",),
    ),
    ConsumerSpec(
        "research/sol/1h-adaptive-regime/scripts/"
        "research_sol_1h_adaptive_regime_search.py",
        ("load_data",),
    ),
    ConsumerSpec(
        "research/eth/1h-adaptive-regime/scripts/"
        "research_eth_1h_adaptive_regime_search.py",
        ("load_data",),
    ),
    ConsumerSpec(
        "research/btc/1h-adaptive-regime/scripts/"
        "research_btc_1h_adaptive_regime_search.py",
        ("load_data",),
    ),
    ConsumerSpec(
        "research/bnb/1h-adaptive-regime/scripts/"
        "research_bnb_1h_adaptive_regime_search.py",
        ("load_data",),
    ),
    ConsumerSpec(
        "research/hype/1h-adaptive-regime/scripts/"
        "research_hype_1h_adaptive_regime_search.py",
        ("load_data",),
    ),
    # Shared hubs.
    ConsumerSpec(
        "research/hype/1h-multi-mechanism-trend-following/scripts/"
        "mmtf_engine.py",
        ("_load_market",),
    ),
    ConsumerSpec(
        "research/hype/15m-multi-mechanism-trend-following/scripts/"
        "mmtf_engine.py",
        ("_load_market",),
    ),
    ConsumerSpec(
        "research/hype/15m-factor-ml/scripts/hype_ml_common.py",
        ("load_hype_market_frame",),
    ),
    ConsumerSpec(
        "research/asset-portfolios/"
        "multi-timeframe-dual-state-trend-campaign/scripts/dstc_data.py",
        ("load_cutoff_ohlcv",),
    ),
    ConsumerSpec(
        "research/asset-portfolios/"
        "1h-multi-leg-six-asset-selector/scripts/ml6as_engine.py",
        ("load_symbol_frame",),
    ),
    ConsumerSpec(
        "research/hype/15m-sequential-drift-state/scripts/sds_engine.py",
        ("load_market",),
    ),
    ConsumerSpec(
        "research/hype/15m-sma-crossover-slope/scripts/sma_xs_engine.py",
        ("load_market",),
    ),
)


BINANCE_CATALOG_CONSUMERS: tuple[ConsumerSpec, ...] = (
    ConsumerSpec(
        "research/asset-portfolios/4h-ma7-regime-continuation/scripts/"
        "research_binance_4h_ma7_regime_continuation_p0r_data.py",
        ("catalog_trusted_load", "load_derived_ohlcv"),
        ("load_trusted_dataset", "require_passing_trusted"),
        "binance-catalog-consumer",
    ),
)

FROZEN_LEGACY_OHLCV_GLOBS: tuple[str, ...] = (
    "research/asset-portfolios/4h-ma7-regime-continuation/scripts/"
    "research_binance_4h_ma7_regime_continuation_p0.py",
    "research/asset-portfolios/1d-monthly-cs-momentum-ls3/scripts/"
    "research_binance_1d_mcsm_ls3.py",
    "research/asset-portfolios/1d-ma7-cross-trend-probability/scripts/"
    "research_binance_1d_ma7_cross_trend_probability_all_market.py",
)

NEW_RESEARCH_FORBIDDEN_SUBSTRINGS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "research/asset-portfolios/4h-ma7-regime-continuation/scripts/"
        "research_binance_4h_ma7_regime_continuation_p0r_data.py",
        (
            "data/normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h",
            "timeframe=1h/date=",
            "data/cache/binance_perp_1d_from_15m",
        ),
    ),
)


DELEGATING_CONSUMERS: tuple[ConsumerSpec, ...] = (
    ConsumerSpec(
        "research/hype/15m-ema-crossover/scripts/compare_hype_ema_v2_v4.py",
        ("main",),
        ("load_trusted_klines",),
        "active-delegating-consumer",
    ),
    ConsumerSpec(
        "research/hype/15m-trend-breakout-multi-indicator-ensemble/scripts/"
        "research_hype_15m_tb_mii_ensemble_backtest.py",
        ("main",),
        ("load_data", "build_context"),
        "active-delegating-consumer",
    ),
    ConsumerSpec(
        "research/asset-portfolios/"
        "1h-adaptive-regime-multi-asset-ensemble/scripts/"
        "research_binance_1h_ar_mae_single_position_backtest.py",
        ("main",),
        ("load_trx", "load_sol", "load_eth", "load_bnb", "load_btc", "load_hype"),
        "active-delegating-consumer",
    ),
)


AUXILIARY_CLASSIFICATIONS: tuple[AuxiliaryClassification, ...] = (
    AuxiliaryClassification(
        "research/asset-portfolios/1d-medium-term-trend-capture/scripts/plot_equity_and_drawdown.py",
        "main", "retained-family-artifacts-only",
        "Plots pinned MTTC portfolio_daily.parquet and account-metrics.json, checks the account calendar and metrics, and embeds source hashes; no market-data access or strategy execution.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-medium-term-trend-capture/scripts/audit_statistics.py",
        "main", "retained-family-artifacts-only",
        "Independently checks pinned MTTC paired results, calendar inference and retained descriptive tables; no market-data lake access.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-medium-term-trend-capture/scripts/explain_capture_gaps.py",
        "main", "retained-family-artifacts-only",
        "Explains waiting and drawdowns from retained MTTC result tables without rerunning or selecting rules.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-medium-term-trend-capture/scripts/audit_research.py",
        "main", "retained-family-artifacts-only",
        "Independently reconstructs current-family verified input snapshots, signals and retained account results.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-medium-term-trend-capture/scripts/export_findings.py",
        "main", "retained-family-artifacts-only",
        "Reads only the current family's retained result tables; no market-data lake access.",
    ),
    AuxiliaryClassification(
        "research/hype/15m-ema-trend-breakout/scripts/"
        "research_hype_ema_tb_v35_profit_floor.py",
        "load_binance_api_data",
        "embedded-producer-route",
        "Explicit API refresh route; the default research loader is trusted.",
    ),
    AuxiliaryClassification(
        "research/hype/15m-ema-trend-breakout/scripts/"
        "research_hype_ema_tb_v35_profit_floor.py",
        "fetch_binance_klines",
        "embedded-producer-route",
        "Explicit API producer; it is not a trusted research input.",
    ),
    AuxiliaryClassification(
        "research/hype/15m-ema-trend-breakout/scripts/"
        "research_hype_ema_tb_v35_profit_floor.py",
        "fetch_binance_funding",
        "embedded-producer-route",
        "Explicit API producer for funding, outside the OHLCV trust contract.",
    ),
    AuxiliaryClassification(
        "research/hype/15m-multi-indicator-intraday/scripts/"
        "research_hype_15m_mii_search.py",
        "fetch_fapi_klines",
        "embedded-legacy-producer-unused",
        "Retained producer helper; load_data() no longer calls it.",
    ),
    AuxiliaryClassification(
        "research/hype/1d-15m-hierarchical-trend-opportunity/scripts/"
        "hto_engine.py",
        "build_book",
        "frozen-artifact-consumer",
        "Reads a SHA-pinned feature snapshot, not standard OHLCV.",
    ),
    AuxiliaryClassification(
        "research/hype/15m-ema-trend-breakout/scripts/"
        "research_hype_ema_tb_v35_profit_floor.py",
        "build_quality_report",
        "raw-ohlcv-parity-audit",
        "Raw OHLCV is intentionally untrusted comparison evidence.",
    ),
    AuxiliaryClassification(
        "research/hype/15m-ema-trend-breakout/scripts/"
        "research_hype_ema_tb_v35_h4_rsi6_entry_filter.py",
        "compare_raw_normalized",
        "raw-ohlcv-parity-audit",
        "Raw OHLCV is intentionally untrusted comparison evidence.",
    ),
    AuxiliaryClassification(
        "research/hype/15m-candle-count-reversal/scripts/"
        "research_hype_cc_v35_dual_ema_filter.py",
        "_read_partitions",
        "raw-mark-funding-audit-reader",
        "Used only for raw/mark/funding quality comparison.",
    ),
    AuxiliaryClassification(
        "research/hype/15m-candle-count-reversal/scripts/"
        "replay_hype_cc_v35_oos_proxy_2026_06_29.py",
        "_load_funding_rate",
        "funding-input-reader",
        "Funding rates are outside the trusted OHLCV contract.",
    ),
    AuxiliaryClassification(
        "research/hype/15m-multi-indicator-intraday/scripts/"
        "research_hype_15m_mii_v1_full_ablation.py",
        "load_partitioned",
        "raw-ohlcv-parity-audit",
        "Raw OHLCV is intentionally untrusted comparison evidence.",
    ),
    AuxiliaryClassification(
        "research/hype/15m-factor-ml/scripts/hype_ml_common.py",
        "_read_many",
        "raw-mark-funding-audit-reader",
        "Standard OHLCV bypasses this helper; other audit inputs do not.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/"
        "multi-timeframe-dual-state-trend-campaign/scripts/dstc_data.py",
        "_read_parquet_cutoff",
        "raw-ohlcv-parity-audit",
        "Normalized OHLCV bypasses this helper; raw parity does not.",
    ),
    AuxiliaryClassification(
        "research/trx/1h-adaptive-regime/scripts/"
        "research_trx_1h_adaptive_regime_search.py",
        "_load_funding",
        "funding-input-reader",
        "Funding rates are outside the trusted OHLCV contract.",
    ),
    AuxiliaryClassification(
        "research/sol/1h-adaptive-regime/scripts/"
        "research_sol_1h_adaptive_regime_search.py",
        "_load_funding",
        "funding-input-reader",
        "Funding rates are outside the trusted OHLCV contract.",
    ),
    AuxiliaryClassification(
        "research/eth/1h-adaptive-regime/scripts/"
        "research_eth_1h_adaptive_regime_search.py",
        "_load_funding",
        "funding-input-reader",
        "Funding rates are outside the trusted OHLCV contract.",
    ),
    AuxiliaryClassification(
        "research/btc/1h-adaptive-regime/scripts/"
        "research_btc_1h_adaptive_regime_search.py",
        "_load_funding",
        "funding-input-reader",
        "Funding rates are outside the trusted OHLCV contract.",
    ),
    AuxiliaryClassification(
        "research/bnb/1h-adaptive-regime/scripts/"
        "research_bnb_1h_adaptive_regime_search.py",
        "_load_funding",
        "funding-input-reader",
        "Funding rates are outside the trusted OHLCV contract.",
    ),
)


CONTROLLED_EXCEPTION_PREFIXES = (
    "research/platform/data-lake-governance/scripts/",
)
CATALOG_CONSUMER_MARKERS = (
    "load_trusted_dataset",
    "load_canonical_binance_perp_1d",
    "load_trusted_research_dataset",
    "read_verified_ohlcv",
)
DIRECT_LAKE_HIT_TOKENS = (
    "read_parquet",
    "data/normalized",
    "data/derived",
    "data/cache",
    "data/raw",
)
FROZEN_RESEARCH_SCRIPTS_RELATIVE = "scripts/governance/frozen_research_scripts.txt"
ARCHIVED_PREFIXES = (
    "archive/",
    "research/asset-portfolios/15m-asset-specific-six-strategy-selector/",
    "research/asset-portfolios/1h-cross-sectional-lightgbm-selector/",
    "research/asset-portfolios/"
    "1h-multi-horizon-cross-sectional-ml-allocator/",
)
PRODUCER_NAME_PREFIXES = (
    "fetch_",
    "ingest_",
    "sync_",
    "migrate_",
    "freeze_",
)


def _call_name(call: ast.Call) -> str:
    parts: list[str] = []
    node: ast.expr = call.func
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _top_level_functions(tree: ast.Module) -> dict[str, ast.AST]:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def classify_path(path: str | Path) -> str:
    normalized = Path(path).as_posix().lstrip("./")
    active = {
        spec.path: spec.classification
        for spec in (*ACTIVE_TRUSTED_CONSUMERS, *DELEGATING_CONSUMERS, *BINANCE_CATALOG_CONSUMERS)
    }
    if normalized in active:
        return active[normalized]
    auxiliary_paths = {
        item.path: item.classification for item in AUXILIARY_CLASSIFICATIONS
    }
    if normalized in auxiliary_paths:
        return auxiliary_paths[normalized]
    if normalized.startswith(ARCHIVED_PREFIXES):
        return "archived-excluded"
    if Path(normalized).name.startswith(PRODUCER_NAME_PREFIXES):
        return "producer-excluded"
    return "unclassified"


def scan_consumer(root: Path, spec: ConsumerSpec) -> list[str]:
    path = root / spec.path
    if not path.is_file():
        return [f"{spec.path}: missing governed consumer"]

    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        return [f"{spec.path}:{exc.lineno}: syntax error: {exc.msg}"]

    functions = _top_level_functions(tree)
    errors: list[str] = []
    governed_nodes: list[ast.AST] = []
    for entrypoint in spec.entrypoints:
        if entrypoint == "<module>":
            # 显式注册的顶层执行入口；不让未调用的函数/类中的读取满足门禁。
            node = ast.Module(
                body=[item for item in tree.body if not isinstance(
                    item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                )],
                type_ignores=[],
            )
        else:
            node = functions.get(entrypoint)
        if node is None:
            errors.append(f"{spec.path}: missing entry point {entrypoint}()")
        else:
            governed_nodes.append(node)

    calls = [
        call
        for node in governed_nodes
        for call in ast.walk(node)
        if isinstance(call, ast.Call)
    ]
    references = {
        reference
        for node in governed_nodes
        for item in ast.walk(node)
        for reference in (
            item.id if isinstance(item, ast.Name) else None,
            item.attr if isinstance(item, ast.Attribute) else None,
        )
        if reference is not None
    }
    for required in spec.required_calls:
        if required not in references:
            errors.append(
                f"{spec.path}: governed entry points do not call {required}()"
            )

    if spec.classification == "active-trusted-consumer":
        for call in calls:
            name = _call_name(call)
            short_name = name.rsplit(".", 1)[-1]
            line = getattr(call, "lineno", "?")
            if short_name in {"read_parquet", "read_csv"}:
                errors.append(
                    f"{spec.path}:{line}: governed OHLCV entry point uses "
                    f"{short_name}()"
                )
            if short_name == "load_dataset":
                rendered = ast.unparse(call).upper()
                if "OHLCV" in rendered:
                    errors.append(
                        f"{spec.path}:{line}: governed OHLCV entry point uses "
                        "load_dataset()"
                    )
            if "cache" in name.lower():
                errors.append(
                    f"{spec.path}:{line}: governed OHLCV entry point calls "
                    f"cache-like function {short_name}()"
                )
    return errors


def check_new_research_forbidden_globs(root: Path) -> list[str]:
    errors: list[str] = []
    for relpath, needles in NEW_RESEARCH_FORBIDDEN_SUBSTRINGS:
        path = root / relpath
        if not path.is_file():
            errors.append(f"{relpath}: missing binance catalog consumer")
            continue
        text = path.read_text(encoding="utf-8")
        for needle in needles:
            if needle in text:
                errors.append(
                    f"{relpath}: new Binance research path contains forbidden "
                    f"legacy glob/cache token {needle!r}"
                )
    for relpath in FROZEN_LEGACY_OHLCV_GLOBS:
        if not (root / relpath).is_file():
            errors.append(f"{relpath}: missing frozen-legacy consumer classification target")
    return errors


def validate_auxiliary_classifications(root: Path) -> list[str]:
    errors: list[str] = []
    for item in AUXILIARY_CLASSIFICATIONS:
        path = root / item.path
        if not path.is_file():
            errors.append(f"{item.path}: missing classified auxiliary consumer")
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if item.symbol not in _top_level_functions(tree):
            errors.append(
                f"{item.path}: missing classified symbol {item.symbol}()"
            )
    return errors


def registered_consumer_paths() -> set[str]:
    paths = {
        spec.path
        for spec in (
            *ACTIVE_TRUSTED_CONSUMERS,
            *DELEGATING_CONSUMERS,
            *BINANCE_CATALOG_CONSUMERS,
        )
    }
    paths.update(FROZEN_LEGACY_OHLCV_GLOBS)
    paths.update(item.path for item in AUXILIARY_CLASSIFICATIONS)
    return paths


def family_of_research_script(relative_path: str) -> str:
    parts = Path(relative_path).parts
    if "scripts" in parts:
        return "/".join(parts[: parts.index("scripts")])
    return "."


def parse_frozen_research_scripts(text: str) -> set[str]:
    found: set[str] = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        path = line.split("#", 1)[0].strip()
        if path:
            found.add(path)
    return found


def load_frozen_research_scripts(root: Path) -> set[str]:
    path = root / FROZEN_RESEARCH_SCRIPTS_RELATIVE
    if not path.is_file():
        return set()
    return parse_frozen_research_scripts(path.read_text(encoding="utf-8"))


def iter_research_script_paths(root: Path) -> list[Path]:
    research = root / "research"
    if not research.is_dir():
        return []
    return [
        path
        for path in research.rglob("*.py")
        if path.parent.name == "scripts"
    ]


def script_hits_direct_lake(text: str) -> bool:
    return any(token in text for token in DIRECT_LAKE_HIT_TOKENS)


def discover_unregistered_binance_ohlcv_scripts(root: Path) -> list[str]:
    """Find research files that call catalog APIs but are not registered."""

    registered = registered_consumer_paths()
    errors: list[str] = []
    research = root / "research"
    if not research.is_dir():
        return [f"{research}: missing research directory"]
    for path in research.rglob("*.py"):
        rel = path.relative_to(root).as_posix()
        if rel.startswith(CONTROLLED_EXCEPTION_PREFIXES) or rel.startswith(ARCHIVED_PREFIXES):
            continue
        if Path(rel).name.startswith(PRODUCER_NAME_PREFIXES):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(f"{rel}: unreadable ({exc})")
            continue
        uses_catalog = any(marker in text for marker in CATALOG_CONSUMER_MARKERS)
        if uses_catalog and rel not in registered:
            errors.append(
                f"{rel}: Binance OHLCV consumer is not registered in "
                "scripts/governance/check_trusted_consumers.py "
                "(add BINANCE_CATALOG_CONSUMERS, FROZEN_LEGACY_OHLCV_GLOBS, "
                "or a controlled exception)"
            )
    return errors


def discover_unfrozen_direct_lake_scripts(root: Path) -> list[str]:
    """Deny-by-default scan of research/**/scripts/*.py lake readers."""

    allowed = registered_consumer_paths() | load_frozen_research_scripts(root)
    errors: list[str] = []
    for path in iter_research_script_paths(root):
        rel = path.relative_to(root).as_posix()
        if rel.startswith(CONTROLLED_EXCEPTION_PREFIXES):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(f"{rel}: unreadable ({exc})")
            continue
        if not script_hits_direct_lake(text):
            continue
        if rel not in allowed:
            errors.append(
                f"{rel}: unregistered direct lake/parquet reader "
                f"(family {family_of_research_script(rel)}; "
                "not on the trusted-consumer whitelist, "
                "CONTROLLED_EXCEPTION_PREFIXES, or "
                f"{FROZEN_RESEARCH_SCRIPTS_RELATIVE})"
            )
    return errors


def run_checks(root: Path) -> list[str]:
    specs: Iterable[ConsumerSpec] = (
        *ACTIVE_TRUSTED_CONSUMERS,
        *DELEGATING_CONSUMERS,
        *BINANCE_CATALOG_CONSUMERS,
    )
    errors = [
        error
        for spec in specs
        for error in scan_consumer(root.resolve(), spec)
    ]
    errors.extend(validate_auxiliary_classifications(root.resolve()))
    errors.extend(check_new_research_forbidden_globs(root.resolve()))
    errors.extend(discover_unregistered_binance_ohlcv_scripts(root.resolve()))
    errors.extend(discover_unfrozen_direct_lake_scripts(root.resolve()))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check governed research consumers for trusted OHLCV use."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Repository root.",
    )
    args = parser.parse_args()

    errors = run_checks(args.root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        print(f"Trusted-consumer check failed with {len(errors)} error(s).")
        return 1

    frozen = load_frozen_research_scripts(args.root)
    print(
        "Trusted-consumer check passed: "
        f"{len(ACTIVE_TRUSTED_CONSUMERS)} direct consumers, "
        f"{len(DELEGATING_CONSUMERS)} delegated chains, "
        f"{len(BINANCE_CATALOG_CONSUMERS)} binance catalog consumers, "
        f"{len(AUXILIARY_CLASSIFICATIONS)} classified auxiliary readers, "
        f"{len(frozen)} frozen direct-lake scripts."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
