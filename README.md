# Quant Research Lab

`quant-knowledge-graph → quant-research-lab → quant-runner`

Repository: [quant-research-lab](https://github.com/KathenZK/quant-research-lab)；Python package: `strategy_lab`（兼容保留）。
本仓库负责因子/策略研究、真实回测、IS/OOS、Walk-forward、DSR/PBO 和研究证据；分工见 [ARCHITECTURE](ARCHITECTURE.md)，迁移和历史兼容见 [命名迁移说明](docs/repository-name-migration.md)。

本仓库定位为"数据优先"的量化研究档案，而不是通用策略平台。研究对象是**线上可实盘执行的策略**：任何策略在进入 promotion 状态（`live spec`、`dry-run`、`live`）前，都必须先证明它能被真实订单时序复现。本仓库不定义额外的模拟盘阶段；模拟盘/仿真运行统一称为 `dry-run`，真实下单归入 `live`，资金边界由子账户资金、runner 配置或上线 decision log 管理。回测依赖无法真实成交的假设时，它不是"高收益候选"，而是失败诊断——这是本项目从趋势策略和 `HYPE-5M-Pullback-Trail` V2.1A/V3.3/V4 锁仓止损审计中反复付出代价换来的硬门槛（细则见 `.cursor/rules/live-executable-strategy-research.mdc`）。

策略通过研究审计后，在同级仓库 `/Users/ZK/OpenCode/quant-runner` 中实现并进行 dry-run 或小额实盘；`quant-runner` 的代码、配置、授权锁、服务状态和运行账本是实例运行与授权的唯一真源，Lab 不保存实例授权 manifest。交接契约见 `.cursor/rules/lab-runner-handoff.mdc`。

长期维护的核心资产：

- `data/`：本地数据湖。
- `research/`：研究文档、策略家族主账和共享研究内核。
- `src/strategy_lab/`：窄范围、可复用、接口稳定的数据湖/归一化/质量检查/特征/因子工具。

旧策略平台、工作流引擎、Dashboard、泛化回测层和早期规划文档已归档到 `archive/`。

## 先读这些

- `AGENTS.md` 与 `.cursor/rules/`：AI agent 在本仓库工作的约束；细则以 `.cursor/rules/` 为准。
- `research/README.md`：研究档案总入口与家族路由表。
- `docs/research-governance/strategy-status-glossary.md`：策略状态词与状态机的唯一定义。

## 当前结构

```text
data/
  # 本地数据湖，结构见 docs/data-lake-spec.md

research/
 README.md          # 家族路由表
 _shared-kernels/      # 跨资产共享研究引擎（冻结版本目录）
 hype/ btc/ eth/ sol/ trx/ bnb/  # 单资产策略家族
 asset-portfolios/      # 组合与跨资产研究
 mu/             # MU-HYPE-Transfer（扁平结构，grandfathered）

docs/research-governance/
 strategy-status-glossary.md # 状态机术语表
 strategy-validation-gates.md # 策略推进门禁
 core-ledger-template.md      # 主账模板

src/strategy_lab/
 data/    # 最小数据湖内核：layout/schema/normalize/read-write/quality/features/factors

tests/    # active 数据湖内核测试 + 研究文档一致性检查

archive/   # 历史代码、配置、文档、研究和报告快照
```

每个策略家族目录的内部结构（`README.md`、core ledger、`decision-log.md`、`diagnostics/`、`ablations/`、`specs/`、`live-specs/`、`notes/`、`scripts/`、`artifacts/`、`runner-tracking/`）由 `.cursor/rules/research-report-storage.mdc` 与 `.cursor/rules/lab-runner-handoff.mdc` 定义，不在本文件重复。

## 数据湖规范

数据湖的唯一结构与质量规范见 [`docs/data-lake-spec.md`](docs/data-lake-spec.md)；本文件不重复维护具体约定。

## 快速开始

```bash
# 严格按 uv.lock 安装项目和开发依赖
uv sync --locked --extra dev --extra ml

# 与 CI 相同的治理、数据契约和 lint 门禁
uv run --locked --extra dev --extra ml python scripts/governance/preflight.py

# 需要时运行全量测试
uv run --locked --extra dev --extra ml pytest -q
```

## QuantGraph 接入

[知识候选筛选、研究证据与 paper 制品契约](research/platform/quantgraph-integration/README.md)。
知识来自 quant-knowledge-graph API；执行仍由独立 quant-runner 承担。
