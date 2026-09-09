"""仅用合成panel验证统计会计、因果接口和推断近似；不读取行情。"""
import importlib.util
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

SPEC = importlib.util.spec_from_file_location("mtcs_statistics_under_test", Path(__file__).with_name("statistics.py"))
stats = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = stats
SPEC.loader.exec_module(stats)


def panel(days=260, assets=3):
    rows = []
    for t in range(days):
        for a in range(assets):
            row = {"symbol": f"ASSET{a}", "signal_time": pd.Timestamp("2020-01-01", tz="UTC") + pd.Timedelta(days=t),
                   "feature_valid": True, "valid20": True,
                   "q20": np.sin(t / 13) + a * 0.4 + (t % 4) / 10,
                   "l20": np.cos(t / 17) / 3 + a * 0.1,
                   **dict.fromkeys(stats.UNITS, False)}
            row["U_LONG" if t % 2 else "U_SHORT"] = True
            if t % 3 != 0:
                side = "LONG" if t % 2 else "SHORT"
                row[f"M_{side}"] = True
                row[f"S{(t // 3) % 3 + 1}_{side}"] = True
            rows.append(row)
    return pd.DataFrame(rows)


def select_only(frame, unit, mask):
    frame.loc[:, list(stats.UNITS)] = False
    frame.loc[mask, unit] = True
    if unit.startswith("M"):
        frame.loc[mask, "S2_" + unit.split("_")[1]] = True
    return frame


def test_hand_calculated_asset_standardization_and_weight_changes():
    f = panel(days=3, assets=2)
    f.loc[f.symbol.eq("ASSET0"), "q20"] = [0, 3, 6]
    f.loc[f.symbol.eq("ASSET1"), "q20"] = [10, 20, 30]
    selected = ((f.symbol.eq("ASSET0") & f.signal_time.dt.day.eq(3)) |
                (f.symbol.eq("ASSET1") & f.signal_time.dt.day.isin([2, 3])))
    select_only(f, "U_LONG", selected)
    p = stats.prepare(f)
    values, counts = stats.estimate(p.sufficient.sum(axis=0))
    # 选中均值(6+20+30)/3；币权重1/3与2/3，对照均值3与20。
    assert counts[0] == 3
    assert values[0] == pytest.approx(56 / 3)
    assert values[1] == pytest.approx(56 / 3 - (3 / 3 + 40 / 3))
    # 复制一枚币的所有日期会改变事件构成；不能硬套等币权重。
    totals = p.sufficient.sum(axis=0)
    totals[0] *= 2
    values2, _ = stats.estimate(totals)
    assert values2[0] == pytest.approx((12 + 20 + 30) / 4)
    assert values2[1] == pytest.approx(62 / 4 - (2 * 3 + 2 * 20) / 4)


def test_all_days_selected_have_exact_zero_delta():
    f = panel(days=170, assets=2)
    select_only(f, "U_LONG", np.ones(len(f), dtype=bool))
    p = stats.prepare(f)
    points, psi, _ = stats.influence(p)
    assert points[1] == pytest.approx(0, abs=1e-14)
    assert points[3] == pytest.approx(0, abs=1e-14)
    assert np.max(np.abs(psi[:, [1, 3]])) < 1e-14


def test_influence_finite_difference_and_zero_sum():
    p = stats.prepare(panel())
    points, psi, _ = stats.influence(p)
    assert len(points) == 46
    assert np.max(np.abs(psi.sum(axis=0))) < 1e-12
    totals = p.sufficient.sum(axis=0)
    eps = 1e-5
    for t in (0, 11, 95, 259):
        plus, _ = stats.estimate(totals + eps * p.sufficient[t])
        minus, _ = stats.estimate(totals - eps * p.sufficient[t])
        np.testing.assert_allclose((plus - minus) / (2 * eps), psi[t], rtol=3e-5, atol=2e-10)


def test_short_direction_is_sign_not_inverse():
    f = panel(days=4, assets=1)
    f["q20"], f["l20"] = 2.0, 0.5
    select_only(f, "U_SHORT", np.ones(len(f), dtype=bool))
    points, _, _ = stats.influence(stats.prepare(f))
    assert points[4] == -2.0
    assert points[6] == -0.5


def test_blocks_match_explicit_date_weights_and_last_partial_block():
    p = stats.prepare(panel(days=173, assets=2))
    starts = stats.draw_starts(123, 60, 173, 8)
    fast = stats.resampled_totals(p.sufficient, starts, 60)
    for ri, row in enumerate(starts):
        indices = np.concatenate([(start + np.arange(60)) % 173 for start in row])[:173]
        np.testing.assert_allclose(fast[ri], p.sufficient[indices].sum(axis=0), atol=1e-11)
    assert fast[:, :, 0, 0].sum(axis=1).tolist() == [173 * 2] * 8


def test_daily_calendar_keeps_empty_dates():
    f = panel(days=180, assets=1)
    f = f.loc[~f.signal_time.dt.day.eq(12)].copy()
    p = stats.prepare(f)
    assert len(p.dates) == 180
    missing = p.dates.day == 12
    assert not p.sufficient[missing].any()


def test_seed_reproducibility_and_prefix_shared_with_exact_replica():
    p = stats.prepare(panel(days=260, assets=1))
    points, psi, _ = stats.influence(p)
    counts = p.sufficient[:, :, 1:, 0].sum(axis=1)
    e1, z1 = stats._bootstrap_errors(psi, counts, 60, 9, 9000)
    e2, z2 = stats._bootstrap_errors(psi, counts, 60, 9, 9000)
    np.testing.assert_array_equal(e1, e2)
    np.testing.assert_array_equal(z1, z2)
    starts = stats.draw_starts(9, 60, len(psi), 12)
    direct = stats.resampled_totals(psi, starts, 60) - psi.sum(axis=0)
    np.testing.assert_allclose(e1[:12], direct, atol=1e-13)
    exact, _ = stats.estimate(stats.resampled_totals(p.sufficient, starts, 60))
    assert np.sqrt(np.mean((exact - points - e1[:12]) ** 2)) < 0.03
    all_starts = stats.draw_starts(9, 60, len(psi), 9000)
    final = stats.resampled_totals(psi, all_starts[-12:], 60) - psi.sum(axis=0)
    np.testing.assert_allclose(e1[-12:], final, atol=1e-13)


def test_cannot_reconstruct_prices_or_use_invalid_labels():
    f = panel(days=150, assets=1)
    f.loc[0, "valid20"] = False
    f.loc[0, ["q20", "l20"]] = [1e99, -1e99]
    f["open"] = "NOT_A_PRICE"
    f["close"] = "DO_NOT_READ"
    p = stats.prepare(f)
    assert p.coverage["observed_rows"] == 149
    assert np.max(np.abs(p.sufficient[:, :, :, 1:])) < 10
    f.loc[1, "q20"] = np.inf
    with pytest.raises(ValueError, match="nonfinite"):
        stats.prepare(f)


@pytest.mark.parametrize("mutation,match", [
    (lambda f: pd.concat([f, f.iloc[[0]]]), "duplicate"),
    (lambda f: f.assign(signal_time=f.signal_time.dt.tz_localize(None)), "timezone"),
    (lambda f: f.assign(signal_time=f.signal_time + pd.Timedelta(hours=1)), "daily-close"),
    (lambda f: f.assign(U_LONG=1), "boolean"),
    (lambda f: f.assign(feature_valid=False), "outside feature"),
    (lambda f: f.assign(S1_LONG=True), "partition|overlapping"),
])
def test_input_contract_rejections(mutation, match):
    with pytest.raises(ValueError, match=match):
        stats.prepare(mutation(panel(days=8, assets=1)))


def test_sparse_zero_replicate_is_not_dropped():
    f = panel(days=260, assets=1)
    select_only(f, "U_LONG", f.index.eq(0) if hasattr(f.index, "eq") else f.index == 0)
    p = stats.prepare(f)
    points, psi, _ = stats.influence(p)
    audit, zeros = stats._approximation_audit(p, points, psi, 60, 44)
    assert zeros[0] > 0
    selected_rows = [r for r in audit if r["unit"] == "U_LONG"]
    assert not any(r["passed"] for r in selected_rows)
    assert all(r["finite_replicates"] < 2048 for r in selected_rows)


def test_basic_bonferroni_keeps_46_family_even_with_missing_units():
    assert stats.TAIL_PROBABILITY == pytest.approx(0.05 / 92)
    errors = np.tile(np.linspace(-2, 3, 20001)[:, None], (1, 46))
    points = np.zeros(46)
    lower, upper = stats.basic_intervals(points, errors)
    assert lower[0] < -2.99
    assert upper[0] > 1.99


def test_analyze_outputs_reproducibly_without_declaring_low_mc_success(tmp_path):
    f = panel(days=260, assets=1)
    a = stats.analyze(f, tmp_path / "a", bootstrap_reps=128, seed=7)
    b = stats.analyze(f, tmp_path / "b", bootstrap_reps=128, seed=7)
    assert not a["all_reliable"]
    assert a["selected_historical_candidate"] is None
    assert a["metric_family_size"] == 46
    assert all("MC_TAIL_PRECISION_INSUFFICIENT" in x["reasons"] for x in a["units"])
    assert a["blocks"] == b["blocks"]
    intervals = pd.read_csv(tmp_path / "a" / "intervals.csv")
    assert len(intervals) == 138
    assert set(intervals.block_days) == {"60", "120", "envelope"}
    assert (tmp_path / "a" / "daily-influence.csv.gz").read_bytes() == (tmp_path / "b" / "daily-influence.csv.gz").read_bytes()
    with pytest.raises(FileExistsError):
        stats.analyze(f, tmp_path / "a", bootstrap_reps=128)


def test_zero_weight_asset_control_can_be_zero():
    totals = np.zeros((2, 11, 3))
    totals[0, 0] = [4, 8, 4]
    totals[0, 1] = [2, 6, 3]
    values, _ = stats.estimate(totals)
    assert values[0] == 3
    assert values[1] == 1
    totals[1, 1] = [1, 1, 1]
    with pytest.raises(ValueError, match="zero all-day control"):
        stats.estimate(totals)


def test_optional_filter_inference_failure_does_not_block_primary_candidate():
    rows = [{"block_days": "envelope", "unit": unit, "metric": metric,
             "lower": 0.4, "upper": 0.8,
             "threshold": 0.0 if metric in ("L20", "DeltaLate") else 0.25}
            for unit, metric in stats.METRICS]
    reasons = {unit: [] for unit in stats.UNITS}
    reasons["S1_LONG"] = ["B60:DeltaFilter:LINEARIZATION_AUDIT_FAILED"]
    decisions = {r["unit"]: r for r in stats._unit_decisions(pd.DataFrame(rows), reasons)}
    result = decisions["S1_LONG"]
    assert result["status"] == "HISTORICAL_CANDIDATE"
    assert result["primary_reliable"]
    assert not result["all_metrics_reliable"]
    assert result["filter_status"] == "INFERENCE_UNRELIABLE"


def test_no_observable_labels_produces_undefined_not_zero_success(tmp_path):
    f = panel(days=130, assets=1)
    f["valid20"] = False
    f[["q20", "l20"]] = np.nan
    result = stats.analyze(f, tmp_path / "empty_labels", bootstrap_reps=128)
    assert result["coverage"]["observed_rows"] == 0
    assert result["selected_historical_candidate"] is None
    assert all(r["status"] == "INFERENCE_UNRELIABLE" for r in result["units"])
    intervals = pd.read_csv(tmp_path / "empty_labels" / "intervals.csv")
    assert intervals["point"].isna().all()
    assert len(pd.read_csv(tmp_path / "empty_labels" / "approximation-audit.csv")) == 92
