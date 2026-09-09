# Scripts

- 最新入口见[连续账户估算报告](../diagnostics/binance-1d-mcsm-baseline-estimate-20260909.md)：76 月身份修正基线，价格对照 +912.33%，资金中心/不利/有利估算 +10,085.43% / +9,647.72% / +10,199.47%。全部为 `EXPLORATORY_ESTIMATED_ACCOUNT_NOT_VERIFIED_NET`，不是参数优化、精确净验证或生产入口；旧绩效仍 `PERFORMANCE_INVALIDATED`。
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
