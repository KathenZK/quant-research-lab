"""Fresh startup for a fixed, already-revealed comparison; preserve prior inputs."""
from pathlib import Path
import hashlib
import json
import shutil
import pandas as pd
from strategy_lab.data.research_bundle import require_research_startup, read_json

ROOT = Path(__file__).resolve().parents[4]
FAMILY = Path(__file__).resolve().parents[1]
OUT = FAMILY / "artifacts/iteration_comparison_20260911/inputs"
OLD = FAMILY / "artifacts/inputs"

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n")

def load_prices(request):
    return require_research_startup(request, project_root=ROOT, data_root=ROOT / "data")

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    old = read_json(OLD / "manifest.json")
    records = {}
    for tf in ("15m", "1h"):
        req = read_json(FAMILY / f"specs/price_request_{tf}.json")
        save(OUT / f"request_{tf}.json", req)
        print(f"STARTUP {tf}", flush=True)
        inputs = load_prices(req)
        save(OUT / f"startup_{tf}.json", inputs.report)
        for symbol, original in inputs.prices.items():
            asset = symbol.split("/")[0]
            frame = original.copy()
            for col in frame.columns:
                if isinstance(frame[col].dtype, pd.ArrowDtype):
                    if col == "ts":
                        frame[col] = pd.to_datetime(frame[col].tolist(), utc=True)
                    elif pd.api.types.is_numeric_dtype(frame[col].dtype):
                        frame[col] = frame[col].astype("float64")
            assert frame.research_window_valid.all() and frame.research_segment_id.nunique() == 1
            name = f"{asset}_{tf}.parquet"
            assert sha(OLD / name) == old["files"][name]["sha256"]
            pd.testing.assert_frame_equal(frame, pd.read_parquet(OLD / name), check_exact=True)
            frame.to_parquet(OUT / name, index=False)
            records[name] = {"sha256": sha(OUT / name), "rows": len(frame), "matches_previous_values": True,
                             "origin": "current_require_research_startup_returned_frame"}
        print(f"SAVED {tf}", flush=True)
    for name, meta in old["files"].items():
        if "funding_" not in name:
            continue
        assert sha(OLD / name) == meta["sha256"]
        shutil.copyfile(OLD / name, OUT / name)
        records[name] = {**meta, "origin": str((OLD / name).relative_to(ROOT)),
                         "interpretation": "pinned_observed_events_not_verified_full_funding"}
    save(OUT / "manifest.json", {"created_for": "iteration_comparison_20260911", "files": records,
        "bundle_path": old["bundle_path"], "bundle_sha256": old["bundle_sha256"],
        "funding_audit": old["funding_audit"], "funding_window_verified": False,
        "previous_manifest_sha256": sha(OLD / "manifest.json"),
        "end_exclusive": "2026-09-05T15:00:00Z", "status": "PRICE_DIAGNOSTIC_INPUTS_VERIFIED"})
    print(json.dumps({"status": "PASS", "files": len(records)}, ensure_ascii=False), flush=True)

if __name__ == "__main__":
    main()
