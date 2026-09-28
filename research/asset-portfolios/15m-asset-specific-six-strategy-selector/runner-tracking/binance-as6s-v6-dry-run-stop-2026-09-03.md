# BIN-15M-AS6S-V6 dry-run 停止记录（2026-09-03）

## 结论

`stop`

用户已决定并在 quant-runner 执行：停止 V6 两条 dry-run 实例。家族研究状态保持 `archived`。Lab 不推断启停，本报告只记录已生效配置与停止前仓位。

## 配置差异（quant-runner 提交 `a5a3b2a`）

| 实例 | TOML `enabled` | lock `enabled_allowed` | lock `approval_level` | lock `mode` |
| --- | --- | --- | --- | --- |
| `bin-15m-as6s-v6-mark-np-dry-run` | `false` | `false` | `none` | `dry_run` |
| `bin-15m-as6s-v6-mark-preemptive-dry-run` | `false` | `false` | `none` | `dry_run` |

- Runner HEAD：`a5a3b2a`
- 配置：`configs/dryrun.toml`；lock：`configs/active-strategy.lock.json`
- strategy_id：`BIN-15M-AS6S-V6-NP` / `BIN-15M-AS6S-V6-SBP`
- kind：`asset_specific_six_selector_v6_mark_joint_np` / `asset_specific_six_selector_v6_mark_joint_preemptive`

## 服务器生效

- 服务：`quant-runner-dryrun`
- 重启时刻：`2026-09-03T06:47:02Z`
- 停止前：两实例 `position_open=0`

## 观察窗口

本条为停止事件记录，不是持续观察窗口。成交、费用/滑点、信号对拍不在本次范围。

## 来源

quant-runner 提交 `a5a3b2a` 与用户转述的服务器重启/仓位观察。Lab 未修改 runner 仓库。
