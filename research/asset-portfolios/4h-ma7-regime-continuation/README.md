# Binance-4H-MA7-Regime-Continuation

- Full family name：`Binance-4H-MA7-Regime-Continuation`
- Alias：`BIN-4H-MA7-RC`
- Market / timeframe：Binance USD-M USDT perpetual，point-in-time 动态全市场币池，UTC `4h`
- 机制：闭合 `4h` 上的固定 `SMA7` 严格穿越只作为事件触发，P0 无条件检验穿越后是否有趋势延续。
- 当前状态：`explore / diagnostic-only / not promoted / not live-ready`
- 当前阶段：`P0` 为六资产诊断；`P0R-DATA` 合同已冻结但全市场绩效未写出；`P0R-GAP-GUARD` 缺口保护 `PASS`（验证范围见验收报告），不是策略有效或可上线。

## 边界

- 这是全新的 `4h` 独立家族，不是 [`Binance-1D-MA7-Regime-Continuation`](../1d-ma7-regime-continuation/README.md) 的新版本。
- 不继承 [`HYPE-4H-MA7-Asymmetric-Body-Trend`](../../hype/4h-ma7-asymmetric-body-trend/README.md) 的参数、收益或结论。
- 不继承 [`Binance-4H-EMA-Cross-LightGBM-Event-Selector`](../4h-ema-cross-lightgbm-event-selector/README.md) 的信号或模型；该线只提供全市场 `1h` 数据、PIT 币池、成本和周期研究方法参考。
- `4h SMA7` 只覆盖约 28 小时，不等于日线 `SMA7`；`4h SMA42` 仅为七日等时钟对照，不能替代或择优淘汰主研究对象。
- P0 禁止搜索 MA 长度、入场过滤、退出、杠杆、仓位或模型参数；禁止 LightGBM、神经网络和其他 ML。

## 入口

- 主账：[binance-4h-ma7-rc-core-ledger.md](binance-4h-ma7-rc-core-ledger.md)
- 决策记录：[decision-log.md](decision-log.md)
- P0 冻结合同：[specs/binance-4h-ma7-regime-continuation-p0-contract-2026-09-02.md](specs/binance-4h-ma7-regime-continuation-p0-contract-2026-09-02.md)
- P0 冻结配置：[configs/binance-4h-ma7-regime-continuation-p0.json](configs/binance-4h-ma7-regime-continuation-p0.json)
- P0 结果报告：[diagnostics/binance-4h-ma7-regime-continuation-p0-results-2026-09-02.md](diagnostics/binance-4h-ma7-regime-continuation-p0-results-2026-09-02.md)
- P0 数据范围修正：[diagnostics/binance-4h-ma7-regime-continuation-p0-data-scope-correction-2026-09-02.md](diagnostics/binance-4h-ma7-regime-continuation-p0-data-scope-correction-2026-09-02.md)
- P0R-DATA 合同：[specs/binance-4h-ma7-regime-continuation-p0r-data-contract-2026-09-03.md](specs/binance-4h-ma7-regime-continuation-p0r-data-contract-2026-09-03.md)
- P0R-GAP-GUARD 合同：[specs/binance-4h-ma7-regime-continuation-p0r-gap-guard-contract-2026-09-03.md](specs/binance-4h-ma7-regime-continuation-p0r-gap-guard-contract-2026-09-03.md)
- P0R-GAP-GUARD 验收：[diagnostics/binance-4h-ma7-regime-continuation-p0r-gap-guard-2026-09-03.md](diagnostics/binance-4h-ma7-regime-continuation-p0r-gap-guard-2026-09-03.md)
- 脚本：[scripts/research_binance_4h_ma7_regime_continuation_p0.py](scripts/research_binance_4h_ma7_regime_continuation_p0.py)（冻结历史复现，复现请用 P0R catalog 路径） · [P0R-DATA](scripts/research_binance_4h_ma7_regime_continuation_p0r_data.py) · [P0R-GAP-GUARD](scripts/research_binance_4h_ma7_regime_continuation_p0r_gap_guard.py)
- 产物索引：[artifacts/README.md](artifacts/README.md)
