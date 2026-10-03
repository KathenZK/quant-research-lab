# Research

`research/` 管理研究文档、当前研究脚本与保留产物。本文件用于定位家族、机制、状态和主账；版本结论从主账追溯到规格与证据。

## 使用入口

- 从下表定位家族；目标已明确时直接读取相关主账、规格或证据。资产与家族 README 用于辨认身份和查找材料。
- Binance 价格与资金费率输入见 [data-lake-spec.md](../docs/data-lake-spec.md) 第 16–19 节与 [数据治理入口](platform/data-lake-governance/README.md)。新研究固定组合并执行启动前校验，历史复现使用原冻结输入。
- 数据与文档规则见 [AGENTS.md](../AGENTS.md)；记录状态时查 [状态术语表](../docs/research-governance/strategy-status-glossary.md)，推进运行状态时查 [状态迁移要求](../docs/research-governance/strategy-validation-gates.md)。

## HYPE 策略家族

详细路由与防串线警告见 [hype/README.md](hype/README.md)。

| Full family name | Alias | Directory | 机制 | 状态 |
| --- | --- | --- | --- | --- |
| `HYPE-1D-MA7-Cross-ATR-Ratchet` | `HYPE-1D-MA7-CAR` | [hype/1d-ma7-cross-atr-ratchet/](hype/1d-ma7-cross-atr-ratchet/README.md) · [主账](hype/1d-ma7-cross-atr-ratchet/hype-1d-ma7-car-core-ledger.md) | 日线MA7穿越、收盘/日K高低价停滞计时、ATR单向收紧、RSI6加速止盈 | 用户正式命名V1：+360.02%/27.42%；V2：+449.61%/27.42%；V3：+548.65%/26.99%/17笔；共同保留空单提前止盈、关闭反手，版本以主账为准 |
| `HYPE-Candle-Count-Reversal` | `HYPE-CC` | [hype/15m-candle-count-reversal/](hype/15m-candle-count-reversal/README.md) · [主账](hype/15m-candle-count-reversal/hype-cc-core-ledger.md) | 10-of-8 K 线颜色反转 + ATR 风控 | V35 dry-run / forward-test required |
| `HYPE-EMA-Crossover` | `HYPE-EMA-X` | [hype/15m-ema-crossover/](hype/15m-ema-crossover/README.md) · [主账](hype/15m-ema-crossover/hype-ema-x-core-ledger.md) | EMA 金叉/死叉家族（V14 时代演化） | V18 dry-run / forward-test required |
| `HYPE-EMA-Trend-Breakout` | `HYPE-EMA-TB` | [hype/15m-ema-trend-breakout/](hype/15m-ema-trend-breakout/README.md) · [主账](hype/15m-ema-trend-breakout/hype-ema-tb-core-ledger.md) | EMA96/384 趋势突破 / 追多追空 | `V35 live / external-observation`；`V35.1 dry-run / not live-ready`；`V35.2-V35.3、V36-V41 registered / not promoted` |
| `HYPE-15M-Multidimensional-Trend-Pyramiding` | `HYPE-15M-MDTP` | [hype/15m-multidimensional-trend-pyramiding/](hype/15m-multidimensional-trend-pyramiding/README.md) · [主账](hype/15m-multidimensional-trend-pyramiding/hype-15m-mdtp-core-ledger.md) | `4h` 多维趋势定向、`1h` 阶段识别、`15m` 波动率目标与盈利后加减仓 | V1 explore / not promoted / not live-ready |
| `HYPE-15M-Multi-Timeframe-Probe-Pyramiding` | `HYPE-15M-MTPP` | [hype/15m-multi-timeframe-probe-pyramiding/](hype/15m-multi-timeframe-probe-pyramiding/README.md) · [主账](hype/15m-multi-timeframe-probe-pyramiding/hype-15m-mtpp-core-ledger.md) | 日周假设、`4h/1h/15m` RSI/KDJ 位置、试仓后由真实浮盈确认并回踩滚仓 | explore / diagnostic-only / not promoted / not live-ready |
| `HYPE-15M-Multi-Mechanism-Trend-Following` | `HYPE-15M-MMTF` | [hype/15m-multi-mechanism-trend-following/](hype/15m-multi-mechanism-trend-following/README.md) · [主账](hype/15m-multi-mechanism-trend-following/hype-15m-mmtf-core-ledger.md) | `15m` breakout / momentum / EMA continuation / volatility-expansion 纯趋势广搜 | V1-V3 registered / HARD-GATE-FAILED / not promoted / not live-ready |
| `HYPE-15M-Sequential-Drift-State` | `HYPE-15M-SDS` | [hype/15m-sequential-drift-state/](hype/15m-sequential-drift-state/README.md) · [主账](hype/15m-sequential-drift-state/hype-15m-sds-core-ledger.md) | 逐根闭合 K 更新趋势证据，以顺序漂移、回归或 Kalman/CUSUM/结构确认驱动迟滞状态机 | explore / HARD-GATE-FAILED / not promoted / not live-ready |
| `HYPE-15M-Price-Kinematics-Continuation` | `HYPE-15M-PKC` | [hype/15m-price-kinematics-continuation/](hype/15m-price-kinematics-continuation/README.md) · [主账](hype/15m-price-kinematics-continuation/hype-15m-pkc-core-ledger.md) | 纯价格运动学验证过去 `1h/3h/6h` 状态对未来 `1h/3h/6h/12h` 延续的预测关系 | explore / diagnostic-only / not promoted / not live-ready |
| `HYPE-1H-Price-Kinematics-Continuation` | `HYPE-1H-PKC` | [hype/1h-price-kinematics-continuation/](hype/1h-price-kinematics-continuation/README.md) · [主账](hype/1h-price-kinematics-continuation/hype-1h-pkc-core-ledger.md) | 固定时间锚点验证价格位移、速度、加速度与路径形状对未来 `3d/7d/14d` 趋势延续的预测关系 | explore / diagnostic-only / not promoted / not live-ready |
| `HYPE-1D-Price-Kinematics-Continuation` | `HYPE-1D-PKC` | [hype/1d-price-kinematics-continuation/](hype/1d-price-kinematics-continuation/README.md) · [主账](hype/1d-price-kinematics-continuation/hype-1d-pkc-core-ledger.md) | 完整 UTC 日 K 的纯价格位移、速度、加速度与路径形状预测未来 `3d/7d/14d` 延续 | explore / diagnostic-only / not promoted / not live-ready |
| `HYPE-1H-Price-Kinematic-Trend-Survival-Control` | `HYPE-1H-PKTSC` | [hype/1h-price-kinematic-trend-survival-control/](hype/1h-price-kinematic-trend-survival-control/README.md) · [主账](hype/1h-price-kinematic-trend-survival-control/hype-1h-pktsc-core-ledger.md) | 纯价格 causal walk-forward 延续概率驱动 `3–14d` campaign 的离散加减仓与半 MFE 保护 | explore / diagnostic-only / not promoted / not live-ready |
| `HYPE-15M-SMA-Crossover-Slope` | `HYPE-15M-SMA-XS` | [hype/15m-sma-crossover-slope/](hype/15m-sma-crossover-slope/README.md) · [主账](hype/15m-sma-crossover-slope/hype-15m-sma-xs-core-ledger.md) | `SMA30/SMA120` 交叉入场 + ATR 归一化斜率提前退出 | explore / HARD-GATE-FAILED / not promoted / not live-ready |
| `HYPE-15M-MA7-MA30-Pyramiding` | `HYPE-15M-MA-PT` | [hype/15m-ma7-ma30-pyramiding/](hype/15m-ma7-ma30-pyramiding/README.md) · [主账](hype/15m-ma7-ma30-pyramiding/hype-15m-ma-pt-core-ledger.md) | `15m` EMA7/EMA30 reclaim + 盈利后目标 `3x`，对比反向交叉与 MA7 退出 | explore / HARD-GATE-FAILED / not promoted / not live-ready |
| `HYPE-15M-Multi-Horizon-EMA-Forecast` | `HYPE-15M-MHEF` | [hype/15m-multi-horizon-ema-forecast/](hype/15m-multi-horizon-ema-forecast/README.md) · [主账](hype/15m-multi-horizon-ema-forecast/hype-15m-mhef-core-ledger.md) | `15m` 多速度 forecast、波动率目标与成本感知连续仓位 | V2 validation-failed / explore / not promoted / not live-ready |
| `HYPE-1M-EMA-Crossover` | `HYPE-1M-EMA-X` | [hype/1m-ema-crossover/](hype/1m-ema-crossover/README.md) | `1m` EMA 金叉/死叉，可执行时序 | explore / not promoted / not live-ready |
| `HYPE-1M-MA-Pullback-Scalp` | - | [hype/1m-ma-pullback-scalp/](hype/1m-ma-pullback-scalp/README.md) | `1m` 双 MA 回踩 scalp | explore / not promoted / not live-ready |
| `HYPE-1H-Adaptive-Regime` | `HYPE-1H-AR` | [hype/1h-adaptive-regime/](hype/1h-adaptive-regime/README.md) · [主账](hype/1h-adaptive-regime/hype-1h-ar-core-ledger.md) | `1h` DI 趋势 + 随机指标反转自适应 ensemble | V1-V4 registered / not promoted / not live-ready |
| `HYPE-1H-Multi-Mechanism-Trend-Following` | `HYPE-1H-MMTF` | [hype/1h-multi-mechanism-trend-following/](hype/1h-multi-mechanism-trend-following/README.md) · [主账](hype/1h-multi-mechanism-trend-following/hype-1h-mmtf-core-ledger.md) | `1h` breakout / momentum / EMA / volatility-expansion 纯趋势广搜 | V1-V3 registered / HARD-GATE-FAILED / not promoted / not live-ready |
| `HYPE-1H-Multi-Horizon-EMA-Forecast` | `HYPE-1H-MHEF` | [hype/1h-multi-horizon-ema-forecast/](hype/1h-multi-horizon-ema-forecast/README.md) · [主账](hype/1h-multi-horizon-ema-forecast/hype-1h-mhef-core-ledger.md) | `1h` 四组 EMA 波动率归一化 forecast 加权连续仓位 | explore / not promoted / not live-ready |
| `HYPE-1D-Multi-Horizon-EMA-Forecast` | `HYPE-1D-MHEF` | [hype/1d-multi-horizon-ema-forecast/](hype/1d-multi-horizon-ema-forecast/README.md) · [主账](hype/1d-multi-horizon-ema-forecast/hype-1d-mhef-core-ledger.md) | `1d` 四组经典 EWMAC forecast 加权连续仓位 | explore / not promoted / not live-ready |
| `HYPE-1D-Pyramiding-Trend` | `HYPE-1D-PT` | [hype/1d-pyramiding-trend/](hype/1d-pyramiding-trend/README.md) · [主账](hype/1d-pyramiding-trend/hype-1d-pt-core-ledger.md) | `1d` 趋势突破/动量 campaign + 最多 `3x` 浮盈加仓 | explore / not promoted / not live-ready |
| `HYPE-1D-MA7-Asymmetric-Body-Trend` | `HYPE-1D-MA7-ABT` | [hype/1d-ma7-asymmetric-body-trend/](hype/1d-ma7-asymmetric-body-trend/README.md) · [主账](hype/1d-ma7-asymmetric-body-trend/hype-1d-ma7-abt-core-ledger.md) | 固定 `SMA7` 的reclaim / 迟滞趋势分支，含OAPP、PEHC handoff及延迟episode、连续状态、转换链、RSI6记忆cross、结构性仓位研究 | `V7.1 dry-run / not live-ready`；`V1–V7 registered / TRANSFER_FAIL / HARD-GATE-FAILED / not promoted / not live-ready` |
| `HYPE-1D-MA7-Machine-Learning-Trend` | `HYPE-1D-MA7-MLT` | [hype/1d-ma7-machine-learning-trend/](hype/1d-ma7-machine-learning-trend/README.md) · [主账](hype/1d-ma7-machine-learning-trend/hype-1d-ma7-mlt-core-ledger.md) | P0全日；P1 strict-cross；P2 episode；P3 purged cross/survival；P4 exact V7.1 clone/residual；P5 opportunity/lifecycle；P6 V7.1 anchor/three-head；P7 cross-asset survival-only | explore / HARD-GATE-FAILED / diagnostic-only / not promoted / not live-ready |
| `HYPE-4H-MA7-Asymmetric-Body-Trend` | `HYPE-4H-MA7-ABT` | [hype/4h-ma7-asymmetric-body-trend/](hype/4h-ma7-asymmetric-body-trend/README.md) · [主账](hype/4h-ma7-asymmetric-body-trend/hype-4h-ma7-abt-core-ledger.md) | 固定 `SMA7/ATR7` 的 4H 斜率趋势、reclaim / pullback / breakout 与保护状态机 | explore / HARD-GATE-FAILED / not promoted / not live-ready |
| `HYPE-4H-MA7-Close-Reversal` | `HYPE-4H-MA7-CR` | [hype/4h-ma7-close-reversal/](hype/4h-ma7-close-reversal/README.md) · [主账](hype/4h-ma7-close-reversal/hype-4h-ma7-cr-core-ledger.md) | 闭合 `4h` 在 `SMA7` 上方持多、下方持空，跨线后下一期开盘直接反手 | explore / HARD-GATE-FAILED / not promoted / not live-ready |
| `HYPE-4H-MA7-RSI6-Asymmetric-Reversal` | `HYPE-4H-MA7-RSI6-AR` | [hype/4h-ma7-rsi6-asymmetric-reversal/](hype/4h-ma7-rsi6-asymmetric-reversal/README.md) · [主账](hype/4h-ma7-rsi6-asymmetric-reversal/hype-4h-ma7-rsi6-ar-core-ledger.md) | SMA7 做多、三根 RSI6 超买记忆过滤反手空、RSI6 超卖平空 | explore / HARD-GATE-FAILED / not promoted / not live-ready |
| `HYPE-1D-15M-Hierarchical-Trend-Opportunity` | `HYPE-D15-HTO` | [hype/1d-15m-hierarchical-trend-opportunity/](hype/1d-15m-hierarchical-trend-opportunity/README.md) · [主账](hype/1d-15m-hierarchical-trend-opportunity/hype-d15-hto-core-ledger.md) | 前一完整日四因子共识定方向，`15m` Donchian/微趋势择时 | V1-V3 registered / not promoted / not live-ready |
| `HYPE-15M-Multi-Indicator-Intraday` | `HYPE-15M-MII` | [hype/15m-multi-indicator-intraday/](hype/15m-multi-indicator-intraday/README.md) · [主账](hype/15m-multi-indicator-intraday/hype-15m-mii-core-ledger.md) | `15m` 多指标日内广搜 | V1.4A dry-run / not live-ready |
| `HYPE-15M-Riptide` | - | [hype/15m-riptide/](hype/15m-riptide/README.md) | `15m` EMA 趋势背景 RSI 回踩 + RV regime | explore / MISSING_EVIDENCE / not promoted / not live-ready |
| `HYPE-15M-Keltner-Trend-Breakout` | `HYPE-15M-KTB` | [hype/15m-keltner-trend-breakout/](hype/15m-keltner-trend-breakout/README.md) · [主账](hype/15m-keltner-trend-breakout/hype-15m-keltner-trend-breakout-core-ledger.md) | `15m` Keltner 外轨突破、压缩扩张与中轨回踩 | explore / HARD-GATE-FAILED / not promoted / not live-ready |
| `HYPE-15M-Bollinger-Keltner-Squeeze-Breakout` | `HYPE-15M-BKSB` | [hype/15m-bollinger-keltner-squeeze-breakout/](hype/15m-bollinger-keltner-squeeze-breakout/README.md) · [主账](hype/15m-bollinger-keltner-squeeze-breakout/hype-15m-bksb-core-ledger.md) | `BB(20,2)` 进入 `KC(20,1.5)` 后释放并突破压缩区间 | explore / HARD-GATE-FAILED / not promoted / not live-ready |
| `HYPE-1H-Bollinger-Keltner-Squeeze-Breakout` | `HYPE-1H-BKSB` | [hype/1h-bollinger-keltner-squeeze-breakout/](hype/1h-bollinger-keltner-squeeze-breakout/README.md) · [主账](hype/1h-bollinger-keltner-squeeze-breakout/hype-1h-bksb-core-ledger.md) | `BB(20,2)` 进入 `KC(20,1.5)` 后释放并突破压缩区间 | explore / HARD-GATE-FAILED / not promoted / not live-ready |
| `HYPE-4H-Bollinger-Keltner-Squeeze-Breakout` | `HYPE-4H-BKSB` | [hype/4h-bollinger-keltner-squeeze-breakout/](hype/4h-bollinger-keltner-squeeze-breakout/README.md) · [主账](hype/4h-bollinger-keltner-squeeze-breakout/hype-4h-bksb-core-ledger.md) | `BB(20,2)` 进入 `KC(20,1.5)` 后释放并突破压缩区间 | explore / HARD-GATE-FAILED / not promoted / not live-ready |
| `HYPE-1D-Bollinger-Keltner-Squeeze-Breakout` | `HYPE-1D-BKSB` | [hype/1d-bollinger-keltner-squeeze-breakout/](hype/1d-bollinger-keltner-squeeze-breakout/README.md) · [主账](hype/1d-bollinger-keltner-squeeze-breakout/hype-1d-bksb-core-ledger.md) | `BB(20,2)` 进入 `KC(20,1.5)` 后释放并突破压缩区间 | explore / HARD-GATE-FAILED / not promoted / not live-ready |
| `HYPE-30M-Keltner-Trend-Breakout` | `K2-FQ-V2-ATRVT-OFF` | [hype/30m-keltner-trend-breakout/](hype/30m-keltner-trend-breakout/README.md) · [主账](hype/30m-keltner-trend-breakout/hype-30m-keltner-trend-breakout-core-ledger.md) | `30m` Keltner 突破 + `1h` EMA regime + ATRVT 动态杠杆 | V3 registered / not promoted / not live-ready |
| `HYPE-30M-Keltner-Breakout-Retest` | - | [hype/30m-keltner-breakout-retest/](hype/30m-keltner-breakout-retest/README.md) · [主账](hype/30m-keltner-breakout-retest/hype-30m-keltner-breakout-retest-core-ledger.md) | `30m` Keltner 突破后等待回踩并 reclaim 的趋势状态机 | explore / not promoted / not live-ready |
| `HYPE-15M-Pullback-Trail` | - | [hype/15m-pullback-trail/](hype/15m-pullback-trail/README.md) | `15m` 回踩事件源 + bracket 搜索 | explore / not promoted / not live-ready |
| `HYPE-5M-Pullback-Trail` | `HYPE-5M-PBTR` | [hype/5m-pullback-trail/](hype/5m-pullback-trail/README.md) · [主账](hype/5m-pullback-trail/hype-5m-pullback-trail-core-ledger.md) | `5m` 回踩/恢复入场 + 固定 ATR bracket | V6.2.1 live / tiny-live-pilot |
| `HYPE-5M-MA-Pullback-Scalp` | - | [hype/5m-ma-pullback-scalp/](hype/5m-ma-pullback-scalp/README.md) | `5m` 双 MA 回踩 scalp | explore / not promoted / not live-ready |
| `HYPE-5M-Micro-Scalp` | `HYPE-5M-MS` | [hype/5m-micro-scalp/](hype/5m-micro-scalp/README.md) · [主账](hype/5m-micro-scalp/hype-5m-micro-scalp-core-ledger.md) | `5m` 高频小利 scalp 搜索 | V1-V1.3 registered / not promoted / not live-ready |
| `HYPE-5M-Event-Quality-Scoring` | `HYPE-5M-EQS` | [hype/5m-event-quality-scoring/](hype/5m-event-quality-scoring/README.md) · [主账](hype/5m-event-quality-scoring/hype-5m-event-quality-scoring-core-ledger.md) | `5m` 事件质量打分 | V1 registered / HARD-GATE-FAILED / not promoted |
| `HYPE-15M-Trend-Breakout-Multi-Indicator-Ensemble` | `HYPE-15M-TB-MII-ENS` | [hype/15m-trend-breakout-multi-indicator-ensemble/](hype/15m-trend-breakout-multi-indicator-ensemble/README.md) · [主账](hype/15m-trend-breakout-multi-indicator-ensemble/hype-15m-tb-mii-ens-core-ledger.md) | `EMA-TB-V39` + `MII-V1.4` 单账户组合（V39 优先 + 强平让位） | V2 dry-run / PASS / not live-ready |
| `HYPE-6H-RS4-Regime-Switch` | - | [hype/6h-rs4-regime-switch/](hype/6h-rs4-regime-switch/README.md) · [主账](hype/6h-rs4-regime-switch/hype-6h-rs4-regime-switch-core-ledger.md) | `6h` regime-switch 趋势（压缩动量腿 + 扩张突破腿）复现 | V1 registered / not promoted / not live-ready |
| `HYPE-15M-Factor-ML` | `HYPE-15M-FML` | [hype/15m-factor-ml/](hype/15m-factor-ml/README.md) · [主账](hype/15m-factor-ml/hype-15m-factor-ml-core-ledger.md) | `15m` 可扩展因子库（Round 2 为 157 因子）+ LightGBM 集成交易研究 | explore / HARD-GATE-FAILED / not promoted / not live-ready |

## 单资产研究（非 HYPE）

| Family | Alias | Directory | 状态 |
| --- | --- | --- | --- |
| `BTC-1H-Adaptive-Regime` | `BTC-1H-AR` | [btc/1h-adaptive-regime/](btc/1h-adaptive-regime/README.md) · [主账](btc/1h-adaptive-regime/btc-1h-ar-core-ledger.md) | V1-V4 registered / clean-equivalent / not promoted / not live-ready |
| `BTC-15M-EMA-Trend-Breakout` | `BTC-15M-EMA-TB` | [btc/15m-ema-trend-breakout/](btc/15m-ema-trend-breakout/README.md) · [主账](btc/15m-ema-trend-breakout/btc-15m-ema-tb-core-ledger.md)；`15m` 快慢 EMA 趋势背景 + 价格突破 | explore / HARD-GATE-FAILED / not promoted / not live-ready |
| `BTC-15M-Keltner-Trend-Breakout` | `BTC-15M-KTB` | [btc/15m-keltner-trend-breakout/](btc/15m-keltner-trend-breakout/README.md) · [主账](btc/15m-keltner-trend-breakout/btc-15m-keltner-trend-breakout-core-ledger.md)；`15m` Keltner 收盘突破 + 可选 `1h` EMA trend regime | explore / HARD-GATE-FAILED / not promoted / not live-ready |
| `BTC-15M-Trend-Continuation` | `BTC-15M-TC` | [btc/15m-trend-continuation/](btc/15m-trend-continuation/README.md) · [主账](btc/15m-trend-continuation/btc-15m-trend-continuation-core-ledger.md)；低波动压缩 + EMA 趋势 + Donchian 突破延续 | explore / observation / not promoted / not live-ready |
| `BTC-30M-Trend-Continuation` | `BTC-30M-TC` | [btc/30m-trend-continuation/](btc/30m-trend-continuation/README.md) · [主账](btc/30m-trend-continuation/btc-30m-trend-continuation-core-ledger.md)；`30m` EMA 趋势 + 压缩/Donchian/Keltner 突破 | explore / HARD-GATE-FAILED / not promoted / not live-ready |
| `BTC-1D-Qingze-Critical-Point-Trend` | `BTC-1D-QZ-CPT` | [btc/1d-qingze-critical-point-trend/](btc/1d-qingze-critical-point-trend/README.md) · [主账](btc/1d-qingze-critical-point-trend/btc-1d-qz-cpt-core-ledger.md)；SMA 定向 + 放量临界点突破 + 浮盈正金字塔 | explore / diagnostic-only / not promoted / not live-ready |
| `BTC-1D-Classic-CTA-Trend` | `BTC-1D-CCTA` | [btc/1d-classic-cta-trend/](btc/1d-classic-cta-trend/README.md) · [主账](btc/1d-classic-cta-trend/btc-1d-ccta-core-ledger.md)；文献 EWMAC 四速 + 20% 波动率缩放 | explore / not promoted / not live-ready |
| `GOLD-1D-Multi-Speed-TSMOM` | `GOLD-1D-MS-TSMOM` | [gold/1d-multi-speed-tsmom/](gold/1d-multi-speed-tsmom/README.md) · [主账](gold/1d-multi-speed-tsmom/gold-1d-ms-tsmom-core-ledger.md)；月末 `sign(1M/3M/12M)` 等权 + 10% 单资产波动率缩放 | raw-unaccepted / explore / not promoted / not live-ready |
| `BTC-1D-MA7-RSI6-LightGBM-Trend` | `BTC-1D-MA7-RSI6-LGBM` | [btc/1d-ma7-rsi6-lightgbm-trend/](btc/1d-ma7-rsi6-lightgbm-trend/README.md) · [主账](btc/1d-ma7-rsi6-lightgbm-trend/btc-1d-ma7-rsi6-lgbm-core-ledger.md)；严格 SMA7 收盘跨越、MA7/K 线几何与 Wilder RSI6 阶段状态输入 LightGBM | explore / diagnostic-only / not promoted / not live-ready |
| `BTC-1W-MA7-Asymmetric-Body-Trend` | `BTC-1W-MA7-ABT` | [btc/1w-ma7-asymmetric-body-trend/](btc/1w-ma7-asymmetric-body-trend/README.md) · [主账](btc/1w-ma7-asymmetric-body-trend/btc-1w-ma7-abt-core-ledger.md)；HYPE 日线 V1 固定 SMA7/ATR7 状态机迁移至周 K | explore / TRANSFER_FAIL / not promoted / not live-ready |
| `ETH-1H-Adaptive-Regime` | `ETH-1H-AR` | [eth/1h-adaptive-regime/](eth/1h-adaptive-regime/README.md) · [主账](eth/1h-adaptive-regime/eth-1h-ar-core-ledger.md) | V1-V4 registered / not promoted / not live-ready |
| `US-Indexes-1D-MA7-Shared-Parameter-Transfer` | `USI-1D-MA7-SP-XFER` | [us-indexes/1d-ma7-shared-parameter-transfer/](us-indexes/1d-ma7-shared-parameter-transfer/README.md) · [主账](us-indexes/1d-ma7-shared-parameter-transfer/us-indexes-1d-ma7-sp-xfer-core-ledger.md) | explore / TRANSFER_FAIL / not promoted / not live-ready |
| `Nasdaq100-1D-MA7-Regime-Continuation` | `NDX100-1D-MA7-RC` | [us-indexes/1d-nasdaq100-ma7-regime-continuation/](us-indexes/1d-nasdaq100-ma7-regime-continuation/README.md) · [主账](us-indexes/1d-nasdaq100-ma7-regime-continuation/ndx100-1d-ma7-rc-core-ledger.md) | explore / diagnostic-only / not promoted / not live-ready |
| `CSI300-1D-HYPE-MA7-V7.1-Transfer` | `CSI300-1D-HM7-XFER` | [cn-indexes/1d-hype-ma7-v7-1-transfer/](cn-indexes/1d-hype-ma7-v7-1-transfer/README.md) · [主账](cn-indexes/1d-hype-ma7-v7-1-transfer/csi300-1d-hm7-xfer-core-ledger.md)；HYPE MA7 V7.1 固定参数迁移至沪深 300 日 K | TRANSFER_FAIL / explore / not promoted / not live-ready |
| `SOX-1D-MA7-Asset-Specific-Search` | `SOX-1D-MA7-AS-SEARCH` | [sox/1d-ma7-asset-specific-search/](sox/1d-ma7-asset-specific-search/README.md) · [主账](sox/1d-ma7-asset-specific-search/sox-1d-ma7-as-search-core-ledger.md) | explore / not promoted / not live-ready |
| `SOX-1D-MA7-Separated-Trend-Transfer` | `SOX-1D-MA7-ST-XFER` | [sox/1d-ma7-separated-trend-transfer/](sox/1d-ma7-separated-trend-transfer/README.md) · [主账](sox/1d-ma7-separated-trend-transfer/sox-1d-ma7-st-xfer-core-ledger.md) | explore / TRANSFER_FAIL / not promoted / not live-ready |
| `SOL-1H-Adaptive-Regime` | `SOL-1H-AR` | [sol/1h-adaptive-regime/](sol/1h-adaptive-regime/README.md) · [主账](sol/1h-adaptive-regime/sol-1h-ar-core-ledger.md) | V1-V3 registered / not promoted / not live-ready |
| `SOL-1H-Volatility-Compression-Breakout` | `SOL-1H-VCB` | [sol/1h-volatility-compression-breakout/](sol/1h-volatility-compression-breakout/README.md) · [主账](sol/1h-volatility-compression-breakout/sol-1h-vcb-core-ledger.md) | explore / HARD-GATE-FAILED / not promoted / not live-ready |
| `SOL-4H-RS4-Regime-Switch` | `SOL-4H-RS4` | [sol/4h-rs4-regime-switch/](sol/4h-rs4-regime-switch/README.md) · [主账](sol/4h-rs4-regime-switch/sol-4h-rs4-core-ledger.md) | explore / HARD-GATE-FAILED / not promoted / not live-ready |
| `SOL-1H-Pullback-Bracket` | `SOL-1H-PB` | [sol/1h-pullback-bracket/](sol/1h-pullback-bracket/README.md) · [主账](sol/1h-pullback-bracket/sol-1h-pb-core-ledger.md) | explore / HARD-GATE-FAILED / not promoted / not live-ready |
| `TRX-1H-Adaptive-Regime` | `TRX-1H-AR` | [trx/1h-adaptive-regime/](trx/1h-adaptive-regime/README.md) · [主账](trx/1h-adaptive-regime/trx-1h-ar-core-ledger.md) | V1-V3 registered / not promoted / not live-ready |
| `BNB-1H-Adaptive-Regime` | `BNB-1H-AR` | [bnb/1h-adaptive-regime/](bnb/1h-adaptive-regime/README.md) · [主账](bnb/1h-adaptive-regime/bnb-1h-ar-core-ledger.md) | V1-V3 registered / not promoted / not live-ready |
| `BNB-15M-Adaptive-Regime` | `BNB-15M-AR` | [bnb/15m-adaptive-regime/](bnb/15m-adaptive-regime/README.md) · [主账](bnb/15m-adaptive-regime/bnb-15m-ar-core-ledger.md) | explore / not promoted |
| `MU-15M-Donchian-Trend-Breakout` | `MU-15M-DTB` | [mu/15m-donchian-trend-breakout/](mu/15m-donchian-trend-breakout/README.md) · [主账](mu/15m-donchian-trend-breakout/mu-15m-dtb-core-ledger.md)；`15m` EMA regime + Donchian 收盘突破 + ATR/trailing exit | explore / HARD-GATE-FAILED / not promoted / not live-ready |
| `MU-1D-MA7-Separated-Trend-Transfer` | `MU-1D-MA7-ST-XFER` | [mu/1d-ma7-separated-trend-transfer/](mu/1d-ma7-separated-trend-transfer/README.md) · [主账](mu/1d-ma7-separated-trend-transfer/mu-1d-ma7-st-xfer-core-ledger.md)；HYPE 日线 V1 固定 SMA7 状态机迁移至 Binance perpetual / Nasdaq equity | explore / TRANSFER_FAIL / raw-unaccepted / not promoted / not live-ready |

各资产入口：[btc/README.md](btc/README.md)、[eth/README.md](eth/README.md)、[gold/README.md](gold/README.md)、[us-indexes/README.md](us-indexes/README.md)、[cn-indexes/README.md](cn-indexes/README.md)、[sox/README.md](sox/README.md)、[sol/README.md](sol/README.md)、[trx/README.md](trx/README.md)、[bnb/README.md](bnb/README.md)、[mu/README.md](mu/README.md)。

## 组合与跨资产研究

入口：[asset-portfolios/README.md](asset-portfolios/README.md)。跨资产研究不是 HYPE 策略家族，除非文档明确把它提升为某个 HYPE family variant。

10,000 美元账户三方向首轮研究与独立验收见[横向比较](platform/small-account-three-line-validation/README.md)；各线仍以自身主账和产物为准。

| Family / Topic | Directory | 状态 |
| --- | --- | --- |
| `Binance-1D-MA7-Cross-ATR-Generalization`（`BIN-1D-MA7-CAR-GEN`） | [asset-portfolios/1d-ma7-cross-atr-generalization/](asset-portfolios/1d-ma7-cross-atr-generalization/README.md) · [主账](asset-portfolios/1d-ma7-cross-atr-generalization/bin-1d-ma7-car-gen-core-ledger.md)；高低价未刷新收紧的全市场适配与穿越后斜率达标入场 | 每边手续费0.1%/滑点0.04%；原V3机会账116,933穿越、676币975段，新增两臂1,950账户；完整242币原V3/候选/空单保护盈利62/36/59，收益中位−29.26%/−56.60%/−33.04%；两改动不升级，完整牛熊及资金费未验证，正式V1/V2/V3不变 |
| `Binance-1D-Medium-Term-Trend-Capture`（`BIN-1D-MTTC`） | [asset-portfolios/1d-medium-term-trend-capture/](asset-portfolios/1d-medium-term-trend-capture/README.md) · [主账](asset-portfolios/1d-medium-term-trend-capture/binance-1d-mttc-core-ledger.md)；共同趋势机会的入场、持有与资金账户比较 | explore / diagnostic-only / not promoted / not live-ready |
| `Binance-1D-Medium-Term-Continuation-State`（`BIN-1D-MTCS`） | [asset-portfolios/1d-medium-term-continuation-state/](asset-portfolios/1d-medium-term-continuation-state/README.md) · [主账](asset-portfolios/1d-medium-term-continuation-state/binance-1d-mtcs-core-ledger.md)；事前方向与状态识别中期延续 | explore / diagnostic-only / not promoted / not live-ready |
| `Binance-1D-Trend-Strength-Pullback-Restart`（`BIN-1D-TSPR`） | [asset-portfolios/1d-trend-strength-pullback-restart/](asset-portfolios/1d-trend-strength-pullback-restart/README.md) · [主账](asset-portfolios/1d-trend-strength-pullback-restart/binance-1d-tspr-core-ledger.md)；事前趋势强度与顺序回撤重启的增量识别 | explore / diagnostic-only / not promoted / not live-ready |
| `Multi-Asset-1D-Small-Account-Slow-Trend`（`XA-1D-SAST`） | [asset-portfolios/1d-small-account-slow-trend/](asset-portfolios/1d-small-account-slow-trend/README.md) · [主账](asset-portfolios/1d-small-account-slow-trend/xa-1d-sast-core-ledger.md)；7ETF 月频多头/现金，首轮趋势增量 NO-GO | explore / diagnostic-only / not promoted / not live-ready |
| `Binance-1D-TPSA-Long-Account`（`BIN-1D-TPSA-LA`） | [asset-portfolios/1d-tpsa-long-account/](asset-portfolios/1d-tpsa-long-account/README.md) · [主账](asset-portfolios/1d-tpsa-long-account/binance-1d-tpsa-la-core-ledger.md)；TPSA 多头事件账户化 | registered / diagnostic-only / HARD-GATE-FAILED / not promoted / not live-ready |
| `BTCETH-8H-Small-Account-Cash-And-Carry`（`BTCETH-8H-SACC`） | [asset-portfolios/8h-btceth-small-account-carry/](asset-portfolios/8h-btceth-small-account-carry/README.md) · [主账](asset-portfolios/8h-btceth-small-account-carry/btceth-8h-sacc-core-ledger.md)；现货与到期/永续 carry，未证实可执行净利润 | explore / diagnostic-only / not promoted / not live-ready |
| `MA7-Bidirectional-Trend-Generalization`（`MA7-BTG`） | [asset-portfolios/1d-ma7-bidirectional-trend-generalization/](asset-portfolios/1d-ma7-bidirectional-trend-generalization/README.md) · [主账](asset-portfolios/1d-ma7-bidirectional-trend-generalization/ma7-btg-core-ledger.md)；SMA7 多空生命周期与跨市场适用性 | explore / not promoted / not live-ready |
| `MA7-ATR14-Long-Fixed-Parameter-Transfer` | [asset-portfolios/1d-ma7-atr14-long-transfer/](asset-portfolios/1d-ma7-atr14-long-transfer/README.md) | explore / diagnostic-only / not promoted / not live-ready |
| `Binance-MTF-Dual-State-Trend-Campaign`（`BIN-MTF-DSTC`） | [asset-portfolios/multi-timeframe-dual-state-trend-campaign/](asset-portfolios/multi-timeframe-dual-state-trend-campaign/README.md) · [主账](asset-portfolios/multi-timeframe-dual-state-trend-campaign/binance-mtf-dstc-core-ledger.md) · [最终报告](asset-portfolios/multi-timeframe-dual-state-trend-campaign/final/binance-mtf-dstc-goal-final-2026-08-04.md) | goal-complete / HARD-GATE-FAILED / explore / not promoted / not live-ready |
| `Binance-MTF-Pullback-Trend-Campaign`（`BIN-MTF-PTC`） | [asset-portfolios/multi-timeframe-pullback-trend-campaign/](asset-portfolios/multi-timeframe-pullback-trend-campaign/README.md) · [主账](asset-portfolios/multi-timeframe-pullback-trend-campaign/binance-mtf-ptc-core-ledger.md) | goal-complete / HARD-GATE-FAILED / explore / not promoted / not live-ready |
| `Binance-1D-Medium-Term-Trend-Capture`（`BIN-1D-MTTC`） | [asset-portfolios/1d-medium-term-trend-capture/](asset-portfolios/1d-medium-term-trend-capture/README.md) · [主账](asset-portfolios/1d-medium-term-trend-capture/binance-1d-mttc-core-ledger.md)；共同趋势机会的入场、持有与资金账户比较 | explore / diagnostic-only / not promoted / not live-ready |
| `Binance-1D-Medium-Term-Continuation-State`（`BIN-1D-MTCS`） | [asset-portfolios/1d-medium-term-continuation-state/](asset-portfolios/1d-medium-term-continuation-state/README.md) · [主账](asset-portfolios/1d-medium-term-continuation-state/binance-1d-mtcs-core-ledger.md)；事前方向与状态识别中期延续 | explore / diagnostic-only / not promoted / not live-ready |
| `Binance-1D-Trend-Strength-Pullback-Restart`（`BIN-1D-TSPR`） | [asset-portfolios/1d-trend-strength-pullback-restart/](asset-portfolios/1d-trend-strength-pullback-restart/README.md) · [主账](asset-portfolios/1d-trend-strength-pullback-restart/binance-1d-tspr-core-ledger.md)；事前趋势强度与顺序回撤重启的增量识别 | explore / diagnostic-only / not promoted / not live-ready |
| `MA7-Bidirectional-Trend-Generalization`（`MA7-BTG`） | [asset-portfolios/1d-ma7-bidirectional-trend-generalization/](asset-portfolios/1d-ma7-bidirectional-trend-generalization/README.md) · [主账](asset-portfolios/1d-ma7-bidirectional-trend-generalization/ma7-btg-core-ledger.md)；SMA7 多空生命周期与跨市场适用性 | explore / not promoted / not live-ready |
| `Binance-1D-MA7-Deviation-Continuation`（`BIN-1D-MA7DC`） | [asset-portfolios/1d-ma7-deviation-continuation/](asset-portfolios/1d-ma7-deviation-continuation/README.md) · [主账](asset-portfolios/1d-ma7-deviation-continuation/binance-1d-ma7dc-core-ledger.md) | explore / not promoted / not live-ready |
| `Binance-1H-Price-Impulse-Campaign`（`BIN-1H-PIC`） | [asset-portfolios/1h-price-impulse-campaign/](asset-portfolios/1h-price-impulse-campaign/README.md) · [主账](asset-portfolios/1h-price-impulse-campaign/binance-1h-pic-core-ledger.md) | explore / candidate / not promoted / not live-ready |
| `Binance-1H-Four-Asset-Trend-Habitat-Audit`（`BIN-1H-FATHA`） | [asset-portfolios/1h-four-asset-trend-habitat-audit/](asset-portfolios/1h-four-asset-trend-habitat-audit/README.md) · [主账](asset-portfolios/1h-four-asset-trend-habitat-audit/binance-1h-fatha-core-ledger.md) | explore / diagnostic-only / not promoted / not live-ready |
| `Binance-1H-Cross-Sectional-LightGBM-Selector`（`BIN-1H-CSLGBM`） | [asset-portfolios/1h-cross-sectional-lightgbm-selector/](asset-portfolios/1h-cross-sectional-lightgbm-selector/README.md) · [主账](asset-portfolios/1h-cross-sectional-lightgbm-selector/binance-1h-cslgbm-core-ledger.md) | archived / formula-invalidated / HARD-GATE-FAILED |
| `Binance-1H-Multi-Horizon-Cross-Sectional-ML-Allocator`（`BIN-1H-MHCSML`） | [asset-portfolios/1h-multi-horizon-cross-sectional-ml-allocator/](asset-portfolios/1h-multi-horizon-cross-sectional-ml-allocator/README.md) · [主账](asset-portfolios/1h-multi-horizon-cross-sectional-ml-allocator/binance-1h-mhcsml-core-ledger.md) | archived |
| `Binance-15M-EMA-Cross-LightGBM-Event-Selector`（`BIN-15M-EMAX-LGBM`） | [asset-portfolios/15m-ema-cross-lightgbm-event-selector/](asset-portfolios/15m-ema-cross-lightgbm-event-selector/README.md)（README 兼任主账） | archived / HARD-GATE-FAILED |
| `Binance-1H-EMA-Cross-LightGBM-Event-Selector`（`BIN-1H-EMAX-LGBM`） | [asset-portfolios/1h-ema-cross-lightgbm-event-selector/](asset-portfolios/1h-ema-cross-lightgbm-event-selector/README.md)（README 兼任临时主账） | archived |
| `Binance-4H-EMA-Cross-LightGBM-Event-Selector`（`BIN-4H-EMAX-LGBM`） | [asset-portfolios/4h-ema-cross-lightgbm-event-selector/](asset-portfolios/4h-ema-cross-lightgbm-event-selector/README.md)（README 兼任临时主账） | explore / HARD-GATE-FAILED / not promoted / not live-ready |
| `Binance-1D-Bull-Top10-30D-Rotation`（`BIN-1D-BT10R30`） | [asset-portfolios/1d-bull-top10-30d-rotation/](asset-portfolios/1d-bull-top10-30d-rotation/README.md) · [主账](asset-portfolios/1d-bull-top10-30d-rotation/binance-1d-bt10r30-core-ledger.md)；牛市等权Top10，固定30日换仓 | explore / diagnostic-only / not promoted / not live-ready |
| `Binance-4H-Bull-Strong-RSI-ATR-Pullback`（`BIN-4H-BSRAP`） | [asset-portfolios/4h-bull-strong-rsi-atr-pullback/](asset-portfolios/4h-bull-strong-rsi-atr-pullback/README.md) · [主账](asset-portfolios/4h-bull-strong-rsi-atr-pullback/binance-4h-bsrap-core-ledger.md)；牛市强势币RSI超卖/ATR下降，MA7−2ATR止损 | explore / diagnostic-only / HARD-GATE-FAILED / not promoted / not live-ready |
| `Binance-4H-MA7-Regime-Continuation`（`BIN-4H-MA7-RC`） | [asset-portfolios/4h-ma7-regime-continuation/](asset-portfolios/4h-ma7-regime-continuation/README.md) · [主账](asset-portfolios/4h-ma7-regime-continuation/binance-4h-ma7-rc-core-ledger.md) | explore / diagnostic-only / DATA_SCOPE_INCOMPLETE / not promoted / not live-ready |
| `Binance-1D-EMA-Cross-LightGBM-Event-Selector`（`BIN-1D-EMAX-LGBM`） | [asset-portfolios/1d-ema-cross-lightgbm-event-selector/](asset-portfolios/1d-ema-cross-lightgbm-event-selector/README.md)（README 兼任临时主账） | archived |
| `Binance-1D-Multi-Asset-TSMOM-Vol-Target`（`BIN-1D-TSMOM-VT`） | [asset-portfolios/1d-multi-asset-tsmom-vol-target/](asset-portfolios/1d-multi-asset-tsmom-vol-target/README.md)（README 兼任临时主账） | explore / not promoted / not live-ready |
| `Binance-1D-Monthly-Cross-Sectional-Momentum-LS3`（`BIN-1D-MCSM-LS3`） | [asset-portfolios/1d-monthly-cs-momentum-ls3/](asset-portfolios/1d-monthly-cs-momentum-ls3/README.md) · [主账](asset-portfolios/1d-monthly-cs-momentum-ls3/binance-1d-mcsm-ls3-core-ledger.md) | explore / not promoted / not live-ready |
| `Binance-1D-Monthly-Cross-Sectional-Momentum-Long10`（`BIN-1D-MCSM-L10`） | [asset-portfolios/1d-monthly-cs-momentum-long10/](asset-portfolios/1d-monthly-cs-momentum-long10/README.md) · [主账](asset-portfolios/1d-monthly-cs-momentum-long10/binance-1d-mcsm-l10-core-ledger.md) | explore / diagnostic-only / not promoted / not live-ready |
| `Multi-Asset-1D-EWMAC-Universal-Trend`（`XA-1D-EWMAC-UT`） | [asset-portfolios/1d-ewmac-universal-trend/](asset-portfolios/1d-ewmac-universal-trend/README.md)（README 兼任临时主账） | explore / research-line-closed / HARD-GATE-FAILED / not promoted / not live-ready |
| `Multi-Asset-1D-Classic-EWMAC-Replication`（`XA-1D-CLASSIC-EWMAC`） | [asset-portfolios/1d-classic-ewmac-replication/](asset-portfolios/1d-classic-ewmac-replication/README.md)（README 兼任临时主账） | explore / diagnostic-only / not promoted / not live-ready |
| `TradFi-1D-Multi-Asset-Futures-TSMOM`（`TF-1D-FUT-TSMOM`） | [asset-portfolios/1d-tradfi-futures-tsmom/](asset-portfolios/1d-tradfi-futures-tsmom/README.md) · [主账](asset-portfolios/1d-tradfi-futures-tsmom/tf-1d-fut-tsmom-core-ledger.md) | explore / diagnostic-only / not promoted / not live-ready |
| `Binance-15M-Multi-Asset-Trend-State-Machine`（`BIN-15M-TSM`） | [asset-portfolios/15m-multi-asset-trend-state-machine/](asset-portfolios/15m-multi-asset-trend-state-machine/README.md)（README 兼任临时主账） | archived / HARD-GATE-FAILED |
| `Binance-1D-Turtle-Breakout` | [asset-portfolios/1d-turtle-breakout/](asset-portfolios/1d-turtle-breakout/README.md) | explore |
| `Binance-1D-MA7-MA30-Pyramiding-Transfer`（`BIN-1D-MA-PT-XFER`） | [asset-portfolios/1d-ma7-ma30-pyramiding-transfer/](asset-portfolios/1d-ma7-ma30-pyramiding-transfer/README.md) · [主账](asset-portfolios/1d-ma7-ma30-pyramiding-transfer/binance-1d-ma-pt-xfer-core-ledger.md) | explore / TRANSFER_FAIL / not promoted / not live-ready |
| `Binance-1D-MA7-Separated-Trend-Transfer`（`BIN-1D-MA7-ST-XFER`） | [asset-portfolios/1d-ma7-separated-trend-transfer/](asset-portfolios/1d-ma7-separated-trend-transfer/README.md) · [主账](asset-portfolios/1d-ma7-separated-trend-transfer/binance-1d-ma7-st-xfer-core-ledger.md) | explore / TRANSFER_FAIL / HARD-GATE-FAILED / not promoted / not live-ready |
| `Binance-1D-Generic-MA7-Trend`（`BIN-1D-GMA7T`） | [asset-portfolios/1d-generic-ma7-trend/](asset-portfolios/1d-generic-ma7-trend/README.md) · [主账](asset-portfolios/1d-generic-ma7-trend/binance-1d-gma7t-core-ledger.md) · [报告](asset-portfolios/1d-generic-ma7-trend/diagnostics/binance-1d-generic-ma7-trend-v0-top30-market-cap-backtest-2026-08-18.md) | explore / not promoted / not live-ready |
| `Binance-1D-MA7-Regime-Continuation`（`BIN-1D-MA7-RC`） | [asset-portfolios/1d-ma7-regime-continuation/](asset-portfolios/1d-ma7-regime-continuation/README.md) · [主账](asset-portfolios/1d-ma7-regime-continuation/binance-1d-ma7-rc-core-ledger.md) · [P3 报告](asset-portfolios/1d-ma7-regime-continuation/diagnostics/binance-1d-ma7-regime-continuation-p3-confirmatory-2026-08-25.md) | explore / HARD-GATE-FAILED / not promoted / not live-ready |
| `Binance-1D-Trend-Prebreakout-State-Atlas`（`BIN-1D-TPSA`） | [asset-portfolios/1d-trend-prebreakout-state-atlas/](asset-portfolios/1d-trend-prebreakout-state-atlas/README.md) · [主账](asset-portfolios/1d-trend-prebreakout-state-atlas/binance-1d-tpsa-core-ledger.md) · [P1 报告](asset-portfolios/1d-trend-prebreakout-state-atlas/diagnostics/binance-1d-trend-prebreakout-state-atlas-p1-barrier-ml-2026-08-25.md) | explore / diagnostic-only / not promoted / not live-ready |
| `Binance-1D-Cross-Asset-Trend-Lifecycle`（`BIN-1D-CATL`） | [asset-portfolios/1d-cross-asset-trend-lifecycle/](asset-portfolios/1d-cross-asset-trend-lifecycle/README.md) · [主账](asset-portfolios/1d-cross-asset-trend-lifecycle/binance-1d-catl-core-ledger.md) · [P0 报告](asset-portfolios/1d-cross-asset-trend-lifecycle/diagnostics/binance-1d-catl-p0-label-distribution-2026-08-31.md) | explore / diagnostic-only / not promoted / not live-ready |
| `Binance-1D-MA7-Cross-Trend-Probability`（`BIN-1D-MA7-CTP`） | [asset-portfolios/1d-ma7-cross-trend-probability/](asset-portfolios/1d-ma7-cross-trend-probability/README.md) · [主账](asset-portfolios/1d-ma7-cross-trend-probability/binance-1d-ma7-ctp-core-ledger.md) · [P7 报告](asset-portfolios/1d-ma7-cross-trend-probability/diagnostics/binance-1d-ma7-ctp-p7-temporal-drift-calibration-decomposition-2026-09-04.md) | explore / diagnostic-only / not promoted / not live-ready |
| `Binance-1D-MA7-Cross-Expansion-Regime`（`BIN-1D-MA7-CER`） | [asset-portfolios/1d-ma7-cross-expansion-regime/](asset-portfolios/1d-ma7-cross-expansion-regime/README.md) · [主账](asset-portfolios/1d-ma7-cross-expansion-regime/binance-1d-ma7-cer-core-ledger.md) · [P0 报告](asset-portfolios/1d-ma7-cross-expansion-regime/diagnostics/binance-1d-ma7-cer-p0-direction-agnostic-expansion-audit-2026-09-04.md) | explore / diagnostic-only / not promoted / not live-ready |
| `Binance-1D-MA7-Asset-Specific-Search`（`BIN-1D-MA7-AS-SEARCH`） | [asset-portfolios/1d-ma7-asset-specific-search/](asset-portfolios/1d-ma7-asset-specific-search/README.md) · [主账](asset-portfolios/1d-ma7-asset-specific-search/binance-1d-ma7-as-search-core-ledger.md) | V1/V2 registered / HARD-GATE-FAILED / not promoted / not live-ready |
| `Binance-1D-BTCETH-Relative-Cycle-Rotation`（`BIN-1D-BE-RCR`） | [asset-portfolios/1d-btceth-relative-cycle-rotation/](asset-portfolios/1d-btceth-relative-cycle-rotation/README.md) · [主账](asset-portfolios/1d-btceth-relative-cycle-rotation/binance-1d-be-rcr-core-ledger.md) | explore / research-line-closed / HARD-GATE-FAILED / not promoted / not live-ready |
| `Binance-1D-BTCETH-Log-Ratio-Mean-Reversion`（`BIN-1D-BE-LRMR`） | [asset-portfolios/1d-btceth-log-ratio-mean-reversion/](asset-portfolios/1d-btceth-log-ratio-mean-reversion/README.md) · [主账](asset-portfolios/1d-btceth-log-ratio-mean-reversion/binance-1d-be-lrmr-core-ledger.md) | explore / research-line-closed / HARD-GATE-FAILED / not promoted / not live-ready |
| `Binance-1H-BTCETH-Cross-Impulse-Lead-Lag`（`BIN-1H-BE-CILL`） | [asset-portfolios/1h-btceth-cross-impulse-lead-lag/](asset-portfolios/1h-btceth-cross-impulse-lead-lag/README.md) · [主账](asset-portfolios/1h-btceth-cross-impulse-lead-lag/binance-1h-be-cill-core-ledger.md) | explore / research-line-closed / HARD-GATE-FAILED / not promoted / not live-ready |
| `Binance-1D-BTCETH-Cross-Breadth-Channel-Trend`（`BIN-1D-BE-CBCT`） | [asset-portfolios/1d-btceth-cross-breadth-channel-trend/](asset-portfolios/1d-btceth-cross-breadth-channel-trend/README.md) · [主账](asset-portfolios/1d-btceth-cross-breadth-channel-trend/binance-1d-be-cbct-core-ledger.md) | explore / research-line-closed / HARD-GATE-FAILED / not promoted / not live-ready |
| `Binance-1D-BTCETH-Dual-Horizon-Campaign-Trend`（`BIN-1D-BE-DHCT`） | [asset-portfolios/1d-btceth-dual-horizon-campaign-trend/](asset-portfolios/1d-btceth-dual-horizon-campaign-trend/README.md) · [主账](asset-portfolios/1d-btceth-dual-horizon-campaign-trend/binance-1d-be-dhct-core-ledger.md) | explore / research-line-closed / HARD-GATE-FAILED / not promoted / not live-ready |
| `Binance-1D-BTCETH-Dual-Alpha-Sleeve-Ensemble`（`BIN-1D-BE-DASE`） | [asset-portfolios/1d-btceth-dual-alpha-sleeve-ensemble/](asset-portfolios/1d-btceth-dual-alpha-sleeve-ensemble/README.md) · [主账](asset-portfolios/1d-btceth-dual-alpha-sleeve-ensemble/binance-1d-be-dase-core-ledger.md) | explore / research-line-closed / HARD-GATE-FAILED / not promoted / not live-ready |
| `Binance-1D-BTCETH-Crisis-Override-Shadow-Trend`（`BIN-1D-BE-COST`） | [asset-portfolios/1d-btceth-crisis-override-shadow-trend/](asset-portfolios/1d-btceth-crisis-override-shadow-trend/README.md) · [主账](asset-portfolios/1d-btceth-crisis-override-shadow-trend/binance-1d-be-cost-core-ledger.md) | V1 registered / research-line-closed / HARD-GATE-FAILED / not promoted / not live-ready |
| `Binance-1D-BTCETH-Crisis-Partial-Profit-Runner`（`BIN-1D-BE-CPPR`） | [asset-portfolios/1d-btceth-crisis-partial-profit-runner/](asset-portfolios/1d-btceth-crisis-partial-profit-runner/README.md) · [主账](asset-portfolios/1d-btceth-crisis-partial-profit-runner/binance-1d-be-cppr-core-ledger.md) | explore / research-line-closed / HARD-GATE-FAILED / not promoted / not live-ready |
| `Binance-1D-BTCETH-Crisis-Profit-Exit-Handoff-Continuity`（`BIN-1D-BE-CPEHC`） | [asset-portfolios/1d-btceth-crisis-profit-exit-handoff-continuity/](asset-portfolios/1d-btceth-crisis-profit-exit-handoff-continuity/README.md) · [主账](asset-portfolios/1d-btceth-crisis-profit-exit-handoff-continuity/binance-1d-be-cpehc-core-ledger.md) | explore / not promoted / not live-ready |
| `Binance-1D-MA7-RSI6-Direction-Aligned-Pooled-ML`（`BIN-1D-MA7-RSI6-DAPML`） | [asset-portfolios/1d-ma7-rsi6-direction-aligned-pooled-ml/](asset-portfolios/1d-ma7-rsi6-direction-aligned-pooled-ml/README.md) · [主账](asset-portfolios/1d-ma7-rsi6-direction-aligned-pooled-ml/binance-1d-ma7-rsi6-dapml-core-ledger.md) | explore / HARD-GATE-FAILED / not promoted / not live-ready |
| `Binance-1D-MA7-Later-Maturity-Meta-Label`（`BIN-1D-MA7-LMML`） | [asset-portfolios/1d-ma7-later-maturity-meta-label/](asset-portfolios/1d-ma7-later-maturity-meta-label/README.md) · [主账](asset-portfolios/1d-ma7-later-maturity-meta-label/binance-1d-ma7-lmml-core-ledger.md) | explore / HARD-GATE-FAILED / not promoted / not live-ready |
| `Binance-1H-MA7-Root-Hazard-Timing`（`BIN-1H-MA7-RHT`） | [asset-portfolios/1h-ma7-root-hazard-timing/](asset-portfolios/1h-ma7-root-hazard-timing/README.md) · [主账](asset-portfolios/1h-ma7-root-hazard-timing/binance-1h-ma7-rht-core-ledger.md) | explore / HARD-GATE-FAILED / not promoted / not live-ready |
| `Binance-1H-Volatility-Impulse-Pullback-Reclaim`（`BIN-1H-VIPR`） | [asset-portfolios/1h-volatility-impulse-pullback-reclaim/](asset-portfolios/1h-volatility-impulse-pullback-reclaim/README.md) · [主账](asset-portfolios/1h-volatility-impulse-pullback-reclaim/binance-1h-vipr-core-ledger.md) | explore / HARD-GATE-FAILED / not promoted / not live-ready |
| `Binance-1D-MA7-Derivatives-Structure-Meta-Label`（`BIN-1D-MA7-DSML`） | [asset-portfolios/1d-ma7-derivatives-structure-meta-label/](asset-portfolios/1d-ma7-derivatives-structure-meta-label/README.md) · [主账](asset-portfolios/1d-ma7-derivatives-structure-meta-label/binance-1d-ma7-dsml-core-ledger.md) | explore / HARD-GATE-FAILED / not promoted / not live-ready |
| `Binance-1D-MA7-Basis-Premium-Meta-Label`（`BIN-1D-MA7-BPML`） | [asset-portfolios/1d-ma7-basis-premium-meta-label/](asset-portfolios/1d-ma7-basis-premium-meta-label/README.md) · [主账](asset-portfolios/1d-ma7-basis-premium-meta-label/binance-1d-ma7-bpml-core-ledger.md) | explore / HARD-GATE-FAILED / not promoted / not live-ready |
| `Binance-1D-MA7-Taker-Flow-Meta-Label`（`BIN-1D-MA7-TFML`） | [asset-portfolios/1d-ma7-taker-flow-meta-label/](asset-portfolios/1d-ma7-taker-flow-meta-label/README.md) · [主账](asset-portfolios/1d-ma7-taker-flow-meta-label/binance-1d-ma7-tfml-core-ledger.md) | explore / diagnostic-only / not promoted / not live-ready |
| `Binance-1D-MA7-Quantile-Utility-Meta-Label`（`BIN-1D-MA7-QUML`） | [asset-portfolios/1d-ma7-quantile-utility-meta-label/](asset-portfolios/1d-ma7-quantile-utility-meta-label/README.md) · [主账](asset-portfolios/1d-ma7-quantile-utility-meta-label/binance-1d-ma7-quml-core-ledger.md) | explore / diagnostic-only / not promoted / not live-ready |
| `Binance-1D-MA7-Asset-Local-Temporal-Audit`（`BIN-1D-MA7-ALTA`） | [asset-portfolios/1d-ma7-asset-local-temporal-audit/](asset-portfolios/1d-ma7-asset-local-temporal-audit/README.md) · [主账](asset-portfolios/1d-ma7-asset-local-temporal-audit/binance-1d-ma7-alta-core-ledger.md) | explore / HARD-GATE-FAILED / not promoted / not live-ready |
| `Binance-1D-Derivatives-Structure-Trend-Opportunity`（`BIN-1D-DSTO`） | [asset-portfolios/1d-derivatives-structure-trend-opportunity/](asset-portfolios/1d-derivatives-structure-trend-opportunity/README.md) · [主账](asset-portfolios/1d-derivatives-structure-trend-opportunity/binance-1d-dsto-core-ledger.md) | explore / diagnostic-only / not promoted / not live-ready |
| `Binance-15M-Multi-Indicator-Intraday-Transfer` | [asset-portfolios/15m-multi-indicator-intraday/](asset-portfolios/15m-multi-indicator-intraday/README.md) | explore / not promoted |
| `Binance-15M-Asset-Specific-Six-Strategy-Selector`（`BIN-15M-AS6S`） | [asset-portfolios/15m-asset-specific-six-strategy-selector/](asset-portfolios/15m-asset-specific-six-strategy-selector/README.md) · [主账](asset-portfolios/15m-asset-specific-six-strategy-selector/binance-15m-as6s-core-ledger.md) | archived |
| `Binance-1H-Adaptive-Regime-Multi-Asset-Ensemble`（`BIN-1H-AR-MAE`） | [asset-portfolios/1h-adaptive-regime-multi-asset-ensemble/](asset-portfolios/1h-adaptive-regime-multi-asset-ensemble/README.md) · [主账](asset-portfolios/1h-adaptive-regime-multi-asset-ensemble/binance-1h-ar-mae-core-ledger.md) | V1 dry-run / not live-ready |
| `Binance-1H-Multi-Leg-Six-Asset-Selector`（`BIN-1H-ML6AS`） | [asset-portfolios/1h-multi-leg-six-asset-selector/](asset-portfolios/1h-multi-leg-six-asset-selector/README.md) · [主账](asset-portfolios/1h-multi-leg-six-asset-selector/binance-1h-ml6as-core-ledger.md) | explore / not promoted / not live-ready |
| `Binance-MK7-Multi-Strategy-Account`（外部别名 `mk7`） | [asset-portfolios/mk7-multi-strategy-account/](asset-portfolios/mk7-multi-strategy-account/README.md) · [主账](asset-portfolios/mk7-multi-strategy-account/mk7-multi-strategy-account-core-ledger.md) | mk7-v8 / external-observation / explore / not promoted / not live-ready |
| `HYPE-Cross-Strategy-Account` | [asset-portfolios/hype-cross-strategy-account/](asset-portfolios/hype-cross-strategy-account/README.md) | explore / diagnostic-only |
| `MU-HYPE-Transfer`（`MU-HYPE-XFER`） | [mu/](mu/README.md)（扁平结构，grandfathered） | explore / not promoted / not live-ready |

旧 HYPE cross-asset transfer 材料位于 `../archive/research/hype-transfer/`。

## 研究平台

- [strategy-factor-discovery](platform/strategy-factor-discovery/README.md)：diagnostic_topic / exploratory；20个Graph模板、20个公开因子、失败学习与登记演化。
- [factor-research-loop](platform/factor-research-loop/README.md)：diagnostic_topic / exploratory；公开定义到真实因子研究与私有 Graph 证据。

入口：[platform/README.md](platform/README.md)。平台审计不承载策略绩效。

- [10,000 美元账户三方向首轮验证](platform/small-account-three-line-validation/README.md)：跨家族诊断比较与独立验收；结果权威仍在各家族，不建立合成策略身份。

| Family / Topic | Directory | 状态 |
| --- | --- | --- |
| `Binance-OHLCV-Data-Lake-Governance`（`BIN-OHLCV-DLG`） | [platform/data-lake-governance/](platform/data-lake-governance/README.md) · [主账](platform/data-lake-governance/binance-ohlcv-dlg-core-ledger.md) | explore / platform-audit |
| `Cross-Sectional Alpha Research Pipeline` | [platform/cross-sectional-alpha-pipeline/](platform/cross-sectional-alpha-pipeline/README.md) | explore / platform-audit |
| `Runner-Authorization-Reconciliation`（`RUNNER-AUTH-RECON`） | [platform/runner-authorization-reconciliation/](platform/runner-authorization-reconciliation/README.md) | explore / platform-audit |
| `Research-Program-Review` | [platform/research-program-review/](platform/research-program-review/README.md) | diagnostic_topic / 研究目标、方法与实盘路径审计 |

## 行业与创业研究

入口：[industry/README.md](industry/README.md)。跨行业产品研究不承载策略绩效或实盘晋升。

| Topic | Directory | 状态 |
| --- | --- | --- |
| `Crypto-Startup-Opportunity-Landscape` | [industry/crypto-startup-opportunities/](industry/crypto-startup-opportunities/README.md) | explore / diagnostic-only |

## 共享研究内核

跨资产或跨家族复用的研究引擎存放在 `_shared-kernels/`，按冻结版本目录管理（见 [_shared-kernels/README.md](_shared-kernels/README.md)）。当前包括 [1h-adaptive-regime-search/](_shared-kernels/1h-adaptive-regime-search/README.md)、[multi-horizon-ema-forecast/](_shared-kernels/multi-horizon-ema-forecast/README.md)、[ema-trend-breakout/](_shared-kernels/ema-trend-breakout/README.md)、[bollinger-keltner-squeeze-breakout/](_shared-kernels/bollinger-keltner-squeeze-breakout/README.md) 与 [binance-ma7-root-data/](_shared-kernels/binance-ma7-root-data/README.md)。

## 目录与存储约定

新建家族、登记版本与保存产物见 [研究存储规则](../.cursor/rules/research-report-storage.mdc)；主账字段见 [主账模板](../docs/research-governance/core-ledger-template.md)。

## 历史或浅层研究

- [早期日内策略落档后回放](asset-portfolios/multi-legacy-post-registration-audit/README.md)：跨家族diagnostic_topic；测试原固定规则在登记之后的盈利与回撤，具体覆盖和结果见报告。

`crowding_reversal` 及早期平台示例（spot CTA、CTA grid、通用 MA crossover、momentum rotation、Donchian 变体）归档于 `../archive/research/`，不作为当前核心研究线。

## QuantGraph 研究接口

- [知识候选与证据联通](platform/quantgraph-integration/README.md)：diagnostic-only / not promoted。
- [quantgraph-diagnostics 共享内核](_shared-kernels/quantgraph-diagnostics/README.md)：v1 通用统计诊断。

- [BTC 1d QuantGraph PRICE_SMA](btc/1d-quantgraph-source-sma/README.md)：独立来源改编；explore / untrusted / not promoted / not live-ready。

- [BTC 1d QuantGraph ZSCORE_REVERSION](btc/1d-quantgraph-source-zscore/README.md)：独立来源改编；explore / untrusted / not promoted / not live-ready。

- [BTC 4h QuantGraph EMA_CROSSOVER](btc/4h-quantgraph-source-ema/README.md)：独立来源改编；explore / untrusted / not promoted / not live-ready。

- [quantgraph-market](_shared-kernels/quantgraph-market/README.md)：v1 冻结账户回放，只做本地研究计算。
- `MA7-ATR14-Long-Short-Reversal-Audit`：[对称多空与信号反手机制诊断](asset-portfolios/1d-ma7-atr14-long-short-audit/README.md)，原多头固定参数延伸，`explore / diagnostic-only / not promoted / not live-ready`。

- [PUBLIC100 公开策略100条逐项复核](asset-portfolios/multi-public-strategies-100/README.md)：diagnostic_topic / explore / untrusted；19条数值诊断，81条数值回测未完成，not promoted / not live-ready。

## M0216 首条来源回放

[BTC日频SMA11/20主账](public-strategies/M0216/m0216-core-ledger.md)：explore / not promoted / not live-ready。真实数据回放完成，源码停机保留持仓，结果低于买入持有；不计严格复现。

## Cloud batch 002 — fixed-source BTC diagnostics

- [M0200 主账](public-strategies/M0200/m0200-core-ledger.md)：执行延迟敏感的RSI2均值回归；explore / not promoted / not live-ready，严格复现0。
- [M0215 主账](public-strategies/M0215/m0215-core-ledger.md)：原列BTC单腿RSI2反弹；explore / not promoted / not live-ready，严格复现0。
- [M0217 主账](public-strategies/M0217/m0217-core-ledger.md)：昨日振幅突破的日级成交假设；explore / not promoted / not live-ready，严格复现0。

## 公开采集策略专区

统一入口：[research/public-strategies](public-strategies/README.md)。与个人深入研究分开，按稳定catalog ID组织，保留来源/实现分类。

历史链接入口：[btc/1d-m0216-sma-cross/](btc/1d-m0216-sma-cross/README.md)。仅重定向，不是个人研究家族。

[M0004 阻塞报告](public-strategies/M0004/README.md)。

## 公开策略小批003

- [M0212 主账](public-strategies/M0212/m0212-core-ledger.md)：时间锚假设，延迟敏感，explore。
- [M0214 主账](public-strategies/M0214/m0214-core-ledger.md)：SMA与HA只多改编，explore。
- [M0233 主账](public-strategies/M0233/m0233-core-ledger.md)：源码逐行重置的z分数只多改编，explore。

小批003时的来源预审入口（M0220现已在小批004执行）：[M0211](public-strategies/M0211/README.md)、[M0220](public-strategies/M0220/README.md)、[M0232](public-strategies/M0232/README.md)。规则/访问阻塞与数据回测完成分别计数。

## 公开策略小批004

[M0220主账](public-strategies/M0220/m0220-core-ledger.md)：20完整周预热后的周线动量假设，explore。
[M0221](public-strategies/M0221/README.md) 与 [M0226](public-strategies/M0226/README.md)：具体规则阻塞，均0回测。

## 公开策略 M0256 / M0259

- [M0256 主账](public-strategies/M0256/m0256-core-ledger.md)：BTC现货4h EMA8/21，4个假设配置及1个买持对照；DIAGNOSTIC_ONLY，严格复现0，未晋级。
- [M0259 主账](public-strategies/M0259/m0259-core-ledger.md)：BbandRsi原定1h窗口的数据完整性阻塞，实际市场回测0；保留缺口与停市异常证据。

## 公开策略 M0288

- [M0288 主账](public-strategies/M0288/m0288-core-ledger.md)：BTC现货日线高浪线形态，原生参考引擎4个假设配置及1个买持；DIAGNOSTIC_ONLY，严格0，未晋级。

## 公开策略 M0286

- [M0286 主账](public-strategies/M0286/m0286-core-ledger.md)：BTC现货4h MultiMa，完整原类信号核对，4个假设配置及1买持；DIAGNOSTIC_ONLY，严格0，未晋级。
