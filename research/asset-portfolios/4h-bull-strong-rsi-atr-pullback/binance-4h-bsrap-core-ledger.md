# Binance-4H-Bull-Strong-RSI-ATR-Pullback Core Ledger

## Family Identity

- Full name / alias：`Binance-4H-Bull-Strong-RSI-ATR-Pullback` / `BIN-4H-BSRAP`。
- Binance USDT perp / 4H / long-only；牛市、强势、RSI超卖、ATR下降，SMA7−2ATR移动止损。
- 新独立家族，不继承其他研究的身份、指标或结论。

## Current State

- `explore / diagnostic-only / HARD-GATE-FAILED / not promoted / not live-ready`；无注册版本、无runner。
- 当前 P1：牛市条件有回顾性收益分层，强势前20%没有稳定同日增量；四种MA7−2ATR入场回放价格贡献均负。P0及其失败结论保留。
- 下一门：冻结本轮规则，市场分层仅支持继续未来验证；不在已揭示历史上继续搜参。历史身份、funding、实际资金及执行门禁仍未通过；P1受限预算只属于条件性价格诊断，未来验证尚未开始。

## Version Rules

- P0/P1为独立研究观察，不是V1；P1修改识别与入场资格定义，不覆盖P0。用户要求登记时另按规范固定版本。

## Version Table

| 观察 | 状态 | 作用 | 证据 | 决定 |
| --- | --- | --- | --- | --- |
| P0 | explore / diagnostic-only / HARD-GATE-FAILED | 主规则247笔成本后未扣funding均值−1.41%，中位数−3.40%；点名52笔+2.65% | [报告](diagnostics/p0-results-2026-09-07.md) · [验算](artifacts/p0-20260907/acceptance.json) | 固定规则继续筛查失败；不登记、不晋升 |
| P1 | explore / diagnostic-only / HARD-GATE-FAILED | 7日牛市+2.60%、全时期+0.32%；同日强势增量+0.031个百分点，区间含0；四种入场价格贡献均负，均未扣funding | [报告](diagnostics/p1-market-strength-entry-2026-09-07.md) · [验算](artifacts/p1-20260907/p1-acceptance.json) | 市场继续研究筛查通过，强势失败；整体不是可用策略，不登记、不晋升 |

## Shared Assumptions

- 输入组合 v2、4H价格v2，严格闭合、分段预热、下一开盘入场。
- 每边手续费0.1%、滑点4bps/8bps；资金费率未验证，只准价格诊断。

## Evidence Map

- [契约](specs/p0-contract.md) · [配置](specs/p0-config.json) · [请求](specs/startup-price-p0.json)
- [产物索引](artifacts/README.md)

- [P0报告](diagnostics/p0-results-2026-09-07.md) · [逐笔交易](artifacts/p0-20260907/trades.csv) · [结果清单](artifacts/p0-20260907/result-manifest.json)
- [P1契约](specs/p1-contract.md) · [事前哈希](specs/p1-prefit-hashes.json) · [P0保护](specs/p1-parent-protection.json)
- [P1报告](diagnostics/p1-market-strength-entry-2026-09-07.md) · [筛查与区间](artifacts/p1-20260907/p1-state-inference.json) · [交付清单](artifacts/p1-20260907/p1-delivery-manifest.json)
