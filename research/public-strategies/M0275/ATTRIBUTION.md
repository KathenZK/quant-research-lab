# 来源、归因与许可边界

## 软件及规则

- M0275 Heracles原作者为Mablue（Masoud Azizi），固定来源：[freqtrade-strategies f3340ce11f5bdf62f598522e64d1f5638eaa13f5](https://github.com/freqtrade/freqtrade-strategies/blob/f3340ce11f5bdf62f598522e64d1f5638eaa13f5/user_data/strategies/Heracles.py)，上游GPL-3.0；本目录研究执行器、检查和恢复脚本按GPL-3.0-or-later，见[LICENSE](LICENSE)
- ta作者Dario López Padial及贡献者，使用PyPI `ta==0.11.0`，上游MIT；固定安装包的指标/工具源码摘要见[依赖清单](specs/requirements.lock.txt.json)。它是本研究明确选定的环境，原作者具体ta版本未知
- Freqtrade2025.9固定commit `c66e221012cd4d68cfdacf4735b38af33a487961` 的参数加载与AgeFilter代码只作语义参考；本任务没有运行完整Freqtrade引擎。上游GPL-3.0
- 数据重建与无损审计脚本沿用先前受审版本，继承数据工具不等于继承M0256策略结论。部分保留的输入清单原strategy_id仍为M0256，这是原证据身份，未改写为新捕获
- 固定URL、字节数、SHA256列在[来源清单](specs/source-manifest.json)；完整第三方源码/官方HTML只留私有来源核验目录，不列公开allowlist。许可证文本本身可随软件保留。私有主表只核M0275原行，不发布主表或完整行

## 行情及数据衍生研究

Binance Public Data / Binance Vision提供原始市场数据。数据及由其得到的指标、交易、收益、净值、Graph记录/私有detail采用 **CC BY-NC-SA 4.0**，并受[Binance固定数据附加条款](https://github.com/binance/binance-public-data/blob/f446ce3812bd4e5521f21faecd4ae3c6460e49fc/TERMS_AND_CONDITIONS.md)约束；[CC BY-NC-SA 4.0许可](https://creativecommons.org/licenses/by-nc-sa/4.0/)。提供方保留权利，不表示认可本研究。

本次变更包括月档无损拼接/质量校验、通道指标及滞后计算、假设执行和成本账户重放、结果统计、月末或日末净值采样。公开文件不含原始行情、完整特征和大曲线；需要恢复时从官方源按固定hash校验。

软件GPL不能替代行情/衍生数据许可。已接受条款的范围仅为本次个人非生产研究，不推导商业、实盘、一般数据外传或重新授权。历史公告页面的轻量事实/短摘录只作来源证据，未发布整页。未来用途或共享范围发生变化时须另审权利；来源URL也不保证永远可访问或永不变化。
