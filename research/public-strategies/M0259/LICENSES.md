# 许可、署名与数据公开边界

- 本ID独立编写的研究/验证脚本：GPL-3.0-or-later，2026-10-03编写；许可正文见sources/LICENSE-GPL-3.0.txt
- 原策略：Gert Wohlgemuth（berlinguyinca），freqtrade/freqtrade-strategies固定commit的BbandRsi。源码保留原Mynt转换署名；公开包仅给固定URL/hash和核验下载脚本，不放第三方完整源码
- 运行所用qtpylib：Ran Aroussi，copyright2016–2018，原文件Apache-2.0；许可见scripts/vendor/LICENSE-APACHE-2.0.txt。完整vendor源码只在私有工作目录
- Binance原始行情及其衍生数值、审计、图表、Graph数据：署名Binance Vision，独立适用CC BY-NC-SA4.0及[固定附加条款](https://github.com/binance/binance-public-data/blob/f446ce3812bd4e5521f21faecd4ae3c6460e49fc/TERMS_AND_CONDITIONS.md)。软件许可不覆盖数据。本次获批用途为个人非生产研究，未授权商业或实盘使用
- 公开包只含自写代码、说明、来源/hash、合成测试回执和无原始价格的阻塞摘要；原始ZIP/CSV/网页HTML、完整私有Graph detail、原始私有总表与每bar大曲线均排除
- 当前没有真实策略收益或完整Graph detail；Graph仅提供DATA_BLOCKED记录，不含metrics、curve或null收益
