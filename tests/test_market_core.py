"""Synthetic unit fixtures only. These never access the private research DB."""

import importlib.util
import json
from pathlib import Path
from urllib.parse import urlencode
import pandas as pd
import pytest
from strategy_lab.knowledge import market_core as core
from strategy_lab.knowledge.market_contract import sha
from strategy_lab.knowledge.candidates import digest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "paged_capture_test",
    ROOT / "research/platform/quantgraph-integration/scripts/fetch_market_paged.py",
)
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)


def candle(t):
    return [t, 10, 12, 9, 11, 3]


def test_silent_cap_bisects_without_skipping_or_filling():
    requests = []

    def capped(lo, hi):
        requests.append((lo, hi))
        ts = list(range(lo, hi, 1000))[-2:]
        return {"request": (lo, hi)}, json.dumps([candle(t) for t in ts])

    leaves, parents = capture.partition(capped, 0, 8000, 1000)
    assert [(x["requested_start_ms"], x["requested_end_ms"]) for x in leaves] == [
        (0, 2000),
        (2000, 4000),
        (4000, 6000),
        (6000, 8000),
    ]
    assert len(parents) == 3 and len(requests) == 7


def test_boundary_overlap_is_explicit_and_duplicates_are_not_collapsed():
    def old_backend(lo, hi):
        return {}, json.dumps([candle(t) for t in range(lo - 1000, hi, 1000)])

    leaves, _ = capture.partition(old_backend, 1000, 5000, 1000)
    assert leaves[0]["excluded_boundary_timestamps"] == [0]
    with pytest.raises(ValueError, match="Duplicated"):
        capture.partition(
            lambda lo, hi: ({}, json.dumps([candle(lo), candle(lo)])), 0, 1000, 1000
        )
    with pytest.raises(ValueError, match="absent"):
        capture.partition(lambda lo, hi: ({}, "[]"), 0, 1000, 1000)
    with pytest.raises(ValueError, match="ignored"):
        capture.partition(
            lambda lo, hi: ({}, json.dumps([candle(-5000)])), 0, 1000, 1000
        )


def test_provider_reverse_order_is_supported_but_not_arbitrary_disorder():
    rows = [candle(t) for t in range(0, 4000, 1000)]
    assert core.ordered_page(rows[::-1], 0, 4000, 1000) == rows
    with pytest.raises(ValueError, match="Unordered"):
        core.ordered_page([rows[0], rows[2], rows[1], rows[3]], 0, 4000, 1000)
    with pytest.raises(ValueError, match="gap/cap"):
        core.ordered_page(rows[1:], 0, 4000, 1000)


def test_optional_fields_do_not_excuse_missing_strategy_fields():
    f = pd.DataFrame(
        [
            dict(
                ts=pd.Timestamp("2025-01-01", tz="UTC"),
                open=10.0,
                high=12.0,
                low=9.0,
                close=11.0,
                volume=3.0,
                exchange="unit",
                source="unit",
                symbol="UNIT",
                market_type="spot",
                timeframe="1d",
            )
        ]
    )
    core.validate_core(f, ["open", "close"])
    with pytest.raises(ValueError, match="missing"):
        core.validate_core(f, ["quote_volume"])
    f["trade_count"] = 0.5
    with pytest.raises(ValueError, match="Fractional"):
        core.validate_core(f, ["close"])
    f = f.drop(columns="trade_count")
    f["high"] = 8
    with pytest.raises(ValueError, match="envelope"):
        core.validate_core(f, ["close"])


def fixture(tmp_path, monkeypatch):
    # Source review is isolated; all actual page, clock, hash, contract,
    # coverage, closure and normalization checks execute unchanged.
    tmp_path = (
        tmp_path
        / "data/raw/ohlcv/exchange=bit2me/market_type=spot/timeframe=1d/source=bit2me_public_rest/snapshot=unit"
    )
    tmp_path.mkdir(parents=True)
    cp = tmp_path / "contract.json"
    c = json.loads(
        (
            ROOT
            / "research/btc/1d-quantgraph-source-sma/specs/research-contract-trusted-v1.json"
        ).read_text()
    )
    c.update(
        requested_start="2025-01-01T00:00:00Z",
        requested_end="2025-01-05T00:00:00Z",
        is_start="2025-01-01T00:00:00Z",
        is_end="2025-01-03T00:00:00Z",
        oos_start="2025-01-03T00:00:00Z",
        oos_end="2025-01-05T00:00:00Z",
    )
    c["engine_config"].update(
        requested_start=c["requested_start"],
        end_exclusive=c["requested_end"],
        evaluation_start=c["is_start"],
        oos_start=c["oos_start"],
    )
    cp.write_text(json.dumps(c))
    (tmp_path / "capture-code.py").write_text("# synthetic test code only")
    rights = {
        "rights_id": "unit-rights",
        "provider": "bit2me",
        "source": "bit2me_public_rest",
    }
    monkeypatch.setattr(core, "reviewed_rights", lambda *a, **k: rights)
    monkeypatch.setattr(core, "_source_policy", lambda *a: "synthetic-unit-market")
    day = 86400000
    start = int(pd.Timestamp(c["requested_start"]).timestamp() * 1000)
    end = start + 4 * day
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
        status="CAPTURED",
        real_market_data=True,
        contract_sha256=sha(cp),
        capture_code_sha256=sha(tmp_path / "capture-code.py"),
        rights_path="unit-rights",
        rights_id="unit-rights",
        rights_sha256=digest(rights),
        interval_ms=day,
        page_plan=[[start, end]],
        page_bar_limit=64,
        query_limit=70,
        raw_files=[],
        subdivision_files=[],
        observation_files=[],
        boundary_policy="request-start-minus-1ms-audited-edge-exclusion-v1",
        finality_policy="closed-grid-newer-bar-stable-recapture-v1",
    )
    for i in (0, 1):
        p = tmp_path / f"pass{i}.json"
        rows = [candle(t) for t in range(start, end, day)]
        p.write_text(json.dumps(rows))
        q = dict(
            symbol="BTC/EUR",
            interval=1440,
            startTime=start - 1,
            endTime=end - 1,
            limit=70,
        )
        m["raw_files"].append(
            dict(
                path=p.name,
                sha256=sha(p),
                http_status=200,
                url="https://gateway.bit2me.com/v1/trading/candle?" + urlencode(q),
                params=q,
                capture_pass=i,
                page=0,
                requested_start_ms=start,
                requested_end_ms=end,
                first_timestamp=start,
                last_timestamp=end - day,
                record_count=4,
                excluded_boundary_timestamps=[],
                fetched_start=f"2025-01-06T00:0{i}:00Z",
                fetched_at=f"2025-01-06T00:0{i}:01Z",
            )
        )
        p = tmp_path / f"current{i}.json"
        p.write_text(json.dumps([candle(end + day)]))
        q = dict(symbol="BTC/EUR", interval=1440)
        m["observation_files"].append(
            dict(
                path=p.name,
                sha256=sha(p),
                http_status=200,
                url="https://gateway.bit2me.com/v1/trading/candle?" + urlencode(q),
                params=q,
                headers={"Date": f"Mon, 06 Jan 2025 00:0{i}:02 GMT"},
                fetched_at=f"2025-01-06T00:0{i}:03Z",
            )
        )
    m.update(
        page_count=2, raw_dataset_sha256=digest([x["sha256"] for x in m["raw_files"]])
    )
    mp = tmp_path / "capture.json"
    mp.write_text(json.dumps(m))
    return cp, mp, m


def test_offline_reconstruction_rejects_normalized_tampering_even_rehashed(
    tmp_path, monkeypatch
):
    cp, mp, m = fixture(tmp_path, monkeypatch)
    path = core.materialize(
        cp,
        mp,
        tmp_path
        / "data/normalized/ohlcv/exchange=bit2me/market_type=spot/timeframe=1d/snapshot=unit",
    )
    core.read_core(cp, path)
    manifest = json.loads(path.read_text())
    dp = path.parent / manifest["dataset_path"]
    dp.write_text(
        dp.read_text().replace("11.0", "10.0").replace('"close":11,', '"close":10,')
    )
    manifest["dataset_sha256"] = sha(dp)
    manifest["trust_assessment"]["dataset_sha256"] = sha(dp)
    manifest["trust_assessment_sha256"] = digest(manifest["trust_assessment"])
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="raw reconstruction"):
        core.read_core(cp, path)


@pytest.mark.parametrize(
    "mutation",
    [
        "revision",
        "stale_clock",
        "current_bar",
        "missing_page",
        "raw_tamper",
        "wrong_contract",
    ],
)
def test_independent_real_input_gates_fail_closed(tmp_path, monkeypatch, mutation):
    cp, mp, m = fixture(tmp_path, monkeypatch)
    if mutation in {"revision", "raw_tamper"}:
        meta = m["raw_files"][1]
        p = mp.parent / meta["path"]
        rows = json.loads(p.read_text())
        rows[0][4] = 10
        p.write_text(json.dumps(rows))
        if mutation == "revision":
            meta["sha256"] = sha(p)
            m["raw_dataset_sha256"] = digest([x["sha256"] for x in m["raw_files"]])
    if mutation == "stale_clock":
        m["observation_files"][0]["headers"]["Date"] = "Sun, 05 Jan 2025 00:00:00 GMT"
    if mutation == "current_bar":
        meta = m["observation_files"][0]
        p = mp.parent / meta["path"]
        p.write_text(json.dumps([candle(0)]))
        meta["sha256"] = sha(p)
    if mutation == "missing_page":
        m["raw_files"].pop()
    if mutation == "wrong_contract":
        cp.write_text(cp.read_text() + " ")
    mp.write_text(json.dumps(m))
    with pytest.raises(ValueError):
        core.audit_capture(cp, mp)


def test_unknown_trust_dimension_never_becomes_trusted():
    checks = {k: "PASS" for k in core.CHECKS}
    assert core.trust_status(checks) == "TRUSTED"
    checks["finality"] = "UNKNOWN"
    assert core.trust_status(checks) == "DIAGNOSTIC_ONLY"
    checks["rights"] = "FAIL"
    assert core.trust_status(checks) == "REJECTED"


def test_normalized_snapshot_requires_lake_partition_and_never_overwrites(
    tmp_path, monkeypatch
):
    cp, mp, _ = fixture(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="partition"):
        core.materialize(cp, mp, tmp_path / "scratch")
    assert not (tmp_path / "scratch").exists()
    output = (
        tmp_path
        / "data/normalized/ohlcv/exchange=bit2me/market_type=spot/timeframe=1d/snapshot=unit"
    )
    manifest = core.materialize(cp, mp, output)
    before = manifest.read_bytes()
    with pytest.raises(ValueError, match="already exists"):
        core.materialize(cp, mp, output)
    assert manifest.read_bytes() == before
