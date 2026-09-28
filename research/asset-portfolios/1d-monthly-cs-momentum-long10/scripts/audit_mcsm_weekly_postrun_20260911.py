"""Check saved weekly research projections and output identities; no market reads."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


FAMILY = Path(__file__).resolve().parents[1]
HERE = FAMILY / "artifacts/drawdown-frequency-round-20260911/weekly"
ROOT = FAMILY.parents[2]
SOURCE = FAMILY / "scripts/research_mcsm_weekly_20260911.py"
sys.path.insert(0, str(FAMILY / "scripts"))
sys.path.insert(0, str(ROOT / "src"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def write_new(path, value):
    text = json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n"
    if path.exists():
        assert path.read_text() == text, f"changed audit output {path}"
    else:
        path.write_text(text)


def main():
    summary = read(HERE / "summary.json")
    started = read(HERE / "execution-started.json")
    plan = read(HERE / "execution-plan.json")
    qplan = read(HERE / "qualification-plan.json")
    selected = read(HERE / "qualified-nomination-freeze.json")
    assert sha(SOURCE) == summary["execution_script_sha256"] == started["script_sha256"]
    assert sha(HERE / "execution-plan.json") == started["execution_plan_sha256"]
    assert sha(HERE / "qualified-nomination-freeze.json") == started["qualified_nominations_sha256"]
    assert sha(HERE / "qualification-plan.json") == selected["qualification_plan_sha256"]
    for name, expected in [
        ("holding-windows.parquet", plan["holding_windows_sha256"]),
        ("target-keys.parquet", plan["target_keys_sha256"]),
        ("nominations.parquet", selected["nominations_sha256"]),
        ("nomination-freeze.json", plan["nomination_freeze_sha256"]),
        ("funding-coverage-summary.json", summary["funding_coverage_sha256"]),
    ]:
        assert sha(HERE / name) == expected, name

    spec = importlib.util.spec_from_file_location("weekly_projection_lineage", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    old, old_receipts = module.load_old_endpoints(plan["old_receipts"])
    assert qplan["old_receipts"] == plan["old_receipts"]
    pieces = [old]
    phase_checks = []
    all_new_receipt_hashes = []
    for directory, phase_plan in [(HERE / "qualification", qplan), (HERE, plan)]:
        target_count = rows_count = 0
        for item in phase_plan["requests"]:
            label = item["label"]
            receipt_path = directory / "receipts" / f"{label}.json"
            receipt = read(receipt_path)
            request_path = directory / "requests" / f"{label}.json"
            report_path = directory / "reports" / f"{label}.json"
            frame_path = directory / "returned-targets" / f"{label}.parquet"
            assert read(request_path) == item["request"]
            for path, role in [(request_path, "request"), (report_path, "report"), (frame_path, "frame")]:
                assert sha(path) == receipt[f"{role}_sha256"]
            assert read(report_path)["status"] == "PRICE_DIAGNOSTIC_INPUTS_VERIFIED"
            frame = pd.read_parquet(frame_path)
            assert not frame.duplicated(["symbol", "ts"]).any()
            wanted = {(s, pd.Timestamp(t)) for s, t in item["target_keys"]}
            actual = set(zip(frame.symbol, frame.ts, strict=True))
            assert actual <= wanted
            assert len(frame) == receipt["rows"]
            assert len(wanted) == receipt["target_count"]
            if directory.name == "qualification":
                assert set(frame.columns) == {"symbol", "ts", "eligible", "research_window_valid", "source_receipt"}
                assert actual == wanted
            pieces.append(frame)
            target_count += len(wanted)
            rows_count += len(frame)
            all_new_receipt_hashes.append({"path": str(receipt_path.relative_to(HERE)), "sha256": sha(receipt_path)})
        phase_checks.append({"phase": "qualification" if directory.name == "qualification" else "execution",
                             "requests": len(phase_plan["requests"]), "requested_targets": target_count,
                             "saved_targets": rows_count, "full_reports_and_hashes_pass": True})

    all_frames = pd.concat(pieces, ignore_index=True)
    assert not all_frames.duplicated(["symbol", "ts"]).any()
    known = set(zip(all_frames.symbol, all_frames.ts, strict=True))
    needed = pd.read_parquet(HERE / "target-keys.parquet")
    holdings = pd.read_parquet(HERE / "holding-windows.parquet")
    module.validate_nominations(holdings)
    missing = []
    for row in needed.itertuples(index=False):
        if (row.symbol, row.ts) in known:
            continue
        affected = holdings.loc[holdings.symbol.eq(row.symbol) & holdings.entry_ts.le(row.ts)
                                & holdings.exit_ts.ge(row.ts)]
        missing.append({"symbol": row.symbol, "target_ts": row.ts, "trade_required": row.trade_required,
                        "affected_planned_windows": affected[["strategy", "entry_ts", "scheduled_exit_ts", "exit_ts"]].to_dict("records")})
    assert len(missing) == 4
    write_new(HERE / "future-input-gaps.json", {
        "status": "FOUR_ABSENT_TARGETS_NOT_ZERO_FILLED_OR_REMATCHED", "missing_targets": missing,
        "distinction": "Account first failure is a missing complete daily mark before these planned exit targets. The daily bar label is one day earlier than its observation time.",
        "first_failures": [
            {"strategy": "W28", "symbol": "KEEP/USDT:USDT", "daily_bar_label": "2022-02-15 00:00:00+00:00", "observation_ts": "2022-02-16 00:00:00+00:00"},
            {"strategy": "W7", "symbol": "BZRX/USDT:USDT", "daily_bar_label": "2021-12-19 00:00:00+00:00", "observation_ts": "2021-12-20 00:00:00+00:00"}],
        "no_new_terminal_price_assumption": True,
    })

    checks = []
    output_hashes = []
    for account in summary["accounts"]:
        label = f"{account['strategy']}-{round(account['slippage_rate'] * 10000)}bp"
        directory = HERE / label
        assert read(directory / "summary.json") == account
        for file in sorted(directory.iterdir()):
            output_hashes.append({"path": str(file.relative_to(HERE)), "sha256": sha(file)})
        if account["status"] != "COMPLETE_PRICE_DIAGNOSTIC_NOT_FUNDING_NET":
            assert account["total_return"] is None and account["max_drawdown_common_grid"] is None
            assert sorted(p.name for p in directory.iterdir()) == ["summary.json"]
            checks.append({"account": label, "status": "EXPLICIT_FAILURE_NO_PARTIAL_ACCOUNT_EXPORT"})
            continue
        monthly = pd.read_parquet(directory / "monthly.parquet")
        nav = pd.read_parquet(directory / "nav.parquet")
        legs = pd.read_parquet(directory / "leg-price-pnl.parquet")
        periods = pd.read_parquet(directory / "periods.parquet")
        assert len(monthly) == 75 and monthly.month.nunique() == 75
        assert len(legs) == 750 and len(periods) == 75
        assert monthly.funding_pnl_usdt.isna().all() and account["funding_pnl_usdt"] is None
        assert np.isfinite(nav.equity.to_numpy(dtype=float)).all()
        assert account["initial_equity"] == 100000.0
        errors = {
            "monthly_pnl_sum": monthly.pnl_usdt.sum() - (account["final_equity"] - 100000.0),
            "monthly_return_product": (1 + monthly["return"]).prod() - (1 + account["total_return"]),
            "monthly_price_pnl_sum": monthly.price_pnl_usdt.sum() - account["price_pnl_usdt"],
            "monthly_fee_sum": monthly.fees_usdt.sum() - account["fees_usdt"],
            "monthly_slippage_sum": monthly.slippage_usdt.sum() - account["slippage_usdt"],
            "leg_price_pnl_sum": legs.period_price_pnl_usdt.sum() - account["price_pnl_usdt"],
            "month_cash_identity_max": monthly.account_pnl_identity_error.abs().max(),
            "yearly_pnl_sum": sum(y["pnl_usdt"] for y in account["yearly"]) - (account["final_equity"] - 100000.0),
        }
        assert max(abs(v) for v in errors.values()) < 1e-5, (label, errors)
        checks.append({"account": label, "status": "PASS_SAVED_OUTPUT_IDENTITIES", "monthly_rows": len(monthly),
                       "nav_rows": len(nav), "legs": len(legs), "errors": errors})

    audit_path = HERE.parent / "independent-audit/weekly-summary.json"
    before_size = sum(p.stat().st_size for p in HERE.rglob("*") if p.is_file() and p.name != "postrun-integrity.json")
    result = {"status": "PASS", "execution_script_sha256": sha(SOURCE), "audit_script_sha256": sha(Path(__file__)),
              "summary_sha256": sha(HERE / "summary.json"), "original_receipts": len(old_receipts), "original_endpoint_rows": len(old),
              "phases": phase_checks, "nomination_leg_counts": holdings.groupby("strategy").size().to_dict(),
              "all_planned_reference_targets": len(needed), "absent_targets": len(missing),
              "same_frozen_lists_after_returns": True, "account_checks": checks,
              "independent_cash_audit_path": str(audit_path.relative_to(ROOT)), "independent_cash_audit_sha256": sha(audit_path),
              "new_receipt_hashes": all_new_receipt_hashes, "account_output_hashes": output_hashes,
              "bytes_before_this_audit_json": before_size, "budget_bytes": 40 * 1024 * 1024,
              "scope": "Saved-artifact integrity and aggregate identities; separate independent cash audit owns full event-by-event verification. No startup, network, raw market read, or parameter changes."}
    assert before_size + len(json.dumps(result, default=str)) < 40 * 1024 * 1024
    write_new(HERE / "postrun-integrity.json", result)
    print(json.dumps({k: v for k, v in result.items() if k not in {"new_receipt_hashes", "account_output_hashes", "account_checks"}}, indent=2))


if __name__ == "__main__":
    main()
