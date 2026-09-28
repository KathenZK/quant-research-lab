# HYPE-5M-Pullback-Trail Runner Tracking

本目录保存 `HYPE-5M-Pullback-Trail` 各版本在 quant-runner dry-run / live 期间的 runner 观察报告。

- 命名：`hype-5m-pbtr-runner-<YYYY-MM-DD>.md`。
- 每份报告必须写明：runner 配置（kind、mode、notional、杠杆）、观察窗口、成交笔数、实际费用/滑点 vs 回测假设、信号与指标对拍偏差、事件（重启、缺 K、拒单）以及 keep/stop/adjust 结论。
- core ledger 中 `forward-test required` 只能由本目录下的报告满足；口头描述不算证据。

## 当前跟踪对象

- `HYPE-5M-PBTR-V6.2.1`：quant-runner 同时保留 dry-run，并追认既有
  `hype-pullback-live` 为限时 `live / tiny-live-pilot / forward-test required`
  （复核截止 2026-07-24）。已有
  [`hype-5m-pbtr-runner-2026-07-09.md`](hype-5m-pbtr-runner-2026-07-09.md)
  的 16/16 replay parity；它不替代真实成交生命周期验收，也不允许 production sizing。
- 2026-07-11 执行安全收尾与 v2 待部署状态见
  [`hype-5m-pbtr-runner-2026-07-11.md`](hype-5m-pbtr-runner-2026-07-11.md)。
- 2026-07-30 零开单审计（runner 健康、独立信号重算确认零信号合法，keep）见
  [`hype-5m-pbtr-runner-2026-07-30.md`](hype-5m-pbtr-runner-2026-07-30.md)。
- 2026-09-03 tiny-live-pilot 续期至 `2026-12-24T00:00:00Z`；live halted incident 见
  [`hype-5m-pbtr-live-halted-incident-2026-09-03.md`](hype-5m-pbtr-live-halted-incident-2026-09-03.md)。
