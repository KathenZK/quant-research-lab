# M0286 来源与许可

原策略 MultiMa V2 作者为 @Mablue（Masoud Azizi），固定 [freqtrade-strategies f3340ce](https://github.com/freqtrade/freqtrade-strategies/blob/f3340ce11f5bdf62f598522e64d1f5638eaa13f5/user_data/strategies/MultiMa.py)。来源文件 3464 字节，SHA256 `cae77a6c8f983377e392a2c66bfc541e7c1400fae03c3a413194902b2eda6626`。来源仓库 GPL-3.0；本目录移植、校验及恢复脚本按 GPL-3.0-or-later，见 [LICENSE](LICENSE)。账户事件框架改编自本仓库 M0256 的冻结移植，改动为 TEMA 排列、参数加载核验、信号冲突和分钟 ROI 开盘代理；不是原作者提供的执行器。

参数加载与信号冲突语义参照 [Freqtrade c66e221](https://github.com/freqtrade/freqtrade/tree/c66e221012cd4d68cfdacf4735b38af33a487961)，不冒称原作者的历史环境。TEMA 数值依赖 TA-Lib Python 0.6.8 / C 0.6.4，公式源码见[来源清单](specs/source-manifest.json)，TA-Lib 源码头为 BSD-3-Clause。完整第三方程序与文档只留私有核验副本，按固定来源和 SHA256 重建；公开记录包含链接及自撰规则，不复制原网页/论文全文或私有采集表。

行情来自 Binance Vision 官方现货月档。行情及派生收益、指标、交易和曲线采用 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)，并受 [Binance Dataset Terms 固定版本 f446ce3](https://github.com/binance/binance-public-data/blob/f446ce3812bd4e5521f21faecd4ae3c6460e49fc/TERMS_AND_CONDITIONS.md) 的附加条件约束。用户已授权本次个人非生产研究，不授权商业或实盘用途。改动包括月档检查、TEMA、假设成交账户计算和日末采样；不暗示 Binance 或原作者认可。原始行情不公开，官方源可能未来变更或不可达；来源失效是恢复阻塞，不绕过限制。
