# Binance-1D-Medium-Term-Trend-Capture Core Ledger

## Family Identity

- Binance-1D-Medium-Term-Trend-Capture；BIN-1D-MTTC；Binance观测COIN永续日线。
- 同一趋势候选下比较立即入场20日、立即入场趋势退出、等待回撤恢复后趋势退出。
- 独立于TSPR/MTCS；这些旧研究提供问题背景，不提供本轮行情事实或有效性结论。

## Current State

- explore / diagnostic-only / not promoted / not live-ready；2026-09-09一轮研究已完成。
- 本轮研究筛选HARD-GATE-FAILED：三者最大回撤均超过事前30%上限；均值与两项改善的联合区间均包含0。有效性判断INSUFFICIENT_EVIDENCE，不是整个中期趋势假设的否定。
- 无runner部署、交易、自动监控或注册策略版本。
- 尚缺全历史身份/资金费完整证明和真正未读数据检验；研究中分开报告这些限制。

## Version Rules

- 本轮为研究观察；实现与规则在收益前固定，发现错误保留修订记录，不按结果加参数。
- 版本登记及上线均需另外授权，本轮不自动登记Vx。

## Version Table

| 观察 | 状态 | 作用 | 证据 | 决策 |
| --- | --- | --- | --- | --- |
| 2026-09-09三种完整做法 | explore / diagnostic-only / not promoted / not live-ready | 1658候选、1561共同完整机会、4档成本共12个账户；独立复算完成 | [规则](specs/research-contract.md) · [结果](diagnostics/research-report-20260909.md) | 没有合格实现；保留A简单参照，B改善尚未证明，C不作必须条件；下一步先补信号参照，再分别检验仓位增长和浮盈回吐 |

## Shared Assumptions

- 固定V3日线至2026-09-05 00:00 UTC；全部历史重复使用，不能称作新验证。
- 多头、无杠杆、最多10槽；每次成交手续费0.001、不利滑点0.0004及压力档。
- 收盘决策下一开盘执行；资金费缺失不补零，不虚构最后结算成交。

## Evidence Map

- [合同](specs/research-contract.md) · [配置](specs/config.json) · [决策记录](decision-log.md)
- [本轮报告](diagnostics/research-report-20260909.md) · [完成清单](artifacts/research-20260909/completed.json)
- [时序与资金独立复算](artifacts/audit-research-20260909/receipt.json) · [统计独立复算](artifacts/statistics-independent.json) · [资金费覆盖](artifacts/funding/summary.json)
- 规则及实现于2026-09-09T08:42:35.823563+00:00固定，[清单](specs/computation-lock.json)SHA256为cad616654fe49494c88db4aaccf1bc5dbc2570b7e9662ea9f6b961d12c5bdae6；收益计算结束再次核对，未按结果改规则。
- 三套基础账户累计+260.6%/+451.4%/+290.7%，最大回撤41.7%/46.0%/42.6%，均为2019-09-09至2026-09-05 UTC、每次0.1%手续费与0.04%滑点后的价格账户，未含完整资金费。
- 资金费：1561个共同机会中0个有完整实际标记价现金，24个BTC/ETH机会可做明确标记的日线价格近似；不能视为全历史费用通过。
