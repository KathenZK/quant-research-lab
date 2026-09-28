---
research_classification: diagnostic_topic
---
# QuantGraph 研究联通

V4 当前入口：[证据链与研究审计](diagnostics/evidence-research-v4.md)。三个模板已补齐合同/许可/数据需求；真实数据仍 PARTIAL/raw_unaccepted，正式候选与正式回测均 0。

本主题负责知识候选筛选、实验族去重、研究结果和晋级文件的接口验证。
不代表任何策略通过回测，也不改变既有研究家族或 runner 状态。

当前状态：工程联通已验证；真实候选 `INSUFFICIENT_EVIDENCE / not promoted`。

入口：[冻结范围](specs/pipeline-v1.md) · [实测结果](diagnostics/acceptance.md) ·
[决策记录](decision-log.md) · [复现脚本](scripts/README.md)。

v2：[实际候选与真实研究阻断](diagnostics/platform-v2.md) ·
[离线晋级契约](../../../docs/research/StrategyArtifact-v2.md)。当前 5813 条记录中合格候选仍为 0；没有真实策略回测或晋级。

v3：[统一研究与证据结果](diagnostics/evidence-research-v3.md)。原始语料 strict parsed 260；三个显式派生模板只缺数据；eligible/正式回测仍为 0。两个真实行情私有诊断不计正式回测。
