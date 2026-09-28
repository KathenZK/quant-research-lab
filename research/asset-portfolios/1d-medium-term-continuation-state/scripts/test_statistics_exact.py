"""精确修复只用合成panel测试，不读取任何真实研究结果。"""
import importlib.util
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

SPEC = importlib.util.spec_from_file_location("mtcs_exact_under_test", Path(__file__).with_name("statistics_exact.py"))
exact = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = exact
SPEC.loader.exec_module(exact)
base = exact.base


def panel(days=173, assets=3):
    rows = []
    for t in range(days):
        for a in range(assets):
            r = {"symbol": f"C{a}", "signal_time": pd.Timestamp("2020-01-01", tz="UTC") + pd.Timedelta(days=t),
                 "feature_valid": True, "valid20": True,
                 "q20": np.sin(t / 11) + a * .3 + (t % 5) * .1,
                 "l20": np.cos(t / 21) * .4 + a * .15,
                 **dict.fromkeys(base.UNITS, False)}
            r["U_LONG" if (t + a) % 2 else "U_SHORT"] = True
            if (t + a) % 3:
                side = "LONG" if (t + a) % 2 else "SHORT"
                r[f"M_{side}"] = True
                r[f"S{(t // 3 + a) % 3 + 1}_{side}"] = True
            rows.append(r)
    return pd.DataFrame(rows)


def test_compact_point_estimator_is_algebraically_identical():
    p = base.prepare(panel())
    packed = exact.pack_daily(p)
    assert packed.shape == (173, 15 * 3 + 20)
    old, old_counts = base.estimate(p.sufficient.sum(axis=0))
    new, new_counts = exact.estimate_packed(packed.sum(axis=0), 3)
    np.testing.assert_allclose(new, old, rtol=0, atol=1e-13)
    np.testing.assert_array_equal(new_counts, old_counts)


@pytest.mark.parametrize("block", [60, 120])
def test_all_2048_full_replicas_match_original_no_if_reference(block):
    p = base.prepare(panel())
    packed = exact.pack_daily(p)
    reference, reference_counts = exact.reference_values(p, block, 20260908)
    starts = base.draw_starts(20260908, block, len(packed), 2048)
    full = base.circular_block_sums(packed, block)
    tail = base.circular_block_sums(packed, len(packed) % block)
    for begin in range(0, 2048, 127):
        end = min(begin + 127, 2048)
        totals = exact.exact_batch(starts[begin:end], full, tail, len(packed), block)
        values, counts = exact.estimate_packed(totals, 3)
        np.testing.assert_allclose(values, reference[begin:end], rtol=0, atol=1e-12)
        np.testing.assert_array_equal(counts, reference_counts[begin:end])


@pytest.mark.parametrize("days,block", [(180, 60), (173, 60), (173, 120), (40, 60)])
def test_full_and_truncated_blocks_retain_exact_calendar_length(days, block):
    p = base.prepare(panel(days=days, assets=2))
    packed = exact.pack_daily(p)
    starts = base.draw_starts(31, block, days, 17)
    k, rem = divmod(days, block)
    full = base.circular_block_sums(packed, block) if k else None
    tail = base.circular_block_sums(packed, rem) if rem else None
    totals = exact.exact_batch(starts, full, tail, days, block)
    wanted = base.resampled_totals(p.sufficient, starts, block)
    values, counts = exact.estimate_packed(totals, 2)
    reference, reference_counts = base.estimate(wanted)
    np.testing.assert_allclose(values, reference, atol=1e-12, rtol=0, equal_nan=True)
    np.testing.assert_array_equal(counts, reference_counts)
    all_day = totals[:, 20:26].reshape(17, 2, 3)[:, :, 0].sum(axis=1)
    np.testing.assert_array_equal(all_day, np.full(17, days * 2))


def test_different_batch_sizes_preserve_rng_starts_and_complete_estimates():
    p = base.prepare(panel())
    packed = exact.pack_daily(p)
    full, tail = base.circular_block_sums(packed, 60), base.circular_block_sums(packed, 53)
    outputs, indices = [], []
    for batch in (1, 31, 256):
        rng = np.random.default_rng(np.random.SeedSequence([7, 60]))
        values, chunks = [], []
        for start in range(0, 511, batch):
            st = rng.integers(0, 173, size=(min(batch, 511 - start), 3), dtype=np.int64)
            chunks.append(st)
            values.append(exact.estimate_packed(exact.exact_batch(st, full, tail, 173, 60), 3)[0])
        outputs.append(np.concatenate(values))
        indices.append(np.concatenate(chunks))
    for result, starts in zip(outputs[1:], indices[1:]):
        np.testing.assert_array_equal(starts, indices[0])
        np.testing.assert_allclose(result, outputs[0], atol=1e-12, rtol=0)


def test_zero_weight_and_sparse_zero_replicas_are_kept():
    f = panel(days=173, assets=2)
    f.loc[:, list(base.UNITS)] = False
    f.loc[0, "U_LONG"] = True
    p = base.prepare(f)
    packed = exact.pack_daily(p)
    starts = base.draw_starts(8, 60, 173, 2048)
    values, counts = exact.estimate_packed(exact.exact_batch(starts,
        base.circular_block_sums(packed, 60), base.circular_block_sums(packed, 53), 173, 60), 2)
    assert (counts[:, 0] == 0).any()
    assert np.isnan(values[counts[:, 0] == 0, 0]).all()
    assert np.isfinite(values[counts[:, 0] > 0, 0]).all()


def test_checkpoint_resume_is_bitwise_identical_and_idempotent(tmp_path):
    f = panel(days=173, assets=1)
    uninterrupted = exact.analyze(f, tmp_path / "full", bootstrap_reps=64, batch_reps=7,
                                  checkpoint_reps=16, progress_callback=lambda _: None)
    def stop(event):
        if event["stage"] == "CHECKPOINT":
            raise InterruptedError("synthetic interruption after durable checkpoint")
    with pytest.raises(InterruptedError):
        exact.analyze(f, tmp_path / "resumed", bootstrap_reps=64, batch_reps=7,
                      checkpoint_reps=16, progress_callback=stop)
    resumed = exact.analyze(f, tmp_path / "resumed", bootstrap_reps=64, batch_reps=7,
                            checkpoint_reps=16, progress_callback=lambda _: None)
    assert [r["error_samples_sha256"] for r in uninterrupted["blocks"]] == [r["error_samples_sha256"] for r in resumed["blocks"]]
    assert not resumed["all_reliable"]
    assert resumed["selected_historical_candidate"] is None
    reread = exact.analyze(f, tmp_path / "resumed", bootstrap_reps=64, batch_reps=7,
                           checkpoint_reps=16, progress_callback=lambda _: None)
    assert reread == resumed
    changed = f.copy()
    changed.loc[0, "q20"] += .01
    with pytest.raises(ValueError, match="contract differs"):
        exact.analyze(changed, tmp_path / "resumed", bootstrap_reps=64, batch_reps=7,
                      checkpoint_reps=16, progress_callback=lambda _: None)


def test_interruption_before_commit_replays_orphan_identically(tmp_path):
    f = panel(days=173, assets=1)
    def stop(event):
        if event["stage"] == "BATCH" and event["processed"] == 7:
            raise InterruptedError("uncommitted batch")
    with pytest.raises(InterruptedError):
        exact.analyze(f, tmp_path / "run", bootstrap_reps=32, batch_reps=7,
                      checkpoint_reps=16, progress_callback=stop)
    report = exact.analyze(f, tmp_path / "run", bootstrap_reps=32, batch_reps=7,
                           checkpoint_reps=16, progress_callback=lambda _: None)
    assert all(b["processed"] == 32 for b in report["blocks"])


def test_complete_artifact_tampering_is_rejected_without_overwrite(tmp_path):
    f = panel(days=173, assets=1)
    exact.analyze(f, tmp_path / "run", bootstrap_reps=16, batch_reps=7,
                  checkpoint_reps=16, progress_callback=lambda _: None)
    target = next((tmp_path / "run" / "shards").rglob("*.npy"))
    original = target.read_bytes()
    target.write_bytes(original + b"tampered")
    with pytest.raises(ValueError, match="artifact changed"):
        exact.analyze(f, tmp_path / "run", bootstrap_reps=16, batch_reps=7,
                      checkpoint_reps=16, progress_callback=lambda _: None)
    assert target.read_bytes() == original + b"tampered"


def test_parity_only_produces_no_statistical_claim(tmp_path):
    report = exact.validate_parity(panel(), tmp_path / "parity", batch_reps=127)
    assert report["status"] == "PASS"
    assert report["mode"] == "PARITY_ONLY_NO_INFERENCE"
    assert report["maximum_absolute_error"] < 1e-12
    assert not (tmp_path / "parity" / "intervals.csv").exists()
    assert len(pd.read_csv(tmp_path / "parity" / "reference-parity.csv")) == 92
