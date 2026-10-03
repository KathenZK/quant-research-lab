#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Freeze first protocol before seeing historical replay; refuse overwrite."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def freeze():
    now = datetime.now(timezone.utc).isoformat()
    spec = json.loads((ROOT.parent / "M0256/specs/M0256-first-replay.json").read_text())
    spec.update(
        record_id="M0286",
        name="MultiMa TEMA alignment",
        family="PUBLIC-M0286-MULTIMA",
        run_id="M0286-20261003-first-replay",
        variant_id="M0286-BTCUSDT-4H-MULTIMA-LONG-20261003",
        frozen_at_utc=now,
    )
    spec["source"].update(
        path="user_data/strategies/MultiMa.py", author="@Mablue (Masoud Azizi)"
    )
    spec["framework_reference"]["purpose"] = (
        "Pinned Freqtrade parameter loading and signal-collision semantics; original author runtime unknown; not original execution engine."
    )
    spec["parameters"] = {
        "buy_ma_count": 4,
        "buy_ma_gap": 15,
        "sell_ma_count": 12,
        "sell_ma_gap": 68,
        "hyperopt": False,
        "loaded_from": "buy_params/sell_params override IntParameter defaults when load=True; no external JSON parameters",
        "unused_defaults": {
            "buy_ma_count": 7,
            "buy_ma_gap": 7,
            "sell_ma_count": 7,
            "sell_ma_gap": 94,
        },
    }
    spec["signals"] = {
        "indicator_price": "raw close",
        "formula": "TA-Lib TEMA(n)=3*EMA1(n)-3*EMA2(n)+EMA3(n); TA-Lib compatibility=0, EMA unstable=0",
        "entry": "TEMA30<TEMA15 AND TEMA45<TEMA30; range(4) skips 0/1 comparisons; no source volume filter",
        "exit": "OR over i=2..11: TEMA(68*i)>TEMA(68*(i-1)); no source volume filter",
        "consumed_periods": [15, 30, 45] + [68 * i for i in range(1, 12)],
        "source_full_indicator_grid": "860 unique count*gap>1 from count=0..19,gap=0..99; maximum1881; unused periods not needed for optimized port, compare original full grid to prove consumed columns and signals equal",
        "nan_policy": "TEMA lookback=3*(n-1); comparisons with NaN false; any finite sell comparison may trigger while longer comparisons are still NaN; no all-indicator readiness mask, no future fill",
        "warmup": "Only 186 pre-evaluation bars. TEMA45 ready at index132; first possible sell pair ready405; entire sell ladder ready2241. Evaluation starts fixed2023-01-01, never trimmed after seeing results. This is limited-history initialization, not infinite-history convergence proof.",
        "collision": "Source framework ignores simultaneous entry+exit for signal entry and signal exit; ROI/stop remain enabled",
        "availability": "only after complete native4h bar; warmup signals never carried into evaluation",
    }
    spec["risk"] = {
        "minimal_roi": {"0": 0.523, "1553": 0.123, "2332": 0.076, "3169": 0},
        "stoploss": -0.345,
        "trailing": False,
        "roi_threshold_formula": "entry_fill*(1+fee)*(1+active_roi)/(1-fee)",
        "roi_slippage": "threshold includes buy/sell fees, excludes sell slippage; adverse sell slip reduces realized net return",
        "stop_threshold_formula": "entry_fill*0.655; fees and sell slip add to nominal decline",
        "minute_roi_proxy": "Select largest ROI minute<=floor((effective current open-entry execution time)/60000); keep that threshold for this whole4h bar. Minute transitions inside bar apply only at next executable open,0..239min late. Never use later threshold with earlier high. Not exact Freqtrade intrabar timing.",
    }
    spec["execution"]["sequence"][0] = (
        "due closed-bar exit signal AND NOT entry signal at executable open"
    )
    spec["execution"]["sequence"][1] = (
        "flat entry signal AND NOT exit signal at executable open; never reenter after exit same bar"
    )
    spec["execution"]["sequence"].insert(
        2,
        "resolve active ROI minute threshold at executable open; risk retained even when signals collide",
    )
    spec["input"]["raw_manifest_sha256"] = (
        "19e169f12d08ec975af2da0936084122593581f84ab09290ecb67f02f9549573"
    )
    spec["input"]["data_qa_sha256"] = sha(ROOT / "specs/data-qa.json")
    spec["input"]["provider_clock_newer_current_bucket"] = (
        "Not re-requested; predecessor HTTP451 respected; no bypass; strict finality still not established"
    )
    spec["exposure"]["source_of_assignment"] = (
        "Coordinator parallel batch005, exclusive M0286 only, Lab main8661e314"
    )
    spec["exposure"]["window_previously_exposed"] = True
    spec["source_hashes"] = {
        x["filename"]: x["sha256"]
        for x in json.loads((ROOT / "specs/source-manifest.json").read_text())["files"]
    }
    spec["code_hashes"] = {
        str(p.relative_to(ROOT)): sha(p)
        for p in sorted((ROOT / "scripts").glob("*.py"))
    }
    spec["supporting_evidence_hashes"] = {
        str(p.relative_to(ROOT)): sha(p)
        for p in sorted((ROOT / "specs").glob("*"))
        if p.is_file()
    }
    path = ROOT / "specs/M0286-first-replay.json"
    with path.open("x") as stream:
        json.dump(spec, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    receipt = {
        "id": "M0286",
        "state": "FROZEN_NOT_EXECUTED",
        "frozen_at_utc": now,
        "protocol_sha256": sha(path),
        "input_sha256": spec["input"]["sha256"],
        "strategy_ids": 1,
        "strategy_configurations": 4,
        "controls": 1,
        "strict_replication": False,
    }
    with (ROOT / "artifacts/20261003-first-replay/freeze-receipt.json").open(
        "x"
    ) as stream:
        json.dump(receipt, stream, indent=2)
        stream.write("\n")
    return receipt


if __name__ == "__main__":
    print(json.dumps(freeze(), indent=2))
