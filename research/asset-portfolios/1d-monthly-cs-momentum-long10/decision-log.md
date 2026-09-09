# Decision Log

## 2026-09-09 — 补出连续估算账户；修复身份错误，保持未验证净收益状态

按用户要求不再只报告精确源 blocker，事前冻结四条独立估算轨，完成 2020-03 至 2026-06 的 76 月固定数量现金账。100,000 USDT 的最终价格对照为 **1,012,334.94（+912.33%）**；含观察资金费的中心/不利/有利分别为 **10,185,430.84（+10,085.43%）/ 9,747,715.89（+9,647.72%）/ 10,299,465.57（+10,199.47%）USDT**。中心 CAGR107.53%、日末及换仓边界 MDD **-93.43%**，价格对照 MDD **-95.43%**。四轨均明确标为 `EXPLORATORY_ESTIMATED_ACCOUNT_NOT_VERIFIED_NET`，不是精确净基线、上下界证明或实盘批准。

在首个价格账之后、含资金费账户之前，四份官方公告确证两处输入身份错误：LIT 形成期把已终止 Litentry 与新 Lighter 相除，属于跨资产伪动量；AERGO 则跨旧合约结算和新上线。原规则不允许把不同身份或已经终止合约的占位值当正常形成起点，故先冻结确定性修正，按既有排名替补 2025-05 LAYER（rank12）及 2026-01 Q（rank11），其他 758 腿逐列不变。替补的两个形成期分别 2,881/2,977 根完整有效 15m bar，均无缺失、无零成交、单连续段；不按替补未来收益选币。原输入、修复前 +932.52% 价格账及审计保留作对照，**不作最终基线**。修复后四轨各自重算月初数量；没有直接加减旧两腿损益。

97,421 个观察资金事件均有原生或明确分钟代理 mark，但其中只有 1,233 个原生 mark、96,188 个代理，95,912 条源类型 Unspecified 按已冻结假设记 Regular；完整日历与全池 PIT 尚未证明，BNX/VIDT 结算价仍为条件估算。中心资金现金 **+6,870,939.50 USDT**，是总账重大来源，不能全部解释成趋势延续 Alpha。也不将价格账的 2021 年集中度叙事套到含资金账：中心 2025 年 +103.15%、2026 上半年 +409.26%。此前双弱整篮子退出不采纳的结论不变，本轮不搜索参数或晋升。

冻结输入/源未改；只补本轮 identity 审计与修正构建器的读取登记。全仓检查仍有 6 个其他家族未登记 reader，以及其他家族分类/共享内核的既有失败，不声称全仓通过。家族本地 artifacts 已约 **1.0 GiB**，达到 `C-externalize`：官方原文、可再生分钟数据和账户明细仅本地保留本轮证据，Git 仅保留文档/获准小型锚点；下一次新增整套大产物前须另作可逆外置/LFS 评估。未获迁移授权，本轮不删除、不搬移、不重复复制源数据。

证据：[主报告](diagnostics/binance-1d-mcsm-baseline-estimate-20260909.md)、[冻结估算契约](specs/binance-1d-mcsm-baseline-estimate-20260909.md)、[身份修正](specs/baseline-estimate-identity-correction-20260909.md)、[四场景最终摘要](artifacts/baseline-estimate-20260909/accounts/summary.json)、[输入](artifacts/baseline-estimate-20260909/inputs-identity-corrected/README.md)、[资金源](artifacts/baseline-estimate-20260909/funding-identity-corrected/summary.json)。旧绩效仍 `PERFORMANCE_INVALIDATED`；前日 `BASELINE_NOT_VERIFIED` 的精确输入裁决原样保留，估算不推翻该精度边界。

## 2026-09-08 — 先验证基线；源端缺精确 mark，未发布净收益

用户要求停止绕开盈利问题的机制扩展，先核固定规则连续账户。独立现金内核完成 35 项测试，首月参考建仓及真实空 mark 事件拒绝实证通过；初稿错误复用完整日 K 而漏 ADA 的 Top9 计划已拒绝，原 15m 部分上市日端点恢复。没有按该错误提名计算收益。

官方数据实质补回 HOME/LAB/H 2026-06 全部 1,235 个事件 mark；但原首月十币 2020-03-01 08:00 的官方 mark 全空，最早持仓日无法精确核资金现金。五个终止公告区分了 BNX/VIDT 持有中结算和 ALPACA/FRONT/LOKA 终止后错误新仓。全 76 月原信号/历史资格、完整资金日历和精确终止价仍未完成。

裁决 `BASELINE_NOT_VERIFIED`，净账完成 0/76 月，收益 null，旧绩效仍 `PERFORMANCE_INVALIDATED`；不能宣称盈利或亏损。下一步只考虑事前明确精度的估算基线或继续补精确源值，估算尚未授权及运行，不转回搜索退出/风控参数。证据：[主报告](diagnostics/binance-1d-mcsm-baseline-verification-20260908.md)、[契约](specs/binance-1d-mcsm-baseline-verification-20260908.md)、[主摘要](artifacts/baseline-verification-20260908/summary.json)。原摘要保留首次内核 hash，Regular/Special 修订另留同事件重验收据；不改旧材料、数据湖或生产。

## 2026-09-08 — 核实负费率来源，统一两条证据轨；否决双弱整篮子退出

按用户批准继续一轮机制研究，未搜索参数、未改旧引擎或生产服务。官方 HOME/LAB/H 2026-06 月档及 CHECKSUM 支持极端负费率原值；但资金金额缺 mark/日历/PIT，旧“净值”仍失效。原每天固定权重与固定数量的会计差异能改变月度盈亏方向，分别留存原账复现与新的 V3 固定数量价格诊断，不混用总收益。

事前冻结的日级 breadth7/leader7 双弱首次触发清仓，在 68 个完整配对月平均损失 4.01pp，错过上涨约为避损 1.94 倍，正利润只保留 67.21%，逐年剔除均不能改变总体负差；因此该具体退出表达不采纳，不事后调窗口救援。未来工作优先固定数量现金账、事件资金费和单腿赢家生命周期，不把周尺度回撤直接等同于趋势结束。本轮仍 `diagnostic-only / not promoted / not live-ready`；缺失月份不连乘账户净值。

证据：[主报告](diagnostics/binance-1d-mcsm-lifecycle-funding-round-20260908.md)、[契约](specs/binance-1d-mcsm-lifecycle-funding-round-20260908.md)、[摘要](artifacts/lifecycle-diagnostic-20260908/summary.json)、[官方源审计](diagnostics/funding-source-20260908.md)。17.18 MiB 返回日线投影仅本地保留供逐标的哈希/窗口审计，可由固定请求重建，不进入普通 Git；未移动或删除旧材料。

## 2026-08-18 — 建立独立 Long10 诊断，不继承 LS3 身份

按用户字面规则建立 Binance 月频 Top10 long-only 家族。全历史收益显著为正，但最大回撤超过 92%、年度集中且峰值尚未完全恢复，因此不登记、不晋升；证据见[诊断](diagnostics/binance-1d-mcsm-long10-diagnostic-2026-08-18.md)。外部现货美股混合版本因缺少点时全市场数据未运行；Binance 原生股票/TradFi 永续本来就属于本回测合约池。

## 2026-08-19 — Top10/20/30/40/50 宽度诊断与股票永续审计

按用户指定的五个宽度运行全上市与 `ADV≥1000万` 两个宇宙。共同起点 `2020-12-01` 后，收益与 Sharpe 随 Top N 扩大整体下降，Top10 仍为本次已揭示扫描中的历史最优宽度；但它依旧有约 `-93%` 回撤，不登记、不晋升。点时持仓审计确认 `MU` 在 `2026-06` 被所有 Top N 组合持有；`SNDK` 和 `SKHYNIX` 因形成期历史不足未入选，而非被资产类别过滤。证据见[宽度诊断](diagnostics/binance-1d-mcsm-long-breadth-diagnostic-2026-08-19.md)。

## 2026-08-19 — 固定 20% 波动目标有效，10/20 缓冲不采纳为改善

用户事前固定的 20% 组合目标波动将全上市 MDD 从 `-93.79%` 降至 `-42.33%`，但 10/20 缓冲只把年化换手从 `4.58x` 降至 `4.17x`，同时降低 CAGR/Sharpe 且未改善 MDD；本轮只保留诊断，不登记、不晋升。证据见[风险与缓冲诊断](diagnostics/binance-1d-mcsm-long10-risk-buffer-diagnostic-2026-08-19.md)。

## 2026-08-19 — 正收益限定仅局部改善，不登记

Top10 全部不大于零只出现1个月；正收益限定使全上市 target20 的 CAGR/MDD 小幅改善，但 ADV target20 的 Sharpe、MDD与水下期反而变差，未形成跨宇宙一致证据。停止门槛搜索，不登记、不晋升；证据见[正收益与现金缺口诊断](diagnostics/binance-1d-mcsm-long10-positive-cash-diagnostic-2026-08-19.md)。

## 2026-08-20 — BTC 市场 gate 与 MH136 均不采纳

事前冻结的 `BTC SMA200 + target15 + 月中退出` 未过 Sharpe、CAGR和后段 MDD 参考线，删除月中退出反而更好；`1M/3M/6M` 等资本袖套未过 Sharpe、MDD和 12m cohort 门禁，且删除 6M 后整体改善。两个机制均停止，不从 SMA 邻域或袖套消融中挑 winner，不登记、不晋升；证据见[可实盘化审计](diagnostics/binance-1d-mcsm-long10-liveability-audit-2026-08-20.md)。

## 2026-08-20 — target12 只保留为风险预算假设

原 `ADV Top10` 信号的无杠杆 `target12` 在旧引擎中接近风险参考线，但五个完整 12m cohort 只有两个为正。`12%` 不作为新增 alpha、不回扫相邻风险目标，也不构成 promotion；只有执行修复后才允许按原冻结值重跑。

## 2026-08-20 — 执行审计使既有绩效失效

真实 15m 审计发现原 `00:00` 同 bar 成交不可因果复现，并存在零成交占位 K 线入场、不可成交退出和持仓缺价被 `.fillna(0)` 静默成零收益。原 target12 路径有 41 个 blocker，按 `00:15 UTC` 可成交入选后仍有 15 个；裁决为 `HARD_BLOCKER / PERFORMANCE_INVALIDATED`。已冻结[执行语义修复合同](specs/binance-1d-mcsm-long10-execution-repair-contract-2026-08-20.md)，四类 blocker 清零前停止一切 promotion、runner handoff 和参数搜索。

## 2026-08-20 — 赚钱效应方向部分成立，但月频 2×2 状态失败

按用户纠正后的目标，停止以 MDD 为主的 gate/波动率搜索，冻结诊断 Binance breadth、市场收益中位数、leader spread、3M strength、流动性与 rank alignment。`strong/strong` 的下一月平均 Top10 超额为 `+12.16%`，且超额从入场后 1 日持续累积到月末，支持“赚钱效应扩散 + 领涨延续”方向；但它在完整价格标签中只捕获 `42.0%` 正 PnL和 `40.1%` 固定右尾 PnL，四个完整 12m cohort 仅一个为正。原利润来自广谱牛市 beta、V 型赚钱效应启动和窄幅 leader continuation 三类稀疏 episode，月初一次性 AND gate 无法统一捕获。冻结候选失败，不改 OR gate、不删特征救援；post-reveal 的 leader-strong 消融只作归因，不登记。证据见[赚钱效应与领涨延续诊断](diagnostics/binance-1d-mcsm-money-effect-continuation-diagnostic-2026-08-20.md)。
