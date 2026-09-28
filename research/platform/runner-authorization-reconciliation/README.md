# Runner Authorization Reconciliation

- Full family name：`Runner-Authorization-Reconciliation`
- Alias：`RUNNER-AUTH-RECON`
- 范围：把 Lab 研究文档主状态与 quant-runner lock / TOML 授权事实对账；不承载策略绩效，也不授权启停。
- 当前状态：`explore / platform-audit`

## 边界

- 实例授权与实际运行只以 `quant-runner` 为准。Lab 只记录用户已执行的运维事实，不推断启停。
- 本目录不是策略家族，不登记 `Vx`，不写入 promotion。

## 入口

- 决策记录：[decision-log.md](decision-log.md)
- 2026-09-03 对账：[diagnostics/runner-lock-vs-lab-2026-09-03.md](diagnostics/runner-lock-vs-lab-2026-09-03.md)
- 脚本说明：[scripts/README.md](scripts/README.md)
- 产物说明：[artifacts/README.md](artifacts/README.md)
