# Docs

本目录存放仓库级说明文档，不承载具体策略研究结论。具体策略材料仍在 [research/README.md](../research/README.md) 路由。

## 数据湖

- [data-lake-spec.md](data-lake-spec.md)：全仓库数据湖结构与质量约定的唯一规范。

## 文档与交接格式

- [strategy-status-glossary.md](research-governance/strategy-status-glossary.md)：主账与机器主状态的含义；正文和补充说明不限定词汇。
- [ci-boundaries.md](research-governance/ci-boundaries.md)：公开 CI、私有数据验收、冻结源码和证据副本的检查边界。
- [core-ledger-template.md](research-governance/core-ledger-template.md)：新建或重构家族主账时使用的模板。
- [external-reproduction-spec.md](research-governance/external-reproduction-spec.md)：交给仓库外读者的单文件复现规格。
- [lab-runner-handoff.md](research-governance/lab-runner-handoff.md)：runner 实现交接、执行证据和观察回流。
- [lab-live-spec-template.md](research-governance/lab-live-spec-template.md)：新建 Lab live spec / runner 交接规格时使用的模板。
- [artifacts-governance.md](research-governance/artifacts-governance.md)：`artifacts/` 目录的非破坏性治理（清单、预算与外置规则）。
- [schemas/lab-live-spec-frontmatter.schema.json](research-governance/schemas/lab-live-spec-frontmatter.schema.json)：Lab live spec YAML front matter 的校验 schema。
- [schemas/parity-report.schema.json](research-governance/schemas/parity-report.schema.json)：runner 对拍报告 JSON 的校验 schema。

## 按需参考

- [research-methods.md](research-governance/research-methods.md)：成本、窗口与验证方法选择；不作为所有研究的必做清单。
- [strategy-validation-gates.md](research-governance/strategy-validation-gates.md)：研究证据与运行状态迁移；固定研究方法套餐已取消。
- [trade-path-guide.md](research-governance/trade-path-guide.md)：根据问题选择图表，登记版本不自动触发出图。

- [ResearchIntegrityAssessment-v1](research/ResearchIntegrityAssessment-v1.md)：历史/探索/确认性结论、TrialRegistry、DSR/PBO 适用性与迁移接口。
