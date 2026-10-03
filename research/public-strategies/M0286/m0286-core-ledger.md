# PUBLIC-M0286-MULTIMA 主账

稳定 ID M0286；原始名称 MultiMa V2；公开采集策略专区。BTC/USDT、Binance 现货、4h 为研究者预先指定实例，不代表原作者币池。不同成本/延迟配置均属此 ID，不计作新策略或严格复现。

| 版本 | 状态 | 结果与证据 | 决策 |
| --- | --- | --- | --- |
| M0286-BTCUSDT-4H-MULTIMA-LONG-20261003 | explore / not promoted / not live-ready；HYPOTHESIS；DIAGNOSTIC_ONLY | [冻结契约](specs/M0286-first-replay.json)，基准收益 38.13%、MDD 10.67%、日 Sharpe 1.147；[完整报告](diagnostics/M0286-20261003.md) | 不晋级。买持收益明显更高；长预热不足、ROI 时点代理、PIT/严格收盘/成交可得性及原框架运行均未证实。 |

累计本次 1 ID、4 策略配置、1 对照；参数搜索 0，严格复现 0。过去全库搜索次数未知，当前历史窗口已曝光，不作 OOS/DSR/PBO 声明。一次恢复和因果核验不增加新配置计数。

规格与首次运行证据冻结，不原地覆盖；规则、预热区间、分钟执行或输入变化需新版本。未来方向是先验证长历史初始化与 ROI 子周期执行，再设计未曝光窗口；本次不执行这些扩展。无 runner、dry-run 或实盘交接。
