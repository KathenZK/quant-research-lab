# Quant Platform 架构

`quant-knowledge-graph → quant-research-lab → quant-runner`

| 仓库 | 职责 |
| --- | --- |
| quant-knowledge-graph | 公开策略、因子、论文、公式、来源和知识关系 |
| quant-research-lab | 因子/策略研究、真实回测、IS/OOS、Walk-forward、DSR/PBO、研究证据 |
| quant-runner | 私有执行和运行风控 |

研究代码和 Python imports 继续位于 `src/strategy_lab/`，不会因仓库改名迁入知识层。现有研究规则、数据合同、证据和审批语义不变。知识层不直接向运行层发布策略。

本次迁移不修改运行层，也不建立新的执行接口。历史摘要和来源身份的兼容方式见 [仓库命名迁移](docs/repository-name-migration.md)。
