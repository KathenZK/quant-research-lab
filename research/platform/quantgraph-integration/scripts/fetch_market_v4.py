"""Contract-pinned private Bit2Me capture. Never creates or grants rights."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys
import urllib.parse
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "src"))
from strategy_lab.knowledge.market_contract import (  # noqa: E402
    read_contract,
    reviewed_rights,
    sha,
    check_contract_binding,
)
from strategy_lab.knowledge.candidates import digest  # noqa: E402
from strategy_lab.data.market_coverage import MarketCoverageValidator  # noqa: E402
from fetch_market_v3 import capture  # noqa: E402


def fetch(contract_path, rights_path, output, proxy=None):
    contract_path, rights_path, output = map(Path, (contract_path, rights_path, output))
    c = read_contract(contract_path)
    if c["provider"] != "bit2me" or c["source"] != "bit2me_public_rest":
        raise ValueError("Unsupported provider: no invented normalization")
    rights = reviewed_rights(
        rights_path,
        provider=c["provider"],
        source=c["source"],
        use_context=c["use_context"],
    )
    output.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(contract_path, output / "contract.json")
    pinned = sha(output / "contract.json")
    shutil.copyfile(rights_path, output / "rights.json")
    evidence_name = Path(rights["evidence_path"])
    if evidence_name.is_absolute() or ".." in evidence_name.parts:
        raise ValueError("Rights evidence must be an adjacent relative artifact")
    (output / evidence_name).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(rights_path.parent / evidence_name, output / evidence_name)
    session = requests.Session()
    session.trust_env = False
    session.proxies = {"https": proxy} if proxy else {}
    # A single request preserves provider-native multiplicity and order. If
    # its bounded history cannot cover the frozen window, coverage is PARTIAL.
    # No truncating the contract, paging overlap collapse or synthetic fills.
    query = dict(
        symbol=c["symbols"][0],
        interval={"1d": 1440, "4h": 240}[c["frequency"]],
        startTime=int(pd.Timestamp(c["requested_start"]).timestamp() * 1000) - 1,
        endTime=int(pd.Timestamp(c["requested_end"]).timestamp() * 1000) - 1,
        limit=1000,
    )
    url = "https://gateway.bit2me.com/v1/trading/candle?" + urllib.parse.urlencode(
        query
    )
    raw = capture(session, url, output, "market-response.json")
    rows = json.loads(raw)
    if not isinstance(rows, list) or any(
        not isinstance(r, list) or len(r) != 6 for r in rows
    ):
        raise ValueError("Unexpected native candle schema")
    frame = pd.DataFrame(
        rows, columns=["timestamp", "open", "high", "low", "close", "volume"]
    )
    frame["ts"] = pd.to_datetime(frame.timestamp, unit="ms", utc=True)
    frame = frame[
        (frame.ts >= pd.Timestamp(c["requested_start"]))
        & (frame.ts < pd.Timestamp(c["requested_end"]))
    ]
    frame.drop(columns="timestamp").to_json(
        output / "observations.jsonl",
        orient="records",
        lines=True,
        date_format="iso",
        double_precision=15,
    )
    saved = pd.read_json(output / "observations.jsonl", lines=True, convert_dates=False)
    saved["ts"] = pd.to_datetime(saved["ts"], utc=True)
    coverage = MarketCoverageValidator().validate(
        saved.ts,
        requested_start=c["requested_start"],
        requested_end=c["requested_end"],
        frequency=c["frequency"],
        calendar=c["data_requirements"]["calendar"],
    )
    manifest = {
        k: c[k]
        for k in (
            "provider",
            "source",
            "symbols",
            "frequency",
            "requested_start",
            "requested_end",
        )
    }
    manifest.update(
        schema_version="market-dataset-v4",
        dataset_version=output.name,
        downloaded_at=datetime.now(timezone.utc).isoformat(),
        timezone=c["data_requirements"]["timezone"],
        calendar=c["data_requirements"]["calendar"],
        adjustment_method=c["data_requirements"]["adjustment"],
        contract_sha256=pinned,
        rights_id=rights["rights_id"],
        rights_sha256=digest(rights),
        rights_path="rights.json",
        raw_files=[
            dict(
                path="market-response.json",
                sha256=sha(output / "market-response.json"),
                url=url,
            )
        ],
        dataset_path="observations.jsonl",
        dataset_sha256=sha(output / "observations.jsonl"),
        real_market_data=True,
        acceptance_status="raw_unaccepted",
        missing_native_fields=["trade_count", "quote_volume", "vwap", "is_closed"],
        source_identity_verified=False,
        closure_evidence_status="UNVERIFIED",
        coverage=coverage,
        capture_code_sha256=sha(Path(__file__)),
        limitations=[
            "Provider native OHLCV response lacks mandatory native count and closed-state fields",
            "No trusted or normalized dataset is written; observation decoding only",
        ],
    )
    check_contract_binding(contract_path, manifest)
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    )
    return output / "manifest.json"


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--contract", type=Path, required=True)
    p.add_argument("--rights", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--proxy")
    a = p.parse_args()
    print(fetch(a.contract, a.rights, a.output, a.proxy))
