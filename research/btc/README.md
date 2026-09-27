# BTC Research Index

本目录存放 Bitcoin 单资产策略家族。任何版本号都必须和市场、周期、机制一起引用；状态词定义见 [strategy-status-glossary.md](../../docs/research-governance/strategy-status-glossary.md)。

## 当前研究线

- `BTC-1H-Adaptive-Regime`（`BTC-1H-AR`）：[1h-adaptive-regime/](1h-adaptive-regime/README.md)。Binance USD-M Futures `BTCUSDT` perpetual `1h` 多指标自适应 regime 家族；V1-V4 已登记；V4 参数邻域已判定局部耗尽，VWAP short-only、wick transition-only、MACD replace-Keltner 三条结构优化路线均为 `0` 严格 gate 命中，未产生 V5；当前 `registered / not promoted / not live-ready`。主账：[btc-1h-ar-core-ledger.md](1h-adaptive-regime/btc-1h-ar-core-ledger.md)。
- `BTC-15M-EMA-Trend-Breakout`（`BTC-15M-EMA-TB`）：[15m-ema-trend-breakout/](15m-ema-trend-breakout/README.md)。Binance USD-M Futures `BTCUSDT` perpetual `15m` 快慢 EMA 趋势背景 + 价格突破家族；V40 模板迁移未找到通过门禁的类似盈利策略，停止扩搜；`explore / not promoted / not live-ready`。主账：[btc-15m-ema-tb-core-ledger.md](15m-ema-trend-breakout/btc-15m-ema-tb-core-ledger.md)。
- `BTC-15M-Keltner-Trend-Breakout`（`BTC-15M-KTB`）：[15m-keltner-trend-breakout/](15m-keltner-trend-breakout/README.md)。Binance USD-M Futures `BTCUSDT` perpetual `15m` Keltner 收盘突破 + 可选 `1h` EMA trend regime；首轮 `630` 组冻结搜索 validation 正收益项为 `0`，停止本轮机制扩搜；`explore / not promoted / not live-ready`。主账：[btc-15m-keltner-trend-breakout-core-ledger.md](15m-keltner-trend-breakout/btc-15m-keltner-trend-breakout-core-ledger.md)。
- `BTC-15M-Trend-Continuation`（`BTC-15M-TC`）：[15m-trend-continuation/](15m-trend-continuation/README.md)。Binance USD-M Futures `BTCUSDT` perpetual `15m` 低波动压缩 + EMA 趋势 + Donchian 突破延续；多头六轮迭代无采纳项，空头专属 `804` 配置无门禁通过项，停止历史扩搜，仅保留 long-only prospective 观察；`explore / not promoted / not live-ready`。主账：[btc-15m-trend-continuation-core-ledger.md](15m-trend-continuation/btc-15m-trend-continuation-core-ledger.md)。
- `BTC-30M-Trend-Continuation`（`BTC-30M-TC`）：[30m-trend-continuation/](30m-trend-continuation/README.md)。Binance USD-M Futures `BTCUSDT` perpetual 原生 `30m` EMA 趋势 + 压缩/Donchian/Keltner 突破；低频结构通过历史成本与相位审计但样本门禁失败，高频路线在 `2024+` 与近期失效，停止本轮扩搜；`explore / not promoted / not live-ready`。主账：[btc-30m-trend-continuation-core-ledger.md](30m-trend-continuation/btc-30m-trend-continuation-core-ledger.md)。
- `BTC-1D-Classic-CTA-Trend`（`BTC-1D-CCTA`）：[1d-classic-cta-trend/](1d-classic-cta-trend/README.md)。Carver EWMAC 四速统一信号 + 20% 波动率缩放 + BTC 永续成本/资金费；文献参数零调参基线净正但相对 1x 买入持有无超额，`explore / not promoted / not live-ready`。主账：[btc-1d-ccta-core-ledger.md](1d-classic-cta-trend/btc-1d-ccta-core-ledger.md)。
- `BTC-1D-Qingze-Critical-Point-Trend`（`BTC-1D-QZ-CPT`）：[1d-qingze-critical-point-trend/](1d-qingze-critical-point-trend/README.md)。SMA 趋势过滤 + 放量临界点突破 + 浮盈正金字塔；20,000 组搜索 rank 1 锁定 validation 为负，`explore / diagnostic-only / not promoted / not live-ready`。主账：[btc-1d-qz-cpt-core-ledger.md](1d-qingze-critical-point-trend/btc-1d-qz-cpt-core-ledger.md)。
- `BTC-1D-MA7-RSI6-LightGBM-Trend`（`BTC-1D-MA7-RSI6-LGBM`）：[1d-ma7-rsi6-lightgbm-trend/](1d-ma7-rsi6-lightgbm-trend/README.md)。严格 SMA7 收盘跨越、MA7/K 线几何与 Wilder RSI6 阶段状态输入 LightGBM；P0 已冻结完整日 K 和最近一年 validation，尚未训练模型；`explore / diagnostic-only / not promoted / not live-ready`。主账：[btc-1d-ma7-rsi6-lgbm-core-ledger.md](1d-ma7-rsi6-lightgbm-trend/btc-1d-ma7-rsi6-lgbm-core-ledger.md)。
- `BTC-1W-MA7-Asymmetric-Body-Trend`（`BTC-1W-MA7-ABT`）：[1w-ma7-asymmetric-body-trend/](1w-ma7-asymmetric-body-trend/README.md)。HYPE 日线 V1 的固定 SMA7/ATR7 多空状态机零调参迁移至 BTC 周 K；主/偏移相位及多空单腿均亏损，direct transfer 失败，`explore / not promoted / not live-ready`。主账：[btc-1w-ma7-abt-core-ledger.md](1w-ma7-asymmetric-body-trend/btc-1w-ma7-abt-core-ledger.md)。
- `Binance-1D-MA7-Asset-Specific-Search`（跨资产家族）：[asset-portfolios/1d-ma7-asset-specific-search/](../asset-portfolios/1d-ma7-asset-specific-search/README.md)。固定 SMA7/ATR7 的 BTC/ETH shared 参数搜索；`V1 / V2 registered / not promoted / not live-ready`。主账：[binance-1d-ma7-as-search-core-ledger.md](../asset-portfolios/1d-ma7-asset-specific-search/binance-1d-ma7-as-search-core-ledger.md)。

- [BTC 1d QuantGraph PRICE_SMA](1d-quantgraph-source-sma/README.md)：独立来源改编；explore / untrusted / not promoted / not live-ready。

- [BTC 1d QuantGraph ZSCORE_REVERSION](1d-quantgraph-source-zscore/README.md)：独立来源改编；explore / untrusted / not promoted / not live-ready。

- [BTC 4h QuantGraph EMA_CROSSOVER](4h-quantgraph-source-ema/README.md)：独立来源改编；explore / untrusted / not promoted / not live-ready。
