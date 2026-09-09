"""只使用合成面板，禁止在测试中读取行情湖或家族研究结果。"""

from pathlib import Path
import importlib.util
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

SPEC = importlib.util.spec_from_file_location("tspr_statistics_under_test", Path(__file__).with_name("statistics.py"))
stats = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = stats
SPEC.loader.exec_module(stats)


def row(symbol, day, direction, strength, p, m, q, late, valid=True):
    x = direction * strength
    result = {"symbol": symbol, "ts": pd.Timestamp("2020-01-01", tz="UTC") + pd.Timedelta(days=int(day)), "feature_valid": True, "valid20": valid, "q20": direction * q if valid else np.nan, "l20": direction * late if valid else np.nan, "q5": direction * (q - late) if valid else np.nan, "label20_status": "COMPLETE_CONTIGUOUS" if valid else "ADMINISTRATIVE_UNMATURED"}
    for d, sign in (("LONG", 1), ("SHORT", -1)):
        value = sign * x
        result[f"strength_{d}"] = value
        result[f"strength_bin_{d}"] = 3 if value > 2 else 2 if value > 1 else 1 if value > 0 else 0
        result[f"P_{d}"] = bool(p) if sign == direction else False
        result[f"M_{d}"] = bool(m) if sign == direction else False
        result[f"cell_{d}"] = 2 * int(p) + int(m) if value > 0 else -1
    return result


def synthetic(days=180, assets=3, seed=147):
    rng = np.random.default_rng(seed)
    rows = []
    for a in range(assets):
        for day in range(days):
            direction = 1 if rng.random() < 0.5 else -1
            strength = (0.5, 1.5, 2.5)[rng.integers(3)] + 0.15 * rng.random()
            p, m = bool(rng.integers(2)), bool(rng.integers(2))
            q = rng.normal() + strength * 0.15 + 0.3 * p * m
            late = 0.7 * q + rng.normal(scale=0.3)
            rows.append(row(f"A{a}", day, direction, strength, p, m, q, late))
    return pd.DataFrame(rows)


class EstimatorTests(unittest.TestCase):
    def test_hand_calculated_harmonic_weights_and_raw_mean(self):
        v = np.zeros((2, 2, 7, 3))
        # A: high11 2件均值4，high10 8件均值1 -> w=1.6。
        # B: high11 9件均值2，high10 3件均值0 -> w=2.25。
        v[0, 0, 3] = (2, 8, 4)
        v[0, 0, 2] = (8, 8, 0)
        v[1, 0, 3] = (9, 18, 9)
        v[1, 0, 2] = (3, 0, 0)
        point = stats.estimate(v)
        self.assertAlmostEqual(point[2], (1.6 * 3 + 2.25 * 2) / (1.6 + 2.25))
        self.assertAlmostEqual(point[10], 26 / 11)
        self.assertNotAlmostEqual(point[10], (1.6 * 4 + 2.25 * 2) / 3.85)
        # 重复整个同币样本使其重叠权重按观察数增加，而不是多算成资产。
        doubled = v.copy()
        doubled[0] *= 2
        self.assertAlmostEqual(stats.estimate(doubled)[2], (3.2 * 3 + 2.25 * 2) / 5.45)

    def test_four_cells_share_one_weight_and_signs(self):
        v = np.zeros((2, 2, 7, 3))
        means = [[1, 3, 4, 10, 2, 1, 2], [3, 8, 5, 12, 1, 4, 8]]
        counts = [[10, 20, 30, 40, 50, 9, 3], [80, 5, 6, 3, 20, 10, 20]]
        for a in range(2):
            for cell in range(7):
                v[a, 0, cell] = counts[a][cell] * np.array([1, means[a][cell], 2 * means[a][cell]])
        point = stats.estimate(v)
        w = [1 / sum(1 / n for n in c[:4]) for c in counts]
        diffs = [10 - 4 - 3 + 1, 12 - 5 - 8 + 3]
        self.assertAlmostEqual(point[6], np.dot(w, diffs) / sum(w))
        self.assertAlmostEqual(point[7], 2 * point[6])
        mod_w = [1 / sum(1 / c[i] for i in (3, 2, 6, 5)) for c in counts]
        mod_d = [10 - 4 - 2 + 1, 12 - 5 - 8 + 4]
        self.assertAlmostEqual(point[8], np.dot(mod_w, mod_d) / sum(mod_w))

    def test_zero_arm_is_defined_zero_overlap_not_deleted_replica(self):
        v = np.zeros((2, 2, 7, 3))
        v[0, 0, 3] = (10, 999, 777)
        v[1, 0, 3] = (2, 8, 4)
        v[1, 0, 2] = (4, 4, 4)
        point = stats.estimate(v)
        self.assertEqual(point[2], 3)
        self.assertTrue(np.isfinite(point[10]))
        v[1, 0, 2] = 0
        self.assertTrue(np.isnan(stats.estimate(v)[2]))

    def test_prepare_direct_matches_all_24_and_direction(self):
        panel = synthetic()
        p = stats.prepare(panel)
        np.testing.assert_allclose(stats.estimate(p.totals), stats.reference_estimate(p), atol=1e-12, rtol=1e-12, equal_nan=True)
        self.assertEqual(p.totals.shape, (3, 2, 7, 3))
        short = p.events.loc[p.events.direction.eq("SHORT")]
        source = panel.set_index(["symbol", "ts"]).loc[list(zip(short.symbol, short.ts)), "q20"].to_numpy()
        np.testing.assert_allclose(short.Q20, -source)

    def test_batch_estimate_and_flat_expansion(self):
        p = stats.prepare(synthetic(80))
        packed = np.stack((p.daily.sum(axis=0), p.daily.sum(axis=0) * 2))
        outputs = stats.estimate(p.expand(packed))
        np.testing.assert_allclose(outputs[0], outputs[1], equal_nan=True)
        np.testing.assert_allclose(p.expand(packed)[0], p.totals)

    def test_support_and_censoring_do_not_change_opportunity_universe(self):
        panel = synthetic(70)
        # 加一条未来未成熟的高档PM；计入机会但不进入点估计。
        extra = pd.DataFrame([row("NEW", 80, 1, 3, True, True, 100, 90, valid=False)])
        p = stats.prepare(pd.concat((panel, extra), ignore_index=True))
        self.assertEqual(len(p.events), len(panel) + 1)
        desc = stats.descriptions(p)
        target = desc["support_and_strength_balance"].query("direction=='LONG' and contrast=='HIGH_PM'").iloc[0]
        self.assertEqual(target.unobserved20, 1)
        self.assertIn("ADMINISTRATIVE_UNMATURED", desc["label_status_counts"].label_status20.tolist())
        self.assertGreaterEqual(target.x_p90, target.x_p10)
        self.assertEqual(set(desc["descriptive_sensitivities"].inference), {"DESCRIPTIVE_ONLY"})

    def test_quarter_and_fine_matching_change_only_descriptive_estimand(self):
        rows = [row("A", 0, 1, 2.1, True, True, 5, 2), row("A", 100, 1, 2.6, True, False, 1, 0)]
        p = stats.prepare(pd.DataFrame(rows))
        self.assertEqual(stats.reference_estimate(p)[2], 4)
        self.assertTrue(np.isnan(stats.reference_estimate(p, quarter=True)[2]))
        self.assertTrue(np.isnan(stats.reference_estimate(p, fine_strength=True)[2]))
        sensitivity = stats.descriptions(p)["descriptive_sensitivities"]
        target = sensitivity.loc[sensitivity.metric.eq("LONG.RESTART.Q20")]
        self.assertTrue(target.support_strata.eq(0).all())
        self.assertTrue(target.high_pm_complete_support_fraction.eq(0).all())

    def test_invalid_inputs_rejected(self):
        panel = synthetic(10, 1)
        for mutate in (
            lambda p: pd.concat([p, p.iloc[:1]], ignore_index=True),
            lambda p: p.assign(valid20=1),
            lambda p: p.assign(ts=p.ts + pd.Timedelta(hours=1)),
            lambda p: p.assign(strength_bin_LONG=3),
            lambda p: p.assign(l20=100),
        ):
            with self.subTest(mutate=mutate):
                with self.assertRaises(ValueError):
                    stats.prepare(mutate(panel.copy()))

    def test_calendar_includes_empty_dates_and_no_price_reconstruction(self):
        panel = pd.DataFrame([row("A", 0, 1, 3, True, True, 2, 1), row("A", 4, 1, 3, True, False, 0, 0)])
        panel["open"] = [1e9, 1e-9]  # 不读取或拼接OHLC；既成标签是唯一结果输入。
        p = stats.prepare(panel)
        self.assertEqual(len(p.dates), 5)
        self.assertTrue((p.daily[1:4] == 0).all())
        self.assertEqual(stats.estimate(p.totals)[2], 2)

    def test_zero_strength_endpoint_dates_remain_in_calendar(self):
        panel = pd.DataFrame([row("A", 0, 1, 0, False, False, 0, 0), row("A", 4, 1, 3, True, True, 2, 1), row("A", 8, 1, 0, False, False, 0, 0)])
        p = stats.prepare(panel)
        self.assertEqual(len(p.dates), 9)
        self.assertEqual(len(p.events), 1)
        self.assertTrue((p.daily[[0, 8]] == 0).all())
        self.assertEqual(p.events.date_index.iloc[0], 4)

    def test_all_zero_strength_has_no_estimable_effect(self):
        panel = pd.DataFrame([row("A", day, 1, 0, False, False, 1, 1) for day in (0, 10)])
        p = stats.prepare(panel)
        self.assertEqual(len(p.dates), 11)
        self.assertEqual(len(p.events), 0)
        self.assertTrue(np.isnan(stats.estimate(p.totals)).all())
        self.assertTrue(np.isnan(stats.reference_estimate(p)).all())


class BootstrapTests(unittest.TestCase):
    def test_exact_truncation_and_circular_sums(self):
        daily = np.arange(14, dtype=float).reshape(7, 2)
        for block in (1, 3, 7, 10):
            sums = stats.circular_block_sums(daily, block)
            for s in range(7):
                np.testing.assert_allclose(sums[s], daily[(s + np.arange(block)) % 7].sum(axis=0))
            starts = stats.draw_starts(np.random.default_rng(8), 10, 7, block)
            weights = stats.weights_from_starts(starts, 7, block)
            np.testing.assert_array_equal(weights.sum(axis=1), 7)

    def test_full_nonlinear_matches_256_original_row_references(self):
        p = stats.prepare(synthetic(80, 2))
        audit = stats.audit_reference(p, block_lengths=(13, 31), replicates=256)
        self.assertTrue(audit["passed"], audit)

    def test_seed_prefix_unchanged_by_batch_size(self):
        seed = np.random.SeedSequence([stats.SEED, 60])
        a = stats.draw_starts(np.random.default_rng(seed), 103, 180, 60)
        rng = np.random.default_rng(seed)
        b = np.concatenate([stats.draw_starts(rng, n, 180, 60) for n in (7, 61, 35)])
        np.testing.assert_array_equal(a, b)

    def test_undefined_dimension_whole_column_unbounded(self):
        rng = np.random.default_rng(42)
        values = rng.normal(size=(1000, 24))
        values[123, 4] = np.nan
        point = np.zeros(24)
        interval = stats.simultaneous_intervals(point, values)
        self.assertEqual(interval["estimable_dimensions"], 23)
        self.assertEqual(interval["registered_dimensions"], 24)
        self.assertEqual(interval["lower"][4], -np.inf)
        self.assertEqual(interval["upper"][4], np.inf)
        self.assertTrue(interval["reliable"][5])

    def test_zero_sd_not_false_certainty_and_bias_not_removed(self):
        point = np.ones(24)
        interval = stats.simultaneous_intervals(point, np.ones((100, 24)))
        self.assertEqual(interval["estimable_dimensions"], 0)
        noise = np.random.default_rng(3).normal(size=(5000, 24))
        shifted = stats.simultaneous_intervals(np.zeros(24), 10 + noise)
        centered = stats.simultaneous_intervals(np.zeros(24), noise)
        self.assertGreater(shifted["critical"], centered["critical"] + 7)

    def test_fixed_five_batch_precision_detects_uneven_mc(self):
        rng = np.random.default_rng(15)
        values = rng.normal(size=(1000, 24))
        values[:200] += 20
        result, rows = stats.monte_carlo_check(np.zeros(24), values)
        self.assertFalse(result["passed"])
        self.assertEqual(len(rows), 120)
        self.assertEqual(rows.batch.nunique(), 5)

    def test_sparse_replicate_stays_nonfinite(self):
        p = stats.prepare(pd.DataFrame([row("A", 0, 1, 3, True, True, 1, 1), row("A", 20, 1, 3, True, False, 0, 0)]))
        starts = np.zeros((1, 21), dtype=np.int64)
        values = stats.bootstrap_estimates(p, starts, 1)
        self.assertTrue(np.isnan(values[0, 2]))
        self.assertEqual(values[0, 10], 1)

    def test_decisions_no_interaction_requirement(self):
        point = np.ones(24)
        low, high, reliable = np.ones(24) * 0.5, np.ones(24) * 1.5, np.ones(24, dtype=bool)
        low[6:10], high[6:10] = -2, -1
        decision = stats.decisions(point, low, high, reliable, precision_ok=True)
        self.assertEqual(decision["candidates"][0]["status"], "HISTORICAL_PRICE_CANDIDATE")
        low[2], high[2] = -0.2, 0.3
        decision = stats.decisions(point, low, high, reliable, precision_ok=True)
        self.assertEqual(decision["candidates"][0]["status"], "INSUFFICIENT_EVIDENCE")
        numerical = stats.decisions(point, low, high, reliable, precision_ok=False)
        self.assertTrue(all(r["status"] == "NUMERICAL_PRECISION_INSUFFICIENT" for r in numerical["associations"]))

    def test_run_retains_replicates_identity_and_idempotency(self):
        panel = synthetic(30, 1)
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / "run"
            kwargs = dict(bootstrap_stages=(50, 100), block_lengths=(7, 13), reference_reps=3, batch_size=17, checkpoint_every=25, progress=lambda _: None)
            report = stats.run(panel, out, **kwargs)
            self.assertEqual(report["configuration_identity"], "TEST_CONFIGURATION")
            self.assertEqual(report, stats.run(panel, out, **kwargs))
            self.assertTrue(list(out.glob("block-*/replicates-*.npz")))
            for path in out.glob("block-*/replicates-*.npz"):
                with np.load(path) as shard:
                    self.assertEqual(shard["replicates"].shape[1], 24)
                    self.assertEqual(len(shard["starts"]), len(shard["replicates"]))
            changed = panel.copy()
            changed.loc[0, "q20"] += 1
            changed.loc[0, "q5"] += 1
            with self.assertRaises(ValueError):
                stats.run(changed, out, **kwargs)
            (out / "point_statistics.csv").write_text("tampered")
            with self.assertRaises(ValueError):
                stats.run(panel, out, **kwargs)

    def test_resume_same_rng_prefix_after_checkpoint(self):
        panel = synthetic(35, 1)
        class Stop(Exception):
            pass
        def halt(message):
            if "7 日块：42/" in message:
                raise Stop()
        kwargs = dict(bootstrap_stages=(50,), block_lengths=(7,), reference_reps=2, batch_size=17, checkpoint_every=25)
        with tempfile.TemporaryDirectory() as temporary:
            out, reference = Path(temporary) / "resume", Path(temporary) / "reference"
            with self.assertRaises(Stop):
                stats.run(panel, out, progress=halt, **kwargs)
            stats.run(panel, out, progress=lambda _: None, **kwargs)
            stats.run(panel, reference, progress=lambda _: None, **kwargs)
            resumed = sorted((out / "block-7").glob("replicates-*.npz"))
            original = sorted((reference / "block-7").glob("replicates-*.npz"))
            for a, b in zip(resumed, original):
                with np.load(a) as x, np.load(b) as y:
                    np.testing.assert_array_equal(x["starts"], y["starts"])
                    np.testing.assert_allclose(x["replicates"], y["replicates"], equal_nan=True)


if __name__ == "__main__":
    unittest.main()
