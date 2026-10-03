# 源码与数据归属

## 软件

mabStra作者为Masoud Azizi（Mablue）。原始策略取自[freqtrade-strategies固定提交](https://github.com/freqtrade/freqtrade-strategies/blob/f3340ce11f5bdf62f598522e64d1f5638eaa13f5/user_data/strategies/mabStra.py)，仓库[GPL第3版许可](https://github.com/freqtrade/freqtrade-strategies/blob/f3340ce11f5bdf62f598522e64d1f5638eaa13f5/LICENSE)。本目录保留许可文本为LICENSE，但不重新分发完整第三方策略源码。

框架参数构造及默认值来自[freqtrade固定提交c66e221](https://github.com/freqtrade/freqtrade/tree/c66e221012cd4d68cfdacf4735b38af33a487961)，准确文件URL、字节数与SHA256见[源码清单](specs/source-manifest.json)。参数构造器和策略类通过原AST执行核验，完整Freqtrade未安装也未运行。源码作者明确要求hyperopt，本研究没有进行超优化，没有保存参数字典可用于还原其原配置。

本目录原创/改写的回放、验证、导出脚本采用GPL-3.0-or-later标识；通用输入审计、分钟ROI执行、账本与恢复部件源于同项目M0275冻结模板，M0317指标/信号独立实现并验证。无需也未修改M0275。GPL软件许可不能取代行情、派生曲线或研究数据的授权。

## 行情及派生结果

提供者为Binance，来自Binance Vision BTCUSDT现货原生4h历史归档。原12字段逐字节保留在既有本地raw快照；本公开包不附行情。源文件/官方CHECKSUM等指纹见[输入清单](specs/input-manifest-inherited.json)。

适用[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)以及固定版[Binance Vision Dataset Terms](https://github.com/binance/binance-public-data/blob/f446ce3812bd4e5521f21faecd4ae3c6460e49fc/TERMS_AND_CONDITIONS.md)，terms SHA256为dcf358e9d18f598a7a635fac80f6e643fa24a0e111a4d39bda47f1e246b31eb1。派生结果包含SMA比值、假设成交/费用/滑点、账户净值与抽样图线；这些变换不免除非商用、署名、相同方式共享和额外条款要求。

使用范围为已授权个人非生产研究。未授权商业使用、模型商业分发或实盘；数据许可合规需由接收方结合用途审查。私有Library保存不等于公共再分发授权，轻量公开候选也应维持上述归属与限制。

## 明确缺失的证明

未证明原作者历史运行环境、优化后参数、PIT、严格核心最终性、订单簿流动性、tick路径、全历史停市或样本外性能。双份历史归档校验相等并不自动补足这些证据。
