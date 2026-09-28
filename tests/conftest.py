"""CI-safe defaults for research tests that need the local data lake."""

from __future__ import annotations

import pytest

_LOCAL_DATA_MARKERS = (
    "FileNotFoundError",
    "no HYPE 1h normalized partitions",
    "data/normalized/",
    "data/features/",
    "data/cache/",
    "/artifacts/",
)

_SKIP_REASON = "Skipped: local research data/artifacts unavailable in CI"

# Collection-time marks keep family-manifest SHA/size locks intact.
_LOCAL_DATA_TESTS: frozenset[tuple[str, str]] = frozenset(
    {
        (
            "test_binance_1d_catl_p1_donor_walk_forward_modeling.py",
            "test_all_preprocessors_are_fit_on_training_only",
        ),
        (
            "test_binance_1d_catl_p1_donor_walk_forward_modeling.py",
            "test_allowlist_is_the_only_model_feature_source",
        ),
        (
            "test_binance_1d_catl_p1_donor_walk_forward_modeling.py",
            "test_every_fold_has_exact_purge_and_no_terminal_selection",
        ),
        (
            "test_binance_1d_catl_p1_donor_walk_forward_modeling.py",
            "test_hype_is_zero_everywhere_and_hyper_is_preserved",
        ),
        (
            "test_binance_1d_catl_p1_donor_walk_forward_modeling.py",
            "test_input_manifest_and_p1_manifest_hashes_are_complete",
        ),
        (
            "test_binance_1d_catl_p1_donor_walk_forward_modeling.py",
            "test_oof_identity_is_unique_and_fold_dates_are_exact",
        ),
        (
            "test_binance_1d_catl_p1_donor_walk_forward_modeling.py",
            "test_outputs_are_diagnostic_not_strategy_or_live_artifacts",
        ),
        (
            "test_binance_1d_catl_p1_donor_walk_forward_modeling.py",
            "test_paired_bootstrap_uses_shared_indices_per_target",
        ),
        (
            "test_binance_1d_catl_p1_donor_walk_forward_modeling.py",
            "test_summary_metrics_reconcile_to_predictions_and_fold_metrics",
        ),
        (
            "test_binance_1d_catl_p1_donor_walk_forward_modeling.py",
            "test_target_specific_eligibility_matches_prediction_counts",
        ),
        (
            "test_binance_1d_ma7_ctp_p1_cross_conditioned_entry_model.py",
            "test_all_training_rows_are_ma7_crosses_with_one_side_per_asset_ts",
        ),
        (
            "test_binance_1d_ma7_ctp_p1_cross_conditioned_entry_model.py",
            "test_allowlist_and_event_t0_and_t1_contract",
        ),
        (
            "test_binance_1d_ma7_ctp_p1_cross_conditioned_entry_model.py",
            "test_every_fold_has_exact_purge_and_2025_is_not_used_for_selection",
        ),
        (
            "test_binance_1d_ma7_ctp_p1_cross_conditioned_entry_model.py",
            "test_hype_zero_everywhere_and_hyper_preserved",
        ),
        (
            "test_binance_1d_ma7_ctp_p1_cross_conditioned_entry_model.py",
            "test_input_manifest_hashes_match_and_hype_is_excluded",
        ),
        (
            "test_binance_1d_ma7_ctp_p1_cross_conditioned_entry_model.py",
            "test_oof_is_unique_and_heads_do_not_share_wrong_sides",
        ),
        (
            "test_binance_1d_ma7_ctp_p1_cross_conditioned_entry_model.py",
            "test_outputs_are_diagnostic_not_strategy_or_live_artifacts",
        ),
        (
            "test_binance_1d_ma7_ctp_p1_cross_conditioned_entry_model.py",
            "test_paired_bootstrap_uses_shared_indices",
        ),
        (
            "test_binance_1d_ma7_ctp_p1_cross_conditioned_entry_model.py",
            "test_summary_metrics_reconcile_to_predictions_and_fold_metrics",
        ),
        (
            "test_binance_1d_ma7_ctp_p1_cross_conditioned_entry_model.py",
            "test_system_year_gate_detects_combined_direction_flip",
        ),
        (
            "test_binance_1d_ma7_ctp_p1_cross_conditioned_entry_model.py",
            "test_t1_features_are_strict_prior_day_lags",
        ),
        (
            "test_binance_1d_ma7_ctp_p1_cross_conditioned_entry_model.py",
            "test_training_and_validation_metrics_exist_together",
        ),
        (
            "test_binance_1d_ma7_ctp_p3r_time_boundary_repair.py",
            "test_original_p3_remains_data_block_not_ready",
        ),
        (
            "test_binance_1d_ma7_ctp_p3r_time_boundary_repair.py",
            "test_p3r_contract_lock_precedes_label_read",
        ),
        (
            "test_binance_1d_ma7_ctp_p3r_time_boundary_repair.py",
            "test_p3r_feature_arrays_match_original_p3_exactly",
        ),
        (
            "test_binance_1d_ma7_ctp_p3r_time_boundary_repair.py",
            "test_p3r_feature_spec_has_no_forbidden_x_fields",
        ),
        (
            "test_binance_1d_ma7_ctp_p3r_time_boundary_repair.py",
            "test_p3r_manifest_hashes_match_after_run",
        ),
        (
            "test_binance_1d_ma7_ctp_p3r_time_boundary_repair.py",
            "test_p3r_oof_has_unique_keys_and_no_2025_or_hype_after_run",
        ),
        (
            "test_binance_1d_ma7_ctp_p3r_time_boundary_repair.py",
            "test_p3r_purge_and_forward_calibration_after_run",
        ),
        (
            "test_binance_1d_ma7_ctp_p3r_time_boundary_repair.py",
            "test_p3r_strict_sample_and_isolation_after_run",
        ),
        (
            "test_binance_1d_ma7_ctp_p4_core_factor_ablation_compression.py",
            "test_all_candidates_same_samples_purge_and_preprocessing_contract_after_run",
        ),
        (
            "test_binance_1d_ma7_ctp_p4_core_factor_ablation_compression.py",
            "test_bootstrap_same_draw_and_manifest_hashes_after_run",
        ),
        (
            "test_binance_1d_ma7_ctp_p4_core_factor_ablation_compression.py",
            "test_candidate_feature_sets_are_exact_and_preregistered",
        ),
        (
            "test_binance_1d_ma7_ctp_p4_core_factor_ablation_compression.py",
            "test_contract_lock_status_after_run",
        ),
        (
            "test_binance_1d_ma7_ctp_p4_core_factor_ablation_compression.py",
            "test_factor_group_spec_builds_before_label_read_and_matches_p2_f1",
        ),
        (
            "test_binance_1d_ma7_ctp_p4_core_factor_ablation_compression.py",
            "test_forbidden_fields_never_enter_x",
        ),
        (
            "test_binance_1d_ma7_ctp_p4_core_factor_ablation_compression.py",
            "test_forward_calibration_uses_only_prior_folds_after_run",
        ),
        (
            "test_binance_1d_ma7_ctp_p4_core_factor_ablation_compression.py",
            "test_p2_p3_p3r_files_are_not_overwritten_by_p4_outputs",
        ),
        (
            "test_binance_1d_ma7_ctp_p4_core_factor_ablation_compression.py",
            "test_p4_did_not_generate_strategy_or_live_ready_artifacts_after_run",
        ),
        (
            "test_binance_1d_ma7_ctp_p4_core_factor_ablation_compression.py",
            "test_strict_sample_time_gate_and_isolation_after_run",
        ),
        (
            "test_binance_1d_ma7_ctp_p4_core_factor_ablation_compression.py",
            "test_summary_compression_checks_include_final_asset_holdout_results_after_run",
        ),
        (
            "test_binance_1d_ma7_ctp_p4_core_factor_ablation_compression.py",
            "test_time_asset_holdout_excludes_target_group_after_run",
        ),
        (
            "test_binance_1d_ma7_ctp_p4_core_factor_ablation_compression.py",
            "test_top10_is_fold_relative_and_oof_keys_unique_after_run",
        ),
        (
            "test_binance_1d_ma7_ctp_p5_oscillator_weekly_validation.py",
            "test_2025_plus_not_used_for_training_calibration_or_thresholds_after_run",
        ),
        (
            "test_binance_1d_ma7_ctp_p5_oscillator_weekly_validation.py",
            "test_bootstrap_draws_shared_json_parquet_markdown_verdict_consistency_after_run",
        ),
        (
            "test_binance_1d_ma7_ctp_p5_oscillator_weekly_validation.py",
            "test_d1_d2_d3_purge_and_2025_prediction_keys_unique_after_run",
        ),
        (
            "test_binance_1d_ma7_ctp_p5_oscillator_weekly_validation.py",
            "test_feature_spec_and_contract_lock_are_frozen_before_label_reads_after_run",
        ),
        (
            "test_binance_1d_ma7_ctp_p5_oscillator_weekly_validation.py",
            "test_forward_calibration_uses_only_labels_completed_before_each_fold_after_run",
        ),
        (
            "test_binance_1d_ma7_ctp_p5_oscillator_weekly_validation.py",
            "test_frozen_threshold_uses_one_probability_space_and_matches_saved_decisions_after_run",
        ),
        (
            "test_binance_1d_ma7_ctp_p5_oscillator_weekly_validation.py",
            "test_p5_candidate_feature_counts_and_p4_b0_reproduction",
        ),
        (
            "test_binance_1d_ma7_ctp_p5_oscillator_weekly_validation.py",
            "test_p5_data_audit_hype_hyper_tradfi_and_strict_sample_after_run",
        ),
        (
            "test_binance_1d_ma7_ctp_p5_oscillator_weekly_validation.py",
            "test_weekly_causality_manifest_and_no_forbidden_outputs_after_run",
        ),
    }
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Apply local_data before tests run so get_closest_marker sees it."""
    marker = pytest.mark.local_data
    for item in items:
        originalname = getattr(item, "originalname", None)
        if originalname is None:
            obj = getattr(item, "obj", None)
            originalname = getattr(obj, "__name__", item.name)
        key = (item.path.name, originalname)
        if key in _LOCAL_DATA_TESTS:
            item.add_marker(marker)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):  # noqa: ARG001
    """Rewrite missing-lake FileNotFoundError to skip only for local_data tests."""
    outcome = yield
    report = outcome.get_result()
    if report.when not in {"setup", "call"} or not report.failed:
        return
    if item.get_closest_marker("local_data") is None:
        return
    longrepr = str(report.longrepr)
    if "FileNotFoundError" not in longrepr:
        return
    if not any(marker in longrepr for marker in _LOCAL_DATA_MARKERS):
        return
    report.outcome = "skipped"
    lineno = 0
    if item.location and item.location[1] is not None:
        lineno = item.location[1]
    report.longrepr = (str(getattr(item, "path", item.fspath)), lineno, _SKIP_REASON)
