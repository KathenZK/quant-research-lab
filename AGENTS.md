# 量化研究仓库

家族不明确时查[研究索引](research/README.md)；已明确时直接查家族主账、规格和证据。使用完整家族身份，不凭裸版本号判断。长期研究文档默认中文，标识和参数保留原文。

按任务读取以下规则，不要求逐级读全部 README：

| 工作 | 入口 |
| --- | --- |
| 市场数据、Binance 输入或新研究启动 | [数据质量](.cursor/rules/data-quality-first.mdc)、[数据湖规范](docs/data-lake-spec.md)第 16–19 节；复现沿用原冻结输入 |
| 研究存储、版本登记和主账 | [存储规则](.cursor/rules/research-report-storage.mdc) |
| 回测收益、执行成本 | [回测口径](.cursor/rules/backtest-standards.mdc) |
| 订单时序与实盘可执行性 | [执行可行性](.cursor/rules/live-executable-strategy-research.mdc) |
| 状态、晋升、门禁复核 | [状态词表](docs/research-governance/strategy-status-glossary.md)、[验证门禁](.cursor/rules/strategy-validation-gates.mdc) |
| runner 交接、对拍、观察回流 | [交接规则](.cursor/rules/lab-runner-handoff.mdc) |
| 对外复现规格 | [对外复现](.cursor/rules/external-reproduction-spec.mdc) |
| 交易路径图、正式登记/冻结版本 | [路径图规则](.cursor/rules/strategy-trade-path-visualization.mdc) |
| 文件引用 | [链接规则](.cursor/rules/clickable-file-references.mdc) |

登记更新家族主账，不等于晋升或运行授权；`handoff` 只是附加标签。规则冲突按事实来源和适用范围核对，不以“更严格”的措辞自动裁决。

可复用数据与特征工具放 `src/strategy_lab/`；当前研究脚本放家族 `scripts/`；跨家族引擎按[共享内核约定](research/_shared-kernels/README.md)冻结。`archive/` 是历史材料，不作为当前可运行平台。

生产执行在 `/Users/ZK/OpenCode/quant-runner`，启停和模式变更须在用户授权范围内。Lab 保存研究状态与证据；回流 DRAFT 经人审后才可作门禁证据。
