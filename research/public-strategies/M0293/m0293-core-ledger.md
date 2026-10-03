# PUBLIC-M0293-REINFORCED-AVERAGE 主账

稳定ID M0293；原名ReinforcedAverageStrategy；公开采集策略专区。BTC/USDT、Binance现货、4h为研究者预先指定实例。高周期48h来自同一4h输入的因果聚合，无额外行情源。

| 版本 | 状态 | 结果与证据 | 决策 |
| --- | --- | --- | --- |
| M0293-BTCUSDT-4H-EMA8-21-48H-SMA50-20261003 | explore / not promoted / not live-ready；HYPOTHESIS；DIAGNOSTIC_ONLY | [协议](specs/M0293-first-replay.json)、[报告](diagnostics/M0293-20261003.md)；基准收益55.73%、MDD28.85%、日Sharpe0.903 | 不晋级。落后同口径买持，对成本/成交时点敏感；原作者环境、充分预热、PIT和真实可成交性均未建立。 |

本次1 ID、4策略配置、1对照、0参数搜索、0严格复现；复核/恢复不是新增配置。协调者独立验收前不写全局完成数。历史窗口已曝光、总搜索次数未知，不作OOS/DSR/PBO声明。

版本变更需新目录/新契约，不覆盖初次规范或结果。后续可预登记更长预热、跨资产、执行细节及新窗口研究；本批不执行这些扩展。无runner、dry-run或实盘交接。
