# 仓库命名迁移（2026-09-28）

正式架构：`quant-knowledge-graph → quant-research-lab → quant-runner`。

原仓库 `KathenZK/quant-strategy-lab` 原地更名为 [KathenZK/quant-research-lab](https://github.com/KathenZK/quant-research-lab)，保留 Git 历史、分支、标签和原 PR。不是新建仓库；迁移文档/代码通过独立 PR 审核，不自动合并。

## 当前名称与兼容边界

- Repository / Python distribution：`quant-research-lab`；Python package/import：`strategy_lab`（兼容保留）。目录 `src/strategy_lab`、包数据和原 import 路径不变。
- 新 repository identity、producer、研究证据 URI 和默认项目名使用新名；原始数据、已生成制品、来源 URI、commit/hash 和历史审核记录不回写。
- v2 研究端校验兼容历史 producer `quant-strategy-lab`；旧 fixture 原字节保留，新 fixture 使用新 producer。默认值仅为 schema 元数据，不会替写或补齐输入。
- 历史代码摘要仍指向冻结 commit 的字节。采集脚本只更新 User-Agent 名称；不要用新脚本 hash 替换旧证据中的 hash。锁定来源、冻结内核、交易逻辑和统计方法没有变化。
- 本轮不修改 quant-runner；旧外部消费者可能仅接受旧 producer。运行端对新 producer 的兼容尚未在本轮验证，不可因此提交或发布新运行制品。

## 本地 workspace

正式目录：`~/OpenCode/quant-research-lab`，origin：`git@github.com:KathenZK/quant-research-lab.git`。
现有 linked worktree 的 Git 指向已修复，旧 `~/OpenCode/quant-strategy-lab` 暂留为到新目录的兼容符号链接，服务已有聊天和历史绝对路径；新任务必须使用新目录。旧 worktree 目录名作为历史工作副本保留。

原研究 main 有独立提交和未提交研究内容，未 reset、stash 或合并；`git pull` 在该目录被已有改动阻止。迁移分支从最新 `origin/main` 的隔离副本建立，那里完成 fetch/pull 和验证。PR 合并后仍需单独处理原 main 的既有分叉。

原 origin 的 Codeup 推送地址移到 `codeup-legacy`，仅作为旧镜像兼容记录；本轮不更名 Codeup，也不向其推送。origin 仅指向 GitHub。此机器 SSH 22 不可用，仓库级 `core.sshCommand` 使用 GitHub SSH 443，并用原 GitHub host key 校验。

Codex 当前工具没有修改项目 folder registration 的接口，且 Computer Use 禁止操作 Codex 自身界面。原生注册未更新；已创建 `~/OpenCode/Quant Platform.code-workspace`，其中研究目录为新路径。知识仓库提供同样的 `quant-platform.code-workspace`（供同级 checkout 使用）。兼容链接保证仍绑定旧目录的并行聊天可继续访问。用户可在 Codex 的“编辑项目”里将研究 folder 改成新目录；本轮未改写 Codex 内部状态库或历史聊天。

## 保留的历史引用

以下文件中的旧名是历史 provenance / 兼容记录，不是当前仓库名。保留原文件字节，避免改变旧证据摘要：

- `archive/docs/canvas-migration-plan.md`（冻结历史记录）
- `archive/docs/hype-cursor-artifacts/agent-artifacts.md`（冻结历史记录）
- `archive/docs/hype-cursor-artifacts/canvas-catalog.md`（冻结历史记录）
- `archive/docs/hype-cursor-artifacts/canvas-groups/README.md`（冻结历史记录）
- `archive/docs/hype-cursor-artifacts/canvas-groups/core-ledgers.md`（冻结历史记录）
- `archive/research/legacy-strategies/crowding-reversal-mvp.md`（冻结历史记录）
- `contracts/fixtures-v2/synthetic-artifact.json`（冻结历史记录）
- `docs/research/StrategyArtifact-v2.md`（兼容 schema / 说明）
- `research/asset-portfolios/1d-derivatives-structure-trend-opportunity/artifacts/p1_oi_funding_development_2026-08-10/p0_data_capacity.json`（冻结历史记录）
- `research/asset-portfolios/1d-derivatives-structure-trend-opportunity/artifacts/p1_oi_funding_development_2026-08-10/p1_report.json`（冻结历史记录）
- `research/asset-portfolios/1d-ma7-deviation-continuation/diagnostics/binance-1d-ma7dc-campaign-tracking-2026-08-04.md`（冻结历史记录）
- `research/asset-portfolios/1d-ma7-deviation-continuation/diagnostics/binance-1d-ma7dc-initial-validation-2026-08-04.md`（冻结历史记录）
- `research/asset-portfolios/1d-ma7-deviation-continuation/diagnostics/binance-1d-ma7dc-tolerance-exit-2026-08-04.md`（冻结历史记录）
- `research/asset-portfolios/1d-tradfi-futures-tsmom/lab-handoff-2026-08-19.md`（冻结历史记录）
- `research/asset-portfolios/1h-price-impulse-campaign/specs/binance-mtf-pullback-trend-campaign-goal-task-spec-draft-2026-08-03.md`（冻结历史记录）
- `research/asset-portfolios/multi-timeframe-pullback-trend-campaign/diagnostics/binance-mtf-ptc-goal-final-report-2026-08-03.md`（冻结历史记录）
- `research/hype/15m-riptide/diagnostics/hype-15m-riptide-v13-cache-audit-2026-06-30.md`（冻结历史记录）
- `research/hype/1d-ma7-asymmetric-body-trend/artifacts/hype_1d_ma7_abt_v7_1_runner_strict_parity_2026-08-12.json`（冻结历史记录）
- `research/hype/1d-ma7-asymmetric-body-trend/artifacts/hype_1d_ma7_abt_v7_2x_leverage_2026-08-11.json`（冻结历史记录）
- `research/hype/5m-micro-scalp/notes/hype-5m-micro-scalp-v1-2-registration-and-leverage-retest-2026-07-01.md`（冻结历史记录）
- `research/mu/artifacts/mu-polygon-15m-acceptance-2026-08-06.json`（冻结历史记录）
- `research/platform/cross-sectional-alpha-pipeline/cross-sectional-alpha-pipeline-readiness-audit-2026-08-18.md`（冻结历史记录）
- `research/platform/quantgraph-integration/decision-log.md`（冻结历史记录）
- `src/strategy_lab/knowledge/strategy_artifact_v2.schema.json`（兼容 schema / 说明）

## 验证边界

完整 CI 命令为 locked 依赖安装、`scripts/governance/preflight.py` 和 `pytest -q`；后者覆盖 unit / integration / governance tests。仓库没有独立 typecheck 配置。额外运行 `mypy 1.19.1 --ignore-missing-imports src/strategy_lab`：迁移分支与原 main 均为 35 个源文件、8 个文件中的 81 个错误，逐条对照一致。不能把这项额外检查报告为通过，也不在命名 PR 中修复原有类型问题。

本机完整测试使用原生 ARM Python 3.12；CI 使用 Python 3.11。原 Intel Python 3.11 与本机 ARM libomp 不兼容，失败发生在 LightGBM 导入。最终按现有 CI 的 `pytest -q` 执行：849 passed / 98 skipped；跳过项缺本地数据或未跟踪产物。治理和 lint 通过。没有改动依赖版本或现有缺数据跳过规则。
