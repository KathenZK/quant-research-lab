"""Display-only actual-source correspondences and rejection checks."""

import argparse
from copy import deepcopy
import csv
import io
import json
from pathlib import Path
import export as e

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--lab-repo", type=Path, required=True)
parser.add_argument("--preview", type=Path, required=True)
parser.add_argument("--rebuild", type=Path, required=True)
parser.add_argument("--receipt", type=Path, required=True)
args = parser.parse_args()
repo = args.lab_repo.resolve()
preview = args.preview.resolve()
assert not args.receipt.exists(), "Receipt must use a fresh path"

checks = []
actual = []


def reject(action, label):
    try:
        action()
    except ValueError:
        checks.append(label)
    else:
        raise AssertionError(label)


for rid in e.PINS:
    data, refs, files = e.load_sources(repo, rid)
    out = (
        preview
        / f"research/public-strategies/{rid}/artifacts/20261003-public-display-prep"
    )
    r = json.loads((out / "graph-record.json").read_bytes())
    d = json.loads((out / "graph-detail.json").read_bytes())
    manifest = (out / "public-display-manifest.json").read_bytes()
    m = json.loads(manifest)
    assert (
        r["id"] == d["id"] == rid
        and r["manifest_kind"] == d["manifest_kind"] == m["manifest_kind"] == e.KIND
    )
    assert (
        d["lineage"]["manifest_sha256"]
        == r["related_results"][0]["manifest_sha256"]
        == e.sha(manifest)
    )
    assert "source_run_manifest_sha256" not in d["lineage"]
    assert not any(k in r for k in ["entity_id", "definition_revision"])
    assert (
        r["strategy_configurations"] == d["lab_counts"]["strategy_configurations"] == 4
    )
    assert (
        r["control_configurations"]
        == d["lab_counts"]["new_control_configurations"]
        == 0
    )
    assert set(m["excluded_from_self_hash"]) == {
        "graph-record.json",
        "graph-detail.json",
        "public-display-manifest.json",
    }
    assert not set(m["files"]) & set(m["excluded_from_self_hash"])
    if rid != "M1358":
        s = json.loads(data["summary"])
        p = json.loads(data["protocol"])
        assert r["results"] == s["results"] and r["signals"] == s["signals"]
        assert r["rules"]["execution"] == p["execution"]
        assert p["execution"]["budget_includes_buy_fee"] is True
        rows = list(
            csv.DictReader(io.StringIO((out / "base-nav-light.csv").read_text()))
        )
        points = json.loads(data["base_daily"])["points"]
        assert len(rows) == len(points) == len(d["curve"]) == 366
        for x, y, z in zip(rows, points, d["curve"]):
            assert (
                float(x["equity"]) == y["equity"]
                and float(x["nav"]) == y["equity"] / 100000 == z["equity"]
            )
            assert (
                float(x["source_native_drawdown"])
                == y["drawdown"]
                == z["source_native_drawdown"]
            )
            assert (
                x["date"] == y["date"] == z["date"]
                and x["valuation_time_utc"]
                == y["timestamp_utc"]
                == z["valuation_time_utc"]
            )
        for case, view in [
            ("base", d["metrics"]["periods"]["full"]),
            ("fee0", d["metrics"]["cost_sensitivity"]["0"]["full"]),
            ("fee20", d["metrics"]["cost_sensitivity"]["20"]["full"]),
            ("delay2", d["metrics"]["additional_native_bar_lag"]["full"]),
        ]:
            original = s["results"][case]["metrics"]
            assert (
                view["total_return"] == original["total_return"]
                and view["cagr"] == original["annualized_return"]
            )
            assert view["sharpe"] == original["sharpe"] and view[
                "max_drawdown"
            ] == -abs(original["max_drawdown"])
        bad = deepcopy(data)
        c = json.loads(bad["C0"])
        c["protocol_sha256"] = "0" * 64
        bad["C0"] = e.encode(c)
        reject(lambda: e.native(rid, bad, refs), rid + ": C0 mismatch")
        bad = deepcopy(data)
        card = json.loads(bad["source_rule_card"])
        card["rules"] = "api_key=secret"
        bad["source_rule_card"] = e.encode(card)
        reject(lambda: e.native(rid, bad, refs), rid + ": credential-like rule value")
        card["rules"] = "/workspace/private-source"
        bad["source_rule_card"] = e.encode(card)
        reject(lambda: e.native(rid, bad, refs), rid + ": private path")
        if rid == "M0289":
            assert all(x["equity"] == 1 and x["drawdown"] == 0 for x in d["curve"])
            assert all(
                v["metrics"]["sharpe"] is None and v["metrics"]["trades"] == 0
                for v in r["results"].values()
            )
            bad = deepcopy(data)
            s2 = deepcopy(s)
            s2["results"]["base"]["metrics"]["sharpe"] = 0
            bad["summary"] = e.encode(s2)
            reject(lambda: e.native(rid, bad, refs), "M0289: null Sharpe replaced")
            bad = deepcopy(data)
            p2 = deepcopy(p)
            p2["parameters"]["loaded_parameter_values"]["buy_pow"] = 1
            bad["protocol"] = e.encode(p2)
            s2 = deepcopy(s)
            s2["protocol_sha256"] = e.sha(bad["protocol"])
            bad["summary"] = e.encode(s2)
            c = json.loads(bad["C0"])
            c["protocol_sha256"] = s2["protocol_sha256"]
            bad["C0"] = e.encode(c)
            reject(lambda: e.native(rid, bad, refs), "M0289: exponent alteration")
    else:
        old = json.loads(data["original_detail"])
        s = json.loads(data["summary"])
        p = json.loads(data["protocol"])
        assert (
            d["curve"]
            == old["curve"]
            == json.loads((out / "base-nav-sampled.json").read_bytes())
        )
        assert len(d["curve"]) == 25 and d["curve_meta"]["total_observations"] == 731
        assert d["curve_meta"]["private_daily_nav_used"] is False
        assert d["metrics"]["periods"] == old["metrics"]["periods"]
        assert (
            d["metrics"]["additional_native_bar_lag"]
            == old["metrics"]["additional_native_bar_lag"]
        )
        assert (
            d["metrics"]["same_instrument_benchmark"]
            == old["metrics"]["same_instrument_benchmark"]
        )
        for case, key in [("fee0", "0"), ("fee20", "20")]:
            assert (
                d["metrics"]["cost_sensitivity"][key]
                == old["metrics"]["cost_sensitivity"][case]
            )
        assert (
            r["results"] == s["summary"]
            and r["benchmark_reference"] == p["benchmark_reference"]
        )
        assert r["fidelity_class"] == d["fidelity_class"] == "HYPOTHESIS"
        assert r["research_fidelity"] == d["research_fidelity"] == "ADAPTED"
        assert r["rules"]["execution"]["buy_fee_additional_in_USDT"] is True
        assert "files" not in refs["private_output_inventory_reference_only"]
        for change in ["rescale", "extra_point", "wrong_fee", "C0", "private"]:
            bad = deepcopy(data)
            detail = deepcopy(old)
            if change == "rescale":
                detail["curve"][0]["equity"] /= 100000
            elif change == "extra_point":
                detail["curve"].append(deepcopy(detail["curve"][-1]))
            elif change == "wrong_fee":
                summary = deepcopy(s)
                summary["summary"]["fee0"]["fee_bps"] = 8
                bad["summary"] = e.encode(summary)
            elif change == "C0":
                detail["lineage"]["C0_sha256"] = "0" * 64
            else:
                detail["limitations"].append("libfile_private000example")
            bad["original_detail"] = e.encode(detail)
            reject(lambda: e.daily(bad, refs), "M1358: " + change)
    for f in out.iterdir():
        e.screen(f.read_bytes())
    actual.append(
        dict(
            id=rid,
            source_files=len(files),
            curve_points=len(d["curve"]),
            first_nav=d["curve"][0]["equity"],
            configuration_metrics_equal=True,
            fidelity=d["fidelity_class"],
        )
    )

pin = e.PINS["M0287"]
e.PINS["M0287"] = (pin[0], "0" * 64)
try:
    reject(lambda: e.load_sources(repo, "M0287"), "publication hash mismatch")
finally:
    e.PINS["M0287"] = pin
reject(lambda: e.export(repo, preview), "immutable output collision")
for text in ["https://example.org/x?sig=abc", "/home/user/private", "Bearer abcdef123"]:
    reject(lambda: e.screen(e.encode({"x": text})), "sensitive content rejected")


def inventory(path):
    return {
        f.relative_to(path).as_posix(): dict(
            sha256=e.sha(f.read_bytes()), bytes=f.stat().st_size
        )
        for f in sorted(path.rglob("*"))
        if f.is_file()
    }


one, two = inventory(preview), inventory(args.rebuild)
assert one == two and len(one) == 13
manifest = json.loads((preview / "DELIVERY-MANIFEST.json").read_bytes())
for f in manifest["source_files"]:
    raw = e.common.git_bytes(repo, f["path"])
    assert len(raw) == f["bytes"] and e.sha(raw) == f["sha256"]
review_root = (
    repo / "research/public-strategies/M0287/artifacts/20261003-public-display-review"
)
exact_raw = (review_root / "EXACT-12-FILES.json").read_bytes()
assert (
    e.sha(exact_raw)
    == "76a05ca8061e38228dff9145cfd67a09b611d051144ac7f736b2ada36ebe422e"
)
assert (
    e.sha((review_root / "independent-review.safe.json").read_bytes())
    == "1028dfa88dee02a57948d2e1c34d023d342ee71053695a9daebddca4c181006f"
)
exact = json.loads(exact_raw)
assert exact["source_commit"] == e.PIN
assert len(exact["files"]) == 12
assert manifest["files"] == exact["files"]
for name, fingerprint in exact["files"].items():
    e.common.safe_path(name)
    raw = (repo / name).read_bytes()
    assert len(raw) == fingerprint["bytes"] and e.sha(raw) == fingerprint["sha256"]
    assert raw == (preview / name).read_bytes()
assert (review_root / "DELIVERY-MANIFEST.json").read_bytes() == (
    preview / "DELIVERY-MANIFEST.json"
).read_bytes()
assert (
    e.sha((Path(__file__).with_name("export.py")).read_bytes())
    == "266c93afa0829b0e504b2e008e1ed0ae1b43a4b5fd2869ffaeb047e41fba3128"
)
assert (
    e.sha((Path(__file__).with_name("common_public_display.py")).read_bytes())
    == "f5a8536676f1575f55adcf3b286ba92c198a01c070399250fbf933f8937c9c13"
)
publication_files = 0
for rid, previous in [("M0287", 1), ("M0289", 1), ("M1358", 3)]:
    family = repo / f"research/public-strategies/{rid}"
    pub = json.loads((family / "publication-manifest.json").read_bytes())
    old_raw = (
        family / f"publication-history/v{previous}/publication-manifest.json"
    ).read_bytes()
    assert pub["revision"] == previous + 1
    assert pub["previous_publication_manifest_sha256"] == e.sha(old_raw)
    names = set()
    for entry in pub["files"]:
        name = e.common.safe_path(entry["path"])
        assert name not in names
        names.add(name)
        raw = (family / name).read_bytes()
        assert e.sha(raw) == entry["sha256"] and len(raw) == entry["bytes"]
        publication_files += 1
    for entry in json.loads(old_raw)["files"]:
        if entry["path"] not in ["README.md", "decision-log.md"]:
            raw = (family / entry["path"]).read_bytes()
            assert e.sha(raw) == entry["sha256"] and len(raw) == entry["bytes"]
result = dict(
    status="PASS",
    actual_source_checks=actual,
    total_base_display_points=757,
    configuration_metrics_checked=12,
    byte_identical_files=13,
    approved_candidate_files_exact=12,
    publication_files_checked=publication_files,
    source_files_rechecked_unchanged=len(manifest["source_files"]),
    source_bytes=sum(f["bytes"] for f in manifest["source_files"]),
    guard_checks=checks,
    guard_check_count=len(checks),
    private_M1358_daily_NAV_accessed=False,
    files=one,
    new_backtests=0,
    site_operations=0,
)
destination = args.receipt
assert not destination.exists()
destination.write_bytes(e.encode(result))
print(
    json.dumps(
        {
            k: result[k]
            for k in [
                "status",
                "total_base_display_points",
                "configuration_metrics_checked",
                "byte_identical_files",
                "source_files_rechecked_unchanged",
                "guard_check_count",
                "private_M1358_daily_NAV_accessed",
            ]
        }
    )
)
