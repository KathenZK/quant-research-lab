# A 线独立验收（2026-09-09）

审计对象：`/Users/ZK/.codex/worktrees/5f41/quant-strategy-lab/research/asset-portfolios/1d-small-account-slow-trend/`，完整家族 `Multi-Asset-1D-Small-Account-Slow-Trend`，别名 `XA-1D-SAST`。

审计范围：契约与补充、原生快照及指纹、数据解析、趋势/风险信号、整数股与资金结算、分红应收、费用和成交时序、报告及跨线总报告。未下载数据，未训练，未下单，未运行会覆盖原产物的 `verify_all.py`、`reproduce.sh` 或原目录主程序。所有新测试及重算输出位于 `/tmp/three-line-a-review-20260909/`；原家族文件未修改。

## 总裁决

**CONDITIONAL_DIAGNOSTIC_ACCEPTANCE — 接受这是一项已完成、可复算的条件账户诊断；不接受为真实可执行收益或已经合格的长期策略。**

- 原冻结口径下，主趋势 CAGR **3.6507837548%**、日收盘最大回撤 **14.5018734706%**、终值 **$14,065.5952151**可以从原生数据和导出交易账本独立重建。
- 同一事前缩仓规则的静态对照 CAGR **6.0590266850%**、最大回撤 **18.5746860485%**可以复算。
- 主规则少约 **2.4082pp CAGR**、回撤少约 **4.0728pp**，满足回撤改善但超过事前最多牺牲 1pp CAGR 的限制。因此 `NO_GO_PREDECLARED_ECONOMIC_INCREMENT` **在原条件与事前取舍门槛下成立**。
- 没有发现足以推翻这个狭义裁决的重大计算错误。结论应保持“未满足事前收益/风险取舍”，不能扩为统计证明所有慢趋势或 12M 规则都没有价值。
- 静态组合优先是看到结果后的资源配置建议，文件已披露这一点；它不是新的 OOS 胜者，也不是已经合格的实盘候选。

## 独立验证做了什么

新脚本没有导入原策略引擎，从留存 Yahoo 原始 JSON 重建未分红复权 OHLC、显式分配、总回报指数，再核对全部 12 个导出账户：

1. 契约、数据准入补充及七个 raw 文件 SHA256 匹配；全产物清单 **0 个指纹不匹配**。
2. 每只 ETF 有效段均 **2706 个交易日**，与 XNYS 日历对齐；有效段没有零成交、重复或非有限价；raw 与导出 OHLC 最大差约 **4.85e-10 美元**，分配差为 0。
3. 核对全部订单的整数数量、方向、先信号后成交、数量决策早于成交、原生开盘代理、不利滑点、最低佣金、T+3/T+2/T+1 结算日期。
4. 从订单重建全部持仓；从买入支出、结算现金及分红支付重建 settled cash、销售应收、分红应收、按 raw close 计价的 NAV；按除息前持股重建分红权益。
5. 从 raw 总回报独立重算每个导出决策的月末动量、126 日协方差、风险缩放系数与目标权重。
6. 从独立重建 NAV 重算 CAGR 和日收盘 MDD。

结果：全部 12 变体通过。主账户 **2394 行**（含种子）、**298 笔订单**；持仓重建误差 0；主账户最大 NAV 误差约 **1.004e-7 美元**，全部变体最大分项误差约 **1.15e-7 美元**，来自 CSV 有效位数；主决策最大误差约 **5.0e-13**。没有把这些通过项当成发行人数据真实性或真实成交证明。

独立证据：

- `/tmp/three-line-a-review-20260909/check_a.py`
- `/tmp/three-line-a-review-20260909/independent-checks.json`
- Python 环境：原研究已留存的 `/tmp/xa-sast-runtime/bin/python`；没有安装或改变依赖。

## 发现与边界

### [P2] “同风险静态”应统一改称“同一事前缩仓规则静态”

两账户共用同池波动估计和最多 10% 的缩仓公式，但趋势门在风险缩放之后关闭资产，不对剩余资产重新加仓，因此实际风险不同：主趋势波动 **6.36%**、平均敞口 **56.39%**；静态对照波动 **8.23%**、平均敞口 **87.84%**。这不是实际等波动账户。

这属于解释/命名问题，不是代码违反契约：契约明确要求先缩放再应用趋势门，而且报告已经披露实际风险差异、给出标注为不可交易的事后等波动诊断。不能根据“CAGR 差 2.41pp”单独宣称固定风险下择时 alpha 为负；可以根据完整的预设收益/回撤取舍裁决失败。

路径与行号：

- `research/asset-portfolios/1d-small-account-slow-trend/specs/p0-contract.json:12,21-22`
- `research/asset-portfolios/1d-small-account-slow-trend/scripts/run_research.py:290-299`
- `research/asset-portfolios/1d-small-account-slow-trend/diagnostics/p0-account-study-2026-09-08.md:5,35-37,58-60,82`
- `research/platform/small-account-three-line-validation/diagnostics/three-line-results-2026-09-08.md:12,31-32`

### [P2] 分配/总回报口径差异已足以翻一次交易开关，虽不改变本轮裁决

独立检查显式分配总回报与同一 raw 文件中的 Yahoo adjclose，总共找到 **一次**主 12M 月末动量符号差异：

- VNQ，**2018-10-31**：显式分配法动量 **+0.00004409521286996565**（+0.0044095%）；Yahoo adjclose 口径 **-0.00015709128342600298**（-0.0157091%）。
- 原冻结显式法会持有该月 VNQ，另一口径会关闭该份额。

这不是证明显式法错误，也不是把 adjclose 当权威替换。它证明报告已披露的分配精度/再投资定义差异并非永远仅影响小数，而可能改变离散决策。发行人精确金额、除息定义和支付日核验仍有实质价值。

为量化影响，只在 `/tmp` 隔离原引擎源码的内存副本，在该日期把 VNQ 门强制关闭一次，其余全部原规则与 raw 保持不变：

| 口径 | 终值 | CAGR | 日收盘 MDD |
| --- | ---: | ---: | ---: |
| 原对象 | $14,065.5952151 | 3.6507837548% | 14.5018734705% |
| 仅该 VNQ 开关关闭 | $14,013.3537742 | 3.6102527029% | 14.5481977587% |

终值差 **-$52.24**，CAGR 差 **-0.04053pp**；原相对取舍门依旧失败。这个单点敏感度不是新候选、不是优化，也不是所有公司行动误差的上界。

路径与行号：

- `research/asset-portfolios/1d-small-account-slow-trend/scripts/run_research.py:105-124,294-299`
- `research/asset-portfolios/1d-small-account-slow-trend/diagnostics/p0-account-study-2026-09-08.md:76-78`
- 新证据：`/tmp/three-line-a-review-20260909/independent-checks.json` 的 `explicit_vs_adj_12m_sign_flips`
- 单点影响脚本和结果：`/tmp/three-line-a-review-20260909/boundary_sensitivity.py`、`/tmp/three-line-a-review-20260909/boundary/sensitivity.json`

### 非新缺陷：分红、现金、日历和开盘代理的限制已披露，不能升级为真实净值

已核对的账户算术正确处理：未分红复权价格、除息前股数应收、应收计入 NAV 但不能买股、销售未结算资金、整数股、低价小额单最低佣金，以及按已知前收盘确定买股数。没有发现用当日开盘反推数量、分红双计或销售款/持仓双计；全部 raw 中 `capitalGains` 为空，没有 `dividends + capitalGains` 重复计入迹象。

但以下仍是实盘准入缺口：

- 分红统一除息后 60 天现金释放，而非实际逐次支付日；60/90 天结果相同只说明本主账户当时现金够用，不能推广到静态账户或真实现金流。
- 发行人全历史精确分配未核验；已看到 Yahoo 金额舍入和以上动量边界。
- 所有现金 0% 利息是冻结条件，不代表任意真实券商、现金管理工具或全部账户规模。基础为个人税前、扣模型化交易成本的条件收益，不是投资者税后净收益。
- 日历用 XNYS 与联邦银行假日交集，是已声明的保守结算近似；Nasdaq 常规交易日相同不等于已证明各交易所开盘竞价。打印开盘加滑点没有历史盘口/真实竞价成交证据。
- 日收盘 MDD 不是盘中最坏可执行账户回撤；不能因历史 14.50%/18.57% 即保证未来不越 30%。

路径与行号：

- `research/asset-portfolios/1d-small-account-slow-trend/specs/p0-contract.json:14-20`
- `research/asset-portfolios/1d-small-account-slow-trend/scripts/run_research.py:159-165,193-214,217-271`
- `research/asset-portfolios/1d-small-account-slow-trend/diagnostics/p0-account-study-2026-09-08.md:21-27,66,76-78`
- `research/asset-portfolios/1d-small-account-slow-trend/diagnostics/official-execution-sources-2026-09-08.md:15-25`

### 静态优先是合理待补证方向，属于结果后的选择

`next-priority-static-account.md` 明确写提出时间在 A/B/C 收益揭示后，不是事前独立检验或已合格候选。保留当前固定池与权重，先补真实分配、权限、费用和整股执行，这是合理的有限补证建议，没有把旧 P4 直接晋升。

不过，应避免总报告“唯一下一优先项”被转述成“已经证明最优”。本次只支持把它列为资源优先级最高的待核查对象。静态等权比静态风险缩放更好也是样本内观察，且静态尚未经历自己的全部税/支付/成本/执行压力。

今日重新投入 $10,000 的整数股可实现权重，不能直接等同于 2017 年 $10,000 启动后已经增长到约 $19,259 的历史账户。以留存 2026-09-04 收盘 SPY $770.19 为例，新 $10,000 账户 1/7 配额留 2% 余量仅可买 **1 股**，实际约 **7.7%** 敞口；历史静态账户此时已有 **3 股**。报告已经指出小账户份额问题，下一阶段必须实际算新的订单预算和完整可实现权重，不能直接搬历史终端持仓，也不应为“修好”权重而事后换 ETF。

路径与行号：

- `research/platform/small-account-three-line-validation/specs/next-priority-static-account.md:3,7,11-20`
- `research/platform/small-account-three-line-validation/diagnostics/three-line-results-2026-09-08.md:3,13,19`
- `research/asset-portfolios/1d-small-account-slow-trend/diagnostics/p0-account-study-2026-09-08.md:68,88-90`
- `research/asset-portfolios/1d-small-account-slow-trend/artifacts/small-account-lot-check.csv:2`
- `research/asset-portfolios/1d-small-account-slow-trend/artifacts/static_equal_weight/account.csv` 最后行（2395，含表头）

## 契约与数据起点变更

原契约先请求 2016-02-01 账户起点，PDBC 33 个零成交量日使原窗口启动失败，补充选择 2015-12-01 共同有效数据起点、2017-03-01 账户起点，涵盖最慢 14M 预热。raw、契约和补充的指纹均可验证，对照统一窗口；没有发现删除标的、拼接替代工具或填补收益让结果通过。

补充文件及曝光日志称变更发生于任何账户结果曝光前。这一记录与留存结构一致；本次可验证指纹和内容，不能仅凭文件中自报时间独立证明人/Agent 当时绝未看过任何其他绩效。全历史本来已标为复用诊断，因此不能把这项程序纪律升级为新盲 OOS。

- `research/asset-portfolios/1d-small-account-slow-trend/specs/p0-contract.json:5,9-10,24`
- `research/asset-portfolios/1d-small-account-slow-trend/specs/data-admissibility.json:3-8,44-46`
- `research/asset-portfolios/1d-small-account-slow-trend/specs/exposure-log.md:1-8`

## 建议根任务的最终表述

“A 线计算与条件账户账本基本通过独立验收。3.65%/14.50% 和静态同缩仓规则 6.06%/18.57% 可以复算，原预设收益/回撤取舍未通过。当前应保留失败对象，不能称所有趋势无效。静态只是一项结果后待补证建议，发行人公司行动、实际账户执行和今日 $10,000 整股权重仍需核验。没有任何对象因此成为实盘合格候选。”
