# Scripts

## 2026-09-24：完整每周Top10

- [首次研究](research_weekly_top10_20260924.py)：复现基线、重建旧周榜、固定73个月共同起点；首次W7在COCOS日线停止的材料保留。
- [首次终止取证](collect_weekly_terminals_20260924.py)：两个固定BZRX/KEEP公告及官方指数分钟窗口，有界公开请求与CHECKSUM。
- [补充并完成](complete_weekly_top10_20260924.py)：`collect/prepare/execute`，保留首次失败并补COCOS/MEMEFI实际终止；相同名单/仓位的8账户另存。
- [独立核对](audit_weekly_top10_20260924.py)：直接按过去日期重建318周榜、原始指数Decimal均值及独立数量×价差现金账；逐时点和逐月/年度核对。
- [报告导出](report_weekly_top10_20260924.py)与[最终检查](finalize_weekly_top10_20260924.py)：318周、73个月和年度表，哈希、测试、相对链接、30MiB预算及登记边界。

[规则](../specs/binance-1d-mcsm-weekly-top10-20260924.md) · [补充](../specs/binance-1d-mcsm-weekly-top10-terminal-amendment-20260924.md) · [主报告](../diagnostics/binance-1d-mcsm-weekly-top10-20260924.md) · [材料与复现顺序](../artifacts/weekly-top10-20260924/README.md)。不读取新原始行情湖、不补零资金、不改被冻结代码和结果；复现使用独立工作副本。

## 2026-09-11：用户指定MA120单规则

- [研究入口](research_mcsm_ma120_20260911.py)：`prepare`先保存买入/退出/新增目标，`execute`复用已核查来源与登记的实际返回帧加载器，先复现原版后计算8账户。
- [部分现金调仓](mcsm_ma120_accounting_20260911.py)与[事件回放](replay_mcsm_ma120_20260911.py)：只为用户现金空位规则新增本地适配，原冻结内核与旧脚本不修改。
- [独立核查](audit_mcsm_ma120_20260911.py)：用120个精确日期直接求均值重建全部买卖，再以独立价格差/数量/资金费公式核全部净值和月账。
- [月年报告导出](report_mcsm_ma120_20260911.py)及[最终检查](finalize_mcsm_ma120_20260911.py)：交付76个月的币种、实际卖出日、账户盈亏和7年比较；不再模拟额外策略。

[完整固定规则](../specs/binance-1d-mcsm-ma120-round-20260911.md) · [结果](../diagnostics/binance-1d-mcsm-ma120-round-20260911.md) · [本轮材料](../artifacts/ma120-round-20260911/README.md)。各脚本的输入与运行哈希由started、summary、audit和completion记录；既有结果不覆盖，复现应使用独立工作副本。本轮冻结入口保留一个无效应的ROOT未用导入，最终风格检查明确只忽略F401，不为消除样式警告改动已冻结代码。

## 2026-09-11：回撤来源、扩大退出与周频

固定入口为[本轮合同](../specs/binance-1d-mcsm-drawdown-frequency-round-20260911.md)，SHA256 `aa38d87cf3cb374d4f587faf3660586950986bfa2a25813e851d65c28862d2d4`。[报告](../diagnostics/binance-1d-mcsm-drawdown-frequency-round-20260911.md)与[材料目录](../artifacts/drawdown-frequency-round-20260911/README.md)记录实际完成/缺失，不把计划当成功。旧脚本及被固定哈希的内核不改，新脚本不采集被拒资金API、不运行生产。

- [`research_mcsm_drawdown_20260911.py`](research_mcsm_drawdown_20260911.py)：原四账的峰谷、恢复期、月年/逐腿现金及过去beta统计拆分；广谱池任一既定币缺价即整日不可用，不拼缺日指数。
- [`audit_mcsm_drawdown_detail_20260911.py`](audit_mcsm_drawdown_detail_20260911.py)：独立核完整持仓日拆分、模型剩余与边界损益，不把相关性当对冲收益。
- [`research_mcsm_broader_exit_20260911.py`](research_mcsm_broader_exit_20260911.py)：X5/X10计划先锁定，必要prior活动经实际启动返回帧补证、open必须与旧价一致；先复现S1，再运行价格/观察资金费与4/8bp八条账户。保存真实数量、月年现金与利润保留，不扫描退出人数或天数。
- [`research_mcsm_weekly_20260911.py`](research_mcsm_weekly_20260911.py)：分`plan / qualify / execute`固定日线候选、此前已闭合活动和最终名单，再看后续价格；M28/W28/W7与同起点B0为75月价格比较。完整日程不足10币、出场/估值/结算缺失须明确失败，资金费不计算即不可用，不当0。
- [`audit_mcsm_weekly_account_20260911.py`](audit_mcsm_weekly_account_20260911.py)：不导入主回放或账户内核，逐事件独立核B0/M28四条完成账和W28/W7四条首个失败；核实际数量、3,000腿、300个月和年度现金，失败前净值不当完整策略结果。
- [`audit_mcsm_round_20260911.py`](audit_mcsm_round_20260911.py)：跨分支独立复核入口，范围与实际验收结果见本轮`independent-audit/`；复用旧独立现金代数时不改旧文件。
- [`build_mcsm_round_tables_20260911.py`](build_mcsm_round_tables_20260911.py)、[`build_mcsm_round_workbook_20260911.mjs`](build_mcsm_round_workbook_20260911.mjs)：只从研究输出整理用户表格，不读取新行情；区分76月00:15月账与75月自然月估值，保留资金费不可用、失败原因和实际名单。

本轮回撤与扩大退出已完成；频率分支B0/M28各两成本共四条价格账完整，W28/W7各两成本共四条因下架币缺价停止，成功账与首个失败均已独立核对。导出保留失败周频的事前名单且明确只是计划，收益/盈亏不可用，不混入实际逐月账。新产物总预算100MiB；各分支只保留目标投影、计划与小型可再生输出，不复制整段市场数据。完整运行与脚本哈希由各分支`started`、冻结计划和最终摘要固定。

- [2026-09-10 三项机制研究](../diagnostics/binance-1d-mcsm-mechanism-round-20260910.md)：`research_mcsm_matched_selection_20260910.py`做事前相似币配对和同月价格对照；`research_mcsm_entry_funding_signal_20260910.py`检验事前72小时资金费；`research_mcsm_single_asset_exit_20260910.py`只测试20/7/2单币退出，并重放8个原/新、价格/资金、4/8bp独立账户。所有新增普通执行价来自实际研究启动返回帧，信号和请求先锁定，不改原内核。
- `audit_mcsm_mechanism_round_20260910.py`独立逐日重建314个退出目标；`audit_mcsm_single_exit_account_20260910.py`不用候选会计算术，独立核8账户、76月现金及全部同步估值/退出事件。缺时点、NaN、缺账户不得通过；证据保留`artifacts/mechanism-round-20260910/independent-audit/`。

- 最新复核见[2026-09-10 资金费收益检查](../diagnostics/binance-1d-mcsm-funding-recheck-20260910.md)。本轮全部账户独立复算、部分官方原文及原生标记价优先对照；不改选币规则，不是参数研究或精确净收益批准。
- [`audit_mcsm_funding_account_bridge_20260910.py`](audit_mcsm_funding_account_bridge_20260910.py)：直接按固定数量进入至退出价格差独立重记四账户、核逐事件现金，并拆出同价格账户数量的直接资金费与后续本金变化。
- [`audit_mcsm_funding_mark_integrity_20260910.py`](audit_mcsm_funding_mark_integrity_20260910.py)、[`audit_mcsm_retained_native_marks_20260910.py`](audit_mcsm_retained_native_marks_20260910.py)：核实际使用的分钟/原生原文、单位和全部固定原生来源清单；不把同日价格范围当结算价证明。
- [`audit_mcsm_all_funding_sources_20260910.py`](audit_mcsm_all_funding_sources_20260910.py)、[`audit_mcsm_retained_funding_sources_20260910.py`](audit_mcsm_retained_funding_sources_20260910.py)、[`merge_mcsm_funding_source_evidence_20260910.py`](merge_mcsm_funding_source_evidence_20260910.py)：保留全760窗口查询计划、失败回执、原始event全集、官方匹配与缺口；已遇源端403，后续复现仅离线，不继续采集。归档费率旁证不能代替明确类型API或完整历史结算日历。
- [`finalize_mcsm_funding_source_halt_20260910.py`](finalize_mcsm_funding_source_halt_20260910.py)：保留请求被拒与停止的真实经过，不改首次计划或回执。
- [`audit_mcsm_legacy_funding_lineage_20260910.py`](audit_mcsm_legacy_funding_lineage_20260910.py)：只沿旧正式清单和下载器声明路径检查本轮所涉费率月档，区分转换表仍在与原ZIP不能重验；不扩大搜索或联网。
- [`replay_mcsm_native_marks_20260910.py`](replay_mcsm_native_marks_20260910.py)：固定原全部输入/会计内核与官方比较表哈希，只替换唯一匹配的可得原生 mark，另算本轮全部账户资本路径；原结果不覆盖、未知费率不补零、已知源冲突拒绝。指定最终 `--comparison artifacts/funding-recheck-20260910/combined-sources/native-event-comparison.parquet` 时需从仓库根提供完整家族路径，输出目录默认存在即拒绝。

- 原账户入口见[连续账户估算报告](../diagnostics/binance-1d-mcsm-baseline-estimate-20260909.md)：76 月身份修正基线，价格对照 +912.33%，资金中心/不利/有利估算 +10,085.43% / +9,647.72% / +10,199.47%。全部为 `EXPLORATORY_ESTIMATED_ACCOUNT_NOT_VERIFIED_NET`，不是参数优化、精确净验证或生产入口；旧绩效仍 `PERFORMANCE_INVALIDATED`。
- [`build_mcsm_baseline_inputs_20260909.py`](build_mcsm_baseline_inputs_20260909.py)：复原原日桶形成/ADV排序，保留 ADA 部分上市日端点并核官方终止限制；输出修复前冻结输入，不把它当最终身份正确名单。
- [`audit_mcsm_baseline_selection_20260909.py`](audit_mcsm_baseline_selection_20260909.py)：冻结旧源复现与 V3 缺日差异、760 个形成段核查；不调排序或重算收益。
- [`audit_mcsm_identity_sources_20260909.py`](audit_mcsm_identity_sources_20260909.py)：保留四份官方 CMS 原文及 hash，确认 LIT 跨资产复用和 AERGO 终止/重开；旧两腿现金贡献只是事后归因，不是删腿反事实。
- [`correct_mcsm_baseline_identity_20260909.py`](correct_mcsm_baseline_identity_20260909.py)：先冻结两处身份输入修正，按原排序以 LAYER/Q 补位，758 腿不变；复核返回价与两个新形成连续段，输出 `inputs-identity-corrected/`，原输入不覆盖。
- [`build_mcsm_baseline_estimated_funding_20260909.py`](build_mcsm_baseline_estimated_funding_20260909.py)：固定实际持仓窗口，保存官方原生事件/分钟 mark 月档及修复证据；最终输入为 `funding-identity-corrected/`，旧计划及无效时间精度初稿不用于账户。
- [`audit_mcsm_estimated_funding_calendar_20260909.py`](audit_mcsm_estimated_funding_calendar_20260909.py)、[`audit_mcsm_estimated_funding_identity_output_20260909.py`](audit_mcsm_estimated_funding_identity_output_20260909.py)：分别核观察日历边界及修正版事件/原文/758 共同窗口，不把 mark 齐全等同于全历史日历认证。
- [`audit_mcsm_estimated_funding_large_cash_20260909.py`](audit_mcsm_estimated_funding_large_cash_20260909.py)：对 RIVER/AIA/MYX/PIPPIN 四个大额资金贡献月做事后官方 API/月档/CHECKSUM 原文核对，2,462 笔费率逐项一致；不改冻结账户、代理价或研究参数，不能以局部证据认证全部历史日历。
- [`run_mcsm_baseline_estimate_20260909.py`](run_mcsm_baseline_estimate_20260909.py)：只消费固定 hash 的本家族输入；四轨分别独立权益、固定数量、00:15 参考价、净额交易、事件资金费和显式终止估算。最终输出 `accounts/summary.json`；不含资金费的 price_only 是反事实，不是永续净收益。
- [`audit_mcsm_price_only_replica_20260909.py`](audit_mcsm_price_only_replica_20260909.py)、[`audit_mcsm_funded_replica_20260909.py`](audit_mcsm_funded_replica_20260909.py)：独立现金/持仓代数复算，不调用主账户算术；复算通过只证明模型账一致，不提升数据精度或实盘资格。
- [`summarize_mcsm_baseline_estimate_20260909.py`](summarize_mcsm_baseline_estimate_20260909.py)：读取最终证据生成报告，完整命令及 QA 范围见[本轮报告](../diagnostics/binance-1d-mcsm-baseline-estimate-20260909.md)。冻结时的原 input builder 仍有 5 项 lint 遗留，不原地改源或将局部 Ruff 通过说成全部脚本通过。
- 以下为 2026-09-08 [严格基线核验](../diagnostics/binance-1d-mcsm-baseline-verification-20260908.md)及更早保留入口；当时精确源缺口和失败不被本轮估算覆盖。
- [`verify_mcsm_baseline_20260908.py`](verify_mcsm_baseline_20260908.py)：分阶段保存候选、首月受治理返回价、ADA 原始部分日端点和真实缺 mark 拒绝；`prepare` 生成的完整日 K 候选已判为原规则不兼容，不得用于绩效。默认拒绝覆盖。
- [`mcsm_baseline_accounting_20260908.py`](mcsm_baseline_accounting_20260908.py)：纯现金会计内核，无行情读取；数量固定、净额换仓、Regular/Special 事件与终止结算，35 项测试。
- [`probe_mcsm_baseline_funding_marks_20260908.py`](probe_mcsm_baseline_funding_marks_20260908.py)、[`probe_mcsm_baseline_first_day_marks_20260908.py`](probe_mcsm_baseline_first_day_marks_20260908.py)：事前固定官方资金源探针，保留原文；不是净回测输入批准。
- [`reconcile_mcsm_baseline_funding_marks_20260908.py`](reconcile_mcsm_baseline_funding_marks_20260908.py)：官方月档与 API 原生时间/费率逐项核对、旧字段可获得性盘点，不把 normalized 盘点值导入策略。
- [`audit_baseline_terminals_20260908.py`](audit_baseline_terminals_20260908.py)：五个终止事件的有界取证和本家族已验证投影复核；分钟指数包络不是精确结算价。
- [`load_binance_1d_mcsm_lifecycle_inputs_20260908.py`](load_binance_1d_mcsm_lifecycle_inputs_20260908.py)：固定 bundle v2、874 历史观测标的的完整治理启动及返回帧证据，不计算收益。
- [`verify_binance_1d_mcsm_lifecycle_inputs_20260908.py`](verify_binance_1d_mcsm_lifecycle_inputs_20260908.py)：独立核对上述返回帧、逐标的哈希、分段与请求，拒绝请求篡改；只读本轮证据。
- [`research_binance_1d_mcsm_lifecycle_20260908.py`](research_binance_1d_mcsm_lifecycle_20260908.py)：固定数量、24h 延迟的日级状态/first-event 价格机制诊断；不计算完整资金净值，不覆盖旧口径。
- [`audit_binance_1d_mcsm_funding_source_20260908.py`](audit_binance_1d_mcsm_funding_source_20260908.py)：旧冻结资金费逐日复现、集中度、官方三币原生月档与价格记账代数桥；不是新的净收益回测。
- 本轮完整生成和验证命令见[主报告](../diagnostics/binance-1d-mcsm-lifecycle-funding-round-20260908.md#6-证据验证和保留)。以下是保留的旧轮次脚本与命令，不是当前新实验默认入口。
- [`research_binance_1d_mcsm_long10.py`](research_binance_1d_mcsm_long10.py)：复用冻结的 Binance 日级缓存与月度横截面引擎，独立运行 Top10 long-only、Top3 control 和 BTC/ETH/全市场基准。
- [`research_binance_1d_mcsm_long_breadth.py`](research_binance_1d_mcsm_long_breadth.py)：在同一口径下运行全上市与 ADV 宇宙的 Top10/20/30/40/50 long-only，并输出动态共同窗口指标。
- [`research_binance_1d_mcsm_long10_risk_buffer.py`](research_binance_1d_mcsm_long10_risk_buffer.py)：按冻结合同运行 Top10 对照、20% 组合目标波动无杠杆版，以及 10/20 持仓缓冲版。
- [`research_binance_1d_mcsm_long10_positive_cash.py`](research_binance_1d_mcsm_long10_positive_cash.py)：只买 Top10 中形成收益严格大于0的名字，每槽10%，空缺持有现金，并与 target20 对照。
- [`research_binance_1d_mcsm_long10_liveability.py`](research_binance_1d_mcsm_long10_liveability.py)：冻结运行 BTC SMA200 市场风控、target12 风险预算、成本/延迟、时间 cohort、bootstrap、超额收益和容量诊断。
- [`research_binance_1d_mcsm_mh136_liveability.py`](research_binance_1d_mcsm_mh136_liveability.py)：冻结运行 1M/3M/6M 等资本袖套、逐袖消融、风险扰动、压力、bootstrap 和容量诊断。
- [`audit_binance_1d_mcsm_long10_target12_execution_timing.py`](audit_binance_1d_mcsm_long10_target12_execution_timing.py)：用真实 15m panel 审计 `00:15 UTC` 可成交入选、退出与持仓缺价；任一 blocker 存在即标记 `PERFORMANCE_INVALIDATED`。
- [`research_binance_1d_mcsm_money_effect_continuation.py`](research_binance_1d_mcsm_money_effect_continuation.py)：以真实 `00:15 UTC` 月度标签诊断 Binance 赚钱效应 breadth、市场中位数、leader spread、3M 延续、流动性/拥挤和冻结 2×2 状态，并输出收益捕获、衰减、cohort 与 post-reveal 消融。

```bash
uv run python research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/research_binance_1d_mcsm_long10.py --self-test
uv run python research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/research_binance_1d_mcsm_long10.py --run-date 2026-08-18 --force
uv run python research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/research_binance_1d_mcsm_long_breadth.py --self-test
uv run python research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/research_binance_1d_mcsm_long_breadth.py --run-date 2026-08-19 --force
uv run python research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/research_binance_1d_mcsm_long10_risk_buffer.py --self-test
uv run python research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/research_binance_1d_mcsm_long10_risk_buffer.py --run-date 2026-08-19 --force
uv run python research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/research_binance_1d_mcsm_long10_positive_cash.py --self-test
uv run python research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/research_binance_1d_mcsm_long10_positive_cash.py --run-date 2026-08-19 --force
uv run python research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/research_binance_1d_mcsm_long10_liveability.py --self-test
uv run python research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/research_binance_1d_mcsm_long10_liveability.py --run-date 2026-08-20 --force
uv run python research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/research_binance_1d_mcsm_mh136_liveability.py --self-test
uv run python research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/research_binance_1d_mcsm_mh136_liveability.py --run-date 2026-08-20 --force
uv run python research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/audit_binance_1d_mcsm_long10_target12_execution_timing.py --self-test
uv run python research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/audit_binance_1d_mcsm_long10_target12_execution_timing.py --run-date 2026-08-20 --force
uv run python research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/research_binance_1d_mcsm_money_effect_continuation.py --self-test
uv run python research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/research_binance_1d_mcsm_money_effect_continuation.py --run-date 2026-08-20 --force
```
