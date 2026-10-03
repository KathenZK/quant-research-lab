#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Freeze M0293 before historical result execution, with no overwrite."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def freeze():
    now = datetime.now(timezone.utc).isoformat()
    spec = json.loads((ROOT.parent / "M0286/specs/M0286-first-replay.json").read_text())
    spec.update(
        record_id="M0293",
        name="ReinforcedAverageStrategy EMA8/21 with closed48h SMA50",
        family="PUBLIC-M0293-REINFORCED-AVERAGE",
        run_id="M0293-20261003-first-replay",
        variant_id="M0293-BTCUSDT-4H-EMA8-21-48H-SMA50-20261003",
        frozen_at_utc=now,
    )
    spec["source"].update(
        path="user_data/strategies/berlinguyinca/ReinforcedAverageStrategy.py",
        author="Gert Wohlgemuth",
    )
    spec["framework_reference"]["purpose"] = (
        "Fixed class defaults and qtpylib/technical reference semantics only; original author environment/external config unknown; not full Freqtrade engine."
    )
    spec["dependencies"]["technical_reference"] = (
        "1.5.3 / 8ce873e269bfbfe0d17d487a3e5163616ec0a872, exact util.py verified"
    )
    spec["parameters"] = {
        "ema_short": 8,
        "ema_long": 21,
        "resample_multiple": 12,
        "resample_minutes": 2880,
        "high_frame_sma": 50,
        "hyperopt": False,
        "external_parameter_file": False,
        "plot_only_bb": {"window": 20, "stds": 2, "used_for_signals": False},
    }
    spec["signals"] = {
        "indicator_price": "raw close; TA-Lib compatibility0/EMA unstable0",
        "entry": "EMA8[t]>EMA21[t] and EMA8[t-1]<=EMA21[t-1] and close[t]>closed48h_SMA50[t] and volume[t]>0",
        "exit": "EMA21[t]>EMA8[t] and EMA21[t-1]<=EMA8[t-1] and volume[t]>0",
        "resample": "technical1.5.3 pandas resample2880min labelleft originstart_day; openfirst/highmax/lowmin/closelast/volumesum, source dropna; fixed raw grid starts2022-12-01T00UTC",
        "merge": "higher interval open plus48h minus4h -> last constituent4h open; higher closed value usable after that native bar closes; forward-fill previously available values only, no backfill",
        "nan_policy": "EMA first8/21 SMA seeds; higherSMA50 first validnativeindex599; first413 evaluation bars have no SMA filter and cannot enter; keep fixed evaluation start, no future fill or prehistory extension",
        "first_high_frame_sma_available_at_utc": "2023-03-11T00:00:00Z",
        "warmup": "186 bars before evaluation; insufficient for50x48h SMA; partial beginning not fabricated; fixed input contains381 full48h groups",
        "collision": "Generic engine suppresses entry+exit collision; these two opposite crossovers cannot both hold; ROI/stop remain active",
        "availability": "closed native4h signals only; no warmup trading or pending warmup order",
    }
    spec["risk"] = {
        "minimal_roi": {"0": 0.5},
        "stoploss": -0.2,
        "trailing": False,
        "inactive_source_trailing_fields": {
            "trailing_stop_positive": 0.01,
            "trailing_stop_positive_offset": 0.02,
            "trailing_only_offset_is_reached": False,
        },
        "roi_threshold_formula": "entry_fill*(1+fee)*1.5/(1-fee)",
        "roi_slippage": "fee-inclusive threshold before adverse2bps sell slip; exact threshold fill net49.97%",
        "stop_threshold_formula": "entry_fill*0.8; fees and sell slip add to nominal20% price decline",
        "minute_roi_transition": "None: constant0minute50% threshold, no intra-bar expiry approximation required",
    }
    spec["execution"]["sequence"][2] = (
        "Resolve constant ROI50% threshold; stop and ROI active independently of signal state"
    )
    spec["input"]["data_qa_sha256"] = sha(ROOT / "specs/data-qa.json")
    spec["input"]["input_use"] = (
        "Offline reuse and raw-to-canonical revalidation of existing authorized snapshot;0 new market requests"
    )
    spec["exposure"]["source_of_assignment"] = (
        "root batch006 claim2026-10-03T10:58:01Z,exclusiveM0293,Lab basea996696"
    )
    spec["exposure"]["window_previously_exposed"] = True
    spec["evidence_class"] = "historical_replay"
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
    target = ROOT / "specs/M0293-first-replay.json"
    with target.open("x") as stream:
        json.dump(spec, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    exposure = {
        "id": "M0293-20261003-first-replay-exposure",
        "kind": "exposure",
        "family": spec["family"],
        "window_start": spec["evaluation"]["start"],
        "window_end": spec["evaluation"]["end_exclusive"],
        "evidence_class": "historical_replay",
        "trial_count": 4,
        "control_configurations": 1,
        "historical_total_search_count": "UNKNOWN",
        "window_previously_exposed": True,
        "oos_claim": False,
        "selection_reason": "Coordinator exclusive assignment; original fixed signals and4 predeclared execution cases, no search; global query empty does not prove no prior exposure",
        "artifacts": {"specs/M0293-first-replay.json": sha(target)},
        "recorded_at_utc": now,
    }
    with (ROOT / "specs/exposure.json").open("x") as stream:
        json.dump(exposure, stream, indent=2)
        stream.write("\n")
    receipt = {
        "id": "M0293",
        "state": "FROZEN_NOT_EXECUTED",
        "frozen_at_utc": now,
        "protocol_sha256": sha(target),
        "input_sha256": spec["input"]["sha256"],
        "source_sha256": spec["source_hashes"]["M0293-ReinforcedAverageStrategy.py"],
        "strategy_ids": 1,
        "strategy_configurations": 4,
        "controls": 1,
        "strict_replication": False,
        "new_market_requests": 0,
    }
    with (ROOT / "artifacts/20261003-first-replay/freeze-receipt.json").open(
        "x"
    ) as stream:
        json.dump(receipt, stream, indent=2)
        stream.write("\n")
    return receipt


if __name__ == "__main__":
    print(json.dumps(freeze(), indent=2))
