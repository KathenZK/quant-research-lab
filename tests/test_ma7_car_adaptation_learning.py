"""Synthetic checks of time-separated, code-separated adaptation learning.

No historical prices or learning outputs are read. These tests independently
specify eligibility, equal-coin weighting and exported-tree edge behavior.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest
from sklearn.tree import DecisionTreeRegressor


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts"
sys.path.insert(0, str(SCRIPTS))
try:
    spec = importlib.util.spec_from_file_location("adaptation_learning_test", SCRIPTS / "learn_adaptation_20260911.py")
    learn = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(learn)
finally:
    sys.path.remove(str(SCRIPTS))


CUT = pd.Timestamp("2025-01-01", tz="UTC")


def training_frame(coins=75, rows_per_coin=8):
    rows = []
    for number in range(coins):
        slug = f"SYNTHETIC{number}"
        for j in range(rows_per_coin):
            base = ((number % 9) - 4) / 10 + j / 100
            rows.append({"slug": slug, "case_id": f"{slug}::{j}", "fold": learn.fold(slug),
                "ready90": True, "terminal_any": False,
                "label_end": CUT - pd.Timedelta(days=3 + j),
                "u_v3": base, "u_defense": base + .01, "u_extension": base - .01,
                **{k: float(number % 7) + j / 10 for k in learn.ASSET + learn.ENTRY}})
    return pd.DataFrame(rows)


def test_target_coin_and_its_entire_fold_never_enter_training():
    frame = training_frame()
    target = "SYNTHETIC4"
    heldout = learn.fold(target)
    model = learn.train_one(frame, CUT, heldout, "D_JOINT")
    assert target not in model["training_slugs"]
    assert all(learn.fold(slug) != heldout for slug in model["training_slugs"])
    assert set(model["training_ids"]) == set(frame.loc[frame.fold.ne(heldout), "case_id"])
    assert learn.fold("  synthetic4 ") == heldout


@pytest.mark.parametrize("late_action", learn.ACTIONS)
@pytest.mark.parametrize("lag", [pd.Timedelta(0), pd.Timedelta(seconds=1)])
def test_all_three_action_exits_must_be_strictly_before_cutoff(late_action, lag):
    frame = training_frame()
    heldout = 0
    index = frame.index[frame.fold.ne(heldout)][0]
    for action in learn.ACTIONS:
        frame["exit_" + action] = CUT - pd.Timedelta(days=2)
    frame.loc[index, "exit_" + late_action] = CUT + lag
    frame["label_end"] = frame[["exit_" + action for action in learn.ACTIONS]].max(axis=1)
    model = learn.train_one(frame, CUT, heldout, "D_JOINT")
    assert frame.loc[index, "case_id"] not in model["training_ids"]
    assert pd.Timestamp(model["max_training_label_end"]) < CUT


def test_terminal_or_less_than_90_days_never_train():
    frame = training_frame()
    eligible = frame.index[frame.fold.ne(0)]
    frame.loc[eligible[:2], "terminal_any"] = True
    frame.loc[eligible[2:4], "ready90"] = False
    model = learn.train_one(frame, CUT, 0, "A_ASSET")
    assert set(frame.loc[eligible[:4], "case_id"]).isdisjoint(model["training_ids"])


@pytest.mark.parametrize("arm", ["A_ASSET", "B_ENTRY"])
def test_asset_and_entry_filters_split_and_decide_only_from_v3_target(arm):
    a = training_frame()
    b = a.copy()
    b["u_defense"] = np.arange(len(b), dtype=float) * 1000
    b["u_extension"] = -b.u_defense
    left = learn.train_one(a, CUT, 0, arm)
    right = learn.train_one(b, CUT, 0, arm)
    assert left["targets"] == right["targets"] == ["u_v3"]
    assert left["tree"] == right["tree"]
    for leaf in left["leaves"]:
        assert left["leaves"][leaf]["allow"] == right["leaves"][leaf]["allow"]
        assert left["leaves"][leaf]["action"] == right["leaves"][leaf]["action"] == "v3"


def test_tree_training_weights_sum_equally_for_each_coin(monkeypatch):
    frame = training_frame()
    chosen = frame.loc[frame.fold.ne(0), "slug"].iloc[0]
    extra = pd.concat([frame.loc[frame.slug.eq(chosen)]] * 7, ignore_index=True)
    extra["case_id"] = [f"extra-{i}" for i in range(len(extra))]
    frame = pd.concat([frame, extra], ignore_index=True)
    recorded = {}
    original = learn.DecisionTreeRegressor

    class RecordingTree:
        def __init__(self, **kwargs):
            self.delegate = original(**kwargs)

        def fit(self, x, y, sample_weight):
            recorded["weights"] = sample_weight.copy()
            self.delegate.fit(x, y, sample_weight=sample_weight)

        def __getattr__(self, key):
            return getattr(self.delegate, key)

    monkeypatch.setattr(learn, "DecisionTreeRegressor", RecordingTree)
    model = learn.train_one(frame, CUT, 0, "A_ASSET")
    retained = frame.loc[frame.fold.ne(0)].copy()
    retained["weight"] = recorded["weights"]
    totals = retained.groupby("slug").weight.sum()
    assert np.allclose(totals, totals.iloc[0], rtol=0, atol=1e-12)
    assert model["training_weight_per_coin_min"] == pytest.approx(model["training_weight_per_coin_max"])


def test_leaf_action_statistics_are_coin_means_not_trade_weighted():
    rows = [{"slug": "MANY", "u_v3": 1., "u_defense": 1., "u_extension": 1.}] * 100
    rows += [{"slug": "ONE", "u_v3": -1., "u_defense": -1., "u_extension": -1.}]
    advice = learn.leaf_advice(pd.DataFrame(rows), "A_ASSET")
    assert advice["means"]["v3"] == 0.
    assert advice["standard_errors"]["v3"] == 1.


@pytest.mark.parametrize("arm", learn.ARMS)
@pytest.mark.parametrize("coins,rows", [(19, 200), (20, 119)])
def test_unsupported_negative_leaf_uses_v3_and_never_rejects(arm, coins, rows):
    frame = pd.DataFrame({"slug": [f"C{i % coins}" for i in range(rows)],
        "u_v3": -1., "u_defense": -2., "u_extension": -3.})
    advice = learn.leaf_advice(frame, arm)
    assert not advice["supported"]
    assert advice["allow"] and advice["action"] == "v3"
    assert advice["reason"] == "insufficient_leaf_support"


@pytest.mark.parametrize("arm,allow", [("A_ASSET", False), ("B_ENTRY", False),
    ("C_ROUTE", True), ("D_JOINT", False)])
def test_supported_all_negative_leaf_filters_only_declared_arms(arm, allow):
    frame = pd.DataFrame({"slug": [f"C{i % 20}" for i in range(120)],
        "u_v3": -.1, "u_defense": -.2, "u_extension": -.3})
    advice = learn.leaf_advice(frame, arm)
    assert advice["supported"] and advice["allow"] is allow
    assert advice["action"] == "v3"


def test_exported_json_tree_matches_sklearn_at_adjacent_float32_midpoint():
    low = np.nextafter(np.float32(4.), np.float32(5.))
    high = np.nextafter(low, np.float32(5.))
    frame = pd.DataFrame({"x": [low, high]})
    x, medians = learn.matrix(frame, ["x"])
    tree = DecisionTreeRegressor(max_depth=1, random_state=0).fit(x, [0., 1.])
    assert tree.tree_.node_count == 3
    leaves = tree.apply(x)
    model = {"model_id": "EDGE", "heldout_fold": 0, "cutoff": str(CUT), "fallback": False,
        "columns": ["x"], "medians": medians,
        "tree": {k: getattr(tree.tree_, k).tolist() for k in
                 ["children_left", "children_right", "feature", "threshold"]},
        "leaves": {str(int(leaf)): {"allow": True, "action": "v3", "reason": "edge"} for leaf in leaves}}
    model = json.loads(json.dumps(model))
    assert np.array_equal(learn.infer(model, frame).leaf_id.to_numpy(), leaves)


def test_missing_fill_uses_training_median_and_fixed_training_feature_indicators():
    training = pd.DataFrame({"x": [2., np.nan, 4.], "all_missing": [np.nan] * 3})
    x, medians = learn.matrix(training, ["x", "all_missing"])
    validation = pd.DataFrame({"x": [np.nan, 10000.], "all_missing": [5., np.nan]})
    y, used = learn.matrix(validation, ["x", "all_missing"], medians)
    assert used == medians == {"x": 3., "all_missing": 0.}
    assert x.shape == (3, 4) and y.shape == (2, 4)
    assert y.tolist() == [[3., 5., 1., 0.], [10000., 0., 0., 1.]]


def fallback_model(year, group, arm, action, allow):
    return {"model_id": f"{year}_f{group}_{arm}", "heldout_fold": group,
        "cutoff": str(pd.Timestamp(f"{year}-01-01", tz="UTC")), "fallback": True,
        "leaves": {"0": {"allow": allow, "action": action, "reason": "switch"}}}


def test_model_switch_uses_signal_day_plus_one_not_signal_day():
    d = pd.DataFrame({"timestamp": pd.to_datetime(["2024-12-30", "2024-12-31", "2025-01-01"], utc=True),
                      "ready90": [True, True, True]})
    for k in learn.ASSET:
        d[k] = 0.
    for side in ("long", "short"):
        for key in learn.ENTRY:
            d[side + "_" + key.removeprefix("entry_")] = 0.
    slug = "SYNTHETIC0"
    group = learn.fold(slug)
    models = {}
    for arm in learn.ARMS:
        for year, action, allow in [(2023, "defense", False), (2025, "extension", True)]:
            model = fallback_model(year, group, arm, action, allow)
            models[model["model_id"]] = model
    result = learn.schedules(d, slug, models)
    for arm in learn.ARMS:
        assert result[arm].route_long.tolist() == ["defense", "extension", "extension"]
        assert result[arm].admit_long.tolist() == [False, True, True]
        assert result[arm].route_short.tolist() == ["defense", "extension", "extension"]
    d.loc[1, "ready90"] = False
    again = learn.schedules(d, slug, models)
    for frame in again.values():
        assert not frame.admit_long.iloc[1] and not frame.admit_short.iloc[1]
        assert frame.rule_id_long.iloc[1] == "INSUFFICIENT_HISTORY90"


@pytest.mark.parametrize("missing_action", learn.ACTIONS)
def test_learning_entrypoint_rejects_any_missing_action_exit(tmp_path, monkeypatch, missing_action):
    source, output = tmp_path / "cases", tmp_path / "learning"
    source.mkdir()
    row = training_frame(1, 1).iloc[[0]].copy()
    row["run_key"], row["source_trade_id"] = "SYNTHETIC0__seg0", 1
    row["signal_day"] = pd.Timestamp("2023-02-01", tz="UTC")
    row["entry_time"] = pd.Timestamp("2023-02-02", tz="UTC")
    for action in learn.ACTIONS:
        row["exit_" + action] = pd.Timestamp("2023-02-03", tz="UTC")
    row["exit_" + missing_action] = pd.NaT
    row.to_parquet(source / "cases.parquet", index=False)
    (source / "completion.json").write_text('{"complete": true}')
    (source / "artifact_checksums.json").write_text(json.dumps({
        "cases.parquet": learn.sha(source / "cases.parquet"),
        "completion.json": learn.sha(source / "completion.json")}))
    (tmp_path / "contract_pin.json").write_text('{}')
    monkeypatch.setattr(learn, "R", tmp_path)
    monkeypatch.setattr(sys, "argv", ["learn", "--cases", str(source), "--output", str(output)])
    with pytest.raises((ValueError, AssertionError)):
        learn.main()
