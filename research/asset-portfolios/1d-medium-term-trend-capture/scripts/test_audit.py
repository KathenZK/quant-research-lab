"""MTTC独立审计的合成原式和时序边界；不读真实收益。"""
from pathlib import Path
import importlib.util
import json
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

SPEC = importlib.util.spec_from_file_location("mttc_independent_audit_tested", Path(__file__).with_name("audit_research.py"))
m = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = m
SPEC.loader.exec_module(m)


def config():
    return {"direction": "LONG", "policies": ["A", "B", "C"], "momentum_window": 20, "atr_window": 14, "warmup": 60, "strength_threshold": 2., "pullback_atr": 1., "stop_atr": 2., "wait_days": 20, "fixed_hold_days": 20, "max_hold_days": 60, "slot_risk_fraction": .1, "slot_notional_fraction": .9, "initial_equity": 10000., "max_slots": 10, "budget_fraction": .1, "start": "2020-01-01T00:00:00Z", "end": "2026-09-05T00:00:00Z"}


def cost(carry=0.):
    return {"id": "synthetic", "fee": .001, "slippage": .0004, "daily_carry": carry}


def prices(close, op=None, high=None, low=None):
    close = np.array(close, dtype=float)
    op = close.copy() if op is None else np.asarray(op, dtype=float)
    return pd.DataFrame({"symbol": "TEST", "ts": pd.date_range("2020-01-01", periods=len(close), tz="UTC"), "open": op, "high": np.maximum(op, close) + 1 if high is None else high, "low": np.minimum(op, close) - 1 if low is None else low, "close": close, "quote_volume": np.ones(len(close)) * 1000, "eligible": True, "is_closed": True, "research_segment_id": 0, "segment": 0, "r20": .1})


def origin(p, index=0, atr=2):
    return {"origin_index": index, "origin_ts": p.ts.iloc[index], "atr": atr}


class FeatureAuditTests(unittest.TestCase):
    def test_exact_strength_atr_and_first_observable(self):
        p = prices(100 * np.exp(np.cumsum(np.tile([.015, .025], 45))))
        result, origins = m.reference_features(p, config())
        j = 59
        r = np.log(p.close.iloc[j] / p.close.iloc[j - 20])
        sigma = np.std(np.log(p.close.iloc[j - 19:j + 1].to_numpy() / p.close.iloc[j - 20:j].to_numpy()), ddof=1)
        self.assertAlmostEqual(result.strength.iloc[j], r / (sigma * np.sqrt(20)))
        tr = [max(p.high.iloc[k] - p.low.iloc[k], abs(p.high.iloc[k] - p.close.iloc[k - 1]), abs(p.low.iloc[k] - p.close.iloc[k - 1])) for k in range(j - 13, j + 1)]
        self.assertAlmostEqual(result.atr14.iloc[j], np.mean(tr))
        self.assertEqual(len(origins), 1)
        self.assertEqual(origins.origin_index.iloc[0], 59)
        self.assertTrue(origins.first_observable.iloc[0])

    def test_armed_releases_only_after_nonpositive_momentum(self):
        increments = np.r_[np.tile([.015, .025], 40), np.tile([-.035, -.025], 20), np.tile([.025, .035], 30)]
        p = prices(100 * np.exp(np.cumsum(increments)))
        _, origins = m.reference_features(p, config())
        self.assertEqual(len(origins), 2)
        self.assertGreater(origins.origin_index.iloc[1], 120)

    def test_future_prefix_and_gap_reset(self):
        p = prices(100 * np.exp(np.cumsum(np.tile([.015, .025], 60))))
        full, candidates = m.reference_features(p, config())
        short, early = m.reference_features(p.iloc[:80], config())
        np.testing.assert_allclose(full.strength.iloc[:80], short.strength, equal_nan=True)
        pd.testing.assert_frame_equal(candidates.loc[candidates.origin_ts <= p.ts.iloc[79]].reset_index(drop=True), early)
        broken = p.drop(index=65).reset_index(drop=True)
        reference, _ = m.reference_features(broken, config())
        after = reference.loc[reference.ts > p.ts.iloc[65]]
        self.assertFalse(after.feature_valid.any())

    def test_invalid_input_rejects_duplicate_or_unknown_closure(self):
        p = prices(np.linspace(100, 140, 70))
        with self.assertRaises(ValueError):
            m.reference_features(pd.concat((p, p.iloc[:1])), config())
        p.loc[0, "is_closed"] = False
        with self.assertRaises(ValueError):
            m.reference_features(p, config())


class UnitAuditTests(unittest.TestCase):
    def test_a_twenty_days_next_open_exit_and_cash(self):
        p = prices(np.repeat(100., 80))
        summary, daily = m.reference_unit(p, origin(p), "A", cost(), config())
        fill = 100 * 1.0004
        q = min(.9 / (fill * 1.001), .1 / 4)
        sale = 100 * .9996
        expected = 1 - q * fill * 1.001 + q * sale * .999
        self.assertAlmostEqual(summary["last_value"], expected)
        self.assertEqual(summary["entry_ts"], p.ts.iloc[1])
        self.assertEqual(summary["exit_ts"], p.ts.iloc[21])
        self.assertEqual(summary["holding_days"], 20)
        self.assertTrue(summary["normal_complete"])
        self.assertFalse(daily.entry_open.iloc[0])

    def test_stop_signal_not_filled_at_old_stop_or_same_close(self):
        p = prices([100, 100, 90, 80, 81], op=[100, 100, 96, 70, 81])
        summary, daily = m.reference_unit(p, origin(p), "B", cost(), config())
        self.assertEqual(summary["exit_reason"], "RISK")
        self.assertEqual(summary["exit_ts"], p.ts.iloc[3])
        self.assertAlmostEqual(summary["exit_price"], 70 * .9996)
        self.assertFalse(daily.exit_open.iloc[2])

    def test_risk_priority_over_trend_and_time(self):
        p = prices(np.r_[np.repeat(100., 20), 90., 80.])
        p.loc[20, "r20"] = -.1
        result, _ = m.reference_unit(p, origin(p), "A", cost(), config())
        self.assertEqual(result["exit_reason"], "RISK")
        self.assertEqual(result["exit_ts"], p.ts.iloc[21])

    def test_b_sixty_day_limit_relative_to_common_origin(self):
        p = prices(np.repeat(100., 80))
        result, _ = m.reference_unit(p, origin(p), "B", cost(), config())
        self.assertEqual(result["exit_ts"], p.ts.iloc[61])
        self.assertEqual(result["holding_days"], 60)

    def test_c_pullback_recovery_strict_and_sequential(self):
        p = prices([100, 98, 99, 100, 101] + [102] * 70)
        # u=1; day2 close=day1 high，不算恢复；day3 close=day2 high，也不算。
        p.loc[1, "high"], p.loc[2, "high"], p.loc[3, "high"] = 99, 100, 100.5
        result, _ = m.reference_unit(p, origin(p), "C", cost(), config())
        self.assertEqual(result["pullback_index"], 1)
        self.assertEqual(result["entry_ts"], p.ts.iloc[5])
        self.assertEqual(result["exit_ts"], p.ts.iloc[61])

    def test_c_cancel_precedes_recovery_and_releases_next_open(self):
        p = prices([100, 98, 102, 103])
        p.loc[2, "r20"] = 0
        result, daily = m.reference_unit(p, origin(p), "C", cost(), config())
        self.assertFalse(result["entered"])
        self.assertTrue(result["normal_complete"])
        self.assertEqual(daily.reason.iloc[-1], "CANCEL")
        self.assertEqual(daily.ts.iloc[-1], p.ts.iloc[3])
        self.assertEqual(result["return"], 0)

    def test_c_day19_recovery_can_enter_day20(self):
        close = np.r_[100, np.repeat(99., 17), 97, 101, np.repeat(102., 45)]
        p = prices(close)
        result, _ = m.reference_unit(p, origin(p), "C", cost(), config())
        self.assertEqual(result["entry_ts"], p.ts.iloc[20])
        self.assertEqual(result["exit_ts"], p.ts.iloc[61])

    def test_c_expiry_not_held_until_day60(self):
        p = prices(np.repeat(100., 70))
        result, daily = m.reference_unit(p, origin(p), "C", cost(), config())
        self.assertFalse(result["entered"])
        self.assertTrue(result["normal_complete"])
        self.assertEqual(daily.ts.iloc[-1], p.ts.iloc[20])
        self.assertEqual(daily.reason.iloc[-1], "EXPIRE")

    def test_incomplete_future_keeps_orders_and_marks(self):
        p = prices([100, 100, 101, 102])
        result, daily = m.reference_unit(p, origin(p), "A", cost(), config())
        self.assertTrue(result["entered"])
        self.assertFalse(result["normal_complete"])
        self.assertTrue(np.isnan(result["return"]))
        self.assertFalse(daily.exit_open.any())
        self.assertGreater(result["last_qty"], 0)
        self.assertLess(result["zero_residual_value_return"], result["observed_return"])

    def test_carry_entry_day_included_exit_day_excluded(self):
        p = prices(np.repeat(100., 80))
        plain, _ = m.reference_unit(p, origin(p), "A", cost(), config())
        charged, daily = m.reference_unit(p, origin(p), "A", cost(.001), config())
        expected = charged["qty"] * 100 * .001 * 20
        self.assertAlmostEqual(charged["carry"], expected)
        self.assertAlmostEqual(plain["last_value"] - charged["last_value"], expected)
        self.assertGreater(daily.carry_close.iloc[1], 0)
        self.assertEqual(daily.carry_close.iloc[-1], 0)

    def test_future_price_changes_do_not_change_past_orders(self):
        p = prices(np.repeat(100., 80))
        _, full = m.reference_unit(p, origin(p), "B", cost(), config())
        altered = p.copy()
        for col in ("open", "high", "low", "close"):
            altered.loc[30:, col] *= .5
        _, changed = m.reference_unit(altered, origin(p), "B", cost(), config())
        pd.testing.assert_frame_equal(full.iloc[:30].reset_index(drop=True), changed.iloc[:30].reset_index(drop=True))

    def test_price_first_hit_is_not_endpoint_or_strategy_exit(self):
        p = prices([100, 105, 95, 99])
        result = m.reference_label(p, 1, 100, 2, 3)
        self.assertEqual(result["first_hit"], "UP_FIRST")
        self.assertEqual(result["hit_day"], 1)
        self.assertEqual(result["endpoint_atr"], -.5)
        early = m.reference_label(p, 1, 100, 2, 20)
        self.assertEqual(early["first_hit"], "UP_FIRST")
        self.assertFalse(early["complete"])
        self.assertTrue(np.isnan(early["endpoint_return"]))

    def test_recent_slice_inherits_prior_equity(self):
        daily = pd.DataFrame({"ts": pd.date_range("2020-01-01", periods=5, tz="UTC"), "equity_open_before": [100, 110, 120, 90, 100], "equity": [110, 120, 90, 100, 108]})
        result = m.recent_account_slices(daily, pd.Timestamp("2020-01-06", tz="UTC"), [2]).iloc[0]
        self.assertEqual(result.initial_equity, 90)
        self.assertAlmostEqual(result["return"], .2)


class EngineReferenceParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[4]
        sys.path.insert(0, str(root / "src"))
        location = root / "research/_shared-kernels/medium-term-trend-capture/v1/engine.py"
        spec = importlib.util.spec_from_file_location("mttc_synthetic_engine_only", location)
        cls.engine = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.engine
        spec.loader.exec_module(cls.engine)
        spec = importlib.util.spec_from_file_location("mttc_synthetic_portfolio_only", location.with_name("portfolio.py"))
        cls.portfolio = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.portfolio
        spec.loader.exec_module(cls.portfolio)
        spec = importlib.util.spec_from_file_location("mttc_synthetic_inference_only", location.with_name("inference.py"))
        cls.inference = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.inference
        spec.loader.exec_module(cls.inference)

    def test_independent_features_and_candidate_set_against_engine(self):
        p = prices(100 * np.exp(np.cumsum(np.r_[np.tile([.01, .02], 50), np.tile([-.03, -.02], 20), np.tile([.03, .02], 35)])))
        p["volume"] = 100.
        p["research_window_valid"] = np.arange(len(p)) >= 59
        expected, eo = m.reference_features(p, config())
        actual = self.engine.build_panel({"TEST": p}, config())
        ao = self.engine.build_origins(actual, config())
        for name in ("r20", "sigma20", "strength", "atr14", "liquidity20", "local_index"):
            m.compare_numeric(actual[name], expected[name], name)
        self.assertEqual(list(actual.feature_valid), list(expected.feature_valid))
        for name in ("symbol", "segment", "origin_ts", "origin_index", "first_observable"):
            m.assert_values(ao[name], eo[name], name)
        self.assertGreater(len(ao), 1)

    def test_independent_portfolio_cash_and_admission_against_engine(self):
        cfg = {**config(), "max_slots": 2, "end": "2020-04-01T00:00:00Z"}
        cases = []
        for oid, symbol, index, length, liquid in [("one", "Z", 0, 80, 100.), ("two", "A", 0, 80, 100.), ("blocked", "B", 0, 80, 99.), ("same", "A", 1, 80, 110.), ("gap", "G", 25, 30, 100.), ("gaprepeat", "G", 40, 80, 100.), ("afterrelease", "C", 21, 80, 100.)]:
            p = prices(100 + 4 * np.sin(np.arange(length) / 3))
            p["symbol"] = symbol
            p["local_index"] = np.arange(len(p))
            o = {**origin(p, index=index), "origin_id": oid, "symbol": symbol, "segment": 0, "liquidity": liquid}
            cases.append((p, o))
        origins = pd.DataFrame([o for _, o in cases])
        for policy in ("A", "B", "C"):
            for carry in (0., .001):
                with self.subTest(policy=policy, carry=carry):
                    reference = {o["origin_id"]: m.reference_unit(p, o, policy, cost(carry), cfg)[1] for p, o in cases}
                    engine = {o["origin_id"]: self.engine.simulate_opportunity(p, o, policy, cost(carry), cfg)["daily"] for p, o in cases}
                    expected, ea = m.reference_portfolio(origins, reference, policy, "synthetic", cfg)
                    actual, aa = self.portfolio.simulate_portfolio(origins, engine, policy, "synthetic", cfg)
                    numeric = [c for c in expected if c not in ("ts", "close_ts", "policy", "cost_id")]
                    m.compare_numeric(actual[numeric], expected[numeric], "portfolio daily")
                    m.compare_actions(aa, ea)

    def test_production_future_changes_cannot_rewrite_past_paths(self):
        p = prices(np.repeat(100., 80))
        p["local_index"] = np.arange(len(p))
        o = {**origin(p), "origin_id": "prefix", "symbol": "TEST", "segment": 0}
        future = p.copy()
        for name in ("open", "high", "low", "close"):
            future.loc[30:, name] *= 2
        future.loc[30:, "r20"] = -1
        for policy in ("A", "B", "C"):
            a = self.engine.simulate_opportunity(p, o, policy, cost(.001), config())["daily"]
            b = self.engine.simulate_opportunity(future, o, policy, cost(.001), config())["daily"]
            pd.testing.assert_frame_equal(a.loc[a.ts < p.ts.iloc[30]].reset_index(drop=True), b.loc[b.ts < p.ts.iloc[30]].reset_index(drop=True))

    def test_fully_serialized_synthetic_audit_and_tamper_detection(self):
        cfg = {**config(), "end": str(pd.Timestamp("2020-01-01", tz="UTC") + 180*m.DAY), "costs": [cost()], "recent_days": [1, 7, 30, 365], "bootstrap": {"blocks": [180], "repetitions": 100, "seed": 77, "confidence": .95}}
        cfg["costs"][0]["id"] = "base"
        with tempfile.TemporaryDirectory() as temporary:
            family = Path(temporary) / "research/asset-portfolios/synthetic"
            inputs, output = family / "artifacts/p0-inputs", family / "artifacts/research"
            inputs.mkdir(parents=True)
            output.mkdir(parents=True)
            (family / "specs").mkdir()
            (family / "specs/config.json").write_text(json.dumps(cfg))
            (family / "specs/computation-lock.json").write_text(json.dumps({"files": {}}))
            frames, manifest = {}, {}
            for j, symbol in enumerate(("TEST", "SECOND")):
                p = prices(100 * np.exp(np.cumsum(np.tile([.01 + .002*j, .025 + .002*j], 90))))
                p = p.drop(columns=["r20", "segment"])
                p["symbol"], p["volume"] = symbol, 10.
                p["research_window_valid"] = np.arange(len(p)) >= 59
                path = inputs / f"{symbol}.pkl.gz"
                p.to_pickle(path, compression="gzip")
                manifest[symbol] = {"path": path.name, "rows": len(p), "sha256": m.sha256(path)}
                frames[symbol] = p
            (inputs / "frame-manifest.json").write_text(json.dumps(manifest))
            panel = self.engine.build_panel(frames, cfg)
            panel.attrs = {}
            panel.to_parquet(output / "panel.parquet", index=False)
            segments = {s: g.reset_index(drop=True) for s, g in panel.groupby("symbol")}
            origins = self.engine.build_origins(panel, cfg)
            labeled = []

            def label(g, first, baseline, atr, horizon):
                q = (g.close.iloc[first:first+horizon].to_numpy()-baseline)/atr
                up, down = np.flatnonzero(q >= 2), np.flatnonzero(q <= -2)
                u, d = up[0] if len(up) else np.inf, down[0] if len(down) else np.inf
                return {"outcome": "CONTINUATION" if u < d else "FAILURE" if d < u else "TIMEOUT" if len(q) == horizon else "CENSORED", "first_hit_day": int(min(u, d) + 1) if np.isfinite(min(u, d)) else None, "endpoint_return": float(g.close.iloc[first+horizon-1]/baseline-1) if first+horizon <= len(g) else None}

            for o in origins.to_dict("records"):
                g, oi = segments[o["symbol"]], o["origin_index"]
                o.update(complete_window_60=oi+61<len(g), segment_rows_after_origin=len(g)-oi-1)
                for h in (20, 60):
                    o.update({f"origin_{h}_{k}": v for k, v in label(g, oi+1, g.open.iloc[oi+1], o["atr"], h).items()})
                labeled.append(o)
            origins = pd.DataFrame(labeled)
            origins.to_parquet(output / "origins.parquet", index=False)
            unit, summary, accounts, actions, metrics = [], [], [], [], {}
            c = cfg["costs"][0]
            for policy in cfg["policies"]:
                paths = {}
                for o in origins.to_dict("records"):
                    g = segments[o["symbol"]]
                    result = self.engine.simulate_opportunity(g, o, policy, c, cfg)
                    s, d = result["summary"], result["daily"]
                    s["complete_window_60"] = o["complete_window_60"]
                    for h in (20, 60):
                        target = label(g, s["entry_index"], s["entry_price"], o["atr"], h) if s["entered"] else {"outcome": "NOT_ENTERED", "first_hit_day": None, "endpoint_return": None}
                        s.update({f"entry_{h}_{k}": v for k, v in target.items()})
                    d["symbol"] = o["symbol"]
                    unit.append(d)
                    summary.append(s)
                    paths[o["origin_id"]] = d
                ad, aa = self.portfolio.simulate_portfolio(origins, paths, policy, "base", cfg)
                accounts.append(ad)
                actions.append(aa)
                metrics["base."+policy] = self.portfolio.portfolio_metrics(ad, aa, cfg)
            s = pd.DataFrame(summary)
            s.to_parquet(output / "opportunities.parquet", index=False)
            for name, parts in [("unit_daily", unit), ("portfolio_daily", accounts), ("portfolio_actions", actions)]:
                pd.concat(parts, ignore_index=True).to_parquet(output / f"{name}.parquet", index=False)
            paired = s.loc[s.normal_complete & s.complete_window_60].pivot(index="origin_id", columns="policy", values="return").dropna().join(origins.set_index("origin_id")[["symbol", "origin_ts"]]).reset_index()
            paired.to_parquet(output / "paired-base.parquet", index=False)
            (output / "account-metrics.json").write_text(json.dumps(metrics))
            (output / "paired-statistics.json").write_text(json.dumps({"base": self.inference.paired_statistics(paired, cfg)}))
            completed = {"files": {p.name: m.sha256(p) for p in output.iterdir()}}
            (output / "completed.json").write_text(json.dumps(completed))
            receipt = m.audit_result(family, output, family / "artifacts/audit")
            self.assertEqual(receipt["status"], "PASS")
            with self.assertRaises(FileExistsError):
                m.audit_result(family, output, family / "artifacts/audit")
            (output / "account-metrics.json").write_text("{}")
            with self.assertRaisesRegex(AssertionError, "completed output changed"):
                m.audit_result(family, output, family / "artifacts/audit-tamper")
            rejected = json.loads((family / "artifacts/audit-tamper/receipt.json").read_text())
            self.assertEqual(rejected["status"], "DATA_OR_REPRODUCTION_FAILURE")

    def test_independent_paths_against_engine(self):
        cases = [prices(np.repeat(100., 80)), prices([100, 100, 90, 80, 81], op=[100, 100, 96, 70, 81]), prices([100, 98, 99, 100, 101] + [102] * 70), prices(np.r_[100, np.repeat(99., 17), 97, 101, np.repeat(102., 45)]), prices([100, 98, 102, 103]), prices([100]), prices([100, 101, 102])]
        cases[4].loc[2, "r20"] = 0
        nums = ["open_before", "open_after", "close_value", "cash_open_before", "cash_open_after", "cash_close", "qty_open_before", "qty_open_after", "qty_close", "fee_open", "slippage_open", "carry_close", "intraday_low_value"]
        for i, p in enumerate(cases):
            p["local_index"] = np.arange(len(p))
            o = {**origin(p), "origin_id": "synthetic", "symbol": "TEST", "segment": 0}
            for policy in ("A", "B", "C"):
                for carry in (0., .001):
                    with self.subTest(case=i, policy=policy, carry=carry):
                        own, daily = m.reference_unit(p, o, policy, cost(carry), config())
                        actual = self.engine.simulate_opportunity(p, o, policy, cost(carry), config())
                        ad = actual["daily"]
                        self.assertEqual(list(daily.ts), list(ad.ts))
                        m.compare_numeric(ad[nums], daily[nums], "synthetic unit cash")
                        for col in ("entry_open", "exit_open", "release_open", "data_gap"):
                            self.assertEqual(list(ad[col]), list(daily[col]), col)
                        for col in ("normal_complete", "released", "unresolved", "entered", "terminal_status", "data_interrupted"):
                            self.assertEqual(actual["summary"][col], own[col], col)
                        for col in ("entry_price", "exit_price", "qty", "fees", "slippage", "carry", "last_value", "last_cash", "last_qty", "holding_days"):
                            m.compare_numeric([actual["summary"][col]], [own[col]], col)


if __name__ == "__main__":
    unittest.main()
