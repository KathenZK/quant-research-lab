# 来源、许可与用途

- 策略：freqtrade/freqtrade-strategies 的 hlhb，commit `f3340ce11f5bdf62f598522e64d1f5638eaa13f5`，[固定源码](https://github.com/freqtrade/freqtrade-strategies/blob/f3340ce11f5bdf62f598522e64d1f5638eaa13f5/user_data/strategies/hlhb.py)。作者在源码中称 HLHB “Huck loves her bucks!”；未凭名字推断个人著作权。源仓库 GPL-3.0；本改编执行及审计代码按 GPL-3.0-or-later 标记，许可证副本见 LICENSE。
- 框架语义参考：Freqtrade commit `c66e221012cd4d68cfdacf4735b38af33a487961` 的 strategy/interface.py；仅核 trailing 边界，绝不表示原作者运行此版本。完整第三方源码保留私有，公开仅 URL/hash 与重建脚本。
- 指标：TA-Lib Python 0.6.8、C 0.6.4，BSD 许可；numpy/pandas 按其各自许可。交叉布尔语义核自 Freqtrade 内置 QTPyLib（原头部 Apache-2.0），当前严格不等/前值含等号。
- 行情：Binance Vision 现货 BTCUSDT 原生 4h 月档，25个月，取得并重建路径已有逐档证据。本次未重新下载行情。归一化与研究派生不是 Binance 官方投资结果。
- 行情与派生数据许可：[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) 和 [Binance 附加条款固定版本](https://github.com/binance/binance-public-data/blob/f446ce3812bd4e5521f21faecd4ae3c6460e49fc/TERMS_AND_CONDITIONS.md)；限此前授权的个人非生产研究。原始行情不进公开 Git。摘要指标/月末归一净值/执行交易为派生，单独按数据许可约束，不能用软件 GPL 替代或消除非商业/相同方式共享等要求。
- 变更：原始 OHLCV 无修复；使用 TA 指标、固定限价报价/整单触价假设、O-L-H-C 路径、成本、风险、统计及轻量投影；这些执行补充假设不是来源承诺。
- 无作者收益复现、PIT完整性、真实成交队列、实盘或投资建议声明。
