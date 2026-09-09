from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType


GOVERNANCE_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts" / "governance"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "render_runner_tracking_from_ledger",
        GOVERNANCE_SCRIPTS / "render_runner_tracking_from_ledger.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_draft_fills_available_fields_and_todos_the_rest(tmp_path: Path) -> None:
    render = _load()
    status = tmp_path / "status.json"
    trades = tmp_path / "trades.json"
    events = tmp_path / "events.json"
    status.write_text(
        json.dumps(
            {
                "ledger_db_path": "/tmp/example.sqlite3",
                "health": [
                    {
                        "strategy_name": "example-dry-run",
                        "status": "ok",
                        "strategy_id": "EXAMPLE-DRAFT-V0",
                        "mode": "dry_run",
                        "symbol": "HYPEUSDT",
                        "timeframe": "5m",
                        "last_bar_ts": "2026-09-03T00:00:00Z",
                        "last_signal_ts": "2026-09-02T23:55:00Z",
                        "last_signal_side": 1,
                        "position_open": False,
                        "updated_at": "2026-09-03T00:01:00Z",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    trades.write_text(
        json.dumps(
            {
                "ledger_db_path": "/tmp/example.sqlite3",
                "trades": [
                    {
                        "trade_id": "trade-1",
                        "strategy_name": "example-dry-run",
                        "strategy_id": "EXAMPLE-DRAFT-V0",
                        "mode": "dry_run",
                        "symbol": "HYPEUSDT",
                        "status": "closed",
                        "side": "long",
                        "entry_ts": "2026-09-02T23:55:00Z",
                        "exit_ts": "2026-09-03T00:05:00Z",
                        "entry_price": 10.0,
                        "exit_price": 10.2,
                        "quantity": 1.0,
                        "notional_usdt": 10.0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    events.write_text(
        json.dumps(
            {
                "events": [
                    {
                        "id": 7,
                        "ts": "2026-09-03T00:05:00Z",
                        "strategy_name": "example-dry-run",
                        "event_type": "fill",
                        "bar_ts": "2026-09-03T00:00:00Z",
                        "payload": {
                            "order_id": "ord-1",
                            "trade_id": "trade-1",
                            "price": 10.2,
                            "fee_usdt": 0.01,
                        },
                    },
                    {
                        "id": 8,
                        "ts": "2026-09-03T00:06:00Z",
                        "strategy_name": "example-dry-run",
                        "event_type": "cycle_error",
                        "payload": {"error": "fixture"},
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "draft.md"
    ns = type(
        "Args",
        (),
        {
            "strategy_id": "EXAMPLE-DRAFT-V0",
            "instance_id": "example-dry-run",
            "family_id": "example-draft",
            "window": "2026-09-03",
            "config": "configs/dryrun.toml",
            "status_json": status,
            "trades_json": trades,
            "events_json": events,
            "generated_command": "scripts/lab_sync/sync_to_lab.sh configs/dryrun.toml example-dry-run 2026-09-03 /tmp/family",
        },
    )()
    text = render.render(ns)
    output.write_text(text, encoding="utf-8")
    assert "DRAFT" in text
    assert "pending evidence review" in text
    assert "来源追溯、缺项补齐、逐笔对账和差异复核完成前，保持 DRAFT，不作为门禁证据" in text
    assert "缺项或未验证" in text
    assert "本报告不证明复核已完成，也不代表实盘启停授权" in text
    assert "pending human review" not in text
    assert "人工核对" not in text
    assert "TODO(human)" not in text
    assert "`trade-1`" in text
    assert "`10.0`" in text
    assert "`10.2`" in text
    assert "`ord-1`" in text
    assert "TODO(unverified)" in text
    assert "- keep：" in text
    assert "- stop：" in text
    assert "- adjust：" in text
    assert "预期回测入场" in text
    assert "标记/参考价" in text
    assert "滑点估计" in text
    assert text.split("## keep / stop / adjust", 1)[1].strip().endswith("- adjust：")
