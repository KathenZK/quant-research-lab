from copy import deepcopy
import json
import zipfile

import pytest

from strategy_lab.research.evidence import create_bundle, local_backup, restore_backup, sha256, verify_bundle
from strategy_lab.research.exposure import append_record, overlaps, read_ledger, observation_coverage


def make_bundle(tmp_path):
    source = tmp_path / "source"
    source.write_text("actual evidence")
    entries = [{"source": str(source), "path": role + ".txt", "role": role, "sha256": sha256(source)}
               for role in ["code", "spec", "input", "reference_output", "environment"]]
    root = tmp_path / "bundle"
    create_bundle(root, entries, metadata={"model_kind": "rule"})
    return root, entries


def test_local_backup_restore_and_corruption(tmp_path):
    root, _ = make_bundle(tmp_path)
    backup = tmp_path / "backup.zip"
    digest = local_backup(root, backup)
    restored = tmp_path / "elsewhere"
    assert restore_backup(backup, restored, expected_sha256=digest) == verify_bundle(root)
    with pytest.raises(FileExistsError):
        restore_backup(backup, restored, expected_sha256=digest)
    (restored / "input.txt").write_text("changed")
    with pytest.raises(ValueError):
        verify_bundle(restored)
    backup.write_bytes(backup.read_bytes() + b"corrupted")
    with pytest.raises(ValueError, match="archive SHA"):
        restore_backup(backup, tmp_path / "bad", expected_sha256=digest)


def test_ml_package_requires_actual_model_and_preprocessing(tmp_path):
    _, entries = make_bundle(tmp_path)
    with pytest.raises(ValueError, match="mandatory"):
        create_bundle(tmp_path / "ml", entries, metadata={"model_kind": "trained"})
    bad = deepcopy(entries)
    bad[0]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="source SHA"):
        create_bundle(tmp_path / "bad", bad, metadata={"model_kind": "rule"})
    assert not (tmp_path / "bad").exists()


@pytest.mark.parametrize("name", ["../outside", "/absolute", "a/../../escape", "a\\escape"])
def test_unsafe_archive_cannot_escape(tmp_path, name):
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr(name, "bad")
    with pytest.raises(ValueError):
        restore_backup(archive, tmp_path / "restore", expected_sha256=sha256(archive))
    assert not (tmp_path / "restore").exists()


def exposure(id="trial-1"):
    return {"kind": "exposure", "id": id, "family": "frozen-family", "window_start": "2025-01-01T00:00:00Z",
            "window_end": "2026-01-01T00:00:00Z", "evidence_class": "historical_replay",
            "trial_count": None, "trial_count_unknown_reason": "older searches not fully retained",
            "selection_reason": "restore predetermined candidate", "artifacts": {"spec": "a" * 64}}


def test_ledger_append_duplicate_corruption_and_overlap(tmp_path):
    path = tmp_path / "ledger.jsonl"
    append_record(path, exposure())
    append_record(path, exposure("trial-2"))
    records = read_ledger(path)
    assert len(records) == 2 and records[1]["previous_sha256"] == records[0]["sha256"]
    assert len(overlaps(records, start="2025-06-01T00:00:00Z", end="2027-01-01T00:00:00Z")) == 2
    assert overlaps(records, start="2026-01-01T00:00:00Z", end="2027-01-01T00:00:00Z") == []
    with pytest.raises(ValueError, match="duplicate"):
        append_record(path, exposure())
    path.write_text(path.read_text().replace("frozen-family", "edited-family", 1))
    with pytest.raises(ValueError, match="chain"):
        append_record(path, exposure("trial-3"))


def test_truncated_tail_rejected(tmp_path):
    path = tmp_path / "ledger.jsonl"
    append_record(path, exposure())
    path.write_text(path.read_text().rstrip())
    with pytest.raises(ValueError, match="truncated"):
        read_ledger(path)


def test_unknown_trials_cannot_be_silently_filled(tmp_path):
    data = exposure()
    del data["trial_count_unknown_reason"]
    with pytest.raises(ValueError, match="unknown"):
        append_record(tmp_path / "x", data)


def test_late_and_backfill_observation_never_gain_prospective_credit(tmp_path):
    data = {"id": "node", "kind": "observation", "family": "f", "decision_at": "2020-01-01T00:00:00Z",
            "deadline_at": "2020-01-01T00:10:00Z", "completed_at": "2020-01-01T00:05:00Z",
            "config_sha256": "a" * 64, "code_sha256": "b" * 64, "status": "backfill_diagnostic",
            "reason": "replayed later", "input_available_at": "2019-12-31T23:59:00Z",
            "execution_link": None, "account_link": None}
    path = tmp_path / "observations.jsonl"
    record = append_record(path, data)
    assert record["data"]["late"] and not record["data"]["prospective_credit"]
    data["id"] = "duplicate-node"
    with pytest.raises(ValueError, match="duplicate observation"):
        append_record(path, data)
    future = deepcopy(data)
    future["input_available_at"] = "2020-01-02T00:00:00Z"
    with pytest.raises(ValueError, match="future input"):
        append_record(tmp_path / "future", future)
    assert json.loads(path.read_text())["data"]["status"] == "backfill_diagnostic"


def test_observation_coverage_counts_absent_nodes():
    report = observation_coverage([], family="f", start="2020-01-01T00:00:00Z",
                                  end="2020-01-04T00:00:00Z", as_of="2020-01-02T12:00:00Z", cadence_hours=24)
    assert report["expected_elapsed_nodes"] == report["missing_records"] == 2
    assert report["timely_nodes"] == report["fully_linked_timely_nodes"] == 0
