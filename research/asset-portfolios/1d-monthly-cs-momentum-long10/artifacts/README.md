# Artifacts

## 2026-09-09 最新：身份修正后的连续账户估算

最终消费 [accounts/summary.json](baseline-estimate-20260909/accounts/summary.json)，状态 `EXPLORATORY_ESTIMATED_ACCOUNT_NOT_VERIFIED_NET`。100,000 USDT，2020-03-01 00:15 至 2026-07-01 00:15 UTC，76 月各轨独立复利；全部最终清仓。

| 场景 | 最终权益（USDT） | 总收益 | 最大回撤（日末及换仓边界） |
| --- | ---: | ---: | ---: |
| price_only | 1,012,334.94 | +912.33% | -95.43% |
| estimated_center | 10,185,430.84 | +10,085.43% | -93.43% |
| estimated_adverse | 9,747,715.89 | +9,647.72% | -93.44% |
| estimated_favorable | 10,299,465.57 | +10,199.47% | -93.43% |

价格轨不含资金费，不是永续净收益；其余三轨是对观察事件与指定代理价的条件情景，**不是实际净收益的数学上下界/置信区间**。中心 CAGR107.53%，资金现金 +6,870,939.50 USDT，需与价格趋势贡献分开解释。精确资金日历/mark、全池 PIT、终止最终价、真实成交及强平未认证，旧绩效保持 `PERFORMANCE_INVALIDATED`。

- [inputs-identity-corrected/README.md](baseline-estimate-20260909/inputs-identity-corrected/README.md)：最终760腿；已证身份错误 AERGO→LAYER（2025-05）、LIT→Q（2026-01）按原排序补位，其余758腿不变；四个补位交易端点有效、新两形成段单连续有效段，旧输入不覆盖。
- [funding-identity-corrected/summary.json](baseline-estimate-20260909/funding-identity-corrected/summary.json)：最终97,421个观察事件、1,233原生mark/96,188分钟代理、未知完整日历；[独立输出审计](baseline-estimate-20260909/funding-identity-corrected/independent-output-audit.json)核事件、原文hash和共同758窗口，非净资格批准。
- [身份原文证据](baseline-estimate-20260909/inputs/selection-appendix/identity-sources/README.md)：四份官方CMS及发布时间/hash，LIT跨资产伪动量与AERGO旧合约终止/新上线明确区分。
- [旧源与形成段附录](baseline-estimate-20260909/inputs/selection-appendix/README.md)：解释2022年11条选币差异的冻结旧源缺日，不改变排序参数；保留原760形成段的30处短零成交边界及两处后续修复身份错误。
- [独立修正版价格复算](baseline-estimate-20260909/independent-final-price-only-audit/summary.json)：固定单位现金代数独立匹配价格轨；其内部 source_run 明确指向修正后的 v2 价格账，不指修复前结果。
- [三条资金轨独立复算](baseline-estimate-20260909/independent-funded-audit/summary.json)：每轨97,421笔事件及2,390个NAV独立匹配，全部满足预设误差；这里只证明模型现金一致，不证明未观测历史事件不存在。[最终 QA 与失败尝试保留](../notes/baseline-estimate-qa-20260909.md)明确98项目标测试通过与全仓4项失败的边界。
- [修复前价格账](baseline-estimate-20260909/price-only-first-run/summary.json)与原 `inputs/` 只留对照；+932.52%不是最终基线。初始时间精度错误资金计划及被拒绝的中间运行也原位保留，不作为最终输入。
- [本轮报告](../diagnostics/binance-1d-mcsm-baseline-estimate-20260909.md)说明现金归因、年度差异、最终独立复算及剩余边界；[冻结契约](../specs/binance-1d-mcsm-baseline-estimate-20260909.md)和[身份修正](../specs/baseline-estimate-identity-correction-20260909.md)定义本轮语义。

### 本地大产物保留边界

本家族本地 artifacts 约 **1.0 GiB**，达到 `C-externalize`；本轮官方原文/分钟 mark 压缩源和可再生账户明细是主要体积。它们仅本地保留当前一轮审计证据，不把完整 raw、日线投影、分钟数据或所有场景明细加入普通 Git；Git 仅保留说明与另行获准的小型摘要/锚点。身份修正复用相同源原文，不重复下载共同758窗口。

生成入口与规则见[脚本索引](../scripts/README.md)和本轮报告；所有重建必须使用原请求、输入及源 hash。后续增加整套大输出之前需另作可逆外置/LFS 方案（目标、指纹、回取验证与回滚），当前未获迁移授权，不删除、不移动历史。仓库预算工具的通过只代表其扫描范围，不能据此宣布本地约1 GiB原文已满足普通Git预算。

## 2026-09-08 保留：严格基线验证

- [baseline-verification-20260908 主摘要](baseline-verification-20260908/summary.json)：`BASELINE_NOT_VERIFIED`，净账 0/76 月、收益 null。首次摘要内核 hash 保留，最终 Regular/Special 修订另有[同事件重验收据](baseline-verification-20260908/accounting-gate/kernel-rate-type-amendment.json)。
- `plan/` 和 `initial-contract-retained.md` 是被拒绝的完整日 K 提名/初稿；首月漏 ADA，不能当有效原 Top10 或绩效输入。[formation-recheck](baseline-verification-20260908/formation-recheck/summary.json) 记录原部分上市日端点恢复。
- [accounting-gate 真实首个缺 mark 拒绝](baseline-verification-20260908/accounting-gate/first-held-funding-rejection.json)：参考建仓仅验数学，真实事件源缺价后账户不变，不是成交或净值批准。
- [funding-evidence](baseline-verification-20260908/funding-evidence/probe-summary.json) 保留原生官方资金费数据和回执；[terminal-evidence](baseline-verification-20260908/terminal-evidence/final-review.json) 保留官方终止时刻、原文和条件指数包络。均不覆盖发布数据湖，不自动升级净输入资格。
- 解释及未关闭项以[基线主报告](../diagnostics/binance-1d-mcsm-baseline-verification-20260908.md)为准。以下前轮材料不自动成为当前账户净收益证据。

## 2026-09-08 当前诊断

- [lifecycle-inputs-20260908](lifecycle-inputs-20260908/README.md)：固定组合返回帧与 7 批启动证据，独立输入 QA 18 项通过；17.18 MiB 投影为本地可再生产物，不是新数据湖底座。
- [lifecycle-diagnostic-20260908 摘要](lifecycle-diagnostic-20260908/summary.json)：固定数量的月名单、日级状态、landmark、首次双弱退出、市场对照及缺口。68 个完整配对月，不拼接净值。
- [funding-source-20260908 摘要](funding-source-20260908/summary.json)：原冻结账复现、官方源费率核验与旧同名单价格代数桥；费率核实不代表资金金额核实。
- 当前解释、限制和复现方式以[主报告](../diagnostics/binance-1d-mcsm-lifecycle-funding-round-20260908.md)为准。

## 保留的历史诊断

本目录保留 `2026-08-18` Long10 诊断，`2026-08-19` 宽度、固定20%波动目标/10-20缓冲、正收益限定/现金缺口诊断，以及 `2026-08-20` 可实盘化、MH136、target12 执行时序和赚钱效应/领涨延续诊断的汇总 JSON、全指标、成本归因、换仓清单、风险系数、日/月路径、状态标签、延续衰减、分年、时间切片、bootstrap、容量与 blocker 明细。

`2026-08-20` 执行审计裁决为 `HARD_BLOCKER / PERFORMANCE_INVALIDATED`：旧路径有 41 个不可成交或持仓缺价事件；按 `00:15 UTC` 可成交条件重选后仍有 15 个退出/估值 blocker。因此本目录中的历史绩效只能作方向性诊断，不能作为 promotion、runner handoff 或资金配置证据。

历史产物可由[脚本目录](../scripts/README.md)中的对应回测脚本按原冻结口径重建；旧日级派生缓存位于 `data/cache/binance_perp_1d_from_15m/`，只用于历史复现。本轮新价格诊断不从该缓存读取。
