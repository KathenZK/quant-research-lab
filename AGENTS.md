# 量化研究仓库

- 使用市场数据时查[数据质量规则](.cursor/rules/data-quality-first.mdc)和[数据湖规范](docs/data-lake-spec.md)。Binance 输入与新研究启动见第 16–19 节；复现沿用原冻结输入。
- 新建研究、登记版本、保存结论按[研究存储规则](.cursor/rules/research-report-storage.mdc)，让家族主账、规格、报告和证据可追溯。
- 家族不明时查[研究索引](research/README.md)；已明确时直接查对应主账、规格和证据，不凭裸版本号认定身份。
- 结论依据冻结契约和实际证据；旧报告、失败诊断和提示词不自动成为其他研究的规则。
- 可复用数据与特征工具放 `src/strategy_lab/`；研究脚本放 `research/.../scripts/`；跨家族引擎按[共享内核约定](research/_shared-kernels/README.md)冻结；`archive/` 用于历史追溯。
- 状态、runner 交接和对外复现等按任务查[文档索引](docs/README.md)。生产执行在 `/Users/ZK/OpenCode/quant-runner`；研究文档不代替下单、启停或运行模式变更的用户授权。
