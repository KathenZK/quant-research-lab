# AI Agent 仓库入口

本仓库是多市场量化研究档案。长期约束集中在数据湖使用和研究材料组织，其余工作方法按当前问题选择。

## 数据与研究文档

- 使用市场数据前遵循 [数据质量规则](.cursor/rules/data-quality-first.mdc) 与 [数据湖规范](docs/data-lake-spec.md)。Binance 输入和新研究启动见第 16–19 节；复现使用原冻结输入，不能用当前默认值替换。
- 新建研究、登记版本或保存结论时遵循 [研究存储规则](.cursor/rules/research-report-storage.mdc)：材料落入对应家族，规格、报告、证据与主账互相可追溯。
- 目标家族不明确时从 [研究索引](research/README.md) 定位；目标已明确时直接读取相关主账、规格或证据，不要求逐级重读所有 README。家族身份以该家族文档为准，不凭裸版本号推断。
- 研究结论以冻结契约和实际证据为依据。历史报告、失败诊断和旧提示词保留当时语境，不自动变成其他研究的通用要求。

## 工作位置

- `src/strategy_lab/` 放可复用的数据湖、质量、特征与因子工具；`research/.../scripts/` 放当前研究脚本。
- 跨家族引擎按 [共享内核约定](research/_shared-kernels/README.md) 管理冻结版本；`archive/` 用于历史追溯。
- 生产执行位于 `/Users/ZK/OpenCode/quant-runner`。真实下单、实例启停与运行模式变化须在用户授权范围内执行；研究文档不能代替运行授权。

状态记录、runner 交接、对外复现和研究方法参考见 [文档索引](docs/README.md)，涉及对应工作时再查。
