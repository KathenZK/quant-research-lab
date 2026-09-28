# strategy-factor-discovery

research_classification: diagnostic_topic

本轮是公开方法选择、独立研究实现、因子诊断与失败学习的跨模板诊断。研究计算和记录已经实际执行，未产生交易授权或确认性通过。本页公开方法、运行状态与证据目录；数值研究附件受所用 Bit2Me 数据条款限制，授权用户可在本机或 C 的私有 evidence 接口查看。

## 选择与真实数量

冻结时读取 Graph 5,816 个策略记录、75 个模板，以及1,085个因子定义变体。另有122个策略规则中的因子引用，单独标 `RULE_REFERENCE_ONLY`；它们没有因此成为已验证因子。完整逐条优先队列保留为 `triage.json`，排序仅使用定义清晰度、追溯、所需数据、实现范围与重复情况，没有按收益筛选。

本轮执行20个不同 Graph 模板，涉及19个 Graph concept；其中3个沿用前轮审查过的来源改编，17个是从实际已采集记录出发的独立研究实现。完整映射（SourceRecord、concept、template、variant、定义摘要、来源URL）在 [strategy-mappings.json](../../../src/strategy_lab/discovery/strategy-mappings.json)。原始采集记录的摘要不是原网页全文摘要。来源仅定义指标或规则转述未经验证时，不能据此归因给原作者。本轮 **source-exact 完整策略复现为0**；没有把BTC/EUR替换原标的、BIL替换零息现金或next-open假设伪称原作者设定。

实现可分9种计算/执行结构；保守的经济机制只计4类：趋势/方向状态、均值回归、波动状态、回撤状态。没有把月频、日频、窗口和阈值算成独立经济发现。5个不同经济方法族的目标未完全达到：配对、多资产轮动、基本面、资金费率与其他方法缺少本轮匹配的可信输入或语义审查。

| Graph原记录 | 本轮登记实现 | 来源说明 |
|---|---|---|
| EV3-M0233-BTC-EUR | 20日zscore低于−1.5，其他状态现金 | Alqama mean_reversion，显式改编 |
| EV3-M0234-BTC-EUR | close高于SMA50 | Alqama momentum，显式改编 |
| EV3-M0256-BTC-EUR | EMA8/21交叉，20%止损/50%止盈 | Freqtrade AverageStrategy，4h来源迁至日线 |
| M4692 | 月末close高于10个月均线 | Graph收集的Quantpedia条目 |
| M4815 | 月末12个月价格收益为正 | Graph收集的CXO条目 |
| M5242 | 月末达到100日最高收盘 | Graph收集的CXO条目 |
| M5582 | SMA10>20>50>100>200 | Fidelity指标说明启发的独立规则 |
| M5625 | Vortex +VI高于−VI | StockCharts指标说明启发的独立规则 |
| M5669 | CCI20>100 | 同上 |
| M5673 | Wilder RSI14>60 | 同上 |
| M5676 | Williams %R14>−20 | 同上 |
| M5678 | Ultimate Oscillator 7/14/28>70 | 同上 |
| M5685 | AroonUp25>50 | 同上 |
| M5688 | MassIndex25>27 | 同上，不能视为原作者给定方向 |
| M5714 | UlcerIndex14<10 | 同上 |
| M5725 | Bollinger %B20,2>0.8 | 同上；ddof0是显式计算选择 |
| M5732 | 滚动CMO14>20 | Fidelity指标说明；非Wilder平滑CMO |
| M5749 | 月末21日实现波动低于15% | CXO条目；本研究年化365、log return、ddof1 |
| M5772 | TRIX12>0 | StockCharts指标说明启发的独立规则 |
| M5779 | Wilder ATR14<ATR100 | 同上 |

公开因子来自固定 [Qlib Alpha158 loader](https://github.com/microsoft/qlib/blob/be725493eb1a6bbb42bf11b37aa7669f59610ff1/qlib/contrib/data/loader.py)，20个concept /20个definition /20个variant，归8个宽泛计算组，**不等于20个独立经济因子**。其中12个已有实现、8个本轮新增，均重新在真实行情上研究；配置见 [factor-settings-v1.json](specs/factor-settings-v1.json)。

- 原12定义：KMID、KLEN、KUP、KLOW、KSFT、ROC5、MA5、STD5、MAX5、MIN5、RANK5、RSV5。
- 新8定义：KMID2、BETA5、RSQR5、RESI5、QTLU5、IMAX5、CNTP5、SUMP5。
- Qlib Rank是时间窗口排名；ROC是过去价格/当前价格；Std为ddof1；回归含截距、缺失位置不压缩；RSQR保留上游近零标准差屏蔽；IMAX并列取第一个。受限登记实现不执行提交的公式。
- 原算子保留部分窗口语义，研究另外屏蔽不完整窗口。CNTP/SUMP需6根原始输入。单资产TS20、CS0；没有同点多资产历史universe，不能报截面IC。

## 协议、预算与演化

现货BTC/EUR日线、未复权、零息EUR现金、不做空、不融资。原始历史范围2022-07-01至2026-09-27（结束不含）；策略共同评估从2023-08-01开始，2025-01-01划分开发与后段。该历史已被观察，所有结论保持 `EXPLORATORY_RETROSPECTIVE`。

每个模板跑手续费10bp+滑点5bp/边、零成本诊断、双倍成本三组，另有3组买持控制。63个基线配置；演化轮先按开发期换手与成本侵蚀选最多两个模板，改成连续两根闭合信号确认，只有这一项变更，包含原规则与三种成本消融。

第一次6个演化配置因Pandas只读数组错误失败，已登记和回写。修复只改非原地布尔操作，保存新代码、新计划与6个新尝试，原失败保持不可变。修复时后段已观察，这一事实记录在修复计划中，没有换参数或假设。

另做开发期限定的Qlib MA5因子组件检验：登记因子值实际驱动下一根开盘持仓，与原SMA50在同一开发期、相同末端清算与三种成本下比较，共6配置。它是窗口/组件消融，不计新独立模板，未再次使用后段演化。

合计 **81个策略配置尝试：75完成、6计算失败**；20因子×2期限=40标签试验，另有初始KMID smoke的2标签单列。独立恢复是同一已登记配置的复跑事件，不伪造新试验或新样本。上限200未用满，不为找到盈利继续搜索。

全部试验复用 `TrialRegistry/v1`；保持未知的历史搜索次数。因子用时序关联、区块置信区间、分段稳定性、冗余、只在开发段拟合的基准增量。策略用成本、换手、暴露、回撤、分段与开发期拟合暴露权重的描述性对照。匹配暴露对照是分析用收益序列，不冒充独立可交易组合。DSR/PBO未用于确认性判断，原因在integrity assessment中保留；不修改旧adjudicate核心。

## 能力与恢复

复用既有Trusted Market Data、FactorRegistry、compute_factor_bundle、冻结v2账户引擎、TrialRegistry和Graph ResearchEvidence。没有新增Graph服务、网站或交易引擎。Worker函数：`strategy_lab.discovery.capabilities.execute(request, context)`；只接受服务器白名单profile及实体版本，客户端不能提供路径、代码或任意算子。三类request共享C的正式契约；中间artifact与typed metadata分开保存。

服务器配置为本机审查文件，包含manifest、原始采集合同、Graph根目录、固定来源目录、独立journal和输出位置。市场/代码/定义权限分别处理。不存在公开授权时，`public_summary.metrics`为空并说明具体限制；公开的计划、样本身份、计算状态、来源和父子关系保留。

新批次或同代码版本中断恢复：

```sh
.venv/bin/python research/platform/strategy-factor-discovery/scripts/run_campaign.py \
  --factor-config /reviewed/factor-server-config.json \
  --strategy-config /reviewed/strategy-server-config.json \
  --output research/platform/strategy-factor-discovery/artifacts/local/new-campaign \
  --workers 2 --stage all
```

`--stage`支持freeze/factors/baselines/evolve/component/finish；all还执行开发期因子组件消融与Graph父子关系写回。输出不可覆盖；完成artifact先验hash再复用，code/schema改变需新修订。部分freeze失败保留并明确BLOCKED，不自动覆盖或伪称后台运行。

本轮已保存完整代码快照的账户独立恢复命令（对同一注册attempt追加恢复事件）：

```sh
.venv/bin/python research/platform/strategy-factor-discovery/scripts/restore_accounts.py \
  --campaign research/platform/strategy-factor-discovery/artifacts/local/campaign-v1
```

本机完整数值报告、每个结果/值/持仓/成交、失败、修复、登记账本、Graph读回和产品导入manifest位于该目录。原始data只读复用，实验账本和Graph journals均为本任务独立路径。详细artifact索引与私有交付说明由交付manifest引用；公开Git不包含受限行情或衍生数值。

## 验证边界

合成测试仅用于语义与账户时序，不计市场研究。9类指标与TA-Lib固定合成oracle对拍，所有登记策略作前缀不变性检查；原3实现与现有冻结信号对拍。Qlib新回归用SciPy linregress独立对照，另核对固定上游Cython公式；本机Xcode许可未接受，未宣称成功编译上游扩展。真实因子逐值独立核算，账户独立恢复逐项比较账户/成交/交易表。

本轮交付不声称找到可实盘盈利策略。计算错误、原方法复现程度、弱关联、经济失败和统计证据不足在私有报告中分别记录。未完成项包括原市场精确策略复现、第五类独立经济机制、截面universe、独立未来验证，以及受当前行情许可阻塞的公开数值展示。
