# AI Agent 仓库规则

仓库名为 `quant-research-lab`，Python 包名 `strategy_lab` 兼容保留。架构为 `quant-knowledge-graph → quant-research-lab → quant-runner`。历史制品不可为改名而重写，见 [迁移说明](docs/repository-name-migration.md)。

本仓库是 data-first 的量化策略研究档案。研究对象可以覆盖加密货币、美股、A 股、港股、大宗商品等多个市场；HYPE 只是当前较早展开的一条研究线。线上执行在同级仓库 `/Users/ZK/OpenCode/quant-runner` 中进行。

`.cursor/rules/` 是硬性工作约束的细则来源；状态机词表与验证门禁的内容细则在 `docs/research-governance/`，由对应规则文件指向。本文件只补充仓库入口、命名口径、active code 边界和术语。不要把 `.cursor/rules/` 的细则复制进本文件、根 `README.md` 或 `research/README.md`；若同一事项重复出现，以更具体、更严格的表述为准。

## 必读入口

当需要基于某个资产或策略家族作结论、修改研究文档或运行相关脚本前，必须先打开：

1. `research/README.md`：家族路由表与阅读顺序。
2. 对应资产或主题目录的 `README.md`，例如 `research/hype/README.md`、`research/mu/README.md`。
3. 对应策略家族的 `README.md` 与 core ledger / 主账。

## 命名与版本口径

- 不要根据 `V13`、`V21`、`V35`、`V36` 这类裸版本号判断策略身份；版本号只在具体资产、市场、周期和策略家族里有意义。
- 标准 family name 使用展开写法，优先包含资产、周期和机制；短 id 只作为历史别名。家族清单与别名以 `research/README.md` 和各资产 README 的路由表为准，不在本文件重复维护。
- “登记 / 记录 / 冻结 / 命名为 Vx”只固定版本身份：必须更新对应家族 core ledger / 主账，默认主状态为 `registered`，不自动触发 promotion（细则见 [.cursor/rules/research-report-storage.mdc](.cursor/rules/research-report-storage.mdc)；新建/重构主账用 [docs/research-governance/core-ledger-template.md](docs/research-governance/core-ledger-template.md)）。只更新 `specs/`、research note、diagnostic 或 decision log 不算完成版本登记。
- “promote / 晋升 / 上线 / 进入 dry-run”是状态迁移请求，不是登记同义词；必须有明确目标状态并满足 [strategy-validation-gates.md](docs/research-governance/strategy-validation-gates.md) 与 runner handoff 门禁。目标不明确时先确认，不得把“登记 Vx”解释为晋升。
- 所有新增或更新的长期研究文档默认使用中文，除非用户明确要求其他语言；策略名、版本号、参数、路径、指标名和状态术语可以保留英文原文。

## 术语口径

- 状态定义、合法组合和权威优先级只以 [strategy-status-glossary.md](docs/research-governance/strategy-status-glossary.md) 为准；AGENTS 不重复维护状态细则。`handoff` 只是 overlay 标签，不是主状态或 promotion 许可。
- `active research line` 指当前仍在 `research/` 下维护、会继续复现或更新结论的研究方向；不再维护的一次性历史脚本应归入 `archive/scripts/research/`。
- `current one-off research script` 指只服务某个研究问题的复现、搜索、审计、导出脚本；它可以保留在对应研究目录，但不应提升为 active package code。

## Active 代码规则

- Active package code 只限于可复用、有稳定接口的最小数据湖内核、数据归一化、数据质量检查、特征构建和因子计算，放在 `src/strategy_lab/`。
- 交易所抓取、补洞、研究搜索和一次性研究导出脚本必须放在对应 `research/.../scripts/`，并记录数据来源与质量校验。
- 被多个资产或家族复用的研究引擎放在 `research/_shared-kernels/`，按冻结版本目录管理（细则见 `.cursor/rules/research-report-storage.mdc`）。
- `archive/code/platform/` 只保留少量被长期研究文档引用的历史策略源码快照；它不是 active 平台，也不是可运行平台。
- 除非用户明确要求考古历史实现，否则不要把 archive 里的代码当作当前事实来源。

## 硬规则索引

细则由 `.cursor/rules/` 维护，不在本文件展开：

- [docs/data-lake-spec.md](docs/data-lake-spec.md)：数据湖结构与质量约定的唯一规范；`data-quality-first.mdc` 只负责强制引用该规范。
- `live-executable-strategy-research.mdc`：订单时序、成交假设、stop/lockout 审计和 promotion 前置条件。
- `backtest-standards.mdc`：回测默认包含最近 `1d/7d/1m/3m/6m/1y` 分片；Binance 默认手续费 `0.001`、滑点 `4 bps`，其他市场需明确成本口径。
- `research-report-storage.mdc`：研究目录、core ledger、索引更新义务、共享内核、artifacts 存放和 Canvas 边界。
- `lab-runner-handoff.mdc`：向 `quant-runner` 交接的规格契约、双向同步和 `runner-tracking/` 回流要求。
- `strategy-validation-gates.mdc`：从 `registered` 推进 promotion 的证据门禁及线上开平仓对账要求。
- `external-reproduction-spec.mdc`：对外（同事/外部 AI）复现规格必须自包含；仓库内部引用只能放在标记为"非复现依赖"的附录里，交付前做 no-repo 自检。
- `clickable-file-references.mdc`：对话回复和研究文档中的文件引用必须可点击——文档内跨文件引用用相对路径 Markdown 链接，对话中给用户的文件指引用 Markdown 链接或代码引用格式，不要只给纯文本路径。
- `strategy-trade-path-visualization.mdc`：策略初步成形、登记版本或逐笔行为发生重大变化时，默认生成并校验完整交易路径 HTML；每笔入场与对应出场必须连线。
