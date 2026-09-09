# Binance-1D-Monthly-Cross-Sectional-Momentum-Long10 Core Ledger

## Family Identity

- Full name：`Binance-1D-Monthly-Cross-Sectional-Momentum-Long10`
- Alias：`BIN-1D-MCSM-L10`
- 市场：Binance USD-M USDT 永续；UTC 日 K 由 `15m` Vision 全市场月档聚合
- 机制：上一完整日历月收益排序，月初开盘等权 long Top10，总 gross 100%，不做空
- 防串线：不是 [`BIN-1D-MCSM-LS3`](../1d-monthly-cs-momentum-ls3/README.md) 的 3+3 多空，也不是外部现货美股/加密混合横截面；Binance 原生股票/TradFi 永续属于 Binance 合约池

## Current State

- 当前主状态：`explore / diagnostic-only / not promoted / not live-ready`
- 最新轮次：2026-09-09 已完成从 2020-03-01 00:15 至 2026-07-01 00:15 UTC 的 **76 月连续账户估算**，四条轨均从 100,000 USDT 独立复利并最终清仓。[本轮报告](diagnostics/binance-1d-mcsm-baseline-estimate-20260909.md) · [最终摘要](artifacts/baseline-estimate-20260909/accounts/summary.json)。状态 `EXPLORATORY_ESTIMATED_ACCOUNT_NOT_VERIFIED_NET`，不是精确净账通过。
- 固定口径：上一完整日历月 Top10、ADV30≥10m、原日桶端点/覆盖条件；每月成本后权益 10%/腿、其后数量固定、同名净额换仓，00:15 open 参考成交仅用此前已闭合活动，手续费每边 0.001、滑点 0.0004。未搜索退出、市场过滤或风险参数。
- 身份修正：官方证实旧 LIT=Litentry、新 LIT=Lighter，+322.47% 形成值是跨资产伪动量；AERGO 形成值跨旧合约结算及新上线。按原排序将 2026-01 LIT→Q（rank11）、2025-05 AERGO→LAYER（rank12），其他 **758 腿逐列不变**，新两形成段均完整有效；原 760 输入及修复前价格账保留，不能作为最终基线。[确定性修正契约](specs/baseline-estimate-identity-correction-20260909.md)
- 资金费边界：97,421 个观察事件，1,233 个原生 mark、96,188 个官方分钟代理；95,912 个 Unspecified 按明确模型假设视作 Regular。观察事件无 mark 缺口不等于完整资金日历，95,771 个事件在仅部分已证日历范围外。BNX/VIDT 使用条件指数估算结算价；全池 PIT、其他 30 个短零成交形成段及精确执行/保证金/强平仍未认证。
- 当前结论：中心估算利润为正且大幅高于价格对照；中心现金归因含价格 **+3,447,309.76**、资金费 **+6,870,939.50**、手续费 **-166,325.33**、滑点 **-66,493.09 USDT**。不能把差额全部归为趋势 Alpha，也不能把含资金账描述为只有 2021 年盈利：中心 2025 年 **+103.15%**、2026 上半年 **+409.26%**。最大回撤仍约 93%，未达到实盘可承受的证据状态。
- 下一步须围绕赚钱效应/趋势与资金费来源分开验证、完整身份/事件日历及可执行账户做有限研究，不恢复无边界参数搜索。旧引擎绩效仍 `PERFORMANCE_INVALIDATED`，本轮不晋升、不交接生产；2026-09-08 严格基线未验证的历史裁决保留。
- 前轮机制裁决保持：固定数量、24h 延迟价格诊断的双弱退出损害利润保留，不采纳；该结论不是完整账户收益或对所有机制的否定。

### 2026-09-09 冻结四场景结果

| 场景 | 最终权益（USDT） | 总收益 | CAGR | 最大回撤（日末及换仓边界） |
| --- | ---: | ---: | ---: | ---: |
| price_only，不含资金费的反事实 | 1,012,334.94 | +912.33% | 44.13% | -95.43% |
| estimated_center | 10,185,430.84 | +10,085.43% | 107.53% | -93.43% |
| estimated_adverse | 9,747,715.89 | +9,647.72% | 106.10% | -93.44% |
| estimated_favorable | 10,299,465.57 | +10,199.47% | 107.90% | -93.43% |

三条资金费场景分别用自身权益确定月初数量；其范围只是已观察事件及指定代理价的条件情景，不是实际净收益的数学上下界或置信区间。回撤不含日内极值；中心最高采样 gross/equity 为 **1.1307x**，月初目标 1x 不代表月内永远不超过 1x。

## Version Rules

- 当前没有注册版本；本轮只按用户字面规则做诊断。
- 改形成期、Top N、波动目标或市场范围均是新 observation 或独立家族，不继承本轮绩效。加入外部现货美股需另建跨市场家族；Binance 原生股票/TradFi 永续已经按同一合约资格规则纳入。

## Version Table

| Observation | Status | Role | Key Frozen Metrics | Evidence | Decision |
| --- | --- | --- | --- | --- | --- |
| `2026-09-09 baseline estimate / identity corrected` | `EXPLORATORY_ESTIMATED_ACCOUNT_NOT_VERIFIED_NET` | 原规则连续现金估算；两处官方身份错误按原排序修复 | 76 月；中心 +10,085.43% / CAGR107.53% / MDD-93.43%；价格对照 +912.33%；资金不利/有利 +9,647.72%/+10,199.47% | [契约](specs/binance-1d-mcsm-baseline-estimate-20260909.md) · [身份修正](specs/baseline-estimate-identity-correction-20260909.md) · [报告](diagnostics/binance-1d-mcsm-baseline-estimate-20260909.md) · [摘要](artifacts/baseline-estimate-20260909/accounts/summary.json) | 估算获利不等于净输入/Alpha验证；旧绩效仍失效；不晋升 |
| `2026-09-08 baseline verification` | `BASELINE_NOT_VERIFIED` | 原规则端点与固定数量现金账核验，不做策略优化 | 完整净账 0/76 月；首日原十币官方 mark 空；1,235 个近期 mark 补回；35 项现金测试 | [契约](specs/binance-1d-mcsm-baseline-verification-20260908.md) · [报告](diagnostics/binance-1d-mcsm-baseline-verification-20260908.md) · [摘要](artifacts/baseline-verification-20260908/summary.json) | 不发布净收益；估算账待精度选择；不晋升 |
| `2026-09-08 lifecycle / funding` | `diagnostic-only / net invalid` | 旧会计复现、官方费率核验、固定数量日级 first-event | 官方 3 币 1,235 个事件费率一致；68 月退出配对均差 -4.01pp，正利润/上尾保留 67.21%/77.35% | [契约](specs/binance-1d-mcsm-lifecycle-funding-round-20260908.md) · [报告](diagnostics/binance-1d-mcsm-lifecycle-funding-round-20260908.md) · [摘要](artifacts/lifecycle-diagnostic-20260908/summary.json) | 双弱清仓不采纳；不是新账户净值；不晋升 |
| `2026-08-18 diagnostic` | `explore / diagnostic-only` | Binance 月频 1M Top10 long-only | 全上市 `+2402.97%` / CAGR `66.31%` / MDD `-93.79%`；ADV 版 `+2104.80%` / MDD `-92.99%` | [契约](specs/binance-1d-mcsm-long10-diagnostic-contract-2026-08-18.md) · [诊断](diagnostics/binance-1d-mcsm-long10-diagnostic-2026-08-18.md) | 不登记、不晋升 |
| `2026-08-19 breadth diagnostic` | `explore / diagnostic-only` | Binance 月频 1M Top10/20/30/40/50 long-only | 共同窗口中 Top10 仍最高；宽度增加时收益单调衰减，MDD 仍为 `-87%` 至 `-94%` | [契约](specs/binance-1d-mcsm-long-breadth-diagnostic-contract-2026-08-19.md) · [诊断](diagnostics/binance-1d-mcsm-long-breadth-diagnostic-2026-08-19.md) | 不登记、不晋升 |
| `2026-08-19 risk-buffer diagnostic` | `explore / diagnostic-only` | Top10 + 20% 组合目标波动、无杠杆；再加 10/20 缓冲 | 全上市 target20 `+217.36%` / CAGR `20.01%` / MDD `-42.33%`；缓冲后 `+199.18%` / MDD `-42.55%` | [契约](specs/binance-1d-mcsm-long10-risk-buffer-diagnostic-contract-2026-08-19.md) · [诊断](diagnostics/binance-1d-mcsm-long10-risk-buffer-diagnostic-2026-08-19.md) | 风险缩放有效；缓冲不改善；不登记、不晋升 |
| `2026-08-19 positive-cash diagnostic` | `explore / diagnostic-only` | Top10 仅买形成收益>0的名字，每槽10%，缺口现金 | 全上市 target20 `+245.39%` / MDD `-41.61%`；ADV target20 `+218.78%` / MDD `-40.56%` | [契约](specs/binance-1d-mcsm-long10-positive-cash-diagnostic-contract-2026-08-19.md) · [诊断](diagnostics/binance-1d-mcsm-long10-positive-cash-diagnostic-2026-08-19.md) | 单宇宙小幅改善、跨宇宙不稳健；不登记、不晋升 |
| `2026-08-20 liveability diagnostic` | `explore / diagnostic-only` | BTC SMA200 gate、MH136、target12 风险预算 | gate 与 MH136 失败；target12 旧引擎 `+94.82%` / Sharpe `0.906` / MDD `-25.073%`，但完整 12m cohort 仅 `2/5` 为正 | [冻结合同](specs/binance-1d-mcsm-long10-liveability-candidate-contract-2026-08-20.md) · [审计](diagnostics/binance-1d-mcsm-long10-liveability-audit-2026-08-20.md) | target12 仅保留假设；不登记、不晋升 |
| `2026-08-20 execution audit` | `HARD_BLOCKER / PERFORMANCE_INVALIDATED` | 真实 15m、`00:15 UTC` 入场/退出/估值审计 | 原路径 41 个 blocker；可成交重选后仍 15 个 | [修复合同](specs/binance-1d-mcsm-long10-execution-repair-contract-2026-08-20.md) · [blockers](artifacts/binance-1d-mcsm-long10-target12-execution-timing-2026-08-20-blockers.csv) | 旧绩效失效；停止 promotion |
| `2026-08-20 money-effect diagnostic` | `explore / diagnostic-only` | 月度赚钱效应 breadth × leader continuation 冻结 2×2 状态 | `strong/strong` 月均超额 `+12.16%`、胜率 `55.6%`，但完整价格正 PnL/右尾捕获仅 `42.0%/40.1%`，完整 12m cohort 仅 `1/4` 为正 | [合同](specs/binance-1d-mcsm-money-effect-continuation-diagnostic-contract-2026-08-20.md) · [诊断](diagnostics/binance-1d-mcsm-money-effect-continuation-diagnostic-2026-08-20.md) | 方向部分成立，月频 gate 失败；不登记、不晋升 |

## 历史口径（不替代各轮契约）

- 信号只使用已闭合上月数据；原“月初 `00:00` 开盘成交”已被执行审计否决，旧 `00:15` 诊断还使用了该 bar 完成后才可知的成交量，不能视为时序已修复。2026-09-08 生命周期轮另用统一 24h 延迟价格诊断；2026-09-09 估算明确只用前一闭合 bar 活动及 00:15 open 参考价，二者均不反改旧结果。
- Binance 每边手续费 `0.001`、滑点 `4 bps`，逐日资金费；末日收盘平仓。
- 全市场月档 `2020-01`–`2026-06`，评估 `2020-03-01`–`2026-06-30`；线性 PnL，不模拟强平。

## Evidence Map

- [2026-09-09 连续账户估算及身份修正报告](diagnostics/binance-1d-mcsm-baseline-estimate-20260909.md)
- [最终四场景现金账户摘要](artifacts/baseline-estimate-20260909/accounts/summary.json)
- [修正版输入、执行端点和形成连续段](artifacts/baseline-estimate-20260909/inputs-identity-corrected/README.md)
- [两处身份错误的官方原文与哈希](artifacts/baseline-estimate-20260909/inputs/selection-appendix/identity-sources/README.md)
- [修正版观察资金费输入](artifacts/baseline-estimate-20260909/funding-identity-corrected/summary.json)
- [最终 QA、独立现金复算与全仓检查边界](notes/baseline-estimate-qa-20260909.md)
- [2026-09-08 基线验证与明确阻断事件](diagnostics/binance-1d-mcsm-baseline-verification-20260908.md)
- [资金费结算 mark 可获得性](diagnostics/baseline-funding-mark-availability-20260908.md)
- [官方终止事件与结算边界](notes/baseline-terminal-evidence-20260908.md)
- [2026-09-08 生命周期与资金费主报告](diagnostics/binance-1d-mcsm-lifecycle-funding-round-20260908.md)
- [2026-09-08 官方资金费及旧记账审计](diagnostics/funding-source-20260908.md)
- [诊断契约](specs/binance-1d-mcsm-long10-diagnostic-contract-2026-08-18.md)
- [诊断报告](diagnostics/binance-1d-mcsm-long10-diagnostic-2026-08-18.md)
- [宽度诊断](diagnostics/binance-1d-mcsm-long-breadth-diagnostic-2026-08-19.md)
- [风险与缓冲诊断](diagnostics/binance-1d-mcsm-long10-risk-buffer-diagnostic-2026-08-19.md)
- [正收益与现金缺口诊断](diagnostics/binance-1d-mcsm-long10-positive-cash-diagnostic-2026-08-19.md)
- [可实盘化与执行审计](diagnostics/binance-1d-mcsm-long10-liveability-audit-2026-08-20.md)
- [赚钱效应与领涨延续诊断](diagnostics/binance-1d-mcsm-money-effect-continuation-diagnostic-2026-08-20.md)
- [执行语义修复合同](specs/binance-1d-mcsm-long10-execution-repair-contract-2026-08-20.md)
- [Artifacts](artifacts/README.md)
- [Scripts](scripts/README.md)
