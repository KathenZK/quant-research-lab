#!/usr/bin/env python3
"""Render a DRAFT runner-tracking report from ledger-status/trades/events JSON."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any


TODO = "TODO(human)"
INCIDENT_TYPES = {
    "cycle_error",
    "group_restarted",
    "group_halted",
    "group_freshness_stale",
    "group_freshness_recovered",
    "transient_exchange_error",
    "manual_halt",
    "manual_halt_set",
    "runner_started",
    "service_graceful_shutdown",
}


def cell(value: Any) -> str:
    if value is None or value == "":
        return TODO
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value).strip()
    return text if text else TODO


def md_cell(value: Any) -> str:
    text = cell(value).replace("|", "\\|").replace("\n", " ")
    return f"`{text}`" if text != TODO else TODO


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def matching_rows(rows: list[dict[str, Any]], instance_id: str) -> list[dict[str, Any]]:
    matched = [row for row in rows if row.get("strategy_name") == instance_id]
    return matched if matched else list(rows)


def sha256_table(paths: list[Path]) -> str:
    lines = ["| 文件 | SHA256 |", "| --- | --- |"]
    found = False
    for path in paths:
        sidecar = Path(str(path) + ".sha256")
        if not sidecar.is_file():
            continue
        found = True
        raw = sidecar.read_text(encoding="utf-8").split()
        digest = raw[0] if raw else TODO
        lines.append(f"| `{path.name}` | `{digest}` |")
    if not found:
        lines.append(f"| {TODO} | {TODO} |")
    return "\n".join(lines)


def payload_get(event: dict[str, Any], *keys: str) -> Any:
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return None
    for key in keys:
        if payload.get(key) not in (None, ""):
            return payload[key]
        nested = payload.get("payload")
        if isinstance(nested, dict) and nested.get(key) not in (None, ""):
            return nested[key]
    return None


def first_event_value(events: list[dict[str, Any]], event_type: str, *keys: str) -> Any:
    for event in events:
        if event.get("event_type") != event_type:
            continue
        value = payload_get(event, *keys)
        if value not in (None, ""):
            return value
    return None


def health_row(status: dict[str, Any], instance_id: str) -> dict[str, Any]:
    rows = matching_rows(list(status.get("health") or []), instance_id)
    return rows[0] if rows else {}


def render(args: argparse.Namespace) -> str:
    status = load_json(args.status_json)
    trades_payload = load_json(args.trades_json)
    events_payload = load_json(args.events_json)
    all_trades = list(trades_payload.get("trades") or [])
    all_events = list(events_payload.get("events") or [])
    trades = matching_rows(all_trades, args.instance_id)
    events = matching_rows(all_events, args.instance_id)
    health = health_row(status, args.instance_id)
    closed = [trade for trade in trades if trade.get("status") == "closed"]
    incidents = [
        event
        for event in events
        if event.get("event_type") in INCIDENT_TYPES
    ]
    generated_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    generated_cmd = args.generated_command or TODO
    family_id = args.family_id or TODO
    ledger_db = status.get("ledger_db_path") or trades_payload.get("ledger_db_path") or TODO

    fill_fee = first_event_value(events, "fill", "fee_usdt")
    fill_price = first_event_value(events, "fill", "price")
    mark_price = first_event_value(events, "fill", "mark_price", "mark")
    order_id = first_event_value(events, "order", "order_id", "client_order_id") or first_event_value(
        events, "fill", "order_id"
    )

    signal_ts = health.get("last_signal_ts")
    bar_ts = health.get("last_bar_ts")
    event_bars = [event.get("bar_ts") for event in events if event.get("bar_ts")]
    event_signals = [
        event.get("ts") for event in events if event.get("event_type") == "signal"
    ]

    trade_rows = []
    for trade in trades:
        trade_id = trade.get("trade_id")
        related = [
            event
            for event in events
            if payload_get(event, "trade_id") == trade_id
            or (event.get("event_type") in {"order", "fill"} and trade_id)
        ]
        related_order = None
        related_fee = None
        related_fill = None
        related_mark = None
        related_event_id = None
        for event in related:
            related_order = related_order or payload_get(event, "order_id", "client_order_id")
            related_fee = related_fee if related_fee is not None else payload_get(event, "fee_usdt")
            related_fill = related_fill or payload_get(event, "price")
            related_mark = related_mark or payload_get(event, "mark_price", "mark")
            related_event_id = related_event_id or event.get("id")
        trade_rows.append(
            "| "
            + " | ".join(
                [
                    md_cell(trade_id),
                    TODO,
                    TODO,
                    md_cell(trade.get("entry_ts")),
                    md_cell(trade.get("exit_ts")),
                    md_cell(trade.get("side")),
                    md_cell(trade.get("quantity")),
                    md_cell(trade.get("notional_usdt")),
                    md_cell(trade.get("entry_price")),
                    md_cell(trade.get("exit_price") or related_fill),
                    md_cell(related_mark),
                    md_cell(related_fee),
                    TODO,
                    md_cell(related_order or related_event_id),
                    TODO,
                ]
            )
            + " |"
        )
    if not trade_rows:
        trade_rows.append(
            "| "
            + " | ".join([TODO] * 15)
            + " |"
        )

    incident_rows = []
    for event in incidents:
        incident_rows.append(
            "| "
            + " | ".join(
                [
                    md_cell(event.get("ts")),
                    md_cell(event.get("event_type")),
                    md_cell(event.get("id")),
                    md_cell(json.dumps(event.get("payload"), ensure_ascii=False) if event.get("payload") is not None else None),
                ]
            )
            + " |"
        )
    if not incident_rows:
        incident_rows.append(f"| {TODO} | {TODO} | {TODO} | {TODO} |")

    return f"""# {args.strategy_id} Runner Tracking DRAFT

> 状态：`DRAFT` / pending human review。本文件由脚本生成，**未经人审不得作为门禁证据**。
>
> 家族：`{family_id}`
> 实例：`{args.instance_id}`
> 生成时间（UTC）：`{generated_at}`
> 生成命令：`{generated_cmd}`

## 源命令 / DB 快照

- 生成命令：`{generated_cmd}`
- Runner config：`{args.config}`
- Ledger DB：`{cell(ledger_db)}`
- status JSON：`{args.status_json}`
- trades JSON：`{args.trades_json}`
- events JSON：`{args.events_json}`

{sha256_table([args.status_json, args.trades_json, args.events_json])}

## 观察窗口

- observation label：`{args.window}`
- 健康更新时间：{md_cell(health.get("updated_at"))}
- 窗口起止（人工核对）：{TODO}

## Runner 配置摘要

- instance：`{args.instance_id}`
- strategy_id：`{args.strategy_id}`
- mode：{md_cell(health.get("mode"))}
- symbol：{md_cell(health.get("symbol"))}
- timeframe：{md_cell(health.get("timeframe"))}
- health status：{md_cell(health.get("status"))}
- position_open：{md_cell(health.get("position_open"))}
- kind / leverage / notional / 账户：{TODO}

## 信号 / bar 时间戳

- last_signal_ts：{md_cell(signal_ts)}
- last_bar_ts：{md_cell(bar_ts)}
- last_signal_side：{md_cell(health.get("last_signal_side"))}
- 事件 bar_ts 样本：{md_cell(", ".join(str(item) for item in event_bars[:8]) if event_bars else None)}
- signal 事件 ts 样本：{md_cell(", ".join(str(item) for item in event_signals[:8]) if event_signals else None)}

## 开平仓对账

交易行 `{len(trades)}`，其中已平仓 `{len(closed)}`。CLI `ledger-trades` 不输出 `signal_ts` / 费用 / 订单号；缺项写 {TODO}。

| trade_id | 预期回测入场 | 预期回测出场 | 实际开仓 ts | 实际平仓 ts | 方向 | 数量 | 名义 | 成交价（入） | 成交价（出） | 标记/参考价 | 费用 | 滑点估计 | 订单或事件 ID | match/mismatch |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
{chr(10).join(trade_rows)}

- 预期回测进出场：{TODO}
- 标记/参考价：{md_cell(mark_price)}
- 费用（fill 事件样本）：{md_cell(fill_fee)}
- 滑点估计 vs 回测假设：{TODO}
- 订单/事件 ID 样本：{md_cell(order_id)}
- 成交价样本：{md_cell(fill_price)}
- match/mismatch 结论：{TODO}

## 费用 / 滑点 vs 回测假设

- 实现费用：{md_cell(fill_fee)}
- 回测费用假设：{TODO}
- 实现滑点：{TODO}
- 回测滑点假设：{TODO}

## 信号 / 指标对拍偏差

{TODO}

## 事件（重启、缺 K、拒单）

Cycle errors：`{sum(1 for event in events if event.get("event_type") == "cycle_error")}`。

| 时间 | 事件类型 | 事件 ID | payload |
| --- | --- | --- | --- |
{chr(10).join(incident_rows)}

## keep / stop / adjust

- keep：
- stop：
- adjust：
"""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render a DRAFT runner-tracking Markdown report from ledger JSON."
    )
    parser.add_argument("--strategy-id", required=True)
    parser.add_argument("--instance-id", required=True)
    parser.add_argument("--family-id", default="")
    parser.add_argument("--window", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--status-json", type=Path, required=True)
    parser.add_argument("--trades-json", type=Path, required=True)
    parser.add_argument("--events-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--generated-command", default="")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(args), encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
