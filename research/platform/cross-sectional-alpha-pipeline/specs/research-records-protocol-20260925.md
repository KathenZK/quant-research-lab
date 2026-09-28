# 研究记录与恢复协议 · 2026-09-25

本协议适用于新增研究记录、候选证据包和离线接口。它不重写已有家族的交易规则，也不授权线上部署。目标是让下一次研究能回答：使用了什么、什么时候看过、怎样算钱、还能不能恢复。

## 1. 开始新实验之前

1. 固定研究问题、币池及其选择依据、完整样本、回看和预测长度、简单对照、费用、持仓与退出约束、验收和停止条件。未决定的事项不能由看过的收益替代决定。
2. 用 `research_records.py overlaps` 查询曝光账本。结果为空只表示账本尚无记录，不证明这段历史从未看过。当前账本是已证实历史的起始清单，尚不穷尽人工查看和旧搜索。
3. 在结果之前追加 `kind=exposure` 记录。记录家族、候选、窗口、明确的尝试数量或未知原因、选择依据、配置/代码/输入的 SHA256。已有结果只能按历史回填登记；`registered_at` 是工具实际写入时刻。
4. 使用固定数据组合和精确窗口启动检查。价格诊断、完整资金费、合约身份、历史币池、标记价和执行约束分别判断。未证明的资金费不得填零；先前的 `price_diagnostic` 不能因为新接口接上账户就升级为净收益证据。

追加工具位于本主题 `scripts/research_records.py`，账本默认研究位置是 `artifacts/research-exposure-ledger.jsonl`，使用时显式传入路径。示例：

```bash
.venv/bin/python research/platform/cross-sectional-alpha-pipeline/scripts/research_records.py overlaps \
  --ledger research/platform/cross-sectional-alpha-pipeline/artifacts/research-exposure-ledger.jsonl \
  --start 2026-04-01T00:00:00Z --end 2026-07-01T00:00:00Z
.venv/bin/python research/platform/cross-sectional-alpha-pipeline/scripts/research_records.py append \
  --ledger research/platform/cross-sectional-alpha-pipeline/artifacts/research-exposure-ledger.jsonl \
  --record /absolute/path/to/new-exposure.json
```

曝光记录的字段是 `id / kind / family / window_start / window_end / evidence_class / trial_count / selection_reason / artifacts`。`artifacts` 为路径到内容哈希的映射；`trial_count=null` 必须同时填写 `trial_count_unknown_reason`。工具允许扩展 `candidate / parameters / scope / stopping_rule` 等字段。`trial_count` 应明确是本轮尝试数还是累计搜索数；两者不混用。当前历史导入全部将累计数保留为未知，并单独记录一条归档方案。

记录通过本地文件锁串行追加，编号、前序哈希和记录哈希组成可校验链，重复 ID 和损坏尾行拒绝写入。已写记录不覆盖，更正追加新 ID 并指向旧 ID。持有文件写权限的人仍能重写整个账本，因此需要独立保留检查点和备份；哈希链不等于外部时间戳或防篡改存储。

## 2. 因子与输入语义

因子要保存公式、单位、方向假设、回看长度、依赖列、缺失语义、可用时点、适用资产范围和版本。现有 `FactorMetadata` 已有多数定义；本轮相对强弱的完整约定如下：

| 项目 | 约定 |
|---|---|
| 公式 | 资产过去 n 根收益减同一窗口基准收益：`C[t]/C[t-n] − B[t]/B[t-n]` |
| 单位 | 小数收益差；0.10 表示相差 10 个百分点 |
| 方向 | 值越高表示过去相对更强；未来有利与否需要验证 |
| 回看 | n+1 根；默认 n=24，含义是 24 根输入 bar，不自动代表 24 小时 |
| 输入 | 同步的 close 与 benchmark_close；价格质量由接受的数据契约检查 |
| 分组 | 已提供的 exchange、symbol、market_type、timeframe、research_segment_id 共同划界 |
| 缺失 | 不向前填补；段首不足长度、资产或基准价格缺失导致对应收益缺失 |
| 时间 | 已提供 ts 时按合约/段检查顺序与重复；没有 ts 的直接调用视为调用方已排序 |
| 可用性 | 只有两侧 bar 均已闭合并实际可得后才能进入分数；计算函数本身不证明 available_at |
| 版本 | 由定义、参数和计算源码生成；本轮默认24根版本已变化，旧缓存不再冒充新计算 |

价格输入目前没有历史 `available_at / received_at / revision_id` 字段。不能把 bar 的发生时间、今天下载时间或者人为补出的发布时刻混为一谈。资金费最终结算值只在相应事件可知后使用，预测费率必须另有发布快照。

## 3. 分数、组合与真实净账户

可复用接口位于 `src/strategy_lab/research/portfolio.py`：

- `Score(symbol, value, available_at)`：只携带分数和可用时刻。
- `rank_targets`：拒绝未来分数、重复标的和非有限值；确定性排序，固定名额等权，没有足够标的时留现金。本轮不优化排序规则。
- `combine_targets`：每个策略明确资金预算，总预算不超过 1；先把同币相反方向抵消，再生成一个真实净持仓目标。
- `delta_orders`：按目标与账户实际数量之差计算净订单；求解扣除净换手手续费后的目标权益，先减仓释放资金再增仓，反手拆为减仓与新开仓。成交后使用实际数量重新计划，部分成交不视为已完成。

每个子策略的仓位是相对于其资金预算的有符号权重。例如趋势策略预算 60%、目标 BTC=100%，对冲策略预算 40%、目标 BTC=−50%、ETH=50%，真实账户最终目标为 BTC=40%、ETH=20%，其余不占用名义敞口。不能同时按两个完整子账户记收益。

账户核对工具位于 `src/strategy_lab/research/accounting.py`。经济恒等式为：

`现金 = 初始现金 + 已实现盈亏 + 资金费现金流 − 成交手续费`

`权益 = 现金 + Σ[带符号持仓数量 × (当前估值价格 − 持仓均价)]`

`资金费现金流 = −带符号持仓数量 × 结算估值价格 × 实际费率`

成交价中的滑点不再额外扣现金。每次事件提供所有持仓的当时估值；时间必须带时区且不倒退。同时间的先入场还是先结算由事件顺序明确给出。资金费普通/特殊结算分开记录，同一结算不能重复计费。负权益和保证金越界可以被观测，不能因此删除亏损；不允许在保证金不足时继续加风险，仍允许减仓。

工具的保证金只采用固定总名义敞口上限。它没有交易所维持保证金阶梯、强平、价格/数量精度、最小名义额、盘口容量、排队或跨账户撮合功能。`delta_orders` 的费用估算假定按传入估值价成交；实际价变化后必须重新核算。它是独立算账参照和离线接口，不是新的生产执行引擎。

## 4. 冻结候选必须可恢复

`src/strategy_lab/research/evidence.py` 支持创建、检查、打包和恢复。最低包含 code、spec、input、reference_output、environment 五类；训练模型还必须包含实际 model、preprocessor、feature_order 文件。包中每个文件记录原始来源、大小、SHA256 和用途。

创建和恢复必须使用新的目录，不覆盖已有包。读入前核对所有字节，拒绝路径越界、符号链接、重复成员、缺失或额外文件；压缩包有单独 SHA256。哈希证明字节一致，不证明策略正确。

恢复验收包括：独立目录、新依赖环境、重新计算特征、历史离散决策和成交、账户输出、独立经济核对。原始文件和开发失败记录保留。规则策略无需假装存在训练模型；已经删除的旧 ML 模型不能通过重新训练冒充恢复。

本轮最终合格包为 `artifacts/implementation-20260925/candidate-bundle-r3`。早期 r1/r2 是恢复脚本验收失败的开发版本；源策略、参数、数据和原始结果没有改变。当前没有通用“自动删除研究证据”的清理入口；已有目录盘点也不执行删除。文件仍可能被有权限的人手动删除，所以长期证据与缓存分离、实际副本和恢复演练仍不可省略。

## 5. 决策链观察合同

本轮完成日志和覆盖统计工具，**观察状态为 NOT_STARTED**。没有启动采集器、定时任务或交易服务，也没有制造任何历史实时信号。实际观察起点、结束、间隔、允许延迟和输入版本要在启动时单独冻结。

`kind=observation` 必须包括：

| 字段 | 含义 |
|---|---|
| family、id | 冻结研究对象和唯一节点记录 |
| decision_at、deadline_at | 应作决策时刻及最晚可接受完成时刻 |
| completed_at、registered_at | 实际完成时刻、工具实际写入时刻，二者不混用 |
| input_available_at | 本节点所有输入最晚可得时刻，不能晚于 decision_at |
| config_sha256、code_sha256 | 本节点实际运行的配置与代码 |
| status、reason | completed / missed / backfill_diagnostic，以及缺失或补算原因 |
| execution_link、account_link | 订单成交链、账户核对证据；缺失保持为空，不伪造关联 |

工具按实际写入时间和完成时间判迟到；事后补算永远没有实时完成计数。`observation_coverage` 根据预先固定的起止与间隔生成应到节点，日志里根本不存在的节点也算缺失。所谓 `prospective_credit` 只表示这条日志按时写入，不能单独认证数据真实可得、交易所核对通过或策略已实盘。

```bash
.venv/bin/python research/platform/cross-sectional-alpha-pipeline/scripts/research_records.py coverage \
  --ledger /absolute/path/to/observation-ledger.jsonl --family FROZEN_FAMILY_ID \
  --start 2026-10-01T00:00:00Z --end 2026-11-01T00:00:00Z \
  --as-of 2026-10-10T00:00:00Z --cadence-hours 24
```

上述日期只是命令格式示例，不构成实际观察合同或启动计划。漏记、迟到、参数变化和数据版本变化均应显式进入记录；若对象改变，旧观察区间结束，新对象重新冻结。

## 6. 研究停止条件

当前仅完成组件和证据验收，不能据此晋升策略。完整资金费、当时身份/可交易池或执行约束未满足时，只保留相应价格或工程诊断。不用调换样本、换家族目录或继续增加模型复杂度掩盖输入不足。任何新净收益实验须先完成其精确输入和简单基线，未来连续观察需要真实经过时间。
