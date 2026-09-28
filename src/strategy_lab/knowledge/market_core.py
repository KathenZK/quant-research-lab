"""Offline, fail-closed OHLCV-core acceptance. No network or rights creation.

Optional native fields never substitute for provenance, bar closure, full
coverage, or the union of core and strategy requirements. The legacy OHLCV
validator remains unchanged. Published schemas are owned by QuantGraph.
"""

import base64
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urlparse

import numpy as np
import pandas as pd

from strategy_lab.data.market_coverage import MarketCoverageValidator
from .candidates import digest
from .market_contract import read_contract, reviewed_rights, sha, validate_schema

PROFILE = "TRUSTED_OHLCV_CORE_V1"
OPTIONAL = ("trade_count", "quote_volume", "vwap", "taker_volume")
CHECKS = (
    "source_identity",
    "rights",
    "coverage",
    "schema_status",
    "calendar",
    "integrity",
    "hashes",
    "finality",
    "provenance",
)


def check_partition(path, contract, layer):
    parts = Path(path).resolve().parts
    expected = (
        "data",
        layer,
        "ohlcv",
        "exchange=" + contract["provider"],
        "market_type=" + contract["market_type"],
        "timeframe=" + contract["frequency"],
    )
    if not any(parts[i : i + len(expected)] == expected for i in range(len(parts))):
        raise ValueError("Dataset outside standard lake identity partition")
    if layer == "raw" and "source=" + contract["source"] not in parts:
        raise ValueError("Raw source partition mismatch")


def trust_status(checks):
    values = [checks[k] for k in CHECKS]
    if any(v not in {"PASS", "FAIL", "UNKNOWN"} for v in values):
        raise ValueError("Unknown audit result")
    return (
        "REJECTED"
        if "FAIL" in values
        else "TRUSTED"
        if set(values) == {"PASS"}
        else "DIAGNOSTIC_ONLY"
    )


def validate_core(frame, required_fields):
    required = {
        "ts",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "exchange",
        "source",
        "symbol",
        "market_type",
        "timeframe",
    } | set(required_fields)
    if (
        not required <= set(frame)
        or frame[list(required)].isna().any().any()
        or frame.empty
    ):
        raise ValueError("Core/strategy fields missing or null")
    for field in {"open", "high", "low", "close", "volume"} | (
        set(OPTIONAL) & set(frame)
    ):
        if not pd.api.types.is_numeric_dtype(
            frame[field]
        ) or pd.api.types.is_bool_dtype(frame[field]):
            raise ValueError("Non-numeric native field: " + field)
        if not np.isfinite(frame[field]).all():
            raise ValueError("Non-finite native field: " + field)
    if (frame[["open", "high", "low", "close"]] <= 0).any().any() or (
        frame.volume < 0
    ).any():
        raise ValueError("Invalid price/volume")
    if (
        (frame.high < frame[["open", "low", "close"]].max(axis=1))
        | (frame.low > frame[["open", "high", "close"]].min(axis=1))
    ).any():
        raise ValueError("Impossible OHLC envelope")
    for field in set(OPTIONAL) & set(frame):
        if (frame[field] < 0).any():
            raise ValueError("Negative optional quality field")
    if "trade_count" in frame and (frame.trade_count % 1 != 0).any():
        raise ValueError("Fractional trade count")
    if "vwap" in frame and ((frame.vwap < frame.low) | (frame.vwap > frame.high)).any():
        raise ValueError("VWAP outside candle range")
    if "taker_volume" in frame and (frame.taker_volume > frame.volume).any():
        raise ValueError("Taker base volume exceeds base volume")
    if (
        not isinstance(frame.ts.dtype, pd.DatetimeTZDtype)
        or str(frame.ts.dt.tz) != "UTC"
    ):
        raise ValueError("Explicit UTC timestamps required")


def ordered_page(rows, start, end, step):
    """Normalize monotone descending order only. Never sort disorder or dedupe."""
    if (
        not isinstance(rows, list)
        or not rows
        or any(not isinstance(r, list) or len(r) != 6 for r in rows)
    ):
        raise ValueError("Missing or malformed native page")
    times = [r[0] for r in rows]
    if any(isinstance(t, bool) or not isinstance(t, int) for t in times):
        raise ValueError("Non-integer native timestamp")
    if len(set(times)) != len(times):
        raise ValueError("Duplicate timestamp within page")
    if times == sorted(times, reverse=True):
        rows = list(reversed(rows))
        times = list(reversed(times))
    elif times != sorted(times):
        raise ValueError("Unordered provider page")
    if times != list(range(start, end, step)):
        raise ValueError("Page gap/cap/truncation/boundary mismatch")
    return rows


def _raw(root, meta):
    path = root / meta["path"]
    if sha(path) != meta["sha256"] or meta["http_status"] != 200:
        raise ValueError("Raw bytes hash/status mismatch")
    parsed = urlparse(meta["url"])
    actual = parse_qs(parsed.query)
    if parsed.scheme != "https" or actual != {
        k: [str(v)] for k, v in meta["params"].items()
    }:
        raise ValueError("Captured URL/parameters differ")
    return json.loads(path.read_bytes())


def _source_policy(root, capture, contract, rights):
    """Reviewed native mapping, pinned to the currently reviewed official spec.

    Provider differences are confined here. Core quality/finality rules below
    do not vary by provider or strategy and cannot be bypassed by this mapping.
    """
    if (contract["provider"], contract["source"], capture["decoder"]) != (
        "bit2me",
        "bit2me_public_rest",
        "native-timestamp-ohlcv-v1",
    ):
        raise ValueError("Unreviewed source decoder")
    bundle = json.loads((root / rights["evidence_path"]).read_text())
    docs = {}
    for doc in bundle["documents"]:
        raw = base64.b64decode(doc["body_base64"], validate=True)
        if (
            hashlib.sha256(raw).hexdigest() != doc["sha256"]
            or doc["http_status"] != 200
        ):
            raise ValueError("Supporting source byte identity mismatch")
        docs[doc["url"]] = (doc["sha256"], raw)
    url = "https://api.bit2me.com/openapi.json"
    spec_hash, spec_raw = docs[url]
    if spec_hash != "e7cca1e5a3f0781a527599618b6c87410239fd90d761268ae6105f760d88f013":
        raise ValueError("Provider specification revision needs independent review")
    spec = json.loads(spec_raw)
    if spec["servers"][0]["url"] != "https://gateway.bit2me.com":
        raise ValueError("Source server mismatch")
    if (
        contract["market_type"] != "spot"
        or contract["data_requirements"]["adjustment"] != "UNADJUSTED"
    ):
        raise ValueError("Unsupported source market/adjustment semantics")
    # Market-data agreement plus published trading-spot candle specification;
    # no source-library license is being used as permission for market data.
    if rights["license_url"] not in docs:
        raise ValueError("Official market-data terms bytes missing")
    if len(capture["identity_files"]) != 1:
        raise ValueError("Missing native market identity")
    m = capture["identity_files"][0]
    if not m["url"].startswith("https://gateway.bit2me.com/v1/trading/market-config?"):
        raise ValueError("Unexpected identity endpoint")
    identities = _raw(root, m)
    matches = [x for x in identities if x["symbol"] == contract["symbols"][0]]
    if len(matches) != 1 or not matches[0].get("id"):
        raise ValueError("Native market identifier missing or ambiguous")
    return matches[0]["id"]


def _finality(root, capture, end, step, rows_by_pass):
    if capture["finality_policy"] != "closed-grid-newer-bar-stable-recapture-v1":
        raise ValueError("Unreviewed finality policy")
    if rows_by_pass[0] != rows_by_pass[1]:
        raise ValueError("Historical revision between captures")
    if len(capture["observation_files"]) != 2:
        raise ValueError("Two independent newer-bar observations required")
    observations = []
    for meta in capture["observation_files"]:
        if not meta["url"].startswith("https://gateway.bit2me.com/v1/trading/candle?"):
            raise ValueError("Finality source endpoint differs")
        rows = _raw(root, meta)
        headers = {k.lower(): v for k, v in meta["headers"].items()}
        server = parsedate_to_datetime(headers["date"])
        fetched = pd.Timestamp(meta["fetched_at"])
        if (
            abs((fetched - server).total_seconds()) > 300
            or float(headers.get("age", 0)) > 300
        ):
            raise ValueError("Stale/unverifiable provider clock")
        server_ms = int(server.timestamp() * 1000)
        current_bucket = server_ms // step * step
        if (
            not rows
            or max(r[0] for r in rows) != current_bucket
            or end > current_bucket
        ):
            raise ValueError("Requested history includes current/unproven candle")
        if (
            meta["params"]["symbol"] != capture["symbols"][0]
            or meta["params"]["interval"] * 60000 != step
        ):
            raise ValueError("Finality observation identity differs")
        observations.append(fetched)
    first_end = max(
        pd.Timestamp(x["fetched_at"])
        for x in capture["raw_files"]
        if x["capture_pass"] == 0
    )
    second_start = min(
        pd.Timestamp(x["fetched_start"])
        for x in capture["raw_files"]
        if x["capture_pass"] == 1
    )
    if second_start <= first_end or observations[1] <= observations[0]:
        raise ValueError("Recapture is not independent in time")


def audit_capture(contract_path, capture_path):
    """Reconstruct from raw pages; no persisted PASS/TRUSTED flag is trusted."""
    capture_path = Path(capture_path)
    root = capture_path.parent
    c = read_contract(contract_path)
    check_partition(root, c, "raw")
    m = json.loads(capture_path.read_text())
    if m.get("real_market_data") is not True:
        raise ValueError("Capture is not real market data")
    if (
        c["data_requirements"]["dataset_profile"] != PROFILE
        or m["status"] != "CAPTURED"
    ):
        raise ValueError("Complete capture and explicit core profile required")
    if m["contract_sha256"] != sha(contract_path) or sha(root / "contract.json") != sha(
        contract_path
    ):
        raise ValueError("Frozen capture contract mismatch")
    if sha(root / "capture-code.py") != m["capture_code_sha256"]:
        raise ValueError("Capture code provenance changed")
    for k in (
        "provider",
        "source",
        "symbols",
        "frequency",
        "requested_start",
        "requested_end",
    ):
        if m[k] != c[k]:
            raise ValueError("Capture identity differs: " + k)
    rights = reviewed_rights(
        root / m["rights_path"],
        provider=c["provider"],
        source=c["source"],
        use_context=c["use_context"],
        expected_id=m["rights_id"],
        expected_sha=m["rights_sha256"],
    )
    native_id = _source_policy(root, m, c, rights)
    step = {"1d": 86400000, "4h": 14400000}[c["frequency"]]
    start, end = (
        int(pd.Timestamp(c[k]).timestamp() * 1000)
        for k in ("requested_start", "requested_end")
    )
    if m["interval_ms"] != step or c["data_requirements"]["calendar"] != "CRYPTO_24_7":
        raise ValueError("Unsupported or inconsistent calendar")
    plan = m["page_plan"]
    if (
        not plan
        or plan[0][0] != start
        or plan[-1][1] != end
        or any(a[1] != b[0] for a, b in zip(plan, plan[1:]))
    ):
        raise ValueError("Page plan omits/overlaps requested history")
    if any(
        hi <= lo or lo % step or hi % step or (hi - lo) // step > m["page_bar_limit"]
        for lo, hi in plan
    ):
        raise ValueError("Unaligned or over-limit page plan")
    if m["boundary_policy"] != "request-start-minus-1ms-audited-edge-exclusion-v1":
        raise ValueError("Unreviewed boundary policy")
    if m["page_count"] != len(m["raw_files"]):
        raise ValueError("Missing or extra raw page")
    if m["raw_dataset_sha256"] != digest([x["sha256"] for x in m["raw_files"]]):
        raise ValueError("Full raw dataset hash mismatch")
    rows_by_pass = []
    for meta in m["subdivision_files"]:
        _raw(root, meta)  # Retain/hash unsuccessful parent windows as well.
    for capture_pass in (0, 1):
        selected = [x for x in m["raw_files"] if x["capture_pass"] == capture_pass]
        leaf_plan = [(x["requested_start_ms"], x["requested_end_ms"]) for x in selected]
        if (
            not leaf_plan
            or leaf_plan[0][0] != start
            or leaf_plan[-1][1] != end
            or any(a[1] != b[0] for a, b in zip(leaf_plan, leaf_plan[1:]))
        ):
            raise ValueError("Leaf pages skip/overlap requested interval")
        if [x["page"] for x in selected] != list(range(len(leaf_plan))):
            raise ValueError("Repeated/skipped/reordered page")
        decoded = []
        seen = set()
        for meta, (lo, hi) in zip(selected, leaf_plan):
            if (
                lo % step
                or hi % step
                or hi <= lo
                or (hi - lo) // step > m["page_bar_limit"]
            ):
                raise ValueError("Invalid leaf boundaries")
            query = dict(
                symbol=c["symbols"][0],
                interval=step // 60000,
                startTime=lo - 1,
                endTime=hi - 1,
                limit=m["query_limit"],
            )
            if meta["params"] != query or not meta["url"].startswith(
                "https://gateway.bit2me.com/v1/trading/candle?"
            ):
                raise ValueError("Request boundary/identity mismatch")
            if meta["sha256"] in seen:
                raise ValueError("Repeated raw page")
            seen.add(meta["sha256"])
            rows = _raw(root, meta)
            if (
                meta["first_timestamp"],
                meta["last_timestamp"],
                meta["record_count"],
            ) != (rows[0][0], rows[-1][0], len(rows)):
                raise ValueError("Page metadata differs from native response")
            excluded = [r[0] for r in rows if not lo <= r[0] < hi]
            if excluded != meta["excluded_boundary_timestamps"] or any(
                t not in {lo - step, hi} for t in excluded
            ):
                raise ValueError("Unexplained out-of-window bars")
            if len({r[0] for r in rows}) != len(rows):
                raise ValueError(
                    "Native duplicates cannot be removed as boundary exclusions"
                )
            decoded.extend(
                ordered_page([r for r in rows if lo <= r[0] < hi], lo, hi, step)
            )
        rows_by_pass.append(decoded)
    _finality(root, m, end, step, rows_by_pass)
    frame = pd.DataFrame(
        rows_by_pass[0], columns=["timestamp", "open", "high", "low", "close", "volume"]
    )
    frame["ts"] = pd.to_datetime(frame.pop("timestamp"), unit="ms", utc=True)
    for key, value in dict(
        exchange=c["provider"],
        source=c["source"],
        symbol=c["symbols"][0],
        market_type=c["market_type"],
        timeframe=c["frequency"],
        native_market_id=native_id,
    ).items():
        frame[key] = value
    # is_closed is deliberately absent: evidence is dataset-level, not a
    # manufactured provider-native boolean, volume, count, or VWAP value.
    validate_core(frame, c["data_requirements"]["required_fields"])
    coverage = MarketCoverageValidator().validate(
        frame.ts,
        requested_start=c["requested_start"],
        requested_end=c["requested_end"],
        frequency=c["frequency"],
        calendar=c["data_requirements"]["calendar"],
    )
    if coverage["coverage_status"] != "VERIFIED":
        raise ValueError("Full calendar coverage not verified")
    return frame, c, m, rights, coverage


def normalized_bytes(frame):
    return frame.to_json(
        orient="records", lines=True, date_format="iso", double_precision=15
    ).encode()


def materialize(contract_path, capture_path, output):
    """Write accepted normalized snapshot only after all independent checks."""
    output = Path(output)
    frame, c, capture, rights, coverage = audit_capture(contract_path, capture_path)
    check_partition(output, c, "normalized")
    if output.exists():
        raise ValueError("Immutable normalized snapshot already exists")
    data = normalized_bytes(frame)
    data_hash = hashlib.sha256(data).hexdigest()
    trust = dict(
        schema_version="market-dataset-trust-v1",
        dataset_profile=PROFILE,
        contract_sha256=sha(contract_path),
        dataset_sha256=data_hash,
        rights_sha256=digest(rights),
        raw_dataset_sha256=capture["raw_dataset_sha256"],
        **{k: "PASS" for k in CHECKS},
        page_count=capture["page_count"],
        assessment_code_sha256=sha(Path(__file__)),
        assessed_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        status="TRUSTED",
        limitations=[
            "As-of historical closure and stable double capture; later provider revisions remain possible",
            "No native optional count/quote-volume/VWAP; no forward-fill or synthetic native finality flag",
            "Private internal research only; no redistribution of data or derivative results",
        ],
    )
    validate_schema(trust, "market_dataset_trust_v1")
    m = {
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
    m.update(
        schema_version="market-dataset-core-v1",
        dataset_profile=PROFILE,
        dataset_version="core-"
        + digest(
            dict(
                profile=PROFILE,
                provider=c["provider"],
                source=c["source"],
                symbols=c["symbols"],
                frequency=c["frequency"],
                dataset_sha256=data_hash,
            )
        ),
        snapshot_name=output.name,
        contract_sha256=sha(contract_path),
        capture_path=str(Path(capture_path).resolve()),
        capture_sha256=sha(capture_path),
        dataset_path="observations.jsonl",
        dataset_sha256=data_hash,
        rights_id=rights["rights_id"],
        rights_sha256=digest(rights),
        coverage=coverage,
        acceptance_status="TRUSTED",
        missing_native_fields=[],
        absent_optional_fields=list(OPTIONAL),
        source_identity_verified=True,
        closure_evidence_status="VERIFIED",
        real_market_data=True,
        timezone="UTC",
        calendar=c["data_requirements"]["calendar"],
        adjustment_method=c["data_requirements"]["adjustment"],
        trust_assessment=trust,
        trust_assessment_sha256=digest(trust),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".pending-core-", dir=output.parent) as temporary:
        staged = Path(temporary) / output.name
        staged.mkdir()
        (staged / "observations.jsonl").write_bytes(data)
        (staged / "manifest.json").write_text(json.dumps(m, indent=2) + "\n")
        staged.rename(output)
    return output / "manifest.json"


def read_core(contract_path, manifest_path):
    path = Path(manifest_path)
    m = json.loads(path.read_text())
    if (
        sha(m["capture_path"]) != m["capture_sha256"]
        or sha(path.parent / m["dataset_path"]) != m["dataset_sha256"]
    ):
        raise ValueError("Capture/dataset bytes changed")
    frame, c, capture, rights, coverage = audit_capture(
        contract_path, m["capture_path"]
    )
    check_partition(path.parent, c, "normalized")
    t = m["trust_assessment"]
    validate_schema(t, "market_dataset_trust_v1")
    if (
        trust_status(t) != "TRUSTED"
        or t["status"] != "TRUSTED"
        or digest(t) != m["trust_assessment_sha256"]
    ):
        raise ValueError("Trust assessment inconsistent")
    expected = dict(
        contract_sha256=sha(contract_path),
        dataset_sha256=m["dataset_sha256"],
        rights_sha256=digest(rights),
        raw_dataset_sha256=capture["raw_dataset_sha256"],
        assessment_code_sha256=sha(Path(__file__)),
        page_count=capture["page_count"],
        dataset_profile=PROFILE,
    )
    if any(t[k] != value for k, value in expected.items()):
        raise ValueError("Trust assessment binding/code changed")
    if normalized_bytes(frame) != (path.parent / m["dataset_path"]).read_bytes():
        raise ValueError("Normalized bytes differ from raw reconstruction")
    if (
        m["coverage"] != coverage
        or m["contract_sha256"] != sha(contract_path)
        or m["rights_sha256"] != digest(rights)
    ):
        raise ValueError("Manifest differs from independent audit")
    for k in (
        "provider",
        "source",
        "symbols",
        "frequency",
        "requested_start",
        "requested_end",
    ):
        if m[k] != c[k]:
            raise ValueError("Manifest identity mismatch")
    if (
        m["real_market_data"] is not True
        or m["acceptance_status"] != "TRUSTED"
        or m["missing_native_fields"]
        or m["rights_id"] != rights["rights_id"]
        or m["source_identity_verified"] is not True
        or m["closure_evidence_status"] != "VERIFIED"
        or m["timezone"] != "UTC"
        or m["calendar"] != c["data_requirements"]["calendar"]
        or m["adjustment_method"] != c["data_requirements"]["adjustment"]
    ):
        raise ValueError("Manifest not accepted")
    return frame, c, m, rights, coverage
