"""Immutable, bounded public capture; reviewed rights are an input, never a grant.

The capture is raw_unaccepted until the independent offline core audit passes.
HTTP failures and incomplete captures remain on disk and cannot be resumed by
silently replacing bytes. Start a new snapshot to retry a failed capture.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import time

import pandas as pd
import requests

from strategy_lab.knowledge.market_contract import read_contract, reviewed_rights, sha
from strategy_lab.knowledge.candidates import digest


def windows(start, end, step_ms, bars=64):
    """Disjoint [start,end) windows, independent of response length or cap."""
    if end <= start or step_ms <= 0 or bars < 1 or (end - start) % step_ms:
        raise ValueError("Invalid aligned requested grid")
    while start < end:
        stop = min(end, start + bars * step_ms)
        yield start, stop
        start = stop


def decode(raw):
    rows = json.loads(raw)
    if not isinstance(rows, list) or any(
        not isinstance(r, list) or len(r) != 6 for r in rows
    ):
        raise ValueError("Unexpected six-column native OHLCV schema")
    return rows


def partition(get_page, start, end, step):
    """Bisect truncated windows, preserving every parent and leaf response.

    Never use a response-derived cursor (silent caps cannot skip time). At one
    bar, failure is terminal. An exact edge observation may be excluded with
    an explicit audit record; internal duplicates/disorder are never repaired.
    """
    meta, raw = get_page(start, end)
    rows = decode(raw)
    times = [r[0] for r in rows]
    if len(times) != len(set(times)) or (
        times != sorted(times) and times != sorted(times, reverse=True)
    ):
        raise ValueError("Duplicated/disordered native page")
    if any(t < start - step or t > end for t in times):
        raise ValueError("Provider ignored request bounds or repeated a page")
    selected = [r for r in rows if start <= r[0] < end]
    excluded = [r[0] for r in rows if not start <= r[0] < end]
    if any(t not in {start - step, end} for t in excluded):
        raise ValueError("Unexpected out-of-window observation")
    if sorted(r[0] for r in selected) == list(range(start, end, step)):
        meta.update(
            requested_start_ms=start,
            requested_end_ms=end,
            excluded_boundary_timestamps=excluded,
        )
        return [meta], []
    if end - start <= step:
        raise ValueError("Native historical bar absent; no synthetic fill permitted")
    middle = start + ((end - start) // step // 2) * step
    left, lp = partition(get_page, start, middle, step)
    right, rp = partition(get_page, middle, end, step)
    return left + right, [meta] + lp + rp


def save_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def request(session, url, params, output, name, pause):
    """Persist every response before interpretation; honor rate-limit backoff."""
    for attempt in range(3):
        time.sleep(pause)
        before = datetime.now(timezone.utc).isoformat()
        response = session.get(
            url, params=params, timeout=45, headers={"Cache-Control": "no-cache"}
        )
        after = datetime.now(timezone.utc).isoformat()
        raw_path = output / f"{name}-attempt{attempt}.json"
        raw_path.write_bytes(response.content)
        metadata = dict(
            path=raw_path.name,
            sha256=sha(raw_path),
            url=response.url,
            params=params,
            http_status=response.status_code,
            fetched_start=before,
            fetched_at=after,
            headers=dict(response.headers),
        )
        save_json(output / f"{name}-attempt{attempt}.request.json", metadata)
        if response.status_code == 429 and attempt < 2:
            # A bounded failure is preferable to changing IP/account or bypassing limits.
            wait = response.headers.get("Retry-After", "60")
            seconds = float(wait) if wait.isdigit() else 60.0
            if seconds > 300:
                response.raise_for_status()
            print(
                json.dumps(dict(event="rate_limit", wait_seconds=max(60, seconds))),
                flush=True,
            )
            time.sleep(max(60, seconds))
            continue
        response.raise_for_status()
        return metadata, response.content
    raise RuntimeError("HTTP retry budget exhausted")


def fetch(contract_path, rights_path, output, proxy=None, pause=10):
    contract_path, rights_path, output = map(Path, (contract_path, rights_path, output))
    c = read_contract(contract_path)
    if (c["provider"], c["source"]) != ("bit2me", "bit2me_public_rest"):
        raise ValueError("No reviewed native decoder for this provider")
    rights = reviewed_rights(
        rights_path,
        provider=c["provider"],
        source=c["source"],
        use_context=c["use_context"],
    )
    evidence = Path(rights["evidence_path"])
    if evidence.is_absolute() or ".." in evidence.parts:
        raise ValueError("Rights source artifact must be adjacent")
    output.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(contract_path, output / "contract.json")
    shutil.copyfile(Path(__file__), output / "capture-code.py")
    shutil.copyfile(rights_path, output / "rights.json")
    (output / evidence).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(rights_path.parent / evidence, output / evidence)
    step = {"1d": 86400000, "4h": 14400000}[c["frequency"]]
    start, end = (
        int(pd.Timestamp(c[k]).timestamp() * 1000)
        for k in ("requested_start", "requested_end")
    )
    plan = list(windows(start, end, step))
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
        schema_version="paged-market-capture-v1",
        contract_sha256=sha(contract_path),
        rights_id=rights["rights_id"],
        rights_sha256=digest(rights),
        rights_path="rights.json",
        capture_code_sha256=sha(Path(__file__)),
        decoder="native-timestamp-ohlcv-v1",
        page_plan=plan,
        interval_ms=step,
        page_bar_limit=64,
        query_limit=70,
        raw_files=[],
        identity_files=[],
        observation_files=[],
        subdivision_files=[],
        real_market_data=True,
        acceptance_status="raw_unaccepted",
        status="CAPTURING",
        finality_policy="closed-grid-newer-bar-stable-recapture-v1",
        boundary_policy="request-start-minus-1ms-audited-edge-exclusion-v1",
    )
    save_json(output / "capture-plan.json", manifest)
    session = requests.Session()
    session.trust_env = False
    session.proxies = {"https": proxy} if proxy else {}
    base = "https://gateway.bit2me.com/v1/trading"
    try:
        identity, _ = request(
            session,
            base + "/market-config",
            {"symbol": c["symbols"][0]},
            output,
            "market-identity",
            pause,
        )
        manifest["identity_files"].append(identity)
        for capture_pass in (0, 1):
            counter = 0

            def get_page(lo, hi):
                nonlocal counter
                params = dict(
                    symbol=c["symbols"][0],
                    interval=step // 60000,
                    startTime=lo - 1,
                    endTime=hi - 1,
                    limit=70,
                )
                metadata, raw = request(
                    session,
                    base + "/candle",
                    params,
                    output,
                    f"pass{capture_pass}-request{counter:03d}",
                    pause,
                )
                counter += 1
                rows = decode(raw)
                metadata.update(
                    capture_pass=capture_pass,
                    first_timestamp=rows[0][0] if rows else None,
                    last_timestamp=rows[-1][0] if rows else None,
                    record_count=len(rows),
                )
                return metadata, raw

            for lo, hi in plan:
                leaves, parents = partition(get_page, lo, hi, step)
                for metadata in leaves:
                    metadata["page"] = sum(
                        x["capture_pass"] == capture_pass for x in manifest["raw_files"]
                    )
                    manifest["raw_files"].append(metadata)
                manifest["subdivision_files"].extend(parents)
                save_json(output / "capture-progress.json", manifest)
                print(
                    json.dumps(
                        dict(
                            event="partition",
                            capture_pass=capture_pass,
                            start_ms=lo,
                            expected=(hi - lo) // step,
                            accepted_pages=len(leaves),
                            subdivided_pages=len(parents),
                        )
                    ),
                    flush=True,
                )
            now = int(datetime.now(timezone.utc).timestamp() * 1000)
            bucket = now // step * step
            params = dict(
                symbol=c["symbols"][0],
                interval=step // 60000,
                startTime=bucket - step * 2,
                endTime=now,
                limit=4,
            )
            meta, raw = request(
                session,
                base + "/candle",
                params,
                output,
                f"contemporary-pass{capture_pass}",
                pause,
            )
            decode(raw)
            manifest["observation_files"].append(meta)
        manifest.update(
            status="CAPTURED",
            page_count=len(manifest["raw_files"]),
            raw_dataset_sha256=digest([r["sha256"] for r in manifest["raw_files"]]),
            captured_at=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as exc:
        manifest.update(status="FAILED", failure=f"{type(exc).__name__}: {exc}")
        save_json(output / "capture.json", manifest)
        raise
    save_json(output / "capture.json", manifest)
    return output / "capture.json"


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--contract", required=True)
    p.add_argument("--rights", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--proxy")
    p.add_argument("--pause", type=float, default=10)
    a = p.parse_args()
    print(fetch(a.contract, a.rights, a.output, a.proxy, a.pause))
