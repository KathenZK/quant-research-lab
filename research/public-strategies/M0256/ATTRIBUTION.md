# M0256 来源与许可

## 软件与规则

- 原策略：Gert Wohlgemuth，`freqtrade/freqtrade-strategies` 的 AverageStrategy；固定 [f3340ce11f5bdf62f598522e64d1f5638eaa13f5](https://github.com/freqtrade/freqtrade-strategies/blob/f3340ce11f5bdf62f598522e64d1f5638eaa13f5/user_data/strategies/berlinguyinca/AverageStrategy.py)。原仓库 GPL-3.0；本目录新增 Python 移植、测试及恢复脚本按 GPL-3.0-or-later 提供，见 [LICENSE](LICENSE)。这些是研究用独立执行实现，非原作者提供的执行器。
- qtpylib：Ran Aroussi（2016–2018）及 Freqtrade contributors；参考 [Freqtrade 2025.9 / c66e2210](https://github.com/freqtrade/freqtrade/blob/c66e221012cd4d68cfdacf4735b38af33a487961/freqtrade/vendor/qtpylib/indicators.py)，文件头 Apache-2.0；Freqtrade 仓库按 GPL-3.0 分发。保留原始文件署名，不将框架版本误当作原策略历史运行环境。
- TA-Lib EMA C 语义：TA-Lib contributors、Mario Fortier，BSD-3-Clause 文件头；[TA-Lib 0.6.4 固定来源](https://github.com/TA-Lib/ta-lib/blob/43f9d5042ecc4bd367941846494ad907bf20ea50/src/ta_func/ta_EMA.c)。实际依赖 Python wrapper 0.6.8 / C 0.6.4。
- [软件来源清单](specs/source-manifest.json)列出原始 URL、commit、字节和 SHA256。完整第三方源码与文档是本地私有核验副本，不属于本次公开文件；[恢复脚本](scripts/fetch_sources.py)从固定公共地址重取并核指纹，失败或不符即中止。
- 私有主表仅用于核 M0256 一行，不发布主表、完整行拷贝或其它条目。

## 行情与派生研究结果

行情提供方为 Binance，来源 Binance Public Data / Binance Vision。数据、数据派生的指标、收益、曲线、交易结果和 Graph 数据采用 CC BY-NC-SA 4.0，并受 Binance Market Data [2026 固定条款（f446ce3812bd4e5521f21faecd4ae3c6460e49fc）](https://github.com/binance/binance-public-data/blob/f446ce3812bd4e5521f21faecd4ae3c6460e49fc/TERMS_AND_CONDITIONS.md)所列附加条件约束。许可文本：[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)。提供方保留权利，不暗示其认可本研究。

本研究对数据进行：UTC 月档拼接及质量检查、EMA 指标计算、假设成交/费用/风险账户重放、指标汇总及日末净值采样。完整原始行情不随公开结果复制，恢复以官方固定源及指纹验证为准。软件许可不能替代行情及其派生结果许可；本条不构成商业用途许可、投资建议、PIT/历史交易可得性证明，亦不保证未来源始终可用。
