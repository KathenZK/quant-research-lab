"""固定组合的研究启动门禁；不改变旧研究入口，也不认证策略可交易性。"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

import pandas as pd

from strategy_lab.data.catalog import (
    DatasetScope, load_trusted_research_dataset, read_verified_ohlcv,
    require_passing_trusted, resolve_dataset,
)
from strategy_lab.data.funding_v2 import load_funding_v2, require_funding_v2_window
from strategy_lab.data.lake import DataLakeLayout
from strategy_lab.data.manifest import inventory_fingerprint, parquet_inventory, sha256_file
from strategy_lab.data.research_inputs import (
    IdentityWindow, STEP, V3_CUTOFF, V3_PRICE_IDS, complete_window_mask,
    segment_research_bars,
)
from strategy_lab.data.windows import require_aware_utc

FAMILY = "research/platform/data-lake-governance"
BUNDLE_ID = "binance.v3.research_inputs.v2"
BUNDLE_PATH = f"{FAMILY}/specs/binance-v3-research-input-bundle-v2.json"
CURRENT_PATH = f"{FAMILY}/specs/current-research-inputs.json"
COMPONENT_IDS = {**V3_PRICE_IDS, "funding": "binance.perp.funding.v3_inputs.v2"}
COMPONENT_ROOTS = {
    "15m": "derived/datasets/binance_perp_15m_history_v3",
    **{tf: f"derived/datasets/binance_perp_{tf}_from_15m_v2" for tf in ("1h", "4h", "1d")},
    "funding": "derived/datasets/binance_perp_funding_v3_inputs_v2",
}
READER_PATHS = {"src/strategy_lab/data/research_inputs.py", "src/strategy_lab/data/funding_v2.py"}


def _need(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def local_path(root: Path, relative: str) -> Path:
    """仅接受显式根下的相对路径；不存在也不搜索其他工作区。"""
    _need(isinstance(relative, str) and bool(relative), "missing relative path")
    p = Path(relative)
    _need(not p.is_absolute() and ".." not in p.parts, "path must be relative without traversal")
    result = (root / p).resolve()
    _need(result.is_relative_to(root.resolve()), "path escapes explicit root")
    return result


def _hash(value: str) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def read_json(path: Path) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            _need(key not in result, f"duplicate JSON key: {key}")
            result[key] = value
        return result
    result = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs)
    _need(isinstance(result, dict), "JSON object required")
    return result


def read_bundle_contract(
    project_root: Path, *, pin: dict | None = None,
) -> tuple[dict, dict]:
    """pin 缺省时仅选择当前指针；研究请求必须传固定 pin，不随指针升级。"""
    selected = read_json(local_path(project_root, CURRENT_PATH)) if pin is None else dict(pin)
    _need(set(selected) == {"bundle_path", "bundle_id", "bundle_sha256"}, "invalid bundle pin fields")
    _need(selected["bundle_id"] == BUNDLE_ID and selected["bundle_path"] == BUNDLE_PATH,
          "unsupported bundle identity/path; no legacy fallback")
    path = local_path(project_root, selected["bundle_path"])
    _need(_hash(selected["bundle_sha256"]) and sha256_file(path) == selected["bundle_sha256"],
          "bundle SHA256 mismatch")
    bundle = read_json(path)
    _need(bundle.get("schema_version") == 1 and bundle.get("bundle_id") == selected["bundle_id"],
          "bundle schema/identity mismatch")
    _need(require_aware_utc(bundle["cutoff_utc"], field="bundle cutoff") == V3_CUTOFF,
          "bundle frozen cutoff mismatch")
    _need(bundle.get("pit_universe_proven") is False
          and bundle.get("full_historical_funding_calendar_verified") is False,
          "bundle cannot assert full PIT/calendar readiness")
    components = bundle["components"]
    _need(set(components) == set(COMPONENT_IDS), "missing or extra bundle components")
    for role, c in components.items():
        _need(c["dataset_id"] == COMPONENT_IDS[role] and c["root"] == COMPONENT_ROOTS[role],
              f"{role}: wrong dataset identity/root")
        _need(_hash(c["manifest_sha256"]) and _hash(c["parquet_inventory_fingerprint"]),
              f"{role}: invalid content pin")
        a = require_aware_utc(c["start_utc"], field="component start")
        b = require_aware_utc(c["end_utc"], field="component end")
        _need(a <= b < V3_CUTOFF, f"{role}: invalid range")
        _need(type(c["rows"]) is int and c["rows"] > 0 and c["symbols"] == 874,
              f"{role}: invalid component size")
        if role in STEP:
            close = require_aware_utc(c["last_bar_close_utc"], field="last close")
            _need(close == b + STEP[role] and close <= V3_CUTOFF
                  and a.value % STEP[role].value == 0 and b.value % STEP[role].value == 0,
                  f"{role}: invalid complete-bar range")
        if role in ("1h", "4h", "1d"):
            _need(c["input_dataset_id"] == COMPONENT_IDS["15m"]
                  and c["input_manifest_sha256"] == components["15m"]["manifest_sha256"],
                  f"{role}: not derived from pinned V3")
    readers = bundle["frozen_readers"]
    _need(set(readers) == READER_PATHS, "missing frozen reader pins")
    for relative, digest in readers.items():
        _need(_hash(digest) and sha256_file(local_path(project_root, relative)) == digest,
              f"frozen reader changed: {relative}")
    inventory = bundle["observed_asset_classes"]
    _need(isinstance(inventory, dict) and len(inventory) == 874
          and all(isinstance(s, str) and s.endswith("/USDT:USDT")
                  and isinstance(c, str) and bool(c) for s, c in inventory.items()),
          "invalid observed symbol inventory")
    _need(_hash(bundle["identity_inventory_source_sha256"]), "missing inventory provenance")
    return bundle, selected


def verify_bundle_files(bundle: dict, *, data_root: Path) -> dict:
    """五组输入全部做内容哈希；不是对某个研究范围的质量批准。"""
    verified = {}
    for role, c in bundle["components"].items():
        root = local_path(data_root, c["root"])
        manifest_path = local_path(root, "_MANIFEST.json")
        _need(sha256_file(manifest_path) == c["manifest_sha256"], f"{role}: manifest changed")
        m = read_json(manifest_path)
        for key in ("dataset_id", "parquet_inventory_fingerprint", "rows", "start_utc", "end_utc"):
            _need(m[key] == c[key], f"{role}: manifest {key} mismatch")
        _need(m.get("symbol_count", m.get("symbols")) == c["symbols"], f"{role}: symbol count mismatch")
        cutoff = m.get("cutoff_exclusive_utc", m.get("cutoff_utc"))
        _need(require_aware_utc(cutoff, field="manifest cutoff") == V3_CUTOFF, f"{role}: cutoff mismatch")
        if role in ("1h", "4h", "1d"):
            for key in ("input_dataset_id", "input_manifest_sha256"):
                _need(m[key] == c[key], f"{role}: parent lineage changed")
        if role == "funding":
            _need(m.get("row_quality") == "PASS" and m.get("status") == "PARTIAL_COVERAGE"
                  and m.get("reader_sha256") == bundle["frozen_readers"]["src/strategy_lab/data/funding_v2.py"],
                  "funding: acceptance/reader mismatch")
        files = list(root.rglob("*.parquet"))
        _need(bool(files) and all(p.resolve().is_relative_to(root) for p in files),
              f"{role}: missing/escaped parquet files")
        actual = inventory_fingerprint(parquet_inventory(root))
        _need(actual == c["parquet_inventory_fingerprint"], f"{role}: parquet content changed")
        verified[role] = {"manifest_sha256": c["manifest_sha256"], "parquet_inventory_fingerprint": actual}
    return verified


def base_report(status: str, pin: dict) -> dict:
    return {"status": status, **pin, "price_inputs_verified": False,
            "funding_window_verified": False, "pit_universe_proven": False,
            "tradability_proven": False, "strategy_approved": False}


REQUEST_FIELDS = {"schema_version", "bundle_path", "bundle_id", "bundle_sha256", "mode",
                  "timeframe", "symbols", "start", "end", "gap_policy", "asset_policy",
                  "backward_bars", "forward_bars"}


def validate_request(request: dict, bundle: dict) -> tuple[pd.Timestamp, pd.Timestamp]:
    _need(REQUEST_FIELDS <= set(request) <= REQUEST_FIELDS | {"identity_review"}, "invalid request fields")
    _need(request["schema_version"] == 1, "unsupported request schema")
    mode, tf = request["mode"], request["timeframe"]
    _need(mode in ("price_diagnostic", "net_research") and tf in STEP, "unsupported mode/timeframe")
    _need(request["gap_policy"] in ("reject", "contiguous_segments"), "explicit gap policy required")
    _need(request["asset_policy"] in ("crypto_only", "observed_mixed_diagnostic"), "unknown asset policy")
    _need(mode != "net_research" or request["asset_policy"] == "crypto_only", "net startup supports crypto_only")
    symbols = request["symbols"]
    _need(isinstance(symbols, list) and bool(symbols) and all(isinstance(s, str) for s in symbols),
          "explicit nonempty symbol list required")
    _need(len(set(symbols)) == len(symbols) and all(s in bundle["observed_asset_classes"] for s in symbols),
          "duplicate, unknown or wildcard symbol")
    if request["asset_policy"] == "crypto_only":
        _need(all(bundle["observed_asset_classes"][s] == "COIN" for s in symbols),
              "non-COIN/unknown observation requires explicit mixed diagnostic policy")
    a = require_aware_utc(request["start"], field="start")
    b = require_aware_utc(request["end"], field="end")
    c = bundle["components"][tf]
    _need(a < b and a.value % STEP[tf].value == 0 and b.value % STEP[tf].value == 0,
          "window must be ordered and aligned")
    _need(a >= require_aware_utc(c["start_utc"], field="dataset start")
          and b <= require_aware_utc(c["last_bar_close_utc"], field="dataset close"),
          "request outside frozen complete-bar coverage")
    _need(type(request["backward_bars"]) is int and request["backward_bars"] >= 1
          and type(request["forward_bars"]) is int and request["forward_bars"] >= 0,
          "invalid feature/label window sizes")
    if mode == "net_research":
        _need("identity_review" in request, "net research requires reviewed identity evidence")
    else:
        _need("identity_review" not in request, "price_diagnostic does not certify identity")
    return a, b


def _identity_windows(project_root: Path, request: dict) -> list[IdentityWindow]:
    if request["mode"] != "net_research":
        return []
    ref = request["identity_review"]
    _need(isinstance(ref, dict) and set(ref) == {"path", "sha256"}, "invalid identity review pin")
    path = local_path(project_root, ref["path"])
    _need(_hash(ref["sha256"]) and sha256_file(path) == ref["sha256"], "identity review hash mismatch")
    review = read_json(path)
    _need(review.get("review_status") == "ACCEPTED_FOR_IDENTITY_ONLY"
          and isinstance(review.get("reviewed_by"), str) and bool(review["reviewed_by"].strip()),
          "independent identity review required; snapshot is not proof")
    windows = []
    for w in review["windows"]:
        _need(set(w) == {"symbol", "start", "end", "evidence_path", "evidence_sha256"},
              "invalid identity evidence fields")
        evidence = local_path(project_root, w["evidence_path"])
        _need(_hash(w["evidence_sha256"]) and sha256_file(evidence) == w["evidence_sha256"]
              and evidence.stat().st_size > 0, "identity evidence missing/changed")
        a = require_aware_utc(w["start"], field="identity start")
        b = require_aware_utc(w["end"], field="identity end")
        _need(a <= require_aware_utc(request["start"], field="start")
              and b >= require_aware_utc(request["end"], field="end"),
              "identity evidence does not cover full request")
        windows.append(IdentityWindow(w["symbol"], w["start"], w["end"],
                                      f'{w["evidence_path"]} sha256={w["evidence_sha256"]}'))
    _need(len(windows) == len(request["symbols"])
          and {w.symbol for w in windows} == set(request["symbols"]),
          "one full-window identity review per requested symbol required")
    return windows


def validate_price_frame(frame: pd.DataFrame, request: dict, symbol: str,
                         identities: list[IdentityWindow]) -> tuple[pd.DataFrame, dict]:
    """校验精确范围和有效段；不静默丢标的，不用缺口两侧拼接窗口。"""
    tf = request["timeframe"]
    a = require_aware_utc(request["start"], field="start")
    b = require_aware_utc(request["end"], field="end")
    _need(not frame.empty and frame.symbol.eq(symbol).all(), f"{symbol}: empty or mixed-symbol frame")
    out = segment_research_bars(frame, tf, identity_windows=identities,
                               identity_policy="require_verified" if request["mode"] == "net_research" else "observed_diagnostic")
    _need(out.ts.ge(a).all() and (out.ts + STEP[tf]).le(b).all(), f"{symbol}: read escaped verified request")
    expected = int((b - a) / STEP[tf])
    missing = expected - len(out)
    _need(missing >= 0, f"{symbol}: more rows than grid")
    if request["gap_policy"] == "reject":
        _need(missing == 0 and out.eligible.all() and out.research_segment_id.nunique() == 1,
              f"{symbol}: missing/invalid bars or identity boundary under reject policy")
    out["research_window_valid"] = complete_window_mask(
        out, backward=request["backward_bars"], forward=request["forward_bars"])
    _need(out.research_window_valid.any(), f"{symbol}: no complete eligible feature/label window")
    return out, {"rows": len(out), "expected_grid_rows": expected, "missing_grid_rows": missing,
                 "ineligible_rows": int((~out.eligible).sum()),
                 "eligible_segments": int(out.research_segment_id.nunique()),
                 "complete_windows": int(out.research_window_valid.sum()),
                 "first_open_utc": out.ts.min().isoformat(), "last_open_utc": out.ts.max().isoformat()}


@dataclass(frozen=True)
class VerifiedResearchInputs:
    prices: dict[str, pd.DataFrame]
    funding: dict[str, pd.DataFrame]
    report: dict[str, Any]


def require_research_startup(
    request: dict, *, project_root: Path, data_root: Path | None = None,
) -> VerifiedResearchInputs:
    """失败抛错且不返回可消费帧；调用者不得捕获后改用旧版/缓存。

    返回 price_diagnostic 仅供价格诊断。净收益仍须单独满足成本、执行、PIT
    和逐笔持仓连续性契约；本函数不认证身份复核材料的事实真实性。
    """
    pin = {k: request[k] for k in ("bundle_path", "bundle_id", "bundle_sha256")}
    bundle, pin = read_bundle_contract(project_root, pin=pin)
    a, b = validate_request(request, bundle)
    identities = _identity_windows(project_root, request)
    lake = (data_root or project_root / "data").resolve()
    verified = verify_bundle_files(bundle, data_root=lake)
    layout = DataLakeLayout(root_dir=lake, raw_dir=lake / "raw", normalized_dir=lake / "normalized",
                           features_dir=lake / "features", cache_dir=lake / "cache", derived_dir=lake / "derived")
    tf = request["timeframe"]
    c = bundle["components"][tf]
    record = resolve_dataset(c["dataset_id"], layout=layout)
    _need(record.absolute_root(layout).resolve() == local_path(lake, c["root"]), "catalog root differs from bundle")
    loaded = require_passing_trusted(load_trusted_research_dataset(
        c["dataset_id"], layout=layout, requested_scope=DatasetScope.FULL_MARKET,
        start=a, end=b, gap_policy="contiguous_segments", max_materialize_rows=0))
    prices, stats, funding = {}, {}, {}
    verified_funding = None
    if request["mode"] == "net_research":
        fc = bundle["components"]["funding"]
        verified_funding = load_funding_v2(local_path(lake, fc["root"]), expected_manifest_sha256=fc["manifest_sha256"])
    for symbol in request["symbols"]:
        # Bounds are exactly the already-audited request, not a wider second read.
        frame = read_verified_ohlcv(loaded, symbol=symbol, start=a, end=b)
        prices[symbol], stats[symbol] = validate_price_frame(frame, request, symbol, identities)
        if verified_funding is not None:
            evidence = next(w.evidence for w in identities if w.symbol == symbol)
            funding[symbol] = require_funding_v2_window(
                verified_funding, symbol=symbol, start=request["start"], end=request["end"], identity_evidence=evidence)
            stats[symbol]["funding_events"] = len(funding[symbol])
            stats[symbol]["funding_segment_id"] = funding[symbol].attrs["coverage_segment_id"]
    report = base_report("NET_INPUT_WINDOW_VERIFIED" if verified_funding is not None else "PRICE_DIAGNOSTIC_INPUTS_VERIFIED", pin)
    report.update(price_inputs_verified=True, funding_window_verified=verified_funding is not None,
                  verified_components=verified, request=request, symbols=stats,
                  identity_evidence_scope="caller-reviewed files; not automatic historical truth/PIT certification")
    return VerifiedResearchInputs(prices, funding, report)
