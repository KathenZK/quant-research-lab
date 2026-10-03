# M0259 来源与执行预审

## 来源与白话

原策略作者为Gert Wohlgemuth；文件署名注明由sthewissen/Mynt的BbandRsi转换。固定来源是 freqtrade/freqtrade-strategies 的 `f3340ce11f5bdf62f598522e64d1f5638eaa13f5`，`user_data/strategies/berlinguyinca/BbandRsi.py`。1854字节，SHA256 `65718e8d0c14094b67be82b66238ea60a4af4bbf6fd9a6e1879dad5c48125547`，下载后核hash再读取。

策略试图在价格低于近期波动区间、RSI超卖时买入，在RSI超买、收益达到ROI条件或stoploss触发时退出。这只是均值回归的经济假设；趋势性下跌、频繁小亏和成本敏感均是事前失败场景，不是本次数据观测结论。

## 指标语义锁定

- Freqtrade2025.9不可变commit `c66e221012cd4d68cfdacf4735b38af33a487961`
- vendored qtpylib hash `39de0b1a666c05e0c11034c993eb96212eb505d20d630712c4bb503008609760`
- RSI为TA-Lib Python0.6.8/C0.6.4、周期14、compatibility0、unstable0，Wilder种子，前14个位置为NaN
- BB使用(H+L+C)/3，rolling20、min_periods1、样本标准差ddof1、2倍宽度；不能用TA-Lib BBANDS的默认总体标准差替代
- 原文件没有volume>0过滤；此处不自行添加
- 用直接列索引访问rsi，避免qtpylib对PandasObject.rsi的猴子补丁命名冲突

## 执行和数据边界

保持ROI10%与stoploss−25%，但明确声明独立移植：exit signal先于后续风险路径，开盘跳空按已知open处理，剩余bar内stop优先ROI。止损按实际入场成交价的75%；ROI阈值按含双边费的10%利润，阈值后卖出滑点使净回报约9.978%。允许最后warmup信号在评估首open执行，额外延迟只使用i−2的历史信号。

输入计划为Binance Vision官方BTCUSDT现货1h月档，2022-12到2024-12，共应有18288根输入、17544根评估bar、731个评估日。此处为最初预审的期望网格。后续实际下载中2023-03月档仅743/744根，同日官方日档23/24根且逐字段相同；已按DATA_BLOCKED停止，未生成整段输入或计算市场指标/收益，详见data-blocked-20261003.md。

仓库标准要求完整身份、许可、coverage、schema、calendar、integrity、hash、finality、provenance检查。月档文件和过去时间本身不能伪造is_closed；缺少既定双次历史抓取闭合协议及PIT证据时保持DIAGNOSTIC_ONLY。不要把源策略GPL许可当作行情授权。

## 许可和公开边界

策略来源库GPL-3.0；原qtpylib头部注明Apache-2.0、Ran Aroussi copyright2016–2018。第三方代码完整字节只在私有工作目录保留，公开包包含固定URL/hash与下载核验脚本。[来源清单](../sources/manifest.json)记录全部引用。

本地新写软件脚本标GPL-3.0-or-later；Binance原始数据以及由其生成的收益、净值、图表、Graph衍生物独立适用CC BY-NC-SA4.0及[固定Binance附加条款](https://github.com/binance/binance-public-data/blob/f446ce3812bd4e5521f21faecd4ae3c6460e49fc/TERMS_AND_CONDITIONS.md)。软件许可不覆盖数据。下载及后续公开须满足实际授权，不以此报告代替接受条款。
