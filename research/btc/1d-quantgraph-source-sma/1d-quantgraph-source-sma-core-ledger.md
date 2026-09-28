# BTC 1d QuantGraph PRICE_SMA Core Ledger

## Family Identity

- Full family name：BTC-1d-QuantGraph-PRICE_SMA。
- Market / exchange / symbol / timeframe：Bit2Me 报告的 spot / BTC/EUR / 1d；底层交易场所身份仍需进一步交叉核验。
- Mechanism：从锁定社区源码转录的显式只做多研究改编。原始摘要保留，不主张等同原生策略。
- Boundary：与既有 BTC/HYPE 家族独立；不继承它们的参数、行情或经济结论。

## Current State

- Current version(s)：无已登记 Vx；只有冻结研究约定。
- Current status：`explore / untrusted / not promoted / not live-ready`。
- Runner / dry-run / live：本轮均未触及、未申请。
- Blockers：原生 trade_count、完整报价量/VWAP 和可信闭合证据缺失；历史长度不足；没有 eligible 候选。
- Next gate：完整获准行情 + 来源/执行约定逐项确认，再运行正式研究。

## Version Rules

未登记 Vx。以后策略、时间框架、执行规则或成本变化均须新研究约定；不得追溯修改当前约定。
私有 raw 诊断不能当成版本登记指标或可晋级证据。

## Version Table

| Version | Status | Role / Core Idea | Key Frozen Metrics | Evidence | Decision / Live Readiness |
| --- | --- | --- | --- | --- | --- |
| 未登记 | explore / untrusted / not promoted / not live-ready | PRICE_SMA 来源改编诊断 | 无正式指标 | [冻结约定](specs/research-contract.json) | 数据门槛未通过 |

## Shared Assumptions

- 数据只在仓库数据湖；不补价格、不伪造原生成交笔数。
- EUR 现金账户，1x；每边手续费 60 bps、滑点 10 bps，均为研究假设。
- 闭合栏计算、下一栏开盘；spot 无 funding，现金利息为 0。
- 来源条件、信号、完整参数网格和止损规则以冻结 JSON 为准。

## Evidence Map

- [冻结约定](specs/research-contract.json) · [决策记录](decision-log.md) · [运行脚本](scripts/README.md)。
- 本机私有结果在 artifacts；行情及其衍生结果不随 PR 分发。
- 没有 live spec、runner tracking 或 live approval。

## What Not To Put Here

不粘贴全量源码、行情、参数表或收益序列；不把单一市场的诊断变成盈利证明。

## V4 证据链复核

2026-09-28：新合同固定字节摘要、完整覆盖和已审核许可。三项机制仍未通过行情准入；只生成私有 diagnostic，不登记新版本。最近证据：[V4 合同](specs/research-contract-v4.json)；本机 `artifacts/20260928-v4-chain-acceptance/`。
