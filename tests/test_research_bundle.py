"""启动门禁合成契约测试；不把合成身份材料当作真实研究证据。"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from strategy_lab.data import research_bundle as rb
from strategy_lab.data.funding_v2 import VerifiedFundingV2
from strategy_lab.data.manifest import inventory_fingerprint, parquet_inventory, sha256_file

ROOT = Path(__file__).resolve().parents[1]
SYMBOL = "BTC/USDT:USDT"


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


@pytest.fixture
def contract(tmp_path):
    components = {}
    for role, identity in rb.COMPONENT_IDS.items():
        root = tmp_path / "data" / rb.COMPONENT_ROOTS[role]
        root.mkdir(parents=True)
        # Inventory test only; catalog frame reads are explicitly mocked below.
        (root / "part.parquet").write_bytes(b"synthetic-content-for-hash-tests")
        m = dict(dataset_id=identity, rows=100, symbols=874,
                 start_utc="2020-01-01T00:00:00+00:00", end_utc="2026-09-04T00:00:00+00:00",
                 cutoff_utc=rb.V3_CUTOFF.isoformat(),
                 parquet_inventory_fingerprint=inventory_fingerprint(parquet_inventory(root)))
        if role in ("1h", "4h", "1d"):
            m.update(input_dataset_id=rb.COMPONENT_IDS["15m"],
                     input_manifest_sha256=components["15m"]["manifest_sha256"])
        if role == "funding":
            m.update(row_quality="PASS", status="PARTIAL_COVERAGE", reader_sha256=sha256_file(ROOT / "src/strategy_lab/data/funding_v2.py"))
        save(root / "_MANIFEST.json", m)
        c = {k: m[k] for k in ("dataset_id", "rows", "symbols", "start_utc", "end_utc", "parquet_inventory_fingerprint")}
        c.update(root=rb.COMPONENT_ROOTS[role], manifest_sha256=sha256_file(root / "_MANIFEST.json"))
        if role in rb.STEP:
            c["last_bar_close_utc"] = (pd.Timestamp(m["end_utc"]) + rb.STEP[role]).isoformat()
        if role in ("1h", "4h", "1d"):
            c.update(input_dataset_id=m["input_dataset_id"], input_manifest_sha256=m["input_manifest_sha256"])
        components[role] = c
    readers = {}
    for p in rb.READER_PATHS:
        path = tmp_path / p
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / p).read_bytes())
        readers[p] = sha256_file(path)
    inventory = {SYMBOL: "COIN", "AAPL/USDT:USDT": "EQUITY"}
    inventory.update({f"SYNTH{i}/USDT:USDT": "COIN" for i in range(872)})
    bundle = dict(schema_version=1, bundle_id=rb.BUNDLE_ID, cutoff_utc=rb.V3_CUTOFF.isoformat(),
                  components=components, frozen_readers=readers, observed_asset_classes=inventory,
                  identity_inventory_source_sha256="a" * 64, pit_universe_proven=False,
                  full_historical_funding_calendar_verified=False)
    pin = repin(tmp_path, bundle)
    return tmp_path, bundle, pin


def repin(root, bundle):
    save(root / rb.BUNDLE_PATH, bundle)
    pin = dict(bundle_id=rb.BUNDLE_ID, bundle_path=rb.BUNDLE_PATH, bundle_sha256=sha256_file(root / rb.BUNDLE_PATH))
    save(root / rb.CURRENT_PATH, pin)
    return pin


def request(pin):
    return dict(schema_version=1, **pin, mode="price_diagnostic", timeframe="1h", symbols=[SYMBOL],
                start="2026-08-01T00:00:00Z", end="2026-08-02T00:00:00Z", gap_policy="reject",
                asset_policy="crypto_only", backward_bars=2, forward_bars=1)


def bars():
    times = pd.date_range("2026-08-01T00:00:00Z", periods=24, freq="1h")
    return pd.DataFrame(dict(ts=times, symbol=SYMBOL, timeframe="1h", is_closed=True,
                             open=2., high=3., low=1., close=2., volume=10., quote_volume=20., trade_count=5))


def test_contract_only_requires_no_data(contract):
    root, _, pin = contract
    # A separate checkout copies only versionable contract + reader files.
    portable = root / "portable"
    for p in [rb.BUNDLE_PATH, rb.CURRENT_PATH, *rb.READER_PATHS]:
        target = portable / p
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((root / p).read_bytes())
    assert not (portable / "data").exists()
    assert rb.read_bundle_contract(portable)[1] == pin
    report = rb.base_report("CONTRACT_ONLY_NOT_DATA_READY", pin)
    assert not any(report[k] for k in ("price_inputs_verified", "funding_window_verified", "strategy_approved"))
    with pytest.raises(FileNotFoundError):
        rb.verify_bundle_files(rb.read_bundle_contract(portable)[0], data_root=portable / "data")


@pytest.mark.parametrize("bad", ["id", "component", "parent", "cutoff", "reader", "pit", "funding_v1", "close"])
def test_bad_bundle_contract_refused_even_with_recomputed_pin(contract, bad):
    root, bundle, _ = contract
    if bad == "id":
        bundle["bundle_id"] = "binance.v3.research_inputs.v1"
    elif bad == "component":
        del bundle["components"]["4h"]
    elif bad == "parent":
        bundle["components"]["1h"]["input_manifest_sha256"] = "b" * 64
    elif bad == "cutoff":
        bundle["cutoff_utc"] = "2026-09-06T15:45:00Z"
    elif bad == "reader":
        bundle["frozen_readers"]["src/strategy_lab/data/funding_v2.py"] = "b" * 64
    elif bad == "pit":
        bundle["pit_universe_proven"] = True
    elif bad == "funding_v1":
        bundle["components"]["funding"]["dataset_id"] = "binance.perp.funding.v3_inputs.v1"
    else:
        bundle["components"]["1h"]["last_bar_close_utc"] = "2026-09-04T02:00:00Z"
    repin(root, bundle)
    with pytest.raises(ValueError):
        rb.read_bundle_contract(root)


def test_fixed_request_does_not_follow_changed_current_pointer(contract):
    root, _, pin = contract
    save(root / rb.CURRENT_PATH, {**pin, "bundle_sha256": "c" * 64})
    with pytest.raises(ValueError, match="SHA256"):
        rb.read_bundle_contract(root)
    assert rb.read_bundle_contract(root, pin=pin)[1] == pin


@pytest.mark.parametrize("relative", ["../outside", "/tmp/absolute"])
def test_path_escape_refused(tmp_path, relative):
    with pytest.raises(ValueError):
        rb.local_path(tmp_path, relative)


@pytest.mark.parametrize("bad", ["manifest", "parquet", "missing", "symlink"])
def test_bundle_integrity_no_legacy_fallback(contract, bad):
    root, bundle, _ = contract
    assert len(rb.verify_bundle_files(bundle, data_root=root / "data")) == 5
    target = root / "data" / rb.COMPONENT_ROOTS["funding"]
    if bad == "manifest":
        (target / "_MANIFEST.json").write_text("{}")
    elif bad == "parquet":
        (target / "part.parquet").write_bytes(b"changed")
    elif bad == "missing":
        (target / "part.parquet").unlink()
    else:
        outside = root / "outside.parquet"
        outside.write_bytes(b"outside")
        (target / "escape.parquet").symlink_to(outside)
    with pytest.raises(ValueError):
        rb.verify_bundle_files(bundle, data_root=root / "data")


@pytest.mark.parametrize("changes", [
    {"symbols": []}, {"symbols": [SYMBOL, SYMBOL]}, {"symbols": ["*"]},
    {"symbols": ["AAPL/USDT:USDT"]}, {"start": "2026-08-01"},
    {"end": "2026-09-05T16:00:00Z"}, {"start": "2026-08-01T00:00:01Z"},
    {"start": "2026-08-02T00:00:00Z"}, {"gap_policy": "report_only"},
    {"forward_bars": -1}, {"backward_bars": True}, {"fallback": True},
    {"mode": "net_research"}, {"mode": "net_research", "asset_policy": "observed_mixed_diagnostic"},
])
def test_invalid_research_requests_refused(contract, changes):
    _, bundle, pin = contract
    req = {**request(pin), **changes}
    with pytest.raises(ValueError):
        rb.validate_request(req, bundle)


def test_mixed_assets_only_explicit_diagnostic(contract):
    _, bundle, pin = contract
    req = {**request(pin), "symbols": ["AAPL/USDT:USDT"], "asset_policy": "observed_mixed_diagnostic"}
    rb.validate_request(req, bundle)


@pytest.mark.parametrize("bad", ["gap", "zero", "leading", "trailing", "reversed", "outside"])
def test_price_reject_and_segmentation(contract, bad):
    _, _, pin = contract
    f, req = bars(), request(pin)
    if bad == "gap":
        f = f.drop(index=10)
    elif bad == "zero":
        f.loc[10, ["volume", "quote_volume", "trade_count"]] = 0
    elif bad == "leading":
        f = f.iloc[1:]
    elif bad == "trailing":
        f = f.iloc[:-1]
    elif bad == "reversed":
        f = f.iloc[::-1]
    else:
        f["ts"] = f.ts + pd.Timedelta(hours=1)
    with pytest.raises(ValueError):
        rb.validate_price_frame(f, req, SYMBOL, [])
    if bad not in ("reversed", "outside"):
        req["gap_policy"] = "contiguous_segments"
        out, stats = rb.validate_price_frame(f, req, SYMBOL, [])
        assert stats["complete_windows"] > 0
        if bad in ("gap", "zero"):
            assert stats["eligible_segments"] == 2
            assert not out.loc[out.ts.eq(pd.Timestamp("2026-08-01T09:00:00Z")), "research_window_valid"].item()


def test_no_eligible_complete_windows_refused(contract):
    _, _, pin = contract
    req = request(pin)
    req["backward_bars"] = 30
    with pytest.raises(ValueError, match="no complete"):
        rb.validate_price_frame(bars(), req, SYMBOL, [])


def identity_packet(root, req):
    source = root / "synthetic-identity.txt"
    source.write_text("SYNTHETIC TEST ONLY, NOT REAL IDENTITY EVIDENCE")
    review = {"reviewed_by": "synthetic test reviewer", "review_status": "ACCEPTED_FOR_IDENTITY_ONLY",
              "windows": [{"symbol": SYMBOL, "start": req["start"], "end": req["end"],
                           "evidence_path": source.name, "evidence_sha256": sha256_file(source)}]}
    save(root / "review.json", review)
    return {"path": "review.json", "sha256": sha256_file(root / "review.json")}


def funding_fixture():
    times = pd.date_range("2026-08-01T08:00:00Z", periods=3, freq="8h")
    e = pd.DataFrame(dict(symbol=SYMBOL, ts=times, event_id=["a", "b", "c"], rate_type="Regular",
                         funding_rate=.0001, event_unambiguous=True))
    x = e.drop(columns="event_unambiguous").assign(segment_id="test")
    s = pd.DataFrame([dict(symbol=SYMBOL, segment_id="test", start=pd.Timestamp("2026-08-01T00:00:00Z"),
                           end=pd.Timestamp("2026-08-02T00:00:00Z"))])
    return VerifiedFundingV2(e, s, x, {"cutoff_utc": rb.V3_CUTOFF.isoformat()})


def mock_catalog(monkeypatch, root, req):
    dataset_root = root / "data" / rb.COMPONENT_ROOTS[req["timeframe"]]
    monkeypatch.setattr(rb, "resolve_dataset", lambda *a, **k: SimpleNamespace(absolute_root=lambda layout: dataset_root))
    loaded = object()
    def load(*args, **kw):
        assert kw["gap_policy"] == "contiguous_segments"
        assert kw["start"] == pd.Timestamp(req["start"]) and kw["end"] == pd.Timestamp(req["end"])
        return loaded
    monkeypatch.setattr(rb, "load_trusted_research_dataset", load)
    monkeypatch.setattr(rb, "require_passing_trusted", lambda obj: obj)
    def read(obj, **kw):
        assert obj is loaded and kw["symbol"] == SYMBOL
        assert kw["start"] == pd.Timestamp(req["start"]) and kw["end"] == pd.Timestamp(req["end"])
        return bars()
    monkeypatch.setattr(rb, "read_verified_ohlcv", read)


def test_price_startup_returns_only_verified_diagnostic_frames(contract, monkeypatch):
    root, _, pin = contract
    req = request(pin)
    mock_catalog(monkeypatch, root, req)
    result = rb.require_research_startup(req, project_root=root)
    assert result.report["status"] == "PRICE_DIAGNOSTIC_INPUTS_VERIFIED"
    assert result.report["symbols"][SYMBOL]["complete_windows"] == 22
    assert "research_window_valid" in result.prices[SYMBOL]
    assert not result.funding and not result.report["funding_window_verified"]
    assert not result.report["pit_universe_proven"] and not result.report["strategy_approved"]


@pytest.mark.parametrize("bad", [None, "identity_changed", "identity_missing", "identity_range", "calendar", "event_missing", "ambiguous"])
def test_net_startup_requires_identity_and_actual_calendar(contract, monkeypatch, bad):
    root, _, pin = contract
    req = request(pin)
    req["mode"] = "net_research"
    req["identity_review"] = identity_packet(root, req)
    f = funding_fixture()
    mock_catalog(monkeypatch, root, req)
    monkeypatch.setattr(rb, "load_funding_v2", lambda *a, **k: f)
    if bad == "identity_changed":
        (root / "synthetic-identity.txt").write_text("changed")
    elif bad == "identity_missing":
        del req["identity_review"]
    elif bad == "identity_range":
        review = rb.read_json(root / "review.json")
        review["windows"][0]["end"] = "2026-08-01T23:00:00Z"
        save(root / "review.json", review)
        req["identity_review"]["sha256"] = sha256_file(root / "review.json")
    elif bad == "calendar":
        f.segments.loc[0, "end"] = pd.Timestamp("2026-08-01T16:00:00Z")
    elif bad == "event_missing":
        f.events.drop(index=1, inplace=True)
    elif bad == "ambiguous":
        f.events.loc[1, "event_unambiguous"] = False
    if bad:
        with pytest.raises(ValueError):
            rb.require_research_startup(req, project_root=root)
    else:
        result = rb.require_research_startup(req, project_root=root)
        assert result.report["status"] == "NET_INPUT_WINDOW_VERIFIED"
        assert len(result.funding[SYMBOL]) == 3
        assert not result.report["pit_universe_proven"] and not result.report["tradability_proven"]


def test_catalog_wrong_root_rejected(contract, monkeypatch):
    root, _, pin = contract
    req = request(pin)
    mock_catalog(monkeypatch, root, req)
    monkeypatch.setattr(rb, "resolve_dataset", lambda *a, **k: SimpleNamespace(absolute_root=lambda layout: root / "cache"))
    with pytest.raises(ValueError, match="catalog root"):
        rb.require_research_startup(req, project_root=root)


def test_duplicate_json_fields_rejected(tmp_path):
    path = tmp_path / "duplicate.json"
    path.write_text('{"mode":"net_research","mode":"price_diagnostic"}')
    with pytest.raises(ValueError, match="duplicate JSON"):
        rb.read_json(path)


def test_cli_failure_report_and_no_overwrite(contract, capsys):
    root, _, pin = contract
    spec = importlib.util.spec_from_file_location("startup_cli", ROOT / "scripts/governance/check_research_startup.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    assert cli.main(["--contract-only", "--project-root", str(root)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "CONTRACT_ONLY_NOT_DATA_READY"
    req = request(pin)
    req["mode"] = "net_research"
    save(root / "request.json", req)
    output = root / "report.json"
    args = ["--request", str(root / "request.json"), "--project-root", str(root), "--output", str(output)]
    assert cli.main(args) == 1
    report = rb.read_json(output)
    assert report["status"] == "RESEARCH_STARTUP_REJECTED" and "identity" in report["error"]
    assert not report["price_inputs_verified"]
    with pytest.raises(SystemExit):
        cli.main(args)
    with pytest.raises(SystemExit):
        cli.main(["--contract-only", "--project-root", str(root), "--output", str(root / "data/report.json")])


def test_published_contract_and_routing_are_available_without_lake():
    bundle, pin = rb.read_bundle_contract(ROOT)
    assert pin["bundle_id"] == rb.BUNDLE_ID
    assert bundle["components"]["funding"]["dataset_id"].endswith(".v2")
    assert "--contract-only" in (ROOT / "scripts/governance/preflight.py").read_text()
    scanner = (ROOT / "scripts/governance/check_trusted_consumers.py").read_text()
    assert '"require_research_startup"' in scanner
    for p in ("AGENTS.md", "research/README.md", "research/platform/data-lake-governance/README.md"):
        assert "19" in (ROOT / p).read_text()


def test_publisher_refuses_overwrite(tmp_path):
    path = ROOT / rb.FAMILY / "scripts/publish_binance_research_bundle_v2.py"
    spec = importlib.util.spec_from_file_location("bundle_publisher", path)
    publisher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(publisher)
    target = tmp_path / "bundle.json"
    publisher.write_immutable(target, {"one": 1})
    old = target.read_bytes()
    publisher.write_immutable(target, {"one": 1})
    with pytest.raises(ValueError, match="refusing to overwrite"):
        publisher.write_immutable(target, {"one": 2})
    assert target.read_bytes() == old
