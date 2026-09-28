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
        "research/asset-portfolios/1d-tpsa-long-account/scripts/account_acceptance.py",
        ("<module>",), ("load_funding_v2",), "funding-input-reader",
    ),

    ConsumerSpec(
        "research/asset-portfolios/multi-legacy-post-registration-audit/scripts/prepare_iteration_inputs.py",
        ("load_prices",), ("require_research_startup",),
        "iteration-comparison-current-startup-returned-prices-with-prior-value-parity",
    ),
    ConsumerSpec(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/research_mcsm_broader_exit_20260911.py",
        ("load_additional_prior_activity",), ("require_research_startup",),
        "precommitted-broader-exit-past-activity-proof-from-startup-returned-bars",
    ),
    ConsumerSpec(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/research_mcsm_weekly_20260911.py",
        ("load_execution",), ("require_research_startup",),
        "precommitted-weekly-past-qualification-and-future-price-stages",
    ),
    ConsumerSpec(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/research_mcsm_weekly_20260911.py",
        ("funding_coverage",), ("load_funding_v2",),
        "weekly-observed-funding-coverage-only-not-a-net-account",
    ),
    ConsumerSpec(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/research_mcsm_matched_selection_20260910.py",
        ("run", "supplement_endpoints", "load_new_endpoint_request"), ("require_research_startup",),
        "precommitted-matched-selection-startup-returned-endpoint-prices",
    ),
    ConsumerSpec(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/research_mcsm_single_asset_exit_20260910.py",
        ("load_exit_execution",), ("require_research_startup",),
        "precommitted-single-asset-exit-startup-returned-reference-prices",
    ),
    ConsumerSpec(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/research_mcsm_entry_funding_signal_20260910.py",
        ("run",), ("load_funding_v2",),
        "pinned-observed-entry-funding-mechanism-not-verified-net",
    ),
    ConsumerSpec(
        "research/asset-portfolios/multi-legacy-post-registration-audit/scripts/prepare_inputs.py",
        ("load_prices", "load_observed_funding"),
        ("require_research_startup", "load_funding_v2"),
        "current-run-api-returned-price-snapshots-and-separate-observed-funding",
    ),
    ConsumerSpec(
        "research/asset-portfolios/multi-legacy-post-registration-audit/scripts/probe_repository_inputs_20260911.py",
        ("load",), ("require_research_startup",),
        "post-freeze-ranking-explicit-mu-and-original-22-asset-input-probes",
    ),
    ConsumerSpec(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/smoke_real_input_dtypes.py",
        ("load_test_frames",), ("require_research_startup_batch",),
        "real-pyarrow-input-roundtrip-and-no-performance-preflight",
    ),
    ConsumerSpec(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/prepare_inputs_v4.py",
        ("load_inputs",), ("require_research_startup_batch",),
        "current-run-verified-batch-pyarrow-compatible-preparation",
    ),
    ConsumerSpec(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/verify_startup_batch_parity.py",
        ("load_original", "main"), ("require_research_startup", "require_research_startup_batch"),
        "original-and-versioned-startup-equivalence-proof",
    ),
    ConsumerSpec(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/startup_batch.py",
        ("create_startup_context", "_scope_token", "require_research_startup_batch"),
        ("read_bundle_contract", "validate_request", "verify_bundle_files", "load_trusted_research_dataset", "read_verified_ohlcv", "validate_price_frame"),
        "versioned-batch-same-startup-validators",
    ),
    ConsumerSpec(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/prepare_inputs_v3.py",
        ("load_inputs",), ("require_research_startup_batch",),
        "current-run-verified-batch-returned-market-inputs",
    ),
    ConsumerSpec(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/prepare_inputs.py",
        ("load_inputs",), ("require_research_startup",),
        "retained-initial-bisection-preparation",
    ),
    ConsumerSpec(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/prepare_inputs_v2.py",
        ("load_inputs",), ("require_research_startup",),
        "explicit-scope-startup-returned-market-inputs",
    ),
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
        "research/hype/1d-ma7-cross-atr-ratchet/scripts/prepare_inputs.py",
        ("load_prices", "attempt_net_startup"), ("require_research_startup",),
    ),
    ConsumerSpec(
        "research/hype/1d-ma7-cross-atr-ratchet/scripts/prepare_inputs.py",
        ("load_observed_funding",), ("load_funding_v2",),
    ),
    ConsumerSpec(
        "research/asset-portfolios/multi-public-strategies-100/scripts/backtest_public100_funding.py",
        ("load_inputs",), ("require_research_startup",),
    ),
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
        "research/asset-portfolios/1d-tpsa-long-account/scripts/load_prices.py",
        ("<module>",),
        ("require_research_startup",),
        "binance-bundle-startup-consumer",
    ),

    ConsumerSpec(
        "research/platform/cross-sectional-alpha-pipeline/scripts/audit_data_capabilities_20260925.py",
        ("main",),
        ("require_research_startup", "load_funding_v2"),
        "binance-bundle-capability-audit",
    ),
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
        "research/platform/small-account-three-line-validation/scripts/audit_b_ledgers.py",
        "audit",
        "frozen-artifact-consumer",
        "Independently reconstructs the new TPSA account exports and reads its retained startup-returned price snapshot; no source lake reads or strategy engine imports.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-tpsa-long-account/scripts/audit_source_execution.py",
        "<module>",
        "raw-ohlcv-parity-audit",
        "Read-only reconstruction of three symbols from the original TPSA cache and comparison with this family's startup-returned frames; not a new trusted OHLCV route.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-tpsa-long-account/scripts/model_and_source_audit.py",
        "<module>",
        "frozen-artifact-consumer",
        "Verifies the original TPSA event hash, fits a new diagnostic object and compares retained original-fold predictions; no lake OHLCV reads.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-tpsa-long-account/scripts/run_account.py",
        "load_inputs",
        "frozen-artifact-consumer",
        "Consumes this family's startup-returned price snapshot and diagnostic predictions in the full replay chain; actual funding remains unknown, not verified net returns.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-tpsa-long-account/scripts/render_trade_paths.py",
        "<module>",
        "frozen-artifact-consumer",
        "Renders retained same-family startup prices, trades and account equity; no source lake reads.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-tpsa-long-account/scripts/summarize_results.py",
        "<module>",
        "frozen-artifact-consumer",
        "Summarizes this family's retained diagnostic results and startup snapshot without reading the source lake.",
    ),

    AuxiliaryClassification(
        "research/platform/cross-sectional-alpha-pipeline/scripts/replay_candidate_bundle.py",
        "main", "self-contained-frozen-candidate-restore",
        "Verifies every bundled SHA before loading retained inputs and v6 engine; restores preselected HYPE V3 only, with no lake reads or new strategy parameters.",
    ),
    AuxiliaryClassification(
        "research/hype/1d-ma7-cross-atr-ratchet/scripts/run_immediate_floor_20260913.py",
        "main", "retained-family-artifacts-only",
        "HYPE-only user-declared instantaneous stop-floor experiment on frozen natural-readiness HYPE inputs; no full-market replay or new prices.",
    ),
    AuxiliaryClassification(
        "research/hype/1d-ma7-cross-atr-ratchet/scripts/build_immediate_floor_20260913.py",
        "main", "retained-family-artifacts-only",
        "Exports the four saved HYPE immediate-floor accounts and stop paths; consumes only frozen HYPE inputs and account artifacts.",
    ),
    AuxiliaryClassification(
        "research/hype/1d-ma7-cross-atr-ratchet/scripts/audit_immediate_floor_20260913.py",
        "audit_run", "retained-family-artifacts-only",
        "Independent reconstruction of HYPE immediate-floor stops with retained account and input data; no simulator imported or fresh price data.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/check_v3_no_extra_warmup_delivery_20260913.py",
        "main", "retained-family-artifacts-only",
        "Read-only validation of natural-readiness account/HTML projections, one-way stops, paired period summaries and the requested HYPE June 18 entry; retains original HTML checksums.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/v3_no_extra_warmup_20260913.py",
        "main", "retained-family-artifacts-only",
        "User-authorized removal of the fixed observation-age mask on hash-verified retained continuous segments; raw row quality, indicators, costs and frozen engine remain unchanged.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/report_v3_no_extra_warmup_20260913.py",
        "main", "retained-family-artifacts-only",
        "Compares retained original and natural-readiness accounts and exports stop-path HTML; no fresh market inputs, threshold fitting or cross-gap account stitching.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/revise_v3_stoplines_20260913.py",
        "main", "retained-family-artifacts-only",
        "Restores stop-line HTML from hash-verified retained pages, stop ledgers and daily indicators; display only, with no strategy replay or new market input.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/audit_v3_stoplines_data_20260913.py",
        "main", "retained-family-artifacts-only",
        "Independently compares restored stop-line payloads with retained HTML and frozen stop ledgers; verifies original arrays and stop timing without new market input.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/audit_v3_opportunity_delivery_20260913.py",
        "main", "retained-family-artifacts-only",
        "Independently verifies frozen V3 opportunity summaries, all coin-page arrays and offline DOM interactions; no new prices, fitted model or live browser fallback.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/v3_opportunity_inputs_20260913.py",
        "main", "retained-family-artifacts-only",
        "Consumes hash-bound retained original V3 segments and opportunity-study evidence only; no current lake fallback, stock inputs, fitted thresholds or cross-gap cash stitching.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/diagnose_v3_opportunity_20260913.py",
        "main", "retained-family-artifacts-only",
        "Consumes hash-bound retained original V3 segments and opportunity-study evidence only; no current lake fallback, stock inputs, fitted thresholds or cross-gap cash stitching.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/check_v3_opportunity_baseline_20260913.py",
        "main", "retained-family-artifacts-only",
        "Consumes hash-bound retained original V3 segments and opportunity-study evidence only; no current lake fallback, stock inputs, fitted thresholds or cross-gap cash stitching.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/run_v3_opportunity_20260913.py",
        "main", "retained-family-artifacts-only",
        "Consumes hash-bound retained original V3 segments and opportunity-study evidence only; no current lake fallback, stock inputs, fitted thresholds or cross-gap cash stitching.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/pair_v3_opportunity_20260913.py",
        "main", "retained-family-artifacts-only",
        "Consumes hash-bound retained original V3 segments and opportunity-study evidence only; no current lake fallback, stock inputs, fitted thresholds or cross-gap cash stitching.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/audit_v3_opportunity_20260913.py",
        "main", "retained-family-artifacts-only",
        "Consumes hash-bound retained original V3 segments and opportunity-study evidence only; no current lake fallback, stock inputs, fitted thresholds or cross-gap cash stitching.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/build_v3_opportunity_report_20260913.py",
        "main", "retained-family-artifacts-only",
        "Consumes hash-bound retained original V3 segments and opportunity-study evidence only; no current lake fallback, stock inputs, fitted thresholds or cross-gap cash stitching.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/build_v3_opportunity_html_20260913.py",
        "main", "retained-family-artifacts-only",
        "Consumes hash-bound retained original V3 segments and opportunity-study evidence only; no current lake fallback, stock inputs, fitted thresholds or cross-gap cash stitching.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/build_adaptation_cases_20260911.py",
        "main", "retained-family-artifacts-only",
        "Constructs explicitly causal 90-day-ready asset and signal features and same-entry exit outcomes from checksum-verified retained historical frames and accounts; preserves every original segment and all censored labels.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/learn_adaptation_20260911.py",
        "main", "retained-family-artifacts-only",
        "Fits fixed-depth interpretable admission and exit-choice trees on fully matured earlier episodes, excluding the target code group and fitting imputation only on training data; emits auditable JSON rules and separated historical decisions.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/run_adaptation_20260911.py",
        "main", "retained-family-artifacts-only",
        "Replays all retained evaluation segments with previously learned closed-day admission and whole-trade exit routing at explicit costs, retaining rejected opportunities and never concatenating cash across gaps.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/audit_adaptation_20260911.py",
        "main", "retained-family-artifacts-only",
        "Independently rebuilds feature timing, paired outcomes, train-code isolation, serialized decision rules and routed accounts from retained sources; source price conflicts remain explicit.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/build_adaptation_report_20260911.py",
        "main", "retained-family-artifacts-only",
        "Reports all declared admission and routing experiments, fixed-period coverage, rejected winners and losses, and every learned rule from frozen results using local interactive tables without selecting parameters.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/multi-legacy-post-registration-audit/scripts/review_cc_iteration_independent.py",
        "main", "independent-hash-verified-retained-cc-mark-review",
        "Independently rebuilds CC signals and ledgers from iteration_common startup-returned prices, with the retained auxiliary mark receipt SHA and full OHLCV alignment checked before use; no lake-price fallback.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/multi-legacy-post-registration-audit/scripts/compare_cc_versions.py",
        "load_inputs", "hash-verified-retained-cc-mark-supplement",
        "Consumes current-startup returned price frames through iteration_common and separately verifies the pinned CC mark snapshot SHA and full OHLCV alignment; no unregistered lake-price fallback.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/build_ma30_pairs_20260911.py",
        "main", "retained-family-artifacts-only",
        "Verifies same-entry normalized fields before reusing retained accounts; otherwise replays the fixed original equity and quantity on the previous startup-returned prices.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/audit_ma30_states_20260911.py",
        "main", "retained-family-artifacts-only",
        "Independently reconstructs MA30 daily admission, protective states, all fills, cash, stops and calendar marks from retained verified frames without importing the simulator.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/audit_ma30_pairs_20260911.py",
        "main", "retained-family-artifacts-only",
        "Independently verifies every reused or fixed same-entry exit label, the original quantity and the derived no-trade decisions on retained family artifacts.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/build_ma30_report_20260911.py",
        "main", "retained-family-artifacts-only",
        "Builds fixed-period comparisons and interactive MA7/MA30 trade paths from checksum-pinned completed family results; no price lake fallback.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/audit_ma30_summary_20260911.py",
        "main", "retained-family-artifacts-only",
        "Independently reconciles retained period rows, fixed-entry winner and loss summaries, and saved-price market context without calling the simulator or reading lake defaults.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/run_ma30_states_20260911.py",
        "main", "retained-family-artifacts-only",
        "Consumes checksum-pinned startup-returned frames from the previous MA7 study and runs the nine predeclared MA30 mechanisms; no raw lake fallback or stock inclusion.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/build_acceleration_html_20260910.py",
        "main", "retained-family-artifacts-only",
        "Renders the checksum-verified first-event, future-price-space and state-coverage diagnostics as a local filterable table, without changing factors or account results.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/analyze_exit_acceleration_20260910.py",
        "main", "retained-family-artifacts-only",
        "Describes predeclared first acceleration events, complete future price windows and state coverage from frozen family bars and new-cost ledgers; does not tune or run new strategies.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/audit_exit_state_analysis_20260910.py",
        "main", "retained-family-artifacts-only",
        "Independently reconstructs account summaries, matched-entry groupings and causal acceleration events from retained trades and source bars without using producer calculation functions.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/build_state_machine_html_20260910.py",
        "main", "retained-family-artifacts-only",
        "Builds frozen exit-state analyses and local interactive trade-path pages from retained verified accounts; no new market-data reader or strategy selection.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/finalize_exit_state_html_20260910.py",
        "main", "retained-family-artifacts-only",
        "Updates official-source conflict explanations in local trade-path pages while preserving all chart and account payloads and recording before-and-after hashes.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/fetch_official_hour_repair_20260910.py",
        "main", "official-source-comparison-no-publication",
        "Archives official REST and checksum-verified public archive responses for one predeclared hour, compares all affected keys with retained inputs, and rejects conflicting sources without changing the data lake.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/audit_mcsm_single_exit_account_20260910.py",
        "main", "independent-retained-8-account-endpoint-and-nav-audit",
        "Verifies original and candidate artifact hashes, directly reconstructs cash and synchronous NAV without candidate account arithmetic, and consumes only the prior verified returned daily projection.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/research_mcsm_drawdown_20260911.py",
        "main", "verified-retained-account-and-returned-daily-attribution",
        "Uses frozen account ledgers and verified returned daily projections to reconcile cash losses and lagged market-factor diagnostics without raw rereads or new trading rules.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/audit_mcsm_round_20260911.py",
        "main", "independent-new-round-frozen-evidence-audit",
        "Rebuilds breadth exit ranks from exact closed-day prices and reuses the prior independent cash auditor on new ledgers without candidate rule or account arithmetic.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/audit_mcsm_drawdown_detail_20260911.py",
        "main", "independent-returned-daily-beta-and-cash-diagnostic-audit",
        "Checks retained full-day attribution using direct past-window OLS and exact market endpoint prices, and describes already executed monthly holdings without new lake reads.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/build_mcsm_round_tables_20260911.py",
        "main", "audited-account-report-export-only",
        "Normalizes saved account, monthly, annual and holding records for the user workbook after input hashes and cash reconciliation; reads no raw market data and runs no strategy.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/finalize_mcsm_round_20260911.py",
        "main", "round-tests-delivery-xml-and-evidence-finalization-only",
        "Runs scoped tests and registration diagnostics, checks the delivered workbook and report links, and records completion hashes without market-data access or changing strategy results.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/audit_mcsm_weekly_account_20260911.py",
        "main", "independent-weekly-returned-frame-account-audit",
        "Directly reconstructs fixed-quantity cash, netted costs and synchronous NAV from hash-verified saved target frames and prior daily projections without candidate account arithmetic.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/research_mcsm_ma120_20260911.py",
        "main", "fixed-ma120-family-projections-and-registered-execution-loader",
        "Reuses exact original frozen Top10 and daily source chains; verifies prior endpoint receipts and delegates new predeclared targets only to the registered weekly load_execution startup-returned-frame consumer. No raw-lake rereads or funding network collection.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/audit_mcsm_ma120_20260911.py",
        "main", "independent-ma120-direct-windows-and-partial-cash-account-audit",
        "Rebuilds all monthly admission and daily exit decisions with exact calendar windows, then independently reconstructs cash and all NAV events from verified retained projections, including zero-weight cash slots.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/report_mcsm_ma120_20260911.py",
        "main", "audited-ma120-markdown-delivery-only",
        "Exports exact monthly holdings, monthly account PnL and yearly comparisons from hash-checked completed accounts after the independent MA120 and cash audit; no new market reads or simulations.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/finalize_mcsm_ma120_20260911.py",
        "main", "ma120-scoped-test-budget-and-evidence-finalization",
        "Checks original frozen input identities and completed MA120 artifacts, runs scoped tests, records outside-family registry failures without modifying those families, and pins the finished delivery.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/audit_mcsm_weekly_postrun_20260911.py",
        "main", "retained-weekly-projection-and-output-integrity-audit",
        "Verifies pinned plans, returned target projections, original endpoint receipts and saved account identities without raw lake access, startup calls, funding loads or network use.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/collect_weekly_terminals_20260924.py",
        "main", "bounded-official-terminal-index-evidence-only",
        "Retrieves two predeclared official delisting announcements and index-minute windows with checksums. Conditional settlement evidence, not a lake-price reader or funding-net validation.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/research_weekly_top10_20260924.py",
        "main", "hash-verified-retained-weekly-input-continuation",
        "Reuses exact frozen startup-returned daily and endpoint projections with complete request, receipt and source hashes; preserves original baselines and excludes funding. No raw lake access.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/complete_weekly_top10_20260924.py",
        "main", "fixed-weekly-terminal-evidence-amendment-and-replay",
        "Keeps failed first accounts immutable, adds two official terminal windows under a separate fixed amendment, and replays unchanged holdings with verified retained projections. No raw lake or funding retrieval.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/audit_weekly_top10_20260924.py",
        "main", "independent-direct-weekly-ranking-and-cash-audit",
        "Reconstructs exact historical weekly nomination windows and independent cash accounts; re-reads only pinned projections and official retained terminal index archives, never raw lake paths.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/report_weekly_top10_20260924.py",
        "main", "audited-weekly-monthly-yearly-artifact-export-only",
        "Exports complete holdings and PnL from hash-pinned independently audited account outputs; does not access market data or simulate new strategy variants.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/finalize_weekly_top10_20260924.py",
        "main", "weekly-scoped-tests-report-and-budget-finalization",
        "Validates existing evidence hashes, delivered table values and relative links, scoped tests and the 30 MiB budget; distinguishes own-family from unrelated registry errors.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/export_mcsm_recent36_20260924.py",
        "main", "frozen-account-recent36-report-extract-only",
        "Reads only hash-pinned independently audited monthly holdings, trades and PnL; reconciles actual new entries, retained positions, terminal exits and monthly exits. No market-data loading or new simulation.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/prepare_exit_state_unknown_history_20260910.py",
        "main", "verified-returned-frame-and-frozen-control-research",
        "Loads only the predeclared officially documented 28 historical crypto contracts through the public observed-mixed diagnostic API; preserves frozen UNKNOWN labels and excludes the three documented indexes.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/audit_exit_state_machine_20260910.py",
        "main", "retained-family-artifacts-only",
        "Independently rebuilds exit-state transitions, equal-entry pairs and account cash, execution and marks from the retained source bars and new ledgers without invoking the strategy simulator.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/audit_mcsm_mechanism_round_20260910.py",
        "main", "independent-frozen-rule-and-returned-frame-audit",
        "Reconstructs only the precommitted 20/7/2 exit signals from the original verified returned daily frame and pinned holdings; no raw market data access, tuning or live approval.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/multi-legacy-post-registration-audit/scripts/other_assets_as6s_replay.py",
        "load_mark", "hash-verified-official-auxiliary-mark-snapshot",
        "Replays recovered frozen AS6S configurations with this audit's returned trade prices and official REST mark snapshot; marks are checked against their manifest and are not substituted for catalog trade-price OHLCV.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/run_exit_state_history_20260910.py",
        "main", "verified-returned-frame-and-frozen-control-research",
        "Runs frozen exit policies at explicit costs on every startup-returned historical joint segment; never joins gaps and derives calendar diagnostics from inherited account marks.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/multi-legacy-post-registration-audit/scripts/audit_common.py",
        "load_checked", "current-audit-hash-verified-returned-frames",
        "Reads only this audit's saved API-returned frames and separately labelled observed funding after exact manifest SHA256 verification; no direct lake fallback.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/multi-legacy-post-registration-audit/scripts/replay_repository_additions_20260911.py",
        "hto", "fixed-rules-with-hash-verified-current-audit-frames",
        "Original feature source is copied with its historical parquet reader removed; all market input is supplied by audit_common hash-verified current-audit snapshots. No original search or data-loader entrypoint is called.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/multi-legacy-post-registration-audit/scripts/replay_repository_new_inputs_20260911.py",
        "checked_frame", "hash-verified-startup-returned-family-extension-frames",
        "Reads only the exact MU and original 22-asset parquet snapshots returned by the registered input probe and verifies each file against that probe's manifest. Separate observed funding uses the registered frozen-bundle capture helper; completeness is not claimed.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/multi-legacy-post-registration-audit/scripts/hype_legacy_replay.py",
        "replay_cc", "retained-mark-snapshot-parity-and-frozen-strategy-replay",
        "Uses startup-returned current-audit prices; the separate retained CC mark snapshot is hash-verified and matched against those prices, and is labelled auxiliary observed mark rather than catalog OHLCV.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/run_exit_state_machine_20260910.py",
        "main", "verified-returned-frame-and-frozen-control-research",
        "Uses original verified startup-returned segments to compare V3 and predeclared exit state policies at the user's new transaction costs; preserves original results and equal-entry episode quantities.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/prepare_exit_state_history_20260910.py",
        "main", "verified-returned-frame-and-frozen-control-research",
        "Loads pinned 2019-2026 observed COIN history through the parity-checked public startup batch adapter; retains all joint segments and marks separate short-history inventory returns as unapproved for trading.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/diagnose_exit_states_20260910.py",
        "full_states", "retained-family-artifacts-only",
        "Checks all retained V3 trade cash and causal pre-cross and held-bar diagnostics with explicit costs, terminal censoring and exit-hour extreme bounds; no raw lake reader.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/run_four_tests_20260910.py",
        "main", "verified-returned-frame-and-frozen-control-research",
        "Runs nine predeclared direction, MA30, risk-sizing and exit controls on original verified returned frames; derives stricter MA30 readiness within each continuous segment and preserves old V1/V3 results.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/audit_four_tests_20260910.py",
        "main", "retained-family-artifacts-only",
        "Independently checks entry opportunities and rejections, MA30 timing, risk quantities, reset stops and every account mark from retained family inputs, without importing the simulator.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/analyze_four_tests_20260910.py",
        "main", "retained-family-artifacts-only",
        "Compares all predeclared accounts and censored post-exit price diagnostics from checksum-verified family artifacts, retaining all cohorts and producing offline interactive HTML.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/audit_four_tests_analysis_20260910.py",
        "main", "retained-family-artifacts-only",
        "Independently reconstructs all post-exit windows, cohort comparisons and risk-budget diagnostics from retained family artifacts without importing the simulator or analysis module.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/run_v2_market_20260910.py",
        "main", "verified-returned-frame-and-frozen-control-research",
        "Replays only official V2 on the original checksum-verified startup-returned frames and unchanged scope; V1 and V3 are reused only for comparison.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/audit_v2_market_20260910.py",
        "main", "retained-family-artifacts-only",
        "Independently checks all saved V2 account marks and the daily net-profit and stalled-stop tightening condition from frozen family inputs; no simulator or new lake read.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/compare_v123_20260910.py",
        "main", "retained-family-artifacts-only",
        "Compares checksum-verified V1 and V3 historical results with the V2 supplement, preserving all declared cohorts and producing searchable HTML without replay.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/review_hype_delayed_ledgers.py",
        "load_ledgers", "retained-family-artifacts-only",
        "Compares saved HYPE account paths without simulation; validates all six source hashes against the finalized result checksum manifest before delivery.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/smoke_real_input_dtypes.py",
        "check_runner", "retained-family-artifacts-only",
        "Loads the five newly verified smoke-test frames and validates the runner feature path without calculating strategy performance.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/build_html.py",
        "build", "retained-family-artifacts-only",
        "Verifies saved account/source hashes and produces an interactive market table and every coin's complete trade paths, with no simulation or market-data requests.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/audit_prepared_inputs.py",
        "main", "retained-family-artifacts-only",
        "Independently reconstructs joint daily/hourly eligibility, warmup, selected continuous segments and all 652 statuses from checksum-protected startup outputs.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/run_market.py",
        "load_selected_frames", "verified-returned-frame-and-frozen-control-research",
        "Verifies retained startup-returned input hashes, selects predeclared continuous daily/hourly segments, and replays four pinned cases with exact HYPE controls.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/summarize_market.py",
        "summarize", "retained-family-artifacts-only",
        "Reports every market and the predeclared full/partial/short cohorts from hashed ledgers; no new data loading or parameter search.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/audit_results.py",
        "load_market_inputs", "retained-family-artifacts-only",
        "Independently rebuilds selected inputs, features, pending-entry lifecycle, stop paths, costs and all account marks from accepted saved frames without importing the simulator.",
    ),
    AuxiliaryClassification(
        "research/hype/1d-ma7-cross-atr-ratchet/scripts/run_r4.py",
        "load_r4_inputs", "verified-returned-frame-and-frozen-control-research",
        "Verifies frozen R3 outputs and source pins, delegates to the original verified input chain, and compares close with high/low progress using 15 exact controls.",
    ),
    AuxiliaryClassification(
        "research/hype/1d-ma7-cross-atr-ratchet/scripts/audit_r4_artifacts.py",
        "main", "retained-family-artifacts-only",
        "Independent read-only reconstruction of every R4 close/high-low progress state and account ledger from pinned records, with no simulator calls.",
    ),
    AuxiliaryClassification(
        "research/hype/1d-ma7-cross-atr-ratchet/scripts/build_trade_paths_r4.py",
        "load_chart_data", "retained-family-artifacts-only",
        "Verifies R4 source and result hashes and charts all nine cases and every saved trade with source-specific close/high-low labels.",
    ),
    AuxiliaryClassification(
        "research/hype/1d-ma7-cross-atr-ratchet/scripts/render_trade_path_pngs_r4.py",
        "main", "retained-family-artifacts-only",
        "Renders static figures from the R4 validated chart payload without market-data access or strategy execution.",
    ),
    AuxiliaryClassification(
        "research/hype/1d-ma7-cross-atr-ratchet/scripts/complete_r3_stress.py",
        "main", "verified-returned-frame-post-result-stress",
        "Disclosed uniform post-result completion of the same four stresses for every remaining R3 case; source-pinned inputs and no new threshold search.",
    ),
    AuxiliaryClassification(
        "research/hype/1d-ma7-cross-atr-ratchet/scripts/audit_r3_artifacts.py",
        "main", "retained-family-artifacts-only",
        "Independently recomputes saved R3 accounting, daily-high/low state and stop decisions from pinned records; never runs a strategy simulation.",
    ),
    AuxiliaryClassification(
        "research/hype/1d-ma7-cross-atr-ratchet/scripts/audit_r3_stress_artifacts.py",
        "main", "retained-family-artifacts-only",
        "Read-only verification of the disclosed supplemental R3 stress ledgers and the combined 56-case table.",
    ),
    AuxiliaryClassification(
        "research/hype/1d-ma7-cross-atr-ratchet/scripts/build_trade_paths_r3.py",
        "load_chart_data", "retained-family-artifacts-only",
        "Verifies retained R3 source and result hashes and charts every saved trade in all 14 cases, without recomputing signals or running the engine.",
    ),
    AuxiliaryClassification(
        "research/hype/1d-ma7-cross-atr-ratchet/scripts/run_r3.py",
        "load_r3_inputs", "verified-returned-frame-and-frozen-control-research",
        "Checks frozen R2 outputs and source pins, delegates to the verified original input loader, and runs predeclared R3 daily-high/low progress comparisons with six exact controls.",
    ),
    AuxiliaryClassification(
        "research/hype/1d-ma7-cross-atr-ratchet/scripts/plot_r2_stall_cases.py",
        "main", "retained-family-artifacts-only",
        "Verifies frozen R2 result checksums and explains saved trades 1, 4 and 9 with daily stop decisions; no market-data refresh, indicator reconstruction or strategy replay.",
    ),
    AuxiliaryClassification(
        "research/hype/1d-ma7-cross-atr-ratchet/scripts/audit_r2_artifacts.py",
        "digest", "retained-family-artifacts-only",
        "Module-level read-only audit of retained R2 ledgers, frozen daily features, checksums and R1 controls; never runs strategy simulation or refreshes market data.",
    ),
    AuxiliaryClassification(
        "research/hype/1d-ma7-cross-atr-ratchet/scripts/r2_post_result_stress.py",
        "main", "verified-returned-frame-post-result-stress",
        "Uses the R2 verified startup-returned loader for explicitly disclosed post-result stress checks; no new parameter search or data refresh.",
    ),
    AuxiliaryClassification(
        "research/hype/1d-ma7-cross-atr-ratchet/scripts/build_trade_paths_r2.py",
        "load_chart_data", "retained-family-artifacts-only",
        "Verifies R2 input manifest and result hashes, renders retained daily features and trade/stop/equity ledgers, and never reruns the strategy.",
    ),
    AuxiliaryClassification(
        "research/hype/1d-ma7-cross-atr-ratchet/scripts/run_r2.py",
        "load_r2_inputs", "verified-returned-frame-and-frozen-control-research",
        "Checks frozen R1 source/output hashes and its startup-returned input loader; R2 uses the same observed window and masks, with exact original controls and separate unverified funding sensitivity.",
    ),
    AuxiliaryClassification(
        "research/hype/1d-ma7-cross-atr-ratchet/scripts/build_trade_paths.py",
        "load_chart_data", "verified-returned-frame-and-frozen-trade-chart",
        "Verifies parent source and ledger hashes, consumes existing startup-returned daily candles and stop histories, and only renders trade paths without strategy execution.",
    ),
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
        "research/hype/1d-ma7-cross-atr-ratchet/scripts/analyze_short_exits.py",
        "main", "verified-returned-frame-and-trade-artifact-audit",
        "Checks the parent run source and artifact hashes and uses its verified returned frames for fixed-entry short-exit counterfactuals; no new strategy tuning or lake read.",
    ),
    AuxiliaryClassification(
        "research/hype/1d-ma7-cross-atr-ratchet/scripts/run_study.py",
        "load_inputs", "verified-returned-frame-artifact-consumer",
        "Verifies content-pinned startup-returned hourly/daily frames, masks and receipts; observed funding is separately labelled unverified and never approved as full net input.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/audit_mcsm_funding_account_bridge_20260910.py",
        "main", "frozen-account-independent-cash-bridge-audit",
        "Reconstructs pinned family accounts with independent interval price PnL and funding arithmetic; no strategy changes or verified-net claim.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/audit_mcsm_funding_mark_integrity_20260910.py",
        "run", "frozen-raw-mark-lineage-and-unit-audit",
        "Checks only pinned raw sources used by original funding events, official checksums and returned daily price ranges; no new market input or calendar approval.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/audit_mcsm_all_funding_sources_20260910.py",
        "main", "bounded-official-funding-source-audit",
        "Compares original 760 holding windows with retained bounded official API responses, explicitly preserves failed and incomplete queries, and never treats missing funding as zero.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/audit_mcsm_retained_funding_sources_20260910.py",
        "main", "pinned-retained-funding-receipt-audit",
        "Follows manifest-pinned official receipts only for frozen holding windows; retained archive rate evidence remains distinct from typed API and complete-calendar evidence.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/audit_mcsm_retained_native_marks_20260910.py",
        "run", "pinned-retained-native-funding-mark-audit",
        "Audits original-family official API receipt inventory against frozen event identities and rates; no network or automatic net-input promotion.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/audit_mcsm_legacy_funding_lineage_20260910.py",
        "main", "bounded-original-funding-lineage-availability-audit",
        "Checks manifest-pinned inherited receipts and exact downloader-declared funding archives for frozen holdings; converted raw tables and self-declared hashes are not treated as authenticated official originals.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/merge_mcsm_funding_source_evidence_20260910.py",
        "main", "retained-official-funding-source-evidence-merge",
        "Combines pinned partial API matches without omitting original event IDs, verifies conflicts and raw file hashes, and preserves archive-only evidence separately; no network or full-calendar claim.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/replay_mcsm_native_marks_20260910.py",
        "main", "frozen-account-native-mark-sensitivity",
        "Replays only pinned original rules with uniquely verified native settlement marks and explicit retained proxies; preserves original results, fails on known source conflicts, and is not verified-net or production approval.",
    ),
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
        "research/asset-portfolios/multi-public-strategies-100/scripts/continue_public100_data.py",
        "fetch", "raw-only-producer",
        "R2 native source capture with payload receipts, checksums and immutable UTC raw partitions; no normalized writes.",
    ),
    AuxiliaryClassification(
        "research/asset-portfolios/multi-public-strategies-100/scripts/public100_r2_inputs.py",
        "raw_files", "untrusted-diagnostic-reader",
        "SHA-verifies exact Yahoo, Coinbase and Boros raw partitions; section 5 exploratory outputs only, no Binance perpetual fallback.",
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
    required_references = (
        {_call_name(call).rsplit(".", 1)[-1] for call in calls}
        if spec.entrypoints == ("<module>",)
        else references
    )
    for required in spec.required_calls:
        if required not in required_references:
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
        if item.symbol != "<module>" and item.symbol not in _top_level_functions(tree):
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
