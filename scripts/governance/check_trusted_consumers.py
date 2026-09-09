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
    ConsumerSpec(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/build_mcsm_baseline_inputs_20260909.py",
        ("main", "scoped_read"),
        ("read_bundle_contract", "verify_bundle_files", "load_trusted_research_dataset", "read_verified_ohlcv"),
    ),
    ConsumerSpec(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/verify_mcsm_baseline_20260908.py",
        ("load_first_month_prices", "recheck_ada_formation"), ("require_research_startup",),
    ),
    ConsumerSpec(
        "research/asset-portfolios/1d-trend-strength-pullback-restart/scripts/audit_inputs.py",
        ("load_inputs",), ("require_research_startup",),
    ),
    ConsumerSpec(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/load_binance_1d_mcsm_lifecycle_inputs_20260908.py",
        ("load_inputs",), ("require_research_startup",),
    ),
    ConsumerSpec(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/audit_binance_1d_mcsm_funding_source_20260908.py",
        ("load_current_funding",), ("load_funding_v2",),
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
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/correct_mcsm_baseline_identity_20260909.py",
        ("main",),
        ("read_bundle_contract", "verify_bundle_files", "load_trusted_research_dataset", "scoped_read"),
        "exploratory-scoped-identity-correction-consumer",
    ),
    ConsumerSpec(
        "research/asset-portfolios/1d-ma7-atr14-long-short-audit/scripts/applicability_features.py",
        ("load_inputs",),
        ("require_research_startup",),
        "binance-bundle-startup-consumer",
    ),
    ConsumerSpec(
        "research/asset-portfolios/1d-ma7-atr14-long-short-audit/scripts/run_audit.py",
        ("load_inputs",),
        ("require_research_startup",),
        "binance-bundle-startup-consumer",
    ),
    ConsumerSpec(
        "research/asset-portfolios/1d-ma7-atr14-long-transfer/scripts/run_full_market.py",
        ("load_inputs",),
        ("require_research_startup",),
        "binance-bundle-startup-consumer",
    ),
    ConsumerSpec(
        "research/asset-portfolios/1d-ma7-atr14-long-transfer/scripts/run_transfer.py",
        ("load_inputs",),
        ("require_research_startup",),
        "binance-bundle-startup-consumer",
    ),
    ConsumerSpec(
        "research/asset-portfolios/1d-bull-top10-30d-rotation/scripts/build_p0_inputs.py",
        ("load_inputs",),
        ("require_research_startup",),
        "binance-bundle-startup-consumer",
    ),
    ConsumerSpec(
        "research/asset-portfolios/4h-bull-strong-rsi-atr-pullback/scripts/build_p1_inputs.py",
        ("load_inputs",),
        ("require_research_startup",),
        "binance-bundle-startup-consumer",
    ),
    ConsumerSpec(
        "research/asset-portfolios/4h-bull-strong-rsi-atr-pullback/scripts/build_p0_features.py",
        ("load_inputs",),
        ("require_research_startup",),
        "binance-bundle-startup-consumer",
    ),
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
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/audit_mcsm_estimated_funding_large_cash_20260909.py",
        "main", "posthoc-bounded-large-funding-cash-source-audit",
        "Checks four named large cash-contribution windows against official funding API and checksum-verified monthly archives; preserves frozen account inputs and does not infer full-calendar or verified-net approval.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/audit_mcsm_estimated_funding_identity_output_20260909.py",
        "main", "identity-corrected-estimated-funding-integrity-audit",
        "Independently verifies corrected holding/event pins, raw mark hashes and unchanged 758 windows; no new account return, missing-calendar inference or trusted-net approval.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/audit_mcsm_identity_sources_20260909.py",
        "main", "bounded-official-identity-and-retained-account-audit",
        "Preserves four official CMS announcements for two preidentified contract boundaries and attributes existing price-account legs; no selection change, counterfactual rerun, or lake reads.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/correct_mcsm_baseline_identity_20260909.py",
        "verified_saved_execution", "hash-pinned-identity-correction-returned-frame-consumer",
        "Fixes only confirmed AERGO/LIT formation identity errors by original frozen ranks, verifies retained execution receipts and two newly scoped formations, and preserves the prior 760-leg input; not PIT or net approval.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/audit_mcsm_funded_replica_20260909.py",
        "main", "independent-estimated-funding-account-replica",
        "Reconstructs retained three funding proxy scenarios with independent reserve-cash arithmetic; no shared account kernel or approval of unknown calendars.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/audit_mcsm_price_only_replica_20260909.py",
        "main", "independent-retained-account-replica",
        "Reconstructs the hash-verified same-family price account with independent spot-equivalent algebra; not a new lake or net approval.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/audit_mcsm_baseline_selection_20260909.py",
        "main", "frozen-selection-lineage-and-segment-audit",
        "Audits retained V3 scoped frames against pinned original inputs; reports missing old days and unresolved signal-segment boundaries without changing holdings.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/audit_mcsm_estimated_funding_calendar_20260909.py",
        "main", "partial-calendar-observed-event-audit",
        "Compares observed estimate events only within frozen evidenced funding segments; cannot assert full calendar/PIT or verified net.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/summarize_mcsm_baseline_estimate_20260909.py",
        "main", "retained-estimated-account-report-generator",
        "Renders hashed same-family account artifacts with native/proxy, calendar and execution limitations; no lake reads.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/build_mcsm_baseline_inputs_20260909.py",
        "load_returned_daily", "hash-pinned-same-family-returned-frame-consumer",
        "Reuses complete receipt-verified same-family daily frames and strict scoped V3 supplements; not historical PIT/net approval.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/build_mcsm_baseline_estimated_funding_20260909.py",
        "prepare", "explicit-untrusted-observed-funding-estimate",
        "Binds funding v2 and actual frozen holding windows, preserves raw API/mark proxy evidence and partial calendar status; no trusted net claim or lake writes.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/run_mcsm_baseline_estimate_20260909.py",
        "main", "hash-pinned-exploratory-account-estimate",
        "Consumes only frozen same-family price and funding estimate outputs; four explicitly modeled accounts, never verified net/PIT/live readiness.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/multi-public-strategies-100/scripts/build_report.py",
        "pct", "artifact-report-generator",
        "Reads retained diagnostic outputs and writes the report; data/raw strings describe provenance, not trusted lake reads.",
    ),
    AuxiliaryClassification(
        'research/asset-portfolios/multi-public-strategies-100/scripts/collect_equity_raw.py',
        'fetch', 'raw-only-producer',
        'Preserves native Yahoo snapshots and atomic raw partitions; never accepted normalized.',
    ),
    AuxiliaryClassification(
        'research/asset-portfolios/multi-public-strategies-100/scripts/collect_spot_raw.py',
        'fetch', 'raw-only-producer',
        'Checksum verified Binance spot archives retained UNACCEPTED; no perpetual substitution.',
    ),
    AuxiliaryClassification(
        'research/asset-portfolios/multi-public-strategies-100/scripts/prepare_freqtrade.py',
        'one', 'untrusted-diagnostic-adapter',
        'SHA-verifies explicit raw partition manifest; builds disposable adapter; outputs EXPLORE_UNTRUSTED only.',
    ),
    AuxiliaryClassification(
        'research/asset-portfolios/multi-public-strategies-100/scripts/backtest_equity_diagnostic.py',
        'load', 'untrusted-diagnostic-reader',
        'Verifies raw partition and payload hashes; numeric outputs remain EXPLORE_UNTRUSTED per data-lake spec section 5.',
    ),
    AuxiliaryClassification(
        'research/asset-portfolios/multi-public-strategies-100/scripts/probe_free_sources.py',
        'fetch', 'raw-access-probe',
        'Read-only public source access evidence; no trusted market consumption.',
    ),
    AuxiliaryClassification(
        'research/asset-portfolios/multi-public-strategies-100/scripts/run_freqtrade.py',
        'main', 'untrusted-native-backtest',
        'Offline native framework uses fingerprint-verified raw-derived adapter, never trusted or live-ready.',
    ),
    AuxiliaryClassification(
        'research/asset-portfolios/multi-public-strategies-100/artifacts/sources/Donvink__quant-trade/scripts/build_historical_market_cap.py',
        'download_historical_market_cap', 'archived-third-party-source',
        'Retained source evidence only, never executed; no historical market-cap input consumed.',
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/verify_binance_1d_mcsm_lifecycle_inputs_20260908.py",
        "main", "verified-returned-frame-artifact-audit",
        "Verifies this round's retained API frame projection, symbol hashes and startup receipts; never reads the lake.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/verify_mcsm_baseline_20260908.py",
        "baseline_gate_closeout", "returned-frame-and-actual-source-rejection-audit",
        "Checks pinned same-family frames and original holdings; demonstrates missing-mark and net-startup rejection, not an approved net backtest.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/verify_mcsm_baseline_20260908.py",
        "load_verified_returned_daily", "verified-returned-frame-artifact-audit",
        "Checks pinned API-returned daily frame and all original startup/source receipts; no raw lake or cache read.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/probe_mcsm_baseline_funding_marks_20260908.py",
        "inspect_local", "funding-source-availability-audit",
        "Hash-checks existing raw API receipts and makes bounded public-source probes; does not approve or publish research inputs.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/probe_mcsm_baseline_first_day_marks_20260908.py",
        "main", "bounded-public-funding-source-probe",
        "Retains official first-held-day funding responses for fixed original nominations; no strategy returns or lake writes.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/reconcile_mcsm_baseline_funding_marks_20260908.py",
        "normalized_inventory", "funding-field-availability-audit-not-research-input",
        "Only inventories native mark field availability in existing normalized files; no normalized values enter strategy calculations.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/audit_baseline_terminals_20260908.py",
        "main", "bounded-terminal-source-and-returned-frame-audit",
        "Captures five official terminal events and checks the pinned same-family returned daily projection; no exact settlement or net approval inferred.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/audit_binance_1d_mcsm_funding_source_20260908.py",
        "load_legacy_reproduction", "frozen-artifact-reproduction-audit",
        "Read-only reproduction of SHA-pinned original engines and retained artifacts; never a new trusted input.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/research_binance_1d_mcsm_lifecycle_20260908.py",
        "main", "verified-returned-frame-artifact-consumer",
        "Reads only this round's content-pinned projection of require_research_startup returned frames and verified receipts, not a direct lake or legacy cache.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-atr14-long-short-audit/scripts/build_applicability_report.py",
        "build",
        "frozen-artifact-consumer",
        "Renders this topic's frozen applicability tables and statistical limitations; no lake reads.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-atr14-long-short-audit/scripts/analyze_applicability.py",
        "main",
        "frozen-artifact-consumer",
        "Verifies this topic's feature pins and evaluates frozen applicability contrasts against retained trade labels; no lake reads.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-atr14-long-short-audit/scripts/audit_paths.py",
        "main",
        "frozen-artifact-consumer",
        "Matches original long entries against this topic's retained long-short ledgers; no lake reads.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-atr14-long-short-audit/scripts/analyze.py",
        "main",
        "frozen-artifact-consumer",
        "Verifies this topic's frozen replay hashes and compares its retained result tables; no lake reads.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-atr14-long-short-audit/scripts/build_report.py",
        "build",
        "frozen-artifact-consumer",
        "Builds the Chinese mechanism audit from this topic's paired result tables; no lake reads.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-atr14-long-transfer/scripts/analyze_full_market.py",
        "main",
        "frozen-artifact-consumer",
        "Consumes this topic's retained full-market result and trade tables; never reads the lake.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-atr14-long-transfer/scripts/build_full_market_report.py",
        "build",
        "frozen-artifact-consumer",
        "Verifies hashes of this topic's retained results, reconstructs accounting and renders an offline report; never reads the lake.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-bull-top10-30d-rotation/scripts/package_p0.py",
        "main",
        "frozen-artifact-consumer",
        "Verifies this family's result hashes and independent price arithmetic; never reads the lake.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-bull-top10-30d-rotation/scripts/replay_p0.py",
        "load_inputs",
        "frozen-artifact-consumer",
        "Consumes hash-verified same-family daily/4h startup results for the fixed 30-day study.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/4h-bull-strong-rsi-atr-pullback/scripts/package_p1_results.py",
        "main",
        "frozen-artifact-consumer",
        "Verifies hash-pinned same-family P1 inputs, result arithmetic and P0 protection; reads no lake data.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/4h-bull-strong-rsi-atr-pullback/scripts/research_p1_states.py",
        "load_verified_inputs",
        "frozen-artifact-consumer",
        "Consumes hash-pinned same-family P1 inputs returned by the daily and 4h startup checks.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/4h-bull-strong-rsi-atr-pullback/scripts/replay_p1_entries.py",
        "main",
        "frozen-artifact-consumer",
        "Consumes hash-pinned same-family P1 inputs returned by the daily and 4h startup checks.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/4h-bull-strong-rsi-atr-pullback/scripts/package_p0_results.py",
        "main",
        "frozen-artifact-consumer",
        "Verifies this family's replay manifest and arithmetic; reads no source lake data.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/4h-bull-strong-rsi-atr-pullback/scripts/replay_p0.py",
        "main",
        "frozen-artifact-consumer",
        "Reads only this family's SHA-verified startup-derived feature artifact; no lake bypass.",
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
    "require_research_startup",
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
