---
research_classification: diagnostic_topic
---
# dot 后续来源、规则与重复项审计

本次有限已读catalog范围和七项额外源码周期核查中，没有确认新增、未认领且可原样使用现有4h输入的策略；这不是全6973条的穷尽结论。dot原生5m首CHECKSUM被Tunnel403拒绝后，M0298/M0304历史运行仍0，保留失败证据，不代抓、转交行情、换源、改周期或重试。

本主题只分配M0296、M0299、M0312、M0314的来源／规则／重复项审计，没有历史收益任务，也不触碰行情。[固定源码与审计重点](source-audit-candidates.json)均已实际读取；四个源码固定jesse-ai/example-strategies提交7c91e0a37bf62165790120d730442e4f6eb00364，MIT许可。原作者引擎版本仍未确定，需明确区分参考引擎与原运行环境。

[输出契约](../dot-batch005-output-contract-20261003.json)和[认领](../claims-20261003-batch008.json)由root单写。每个ID单独交原文出处、规则差异、依赖／时间因果／参数和可执行性证据，结果为源码审计或精确阻塞；不得算策略回测或严格复现。稳定ID不合并、删改或重新编号。重复关系只是带证据的关联，不覆盖原记录。

[决策记录](decision-log.md)。
