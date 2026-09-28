# HYPE MA7 策略版本主账：V1 / V2 / V3

2026-09-10按用户指定名称登记。**以后本策略的版本统一以本文件为准；R1—R4仅为旧研究轮次。** 家族：HYPE-1D-MA7-CAR。

## 版本总表

**三个版本都保留空单加速下跌＋RSI6超卖提前止盈，都关闭反手，都用原穿越当天斜率达标入场。**

| 版本 | 用于讨论的名称 | 收紧规则 | HYPE收益 | 最大回撤 | 交易数 |
| --- | --- | --- | ---: | ---: | ---: |
| **V1** | 基础移动止损 | ATR倍数固定1.5；止损价仍移动且只收窄 | **+360.02%** | **27.42%** | **15** |
| **V2** | 盈利停滞日收紧 | 只有当日同时持仓盈利且MA止损线无法继续收窄，才将ATR倍数减0.2，最低0.5 | **+449.61%** | **27.42%** | **15** |
| **V3** | 高低价4日停滞后持续收紧 | 连续4日未创新高/低启动，此后每天将ATR倍数减0.2，最低0.5 | **+548.65%** | **26.99%** | **17** |

统一测试时间：UTC **2025-06-29至2026-09-04，433天**。每次成交手续费0.05%＋不利滑点0.03%，每次约1倍权益名义仓位，初始10,000 USDT；**未计真实资金费率**。表中是已完成回测的历史结果，本次命名没有改策略或重跑收益。

## 容易混淆的地方

- **V1不是固定价格止损**：固定的是1.5这个ATR倍数，止损线依然随MA7/ATR变化单向移动。
- **V2不是连续4天不创新高低**：它每天检查浮盈和MA止损线是否停滞；不满足就暂停减倍数。
- **V3使用日K最高价/最低价，不用收盘价**。首个完整持仓日初始化，之后连续4日未严格刷新才启动；不要求盈利。启动后即使再次刷新高低价，也继续每日收紧。
- V3的高低价用于决定何时收紧，实际止损仍以MA7±倍数×ATR14计算；0.5 ATR不是现价到止损的距离保证。
- 穿越后等待2/3天、收盘价收紧、减速补充入场仍是实验。它们不是上述三个版本，后续讨论必须另写清楚实验名称；没有自动设立V4。

## 完整规则和交易路径

三个版本共同使用SMA7、Wilder ATR14/RSI6、方向斜率严格超过0.05 ATR/日；日收盘确认，次日开盘执行。空单提前止盈的完整条件、止损更新及状态重置见[正式版本规格](specs/versions-v1-v3-20260910.md)。

| 版本 | 全部交易路径 | 已保存逐笔账本 | 规则及结果原编号（仅用于追溯） |
| --- | --- | --- | --- |
| V1 | [V1：15笔](artifacts/r3_trade_paths_20260909/hype-ma7-r3-trade-paths.html#B1_r1_fixed) | [交易](artifacts/r3_price_progress_20260909/runs/B1_r1_fixed/full/trades.csv) · [汇总](artifacts/r3_price_progress_20260909/runs/B1_r1_fixed/full/summary.json) | R1关闭反手；R3/B1_r1_fixed；全市场F0 |
| V2 | [V2：15笔](artifacts/r3_trade_paths_20260909/hype-ma7-r3-trade-paths.html#B0_r2_stall) | [交易](artifacts/r3_price_progress_20260909/runs/B0_r2_stall/full/trades.csv) · [汇总](artifacts/r3_price_progress_20260909/runs/B0_r2_stall/full/summary.json) | R2仅盈利停滞日收紧；R3/B0_r2_stall |
| V3 | [V3：17笔](artifacts/r3_trade_paths_20260909/hype-ma7-r3-trade-paths.html#P4_ma) | [交易](artifacts/r3_price_progress_20260909/runs/P4_ma/full/trades.csv) · [汇总](artifacts/r3_price_progress_20260909/runs/P4_ma/full/summary.json) | R3/P4_ma；R4/H4_ma；全市场H4_D0 |

原HTML保留历史编号；上表深链接会直接选中对应方案。正式对话名称始终用V1/V2/V3，旧编号仅查证时使用。准确配置、结果与来源哈希见[机器可读版本映射](specs/version-map-20260910.json)。

## 已做和未完成的事

已完成这三个HYPE版本的历史回测和原结果复现。V3已用固定规则检验全市场：完整433日346币中93币赚钱、中位收益−27.76%、最大回撤中位数59.21%，因此V3不是已经证明通用的策略。[全市场报告](../../asset-portfolios/1d-ma7-cross-atr-generalization/diagnostics/results-p1-20260909.md)。V2没有被列入那一轮全市场四方案，不能把其结果套用给V2。

真实资金费率、历史市场身份及未参与调参的新时间段验证仍未完成。这些名称用于研究与对话，未登记生产执行版本。

## 历史和登记

- [版本完整规格](specs/versions-v1-v3-20260910.md) · [版本映射和哈希](specs/version-map-20260910.json)
- [原R1—R4研究记录](diagnostics/research-rounds-through-r4-20260910.md) · [决策记录](decision-log.md)
- [原R3结果校验清单](artifacts/r3_price_progress_20260909/artifact_checksums.json) · [原始输入校验清单](artifacts/inputs_20260909/checksums.json)
