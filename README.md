# Quant Research Lab

`quant-knowledge-graph → quant-research-lab → quant-runner`

Repository: [quant-research-lab](https://github.com/KathenZK/quant-research-lab)；Python package: `strategy_lab`（兼容保留）。
本仓库负责因子/策略研究、真实回测、IS/OOS、Walk-forward、DSR/PBO 和研究证据；分工见 [ARCHITECTURE](ARCHITECTURE.md)，迁移和历史兼容见 [命名迁移说明](docs/repository-name-migration.md)。

本仓库是 data-first 的量化策略研究档案。Agent 的核心约束是数据湖使用与研究材料组织，入口见 [AGENTS.md](AGENTS.md)。

线上执行在同级仓库 `/Users/ZK/OpenCode/quant-runner`；交接与授权边界见 [Lab / Runner 交接](docs/research-governance/lab-runner-handoff.md)。

长期维护的核心资产：

- `data/`：本地数据湖。
- `research/`：研究文档、策略家族主账和共享研究内核。
- `src/strategy_lab/`：窄范围、可复用、接口稳定的数据湖/归一化/质量检查/特征/因子工具。

旧策略平台、工作流引擎、Dashboard、泛化回测层和早期规划文档已归档到 `archive/`。

## 任务入口

- [AGENTS.md](AGENTS.md)：数据与文档约束、工作位置。
- [research/README.md](research/README.md)：研究档案总入口与家族路由表。
- [docs/README.md](docs/README.md)：数据规范、文档格式和按需使用的方法参考。

## 当前结构

```text
data/
  # 本地数据湖，结构见 docs/data-lake-spec.md

research/
  README.md                 # 家族路由表
  _shared-kernels/          # 跨资产共享研究引擎（冻结版本目录）
  hype/ btc/ eth/ sol/ trx/ bnb/ gold/ sox/
                            # 单资产策略家族
  us-indexes/ cn-indexes/   # 指数研究
  asset-portfolios/         # 组合与跨资产研究
  mu/                       # MU-HYPE-Transfer（扁平结构，grandfathered）
  platform/                 # 研究平台（数据湖治理等）

docs/
  data-lake-spec.md         # 数据湖结构与质量规范
  research-governance/      # 清单见 docs/README.md

src/strategy_lab/
  data/    # 最小数据湖内核：layout/schema/normalize/read-write/quality/features/factors

tests/    # active 数据湖内核测试 + 研究文档一致性检查

archive/   # 历史代码、配置、文档、研究和报告快照
```

家族目录组织见 [研究存储规则](.cursor/rules/research-report-storage.mdc)，runner 相关文档见 [交接格式](docs/research-governance/lab-runner-handoff.md)。

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
