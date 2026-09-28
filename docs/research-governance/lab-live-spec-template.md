---
schema_version: "1.0"
spec_role: lab_handoff
family_id: FAMILY-ID
main_status: live spec
spec_status: draft
strategy_id: FAMILY-ID-V1
runner_kind: runner_kind
peer_spec: crates/quant-runner/src/runner/strategies/runner_kind/FAMILY-ID-V1-SPEC.md
approval_level_max: none
overlays:
  - handoff
---

# <Family Full Name> <Version> Lab Live Spec

> 状态：`live spec`。本规格描述 runner 实现合同；实例启用与实际模式只由 `quant-runner` 决定。

## Front matter 约定

`research/**/live-specs/` 下除 `README.md` 外的每个 Markdown 都必须有 YAML front matter，且 `spec_role` 必须是下列之一，否则 `validate_live_specs.py` 报 ERROR：

| `spec_role` | 用途 | schema |
| --- | --- | --- |
| `lab_handoff` | runner 交接合同（本模板） | `lab-live-spec-frontmatter.schema.json` |
| `external_reproduction` | 对外自包含复现规格 | `live-spec-external-reproduction-frontmatter.schema.json` |
| `ensemble_component` | ensemble 子配置 / 子腿规格 | `live-spec-ensemble-component-frontmatter.schema.json` |
| `live_feasibility` | 实盘可行性评估（不是交接合同） | `live-spec-live-feasibility-frontmatter.schema.json` |

后三种角色的最小字段：`schema_version`、`spec_role`、`family_id`、`strategy_id` 或 `component_id`、`spec_status`；`supersedes` / `superseded_by` 可选。

`lab_handoff` 的 `peer_spec`（含 `implementations[].peer_spec`）必须是 `quant-runner` 仓库内的相对路径：以 `crates/` 开头，不得以 `quant-runner/` 或 `/` 开头。

若环境变量 `QUANT_RUNNER_ROOT` 或默认路径 `/Users/ZK/OpenCode/quant-runner` 存在，校验每个 `spec_status: active` 的 `lab_handoff`：peer 文件必须存在，且对方 front matter 的 `peer_spec` 反向指向本 Lab 文件。仓库不存在时输出 `SKIPPED`，不把跨仓检查记为通过。

`main_status` 为 `dry-run` 或 `live` 的 active `lab_handoff` 还须通过 `check_promotion_surface.py`：家族 `runner-tracking/` 非空；家族 `artifacts/` 存在符合 `parity-report.schema.json` 且 `conclusion ≠ MISSING_EVIDENCE` 的报告。最新 runner-tracking 报告距今超过 45 天只 WARNING，不单独失败。

## 身份与边界

- Family / version：
- Exchange / market / symbol / timeframe：
- Runner module：

> Joint SPEC 不得使用并行的 `strategy_ids` / `runner_kinds` 列表。删除标量
> `strategy_id`、`runner_kind`、`peer_spec`，改用下面的一一映射：
>
> ```yaml
> implementations:
>   - strategy_id: FAMILY-ID-V1-A
>     runner_kind: runner_kind_a
>     peer_spec: crates/quant-runner/src/runner/strategies/runner_kind_a/FAMILY-ID-V1-A-SPEC.md
>   - strategy_id: FAMILY-ID-V1-B
>     runner_kind: runner_kind_b
>     peer_spec: crates/quant-runner/src/runner/strategies/runner_kind_b/FAMILY-ID-V1-B-SPEC.md
> ```

## 完整参数表

<!-- 使用 quant-runner 的准确配置字段名与字面值。 -->

## 数据与 warmup

<!-- 来源、schema、closed-bar-only、质量门禁、最小 warmup。 -->

## 执行与恢复合同

<!-- entry/exit/order/cancel/restart/missing-bar/kill-switch。 -->

## 成本与资金

<!-- fee、slippage、funding；资金边界可链接 operations/decision log。 -->

## Runner TOML

```toml
# 完整可解析示例
```

## 验证与未决缺口

- Smoke：
- Offline parity JSON artifact：
- Online open/close reconciliation：
- Remaining blockers：

## 双向链接

- Core ledger：
- Research evidence：
- Runner SPEC：
