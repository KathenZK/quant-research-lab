# M0293 来源与许可

原始策略为 Gert Wohlgemuth 的 ReinforcedAverageStrategy，固定 [freqtrade-strategies f3340ce](https://github.com/freqtrade/freqtrade-strategies/blob/f3340ce11f5bdf62f598522e64d1f5638eaa13f5/user_data/strategies/berlinguyinca/ReinforcedAverageStrategy.py)。源程序3502字节，SHA256 `50c8e88441ffead38fd1e1b3d49b151a001068f5eff01a23c10178b1f2c87e38`，仓库GPL-3.0。本目录新增研究移植和校验代码采用GPL-3.0-or-later，见[LICENSE](LICENSE)。账户核心复用M0286已审函数为本ID冻结派生快照，[逐函数AST核验](specs/execution-reuse.json)记录父源码和摘要；旧文件不改，未新建平台或修改全局共享内核。

重采样参照 [technical 1.5.3 / 8ce873e](https://github.com/freqtrade/technical/blob/8ce873e269bfbfe0d17d487a3e5163616ec0a872/technical/util.py)，qtpylib参照[Freqtrade c66e221](https://github.com/freqtrade/freqtrade/blob/c66e221012cd4d68cfdacf4735b38af33a487961/freqtrade/vendor/qtpylib/indicators.py)；qtpylib原署名Ran Aroussi及其Apache-2.0文件头保留在私有源码恢复件。TA-Lib wrapper0.6.8/C0.6.4负责EMA/SMA，原作者历史环境未知。完整第三方代码只留私有核验副本；公开内容为来源链接、指纹和自撰规则，不复制论文、网页全文或私有采集主表。

行情来自Binance Vision官方月档，行情及派生收益/指标/交易/曲线遵循[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)及[Binance Dataset Terms固定版本](https://github.com/binance/binance-public-data/blob/f446ce3812bd4e5521f21faecd4ae3c6460e49fc/TERMS_AND_CONDITIONS.md)。本轮用户授权个人非生产研究，未授权商业或实盘。改动包括数据校验、48h聚合、指标计算、假设成交账户和日末采样；不暗示提供方认可。完整原始行情不公开；公开指纹和重建配方不保证官方源永久可得。
