# AI Agent 仓库入口

本仓库是多市场量化策略研究档案。生产执行位于同级仓库 `/Users/ZK/OpenCode/quant-runner`。

## 上下文与事实来源

- 涉及某个资产或家族的结论、研究文档或脚本时，先从 [research/README.md](research/README.md) 和对应资产/主题 README 定位，阅读目标家族 README 与 core ledger；再按问题查规格和证据。已读且未变更的内容不必重复打开。
- 家族身份以家族 README / 主账为准，使用完整 family name；裸版本号和相似指标不能证明属于同一家族。
- 状态词、登记与晋升的区别、研究与 runner 的权威边界，以 [状态术语表](docs/research-governance/strategy-status-glossary.md) 为准。版本登记更新主账；状态迁移按目标核验证据。
- `archive/` 是历史材料，仅在需要追溯时使用；当前结论以当前规格和可核验的证据为准。

## 按任务读取规则

下表列出适用范围；只读取与当前工作有关的规则。规则中的规范、模板和 schema 是相应细节的维护入口，不把它们复制进索引。冲突时按事实来源和适用范围核对，不以“更严格”的措辞自动裁决。

| 当前工作 | 规则 / 规范 |
| --- | --- |
| 读取、抓取、修复市场数据或据此作结论 | [数据质量](.cursor/rules/data-quality-first.mdc) → [数据湖规范](docs/data-lake-spec.md)；Binance 输入与新研究启动见第 16–19 节，历史复现保留原冻结输入 |
| 新建家族、登记版本、保存研究结论 | [研究存储](.cursor/rules/research-report-storage.mdc) |
| 策略收益回测、成本或近期表现审计 | [回测口径](.cursor/rules/backtest-standards.mdc) |
| 评估订单时序、成交模型或实盘可执行性 | [执行可行性](.cursor/rules/live-executable-strategy-research.mdc) |
| 晋升、门禁复核或状态迁移 | [验证门禁](.cursor/rules/strategy-validation-gates.mdc) → [门禁规范](docs/research-governance/strategy-validation-gates.md) |
| runner 交接、实现对拍或运行观察回流 | [Lab / Runner 交接](.cursor/rules/lab-runner-handoff.mdc) |
| 给仓库外读者或 AI 的复现规格 | [对外复现](.cursor/rules/external-reproduction-spec.mdc) |
| 请求交易路径图或正式登记/冻结策略版本 | [交易路径图](.cursor/rules/strategy-trade-path-visualization.mdc) |
| 在回复或文档中引用文件 | [文件链接](.cursor/rules/clickable-file-references.mdc) |

## 代码放置

- `src/strategy_lab/`：可复用、接口稳定的数据湖、归一化、质量检查、特征与因子工具。
- `research/.../scripts/`：当前研究的抓取、补洞、搜索、审计与导出脚本；数据来源和质量校验随研究留存。
- [research/_shared-kernels/](research/_shared-kernels/README.md)：跨资产/家族复用的研究引擎，按该目录约定冻结版本。
- `archive/scripts/research/`：已不再维护的历史一次性脚本；`archive/code/platform/` 不作为可运行平台。
