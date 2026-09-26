# 联通验收与候选判定

真实 GrokBot 批次已从 HTTP API 流入研究候选筛选，结果为
**INSUFFICIENT_EVIDENCE**。工程路径可用，但没有可启动的完整策略研究。

| 项目 | 实测 |
|---|---:|
| 输入记录 | 5813 |
| 严格规则通过 | 170 |
| 方法族 / 模板 | 23 / 32 |
| 规则不完整排除 | 5643 |
| 达到全部研究准入条件 | 0 |
| 真实回测次数 / 晋级数 | 0 / 0 |

170 条规则全部还缺许可、独立来源核验、执行契约及数据可得性证据。
同模板的多个阈值/ETF 不能拆成独立概念以达到 100–300 个目标。
[聚合筛选结果](../artifacts/candidate-summary.json) 保存输入摘要与各阻断计数。

[Synthetic diagnostics](../artifacts/synthetic-diagnostics.json) 仅验证数值计算和结果格式：
已实际计算固定样本内/外、两个固定前向窗口、PBO、DSR、参数区间；
它们不是 5813 条策略的回测结果，也不构成任何真实策略的研究证据。
证据写回接口经实际 HTTP 调用验证，kind=PIPELINE_DIAGNOSTIC、
validation_status=SUBMITTED_NOT_INDEPENDENTLY_VERIFIED，promotion_triggered=false。

实际制品契约测试由本仓库导出合成 paper 文件，runner 校验摘要和必要字段；
错误摘要、未批准状态、未来批准时间、缺成本/数据/OOS/parity 或 live 目标都被拒绝。
没有改变任何运行策略、账户配置或 active lock。

下一阶段须逐模板补来源/许可审核和执行契约，取得相应数据后冻结实验。
这些属于尚未完成的研究准备工作；不能只合并工程 PR 就宣称研究目标完成。
