from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "research/asset-portfolios/1d-ma7-cross-trend-probability/scripts/run_binance_1d_ma7_ctp_p6_market_regime_side_conditional_ranking.py"


def load_p6():
    spec = importlib.util.spec_from_file_location("p6_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_hype_isolation_constant_and_hyper_retained() -> None:
    p6 = load_p6()
    assert p6.HYPE_ASSET == "HYPE/USDT:USDT"
    assert p6.HYPER_ASSET == "HYPER/USDT:USDT"
    assert p6.base_symbol(p6.HYPER_ASSET) == "HYPER"
    assert p6.base_symbol(p6.HYPE_ASSET) == "HYPE"


def test_restore_direction_aligned_market_state_consistent_across_sides() -> None:
    p6 = load_p6()
    rows = [
        {"asset": "BTC/USDT:USDT", "ts": "2024-01-01T00:00:00Z", "side": "long", "dir_market_breadth_ma30_p0r": 0.7, "dir_btc_price_side_ma30": 1},
        {"asset": "ETH/USDT:USDT", "ts": "2024-01-01T00:00:00Z", "side": "short", "dir_market_breadth_ma30_p0r": 0.3, "dir_btc_price_side_ma30": -1},
        {"asset": "SOL/USDT:USDT", "ts": "2024-01-02T00:00:00Z", "side": "long", "dir_market_breadth_ma30_p0r": 0.3, "dir_btc_price_side_ma30": -1},
        {"asset": "BNB/USDT:USDT", "ts": "2024-01-02T00:00:00Z", "side": "short", "dir_market_breadth_ma30_p0r": 0.7, "dir_btc_price_side_ma30": 1},
        {"asset": "XRP/USDT:USDT", "ts": "2024-01-03T00:00:00Z", "side": "long", "dir_market_breadth_ma30_p0r": np.nan, "dir_btc_price_side_ma30": 1},
    ]
    frame = pd.DataFrame(rows)
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
    out, audit = p6.restore_market_state(frame)
    assert audit["long_short_state_mismatch_days"] == 0
    assert out.loc[out["ts"].eq(pd.Timestamp("2024-01-01T00:00:00Z")), "market_state"].tolist() == ["BULL", "BULL"]
    assert out.loc[out["ts"].eq(pd.Timestamp("2024-01-02T00:00:00Z")), "market_state"].tolist() == ["BEAR", "BEAR"]
    assert out.loc[out["ts"].eq(pd.Timestamp("2024-01-03T00:00:00Z")), "market_state"].iloc[0] == "UNKNOWN"


def test_fold_split_uses_label_end_before_validation_start() -> None:
    p6 = load_p6()
    frame = pd.DataFrame(
        {
            "ts": pd.to_datetime(["2021-12-01", "2021-12-20", "2022-01-05"], utc=True),
            p6.LABEL_END: pd.to_datetime(["2021-12-21", "2022-01-02", "2022-01-25"], utc=True),
            p6.TARGET: [0, 1, 1],
        }
    )
    train, valid = p6.fold_split(frame, pd.Timestamp("2022-01-01T00:00:00Z"), pd.Timestamp("2023-01-01T00:00:00Z"))
    assert len(train) == 1
    assert train[p6.LABEL_END].max() < pd.Timestamp("2022-01-01T00:00:00Z")
    assert len(valid) == 1


def test_top_percentile_tie_breaker_is_outcome_blind() -> None:
    p6 = load_p6()
    frame = pd.DataFrame(
        {
            "asset": ["BBB", "AAA", "CCC", "DDD"],
            "ts": pd.to_datetime(["2024-01-01"] * 4, utc=True),
            "side": ["long"] * 4,
            "score": [0.9, 0.9, 0.8, 0.7],
            p6.TARGET: [0, 1, 1, 0],
        }
    )
    mask = p6.top_mask(frame, "score", pct=0.25, group_cols=None)
    assert frame.loc[mask, "asset"].tolist() == ["AAA"]


def test_same_day_market_only_random_baseline_equal_opportunity() -> None:
    p6 = load_p6()
    assets = [f"A{i:02d}/USDT:USDT" for i in range(20)]
    frame = pd.DataFrame(
        {
            "asset": assets,
            "ts": pd.to_datetime(["2024-01-01"] * 20, utc=True),
            "side": ["long"] * 20,
            "six_grid": ["BULL_LONG"] * 20,
            "score": list(reversed(np.arange(20))),
            p6.TARGET: [1] * 5 + [0] * 15,
            p6.NET_RETURN: [0.1] * 5 + [-0.1] * 15,
        }
    )
    res = p6.same_day_top5(frame, "score")
    assert res["selected_n"] == 1
    assert res["expected_success_rate"] == 0.25
    assert res["expected_net_mean"] == -0.05
    frame["constant_market_only_score"] = 0.42
    tied = p6.same_day_top5(frame, "constant_market_only_score")
    assert tied["success_delta_vs_same_day_random"] == 0
    assert tied["net_delta_vs_same_day_random"] == 0


def test_constant_score_basic_top_metrics_equal_base_rate() -> None:
    p6 = load_p6()
    frame = pd.DataFrame(
        {
            "asset": [f"A{i}/USDT:USDT" for i in range(10)],
            "ts": pd.date_range("2024-01-01", periods=10, freq="D", tz="UTC"),
            "side": ["long"] * 10,
            "block28": [0] * 10,
            "score": [0.3] * 10,
            p6.TARGET: [1, 1, 1, 0, 0, 0, 0, 0, 0, 0],
            p6.NET_RETURN: [0.1, 0.1, 0.1, -0.1, -0.1, -0.1, -0.1, -0.1, -0.1, -0.1],
        }
    )
    out = p6.basic_metrics(frame, "score")
    assert out["positive_rate"] == 0.3
    assert out["top5_success_rate"] == 0.3
    assert out["top5_uplift"] == 0


def test_inner_b0_oof_uses_forward_label_cutoffs(monkeypatch) -> None:
    p6 = load_p6()
    n = 1400
    dates = pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC")
    frame = pd.DataFrame(
        {
            "asset": ["BTC/USDT:USDT"] * n,
            "side": ["long"] * n,
            "ts": dates,
            p6.LABEL_END: dates + pd.Timedelta(days=20),
            p6.TARGET: [0, 1] * (n // 2),
            "f0": np.linspace(-1, 1, n),
        }
    )

    def fake_fit(fit, valid, features):
        assert fit[p6.LABEL_END].max() < valid["ts"].min()
        return np.zeros(len(fit)), np.full(len(valid), 0.55), {}

    monkeypatch.setattr(p6.P5, "fit_logit", fake_fit)
    oof, stages = p6.generate_inner_b0_oof(frame, ["f0"], pd.Timestamp("2024-01-01T00:00:00Z"))
    assert len(oof) > 0
    assert oof["b0_raw_probability"].eq(0.55).all()
    assert any(stage["used"] for stage in stages)


def test_bootstrap_contributions_match_full_resampled_same_day_recompute() -> None:
    p6 = load_p6()
    rows = []
    for day in pd.date_range("2024-01-01", periods=56, freq="D", tz="UTC"):
        for i in range(20):
            rows.append(
                {
                    "period": "development_oof",
                    "asset": f"A{i:02d}/USDT:USDT",
                    "ts": day,
                    "side": "long",
                    "six_grid": "MIXED_LONG",
                    "block28": int((day - pd.Timestamp("2024-01-01T00:00:00Z")).days // 28),
                    p6.TARGET: int(i % 3 == 0),
                    p6.NET_RETURN: float(i) / 100,
                    "R_B0_69_score": float(i) / 20,
                    "M1_B0_X_SIDE_X_REGIME_score": float(20 - i) / 20,
                }
            )
    frame = pd.DataFrame(rows)
    sample = pd.concat([frame[frame["block28"].eq(0)], frame[frame["block28"].eq(0)], frame[frame["block28"].eq(1)]], ignore_index=True)
    full = p6.same_day_top5(sample, "M1_B0_X_SIDE_X_REGIME_score")
    contrib = p6.same_day_contributions(frame, "M1_B0_X_SIDE_X_REGIME_score")
    block_contrib = contrib.groupby("block28")[["selected_n", "success_diff_sum", "net_diff_sum"]].sum()
    summed = block_contrib.loc[[0, 0, 1]].sum()
    assert np.isclose(full["success_delta_vs_same_day_random"], summed["success_diff_sum"] / summed["selected_n"])
    assert np.isclose(full["net_delta_vs_same_day_random"], summed["net_diff_sum"] / summed["selected_n"])


def test_frozen_threshold_uses_pre2025_oof_score_space() -> None:
    p6 = load_p6()
    frame = pd.DataFrame(
        {
            "period": ["development_oof"] * 20 + ["validation_2025_plus"] * 10,
            "event_year": [2024] * 20 + [2025] * 10,
            "asset": ["A/USDT:USDT"] * 30,
            "ts": pd.date_range("2024-01-01", periods=30, freq="D", tz="UTC"),
            "side": ["long"] * 30,
            p6.TARGET: [0, 1] * 15,
            p6.NET_RETURN: [0.0] * 30,
            "R_B0_69_score": np.linspace(0, 1, 30),
            "M0_MARKET_ONLY_score": np.linspace(0, 1, 30),
            "M1_B0_X_SIDE_X_REGIME_score": np.linspace(0, 1, 30),
        }
    )
    out = p6.frozen_threshold_metrics(frame)
    row = out[(out["model"].eq("R_B0_69")) & (out["scope"].eq("validation_2025_plus"))].iloc[0]
    assert row["threshold"] == frame.loc[:19, "R_B0_69_score"].quantile(0.95)


def test_manifest_excludes_self_if_p6_manifest_exists() -> None:
    p6 = load_p6()
    if not p6.MANIFEST_PATH.exists():
        return
    manifest = p6.load_json(p6.MANIFEST_PATH)
    paths = {item["path"] for item in manifest["artifacts"]}
    assert str(p6.MANIFEST_PATH.relative_to(p6.ROOT)) not in paths
    assert manifest["manifest_excludes_self"] is True
