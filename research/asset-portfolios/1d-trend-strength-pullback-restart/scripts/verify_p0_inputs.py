"""只读核验本家族P0返回帧、请求/回执、连续过去窗口和当前源码pin。"""

from pathlib import Path
import datetime as dt
import hashlib
import json

import numpy as np
import pandas as pd


FAMILY = Path(__file__).resolve().parents[1]
LAB = Path("/Users/ZK/OpenCode/quant-strategy-lab")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path):
    return json.loads(path.read_text())


def main():
    run = FAMILY / "artifacts/p0-inputs"
    output = FAMILY / "artifacts/p0-independent-verification.json"
    if output.exists():
        raise FileExistsError(output)
    summary = load(run / "summary.json")
    started = load(run / "started.json")
    manifest = load(run / "frame-manifest.json")
    request = load(FAMILY / "specs/input-request.json")
    pins = load(FAMILY / "specs/source-pins.json")
    universe = load(FAMILY / "specs/observed-universe.json")
    checked = {}

    def check(path, expected, root=FAMILY):
        path = path.resolve()
        assert path.is_relative_to(root.resolve()), f"path escaped: {path}"
        actual = sha(path)
        assert actual == expected, f"hash differs: {path}"
        checked[str(path)] = actual

    assert summary["status"] == "PRICE_INPUTS_READY_WITH_RECORDED_EXCLUSIONS"
    assert summary["requested_symbols"] == 652 and summary["startup_failed_symbols"] == 0
    assert summary["source_pins_unchanged"] and not summary["changed_family_files"]
    for flag in ("signals_computed", "labels_computed", "old_family_frames_read", "data_lake_written"):
        assert summary[flag] is False
    check(run / "frame-manifest.json", summary["frame_manifest_sha256"])
    check(run / "coverage.csv", summary["coverage_sha256"])
    check(run / "segments.csv", summary["segments_sha256"])
    for name, digest in started["family_files_sha256"].items():
        check(FAMILY / name, digest)
    for name, digest in pins["files"].items():
        check(LAB / name, digest, root=LAB)
    assert started["verified_src_files"] == {
        name: digest for name, digest in pins["files"].items() if name.startswith("src/")
    }
    assert request["symbols"] == universe["included"]
    assert len(request["symbols"]) == len(set(request["symbols"])) == 652
    coverage = pd.read_csv(run / "coverage.csv")
    assert coverage.symbol.tolist() == request["symbols"]
    assert coverage.status.value_counts().to_dict() == summary["status_counts"]
    assert set(coverage.loc[coverage.frame_saved, "symbol"]) == set(manifest)
    assert len(manifest) == summary["frames"]
    total_rows = total_eligible = total_past = total_segments = 0
    for symbol, entry in sorted(manifest.items()):
        path = (run / entry["path"]).resolve()
        assert path.is_relative_to(run)
        check(path, entry["sha256"])
        for key in ("request", "startup_report"):
            check(run / entry[f"{key}_path"], entry[f"{key}_sha256"])
        call_request = load(run / entry["request_path"])
        receipt = load(run / entry["startup_report_path"])
        assert receipt["request"] == call_request
        assert receipt["status"] == "PRICE_DIAGNOSTIC_INPUTS_VERIFIED"
        assert call_request["backward_bars"] == 60 and call_request["forward_bars"] == 0
        assert call_request["start"] == request["start"] and call_request["end"] == request["end"]
        assert symbol in call_request["symbols"]
        frame = pd.read_pickle(path, compression="gzip")
        digest = hashlib.sha256(pd.util.hash_pandas_object(frame, index=True).values.tobytes()).hexdigest()
        assert digest == entry["dataframe_hash"]
        assert frame.symbol.eq(symbol).all() and len(frame) == entry["rows"]
        assert frame.ts.is_monotonic_increasing and not frame.ts.duplicated().any()
        assert frame.ts.ge(pd.Timestamp(request["start"])).all()
        assert (frame.ts + pd.Timedelta(days=1)).le(pd.Timestamp(request["end"])).all()
        past = frame.eligible & (frame.groupby("research_segment_id", sort=False).cumcount() + 1).ge(60)
        np.testing.assert_array_equal(past.to_numpy(bool), frame.research_window_valid.to_numpy(bool))
        assert int(past.sum()) == entry["complete_past_windows"]
        for _, segment in frame.loc[frame.eligible].groupby("research_segment_id", sort=False):
            assert segment.ts.diff().iloc[1:].eq(pd.Timedelta(days=1)).all()
        total_rows += len(frame)
        total_eligible += int(frame.eligible.sum())
        total_past += int(past.sum())
        total_segments += frame.research_segment_id.nunique()
    result = {
        "utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "P0_RECEIPTS_FRAMES_PAST_WINDOWS_AND_CURRENT_PINS_VERIFIED",
        "requested_symbols": 652, "returned_symbols": len(manifest),
        "rows": total_rows, "eligible_rows": total_eligible,
        "past60_windows": total_past, "eligible_segments": total_segments,
        "source_pins_verified": len(pins["files"]),
        "file_hashes_checked": len(checked),
        "scope": "all saved new-family P0 frames; no new signals, labels or strategy results",
        "funding_window_verified": False, "pit_universe_proven": False,
        "tradability_proven": False, "signals_computed": False, "labels_computed": False,
        "script_sha256": sha(Path(__file__)), "checked_files": checked,
    }
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "checked_files"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
