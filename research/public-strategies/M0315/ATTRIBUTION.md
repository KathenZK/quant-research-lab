# 来源与许可

原策略：Masoud Azizi（@mablue）的 [UniversalMACD.py](https://github.com/freqtrade/freqtrade-strategies/blob/f3340ce11f5bdf62f598522e64d1f5638eaa13f5/user_data/strategies/UniversalMACD.py)，固定提交 f3340ce11f5bdf62f598522e64d1f5638eaa13f5。原库 GNU GPL-3.0 许可证全文在 [LICENSE](LICENSE)。本地信号实现保留原数学表达及默认值；执行派生自仓库 M0293 的已审端口，父源码哈希见[复用清单](specs/execution-reuse.json)。本目录派生代码按 GPL-3.0 提供。

数据来源：Binance 官方公开数据仓库，13 份 BTCUSDT 现货原生 5m 月档（2023-12..2024-12）。数据许可为 CC BY-NC-SA-4.0 并受 [Binance Dataset Terms](https://github.com/binance/binance-public-data/blob/f446ce3812bd4e5521f21faecd4ae3c6460e49fc/TERMS_AND_CONDITIONS.md) 约束。用户已授权个人非生产研究。原始行情仅保存在私有恢复目录，未入 Git。

本次转换：校验官方压缩档及十二字段、规范时间字段、计算 EMA 比率、模拟已冻结账户、汇总指标并采样日净值。衍生数据沿用相关非商业及署名／相同方式共享条件。本地成果不构成额外外传、公开部署或商业使用授权；root 负责展示集成与远端保存。
