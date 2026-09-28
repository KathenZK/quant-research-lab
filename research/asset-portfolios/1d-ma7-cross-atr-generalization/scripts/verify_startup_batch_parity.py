"""Live input-only equivalence check of original and batched startup paths."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import pandas as pd

LAB = Path(__file__).resolve().parents[4]
FAMILY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB / "src"))

from strategy_lab.data.research_bundle import require_research_startup  # noqa: E402
from startup_batch import create_startup_context, require_research_startup_batch  # noqa: E402


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_original(request):
    return require_research_startup(request, project_root=LAB, data_root=LAB / "data")


def main():
    output = FAMILY / "artifacts/startup_batch_parity_20260909.json"
    if output.exists():
        raise FileExistsError(output)
    plan = json.loads((FAMILY / "specs/input-plan-v3-20260909.json").read_text())
    window = plan["windows"][0]
    good = ["BTC/USDT:USDT", "HYPE/USDT:USDT", "0G/USDT:USDT"]
    bad = "AGIX/USDT:USDT"
    context = create_startup_context(project_root=LAB, data_root=LAB / "data",
        pin=plan["bundle_pin"], symbols=good+[bad], start=window["input_start"], end=window["end"])
    results = []
    for tf, backward in (("1d", 29), ("1h", 1)):
        request = {"schema_version": 1, **plan["bundle_pin"], "mode": "price_diagnostic",
                   "timeframe": tf, "symbols": good, "start": window["input_start"], "end": window["end"],
                   "gap_policy": "contiguous_segments", "asset_policy": "crypto_only",
                   "backward_bars": backward, "forward_bars": 0}
        print(f"PARITY_ORIGINAL {tf}", flush=True)
        original = load_original(request)
        batched = require_research_startup_batch(request, context=context)
        if batched.failures:
            raise ValueError("Expected usable parity assets rejected")
        for symbol in good:
            old, new = original.prices[symbol], batched.prices[symbol]
            pd.testing.assert_frame_equal(old, new, check_exact=True, check_dtype=True,
                                          check_index_type=True, check_column_type=True)
            if original.report["symbols"][symbol] != batched.report["symbols"][symbol]:
                raise ValueError("Original and new symbol statistics differ")
            results.append({"symbol": symbol, "timeframe": tf, "rows": len(new),
                            "columns": list(new.columns), "all_columns_values_dtypes_masks_equal": True,
                            "dataframe_sha256": hashlib.sha256(pd.util.hash_pandas_object(new, index=True).values.tobytes()).hexdigest(),
                            "first_open": new.ts.min().isoformat(), "last_open": new.ts.max().isoformat()})
            print(f"PARITY_PASS {tf} {symbol} rows={len(new)}", flush=True)
    bad_request = {**request, "timeframe": "1d", "backward_bars": 29, "symbols": [bad]}
    try:
        load_original(bad_request)
    except ValueError as exc:
        old_error = str(exc)
    else:
        raise ValueError("Expected original unavailable-window error did not occur")
    new_bad = require_research_startup_batch(bad_request, context=context)
    if old_error != f"{bad}: no complete eligible feature/label window" or new_bad.failures != {bad: old_error} or new_bad.prices:
        raise ValueError("Original and batch failure semantics differ")
    report = {"status": "PASS", "candidate_results_computed": False, "compared_frames": len(results),
              "results": results, "failure_parity": {"symbol": bad, "original_error": old_error,
              "new_error": new_bad.failures[bad], "equal": True},
              "source_sha256": {name: sha(FAMILY / "scripts" / name)
                                 for name in ("startup_batch.py", "verify_startup_batch_parity.py")},
              "context": context.receipt()}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str, allow_nan=False) + "\n")
    print("PARITY_ALL_PASS", flush=True)


if __name__ == "__main__":
    main()
