#!/usr/bin/env python3
"""检查固定研究组合或具体研究请求；不启动策略、不批准策略收益结论。"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from strategy_lab.data.manifest import sha256_file
from strategy_lab.data.research_bundle import (
    base_report, read_bundle_contract, read_json, require_research_startup, verify_bundle_files,
)

ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--contract-only", action="store_true", help="无数据湖的清单/指针/冻结读取器检查")
    mode.add_argument("--bundle-only", action="store_true", help="五组输入全内容哈希；不是研究窗口检查")
    mode.add_argument("--request", type=Path, help="研究方冻结的请求 JSON")
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--data-root", type=Path, help="显式共享数据湖根；不自动扫描其他工作区")
    parser.add_argument("--output", type=Path, help="新的报告 JSON；拒绝覆盖已有文件")
    args = parser.parse_args(argv)
    report = base_report("RESEARCH_STARTUP_REJECTED", {})
    report["checker_sha256"] = sha256_file(Path(__file__))
    report["startup_core_sha256"] = sha256_file(Path(sys.modules["strategy_lab.data.research_bundle"].__file__))
    report["checked_at_utc"] = datetime.now(timezone.utc).isoformat()
    # All intended writes are outside the lake, never overwrite input/protected files.
    lake = (args.data_root or args.project_root / "data").resolve()
    if args.output:
        if args.output.exists() or any(args.output.resolve().is_relative_to(p) for p in
                                      (lake, (args.project_root / "data").resolve())):
            parser.error("output must be a new file outside the data lake")
    code = 1
    try:
        if args.request:
            report["request_sha256"] = sha256_file(args.request)
            report.update(require_research_startup(
                read_json(args.request), project_root=args.project_root, data_root=lake).report)
        else:
            bundle, pin = read_bundle_contract(args.project_root)
            report.update(base_report("CONTRACT_ONLY_NOT_DATA_READY", pin))
            if args.bundle_only:
                report["verified_components"] = verify_bundle_files(bundle, data_root=lake)
                report["status"] = "BUNDLE_INTEGRITY_PASS_NOT_RESEARCH_READY"
        code = 0
    except Exception as exc:
        report.update(status="RESEARCH_STARTUP_REJECTED", error_type=type(exc).__name__, error=str(exc),
                      price_inputs_verified=False, funding_window_verified=False)
    rendered = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as handle:
            handle.write(rendered)
    print(rendered, end="")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
