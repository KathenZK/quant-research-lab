# Binance-1D-Monthly-Cross-Sectional-Momentum-Long10 Core Ledger

## Family Identity

- Full name：`Binance-1D-Monthly-Cross-Sectional-Momentum-Long10`
- Alias：`BIN-1D-MCSM-L10`
- 市场：Binance USD-M USDT 永续；UTC 日 K 由 `15m` Vision 全市场月档聚合
- 机制：上一完整日历月收益排序，月初开盘等权 long Top10，总 gross 100%，不做空
- 防串线：不是 [`BIN-1D-MCSM-LS3`](../1d-monthly-cs-momentum-ls3/README.md) 的 3+3 多空，也不是外部现货美股/加密混合横截面；Binance 原生股票/TradFi 永续属于 Binance 合约池

## Current State

- 2026-09-24周Top10：2020-06-01至2026-07-01同起点73个月，每边费0.10%+滑点0.04%、不含资金费、条件终止估算。W7累计+64.51%、年化8.53%、回撤-97.42%；B0月频+925.13%、年化46.63%、回撤-95.43%。318次周榜、3,180腿及8个成本/终止情景独立复核，补齐BZRX/KEEP/COCOS/MEMEFI官方指数，未跳过下架交易。滑点0.08%时W7仅+32.84%；不加MA120、不采纳为实盘候选。旧76月和75月基线均复现，旧周频缺价状态保留为历史。精确结算、资金费、PIT及执行未认证。[报告](diagnostics/binance-1d-mcsm-weekly-top10-20260924.md) · [材料](artifacts/weekly-top10-20260924/README.md)

- 2026-09-11 MA120：用户指定上月Top10、月初价格高于120日均线才买、持有后日线收盘跌破次日00:15卖；空缺10%份额留现金。76月8账户及760入场/12,381持有日/173次退出独立核对。4bp价格+156.46%、年化16.03%、回撤-90.47%；含已有资金费估算+576.05%、年化35.23%、回撤-80.00%。原版收益完整重现；主要损失为入场漏掉大赢家，当前规则不实盘。只保留一个固定观察，不搜索均线长度。[规则](specs/binance-1d-mcsm-ma120-round-20260911.md) · [报告](diagnostics/binance-1d-mcsm-ma120-round-20260911.md) · [材料](artifacts/ma120-round-20260911/README.md)

- 2026-09-11新增研究：原四账户回撤/月年损益及X5/X10八账户已独立核对；76月、10万USDT、每边费0.1%加滑点0.04%，X5价格 **+2,991.81% / MDD-88.45%**、含观察资金费估算 **+14,080.41% / MDD-87.49%**；X10价格 **+200.68% / MDD-91.57%**、含费 **+231.89% / MDD-87.33%**。X5比S1多保住部分本金，但原盈利腿/最高76腿利润保留降至78.01%/82.58%，2022仍亏74.20%；只保留研究候选，不实盘。原含费基线最大回撤权益损失477.62万中，价格损失476.43万；资金净收5.76万，不是资金费造成该主要回撤。[报告](diagnostics/binance-1d-mcsm-drawdown-frequency-round-20260911.md) · [材料](artifacts/drawdown-frequency-round-20260911/README.md)
- 本轮频率实际结果：2020-04-01 00:15至2026-07-01 00:15 UTC，75月B0/M28、各4/8bp共四条价格账完成并独立核对，W28/W7的四条周频账因缺价停止。相同10万USDT、每边手续费0.1%与滑点0.04%、不含资金费，B0累计+1,428.03%/MDD-95.43%，月换仓28日榜M28累计+2,210.85%/MDD-96.51%。W7先缺BZRX、W28先缺KEEP，不能发布周频全期收益或认为周换更好；已核自动结算下架时点，仍不猜结算价。76月年表按00:15月账复利，区别于旧报告的00:00年界；75月表按自然月00:00、首尾00:15。原全期收益不因报表边界改变而重写。
- 当前主状态：`explore / diagnostic-only / not promoted / not live-ready`
- 最新机制轮（2026-09-10）：已实际完成三项固定问题。61个相似币可比月Top10价格月均差+6.59pp，但胜率49.18%、区间含0且风险匹配不完全；事前72h负资金费的同月总收益差-5.90pp，不加此入场门槛；单币20/7/2退出8账完成，4bp含费估算 **+13,663.98% / CAGR117.64% / MDD-91.92%**，对应原生价优先基线 **+10,084.17% / MDD-93.43%**。价格账户 **+1,679.84% / MDD-93.90%** 对原 **+912.33% / MDD-95.43%**。赢家利润保留改善，但2022年仍亏83.21%，只保留研究候选，不实盘。[主报告](diagnostics/binance-1d-mcsm-mechanism-round-20260910.md)
- 最新核查：2026-09-10 全部四账户用新独立算法复现，未发现资金方向、重复、数量单位或复利错误；同价格账户数量的直接资金净现金 +1,784,655.86 USDT。明确类型的官方 API 原文核到 16,211/97,421 笔，HTTP403 后停止采集，未完成全量来源验证。3,695 笔可得原生 mark 优先重算期末 **10,184,171.81 USDT（+10,084.17%）**，较原中心少 1,259.03 USDT，MDD 仍 -93.43%。[复核报告](diagnostics/binance-1d-mcsm-funding-recheck-20260910.md)
- 最新轮次：2026-09-09 已完成从 2020-03-01 00:15 至 2026-07-01 00:15 UTC 的 **76 月连续账户估算**，四条轨均从 100,000 USDT 独立复利并最终清仓。[本轮报告](diagnostics/binance-1d-mcsm-baseline-estimate-20260909.md) · [最终摘要](artifacts/baseline-estimate-20260909/accounts/summary.json)。状态 `EXPLORATORY_ESTIMATED_ACCOUNT_NOT_VERIFIED_NET`，不是精确净账通过。
- 固定口径：上一完整日历月 Top10、ADV30≥10m、原日桶端点/覆盖条件；每月成本后权益 10%/腿、其后数量固定、同名净额换仓，00:15 open 参考成交仅用此前已闭合活动，手续费每边 0.001、滑点 0.0004。未搜索退出、市场过滤或风险参数。
- 身份修正：官方证实旧 LIT=Litentry、新 LIT=Lighter，+322.47% 形成值是跨资产伪动量；AERGO 形成值跨旧合约结算及新上线。按原排序将 2026-01 LIT→Q（rank11）、2025-05 AERGO→LAYER（rank12），其他 **758 腿逐列不变**，新两形成段均完整有效；原 760 输入及修复前价格账保留，不能作为最终基线。[确定性修正契约](specs/baseline-estimate-identity-correction-20260909.md)
- 资金费边界：97,421 个观察事件，1,233 个原生 mark、96,188 个官方分钟代理；95,912 个 Unspecified 按明确模型假设视作 Regular。观察事件无 mark 缺口不等于完整资金日历，95,771 个事件在仅部分已证日历范围外。BNX/VIDT 使用条件指数估算结算价；全池 PIT、其他 30 个短零成交形成段及精确执行/保证金/强平仍未认证。
- 当前结论：中心估算利润为正且大幅高于价格对照；中心现金归因含价格 **+3,447,309.76**、资金费 **+6,870,939.50**、手续费 **-166,325.33**、滑点 **-66,493.09 USDT**。不能把差额全部归为趋势 Alpha，也不能把含资金账描述为只有 2021 年盈利：中心 2025 年 **+103.15%**、2026 上半年 **+409.26%**。最大回撤仍约 93%，未达到实盘可承受的证据状态。
- 下一步优先分开共同市场涨跌与领涨币自身延续，判断能否在不放弃大赢家的情况下减少共同下跌风险；带对冲的独立版本未运行、未授权生产。保留固定单币退出作为研究候选，不调20/7/2救历史曲线，不加负费率买入门槛。完整身份/资金日历及真实执行仍缺；旧引擎绩效仍 `PERFORMANCE_INVALIDATED`，2026-09-08严格净输入未验证的历史裁决保留。
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
| `2026-09-24 Weekly Top10 W7` | `PRICE_ACCOUNTS_AND_RANKING_AUDITED / NOT_LIVE_READY` | 上周榜、周一换仓、不加MA120；同73个月B0对照 | 4bp W7+64.51%/CAGR8.53%/MDD-97.42%；B0+925.13%/46.63%/-95.43%；8bp W7+32.84%；不含资金费 | [规则](specs/binance-1d-mcsm-weekly-top10-20260924.md) · [终止补充](specs/binance-1d-mcsm-weekly-top10-terminal-amendment-20260924.md) · [报告](diagnostics/binance-1d-mcsm-weekly-top10-20260924.md) · [独立核对](artifacts/weekly-top10-20260924/terminal-complete/independent-audit.json) | 未改善价格表现，不采纳为实盘候选；不把同时改形成期/持有期的差额解释成单一因果机制 |
| `2026-09-11 Top10 + MA120` | `RULE_AND_ACCOUNT_AUDITED / NOT_LIVE_READY` | 唯一用户指定120日均线入场及收盘跌破退出，现金不重新分配 | 76月4bp价格+156.46%/MDD-90.47%；含观察资金费+576.05%/MDD-80.00%；8bp价格+147.23%、含费+551.89%；最高76价格盈利腿利润保留48.65% | [规则](specs/binance-1d-mcsm-ma120-round-20260911.md) · [报告](diagnostics/binance-1d-mcsm-ma120-round-20260911.md) · [核对](artifacts/ma120-round-20260911/independent-audit.json) | 当前完整规则不实盘；主要利润损失发生在入场，尤其不足120日历史的强势币；不推论所有均线退出无效 |
| `2026-09-11 drawdown / breadth / frequency` | `BREADTH_AND_DRAWDOWN_AUDITED / FREQUENCY_4_COMPLETE_4_BLOCKED / NOT_LIVE_READY` | 真实现金回撤拆分；首次卖弱5/全篮子；月换/周换28日榜及周换7日榜 | 76月4bp X5含费+14,080.41%/MDD-87.49%、价格+2,991.81%/MDD-88.45%；X10含费+231.89%/MDD-87.33%；75月4bp价格B0+1,428.03%/MDD-95.43%、M28+2,210.85%/MDD-96.51%；W28/W7收益不可用 | [合同](specs/binance-1d-mcsm-drawdown-frequency-round-20260911.md) · [报告](diagnostics/binance-1d-mcsm-drawdown-frequency-round-20260911.md) · [材料](artifacts/drawdown-frequency-round-20260911/README.md) | X5只保留研究候选；X10利润保留差；月度M28风险未改善；四条周频账缺价停止，不填零、不改名单救结果 |
| `2026-09-10 three mechanism questions` | `REVEALED_HISTORY_DIAGNOSTIC / NOT_LIVE_READY` | 同月相似币对照、事前资金费、唯一单币退出；无参数搜索 | Top10月均差+6.59pp/61月；负费组总差-5.90pp/65月；退出含费+13,663.98%/MDD-91.92%，价格+1,679.84%/MDD-93.90%；8bp含费+12,977.37% | [合同](specs/binance-1d-mcsm-mechanism-round-20260910.md) · [报告](diagnostics/binance-1d-mcsm-mechanism-round-20260910.md) · [材料](artifacts/mechanism-round-20260910/README.md) | 不加负费入场门槛；退出保留研究候选，正腿96.03%/前76腿98.64%利润保留；2022仍-83.21%，不实盘 |
| `2026-09-10 funding return recheck` | `ACCOUNT_REPRODUCED / SOURCE_PARTIAL / NOT_VERIFIED_NET` | 不改策略的独立记账、官方事件复核及原生 mark 敏感性 | 原四轨复现；官方 API 16,211 笔；3,695 原生价优先 +10,084.17% / MDD-93.43%；未覆盖 API 81,210 笔 | [计划](specs/binance-1d-mcsm-funding-recheck-20260910.md) · [报告](diagnostics/binance-1d-mcsm-funding-recheck-20260910.md) · [新对照](artifacts/funding-recheck-20260910/native-replay/summary.json) | 含资金收益更高有账目与部分原文支持；不冒充全历史来源或实盘认证 |
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

- [2026-09-11 回撤来源、扩大退出与周频](diagnostics/binance-1d-mcsm-drawdown-frequency-round-20260911.md) · [逐月/年度/逐腿材料索引](artifacts/drawdown-frequency-round-20260911/README.md)
- [2026-09-10 三项机制研究与8账户](diagnostics/binance-1d-mcsm-mechanism-round-20260910.md)
- [2026-09-10 资金费收益差复核](diagnostics/binance-1d-mcsm-funding-recheck-20260910.md)
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
