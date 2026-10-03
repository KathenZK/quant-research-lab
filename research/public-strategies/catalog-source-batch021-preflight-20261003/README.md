---
research_classification: diagnostic_topic
---

# 批021既有目录来源准备

M1510 已由 root [独占登记](../claims-20261003-batch021-source-only.json)给父端 single dot executor，范围仅为来源、规则和数据复用准备；该执行者尚未启动本家族准备，root/m0288 完成的是只读独立来源支持。没有历史运行权限，没有 C0，没有新增策略配置或对照。

固定公开源码已验真，但原目录遗漏 `sell_profit_only=True` 及限价执行设置，不能把反向交叉写成无条件平仓。[源卡](source-card.safe.json)与[自撰报告](REPORT.safe.md)保留代码版本、源码指纹、仓库许可证据、规则差异、可复用日线输入指纹、经济假设和失败场景。

当前门禁为 [BLOCKED_SOURCE_FRAMEWORK_SEMANTICS](framework-gate.safe.json)。父端下一步需先锁定实际框架和配置，或明确声明执行适配，再做独立合成核验；不得删除盈利退出门、有限止损和 ROI 来迁就已有内核，不得把源码核实升级为严格复现。既有 831 行日线具备 HLC 原料，但暖启动、预算、成本、成交和控制复用仍须单独冻结。

这里保存三件经审查的自撰安全载荷原字节；原源码、许可证正文、HTTP 证据及完整私有目录条目不在公开 Git。本地私有证据尚待 Library 持久化，不称已远端备份。M2903/M3710/M0974 的[批020历史门禁](../catalog-daily-next3-batch020-preflight-20261003/HISTORY-RELEASE-GATES-v1.md)继续关闭。
