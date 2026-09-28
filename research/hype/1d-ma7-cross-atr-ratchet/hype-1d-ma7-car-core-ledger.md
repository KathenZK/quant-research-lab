# HYPE MA7 策略版本主账：V1 / V2 / V3

## 2026-09-24：固定入场ATR验证完成，保留原V3

保持其他规则与成本，完成HYPE原起点、45组邻域和18组固定入场双臂对照，再验证非HYPE的649币947连续段；原全市场动态ATR账户复用，仅新增固定版。原起点HYPE **544.76% → 537.60%**，回撤 **27.26% → 28.98%**，同18笔。共同起点463.60% → 585.08%的增益几乎来自6月28日单笔；剔除它，其余16笔457.66% → 456.51%。34/45邻域改善，但初始止损倍数四邻点全部变差。

649币最长段仅295改善，配对收益变化中位−0.87个百分点、回撤变化+0.34个百分点；完整2025至截止255币仅111改善，收益变化中位−1.50、回撤变化+0.81个百分点。不支持普遍替换，不登记V4。所有历史均已见；完整牛熊、资金费、身份、强平和流动性证据仍不足。

[完整结论](diagnostics/v3-fixed-atr-validation-results-20260924.md) · [交互报告与全部币](artifacts/v3_fixed_atr_validation_20260924/html/index.html) · [HYPE止损虚线](artifacts/v3_fixed_atr_validation_20260924/html/coins/HYPE.html) · [冻结契约](specs/v3-fixed-entry-atr-validation-20260924.md)。7项测试、新993个完整账户及36个单笔探针核验通过。浏览器安全策略拒绝自动访问本地HTML，离线交互、70条HYPE交易路径及649币22,611条配对展示检查通过。

## 2026-09-24：V3全参数消融与邻域检查（仅HYPE）

完成20项规则移除/替换、11个生效数值参数各五点、六组3×3和32个不同联合参数向量，去重后121配置；原V3+544.76%/27.26%/18笔精确复现。因ATR18自然就绪时间，实验统一2025-06-19空仓起点，基线+463.60%/27.26%/17笔，不能混用旧起点收益。

44个单参数邻点全部盈利，但MA6/7/8分别+64.11%/+463.60%/+101.27%，高收益平台不宽。斜率、初始ATR倍数、收紧步长和下限相对平缓；停滞3/4/5日较稳。32组同时扰动收益+23.51%至+90.46%，中位+64.96%、回撤中位37.54%。空单止盈几个阈值的差距被2026-07-17空单是否及时退出、能否接上8月9日多单所放大；最后多单仍为样本末估值。正式V3保持不变。

[完整中文报告](diagnostics/v3-parameter-stability-results-20260924.md) · [交互HTML：全部参数、账户及交易对照](artifacts/v3_parameter_stability_20260924/html/index.html) · [运行前契约及登记更正](specs/v3-parameter-stability-registry-correction-20260924.md)。121账户2,197笔、27,146条止损、2,577,338个权益点独立核验通过。初次登记的重复组合已留档并修正，不当作额外稳定性证据。仅已见HYPE样本内诊断，费用每边0.1%+滑点0.04%，资金费未完整核实；不登记V4。

## 2026-09-13：HYPE双触发一步收紧实验

按用户要求只验证HYPE：收盘反向超过MA7 0.2ATR，或最高/最低价连续4日不刷新，任一满足即把止损倍数直接降到0.5，次日生效，实际价格只收窄。保留当前V3自然就绪、原开仓、空单提前止盈和关闭反手；每边手续费0.1%、滑点0.04%。

相同起点下，当前V3为+544.76% / 回撤27.26% / 18笔；仅反向触发+76.64% / 32.28% / 21笔；仅停滞一步收紧+296.15% / 36.73% / 20笔；用户双触发为+71.17% / 31.79% / 22笔。双触发让3笔原亏单改善，也让6笔原赢家转亏，未替换原V3定义，不登记V4。

[最新HYPE四方案路径与触发原因](artifacts/v3_immediate_floor_20260913/html/coins/HYPE.html) · [全部结果与正反案例](diagnostics/v3-immediate-floor-results-20260913.md) · [固定规格](specs/v3-immediate-floor-20260913.md)。四账户81笔和798条止损独立核验通过；16项执行边界检查通过。本轮没有回测全市场。

## 当前执行修订：V3取消额外预热（2026-09-13）

用户明确要求去掉额外固定28天等待。**后续当前V3使用指标自然就绪：MA7、ATR14、RSI6、斜率有效后即可产生信号，次日开盘交易。** 原V3穿越、四日高低价停滞收紧、空单提前止盈、关闭反手均保留；不新增策略V4。下方三版原费用与原起点的历史成绩不覆盖。

新费用每边0.1%手续费、0.04%滑点下，取消额外等待的HYPE为**+544.76% / 最大回撤27.26% / 18笔**；从6月15日开始接受交易，新增6月18日开空。旧等待口径同新费用为+536.04% / 27.26% / 17笔，6月29日起交易。起点不同，共同旧起点结果在报告中另列。

[最新HYPE全部交易与ATR止损](../../asset-portfolios/1d-ma7-cross-atr-generalization/artifacts/v3_no_extra_warmup_20260913/html/coins/HYPE.html) · [执行修订规格](../../asset-portfolios/1d-ma7-cross-atr-generalization/specs/contract-v3-no-extra-warmup-20260913.md) · [全市场及核验](../../asset-portfolios/1d-ma7-cross-atr-generalization/diagnostics/v3-no-extra-warmup-results-20260913.md)。

2026-09-10按用户指定名称登记。**以后本策略的版本统一以本文件为准；R1—R4仅为旧研究轮次。** 家族：HYPE-1D-MA7-CAR。

## 版本总表

**三个版本都保留空单加速下跌＋RSI6超卖提前止盈，都关闭反手，都用原穿越当天斜率达标入场。**

| 版本 | 用于讨论的名称 | 收紧规则 | HYPE收益 | 最大回撤 | 交易数 |
| --- | --- | --- | ---: | ---: | ---: |
| **V1** | 基础移动止损 | ATR倍数固定1.5；止损价仍移动且只收窄 | **+360.02%** | **27.42%** | **15** |
| **V2** | 盈利停滞日收紧 | 只有当日同时持仓盈利且MA止损线无法继续收窄，才将ATR倍数减0.2，最低0.5 | **+449.61%** | **27.42%** | **15** |
| **V3** | 高低价4日停滞后持续收紧 | 连续4日未创新高/低启动，此后每天将ATR倍数减0.2，最低0.5 | **+548.65%** | **26.99%** | **17** |

统一测试时间：UTC **2025-06-29至2026-09-04，433天**。每次成交手续费0.05%＋不利滑点0.03%，每次约1倍权益名义仓位，初始10,000 USDT；**未计真实资金费率**。表中是已完成回测的历史结果，本次命名没有改策略或重跑收益。

## 2026-09-11：案例学习与动态过滤，正式三版不变

本轮跨市场研究新增标的状态过滤、穿越状态过滤和按条件选择退出，完成660币4,770账户。完整2025年初至2026-09-04的242币中，原V3同观察期63币盈利，标的过滤75币，联合过滤退出76币；尚未全市场盈利。保留所有成功、失败规则及误伤赢家，不按币登记最优版本。共享引擎v4只是代码版本，不是策略V4。

[本轮研究报告](../../asset-portfolios/1d-ma7-cross-atr-generalization/diagnostics/adaptation-learning-results-20260911.md) · [全部币与条件HTML](../../asset-portfolios/1d-ma7-cross-atr-generalization/artifacts/adaptation_20260911/html/index.html)。上方正式三版定义和原费用结果保持原样。

## 2026-09-10：新费用退出研究，正式版本不变

用户指定每边手续费0.1%、滑点0.04%后，跨市场家族重算V3并比较三套退出状态机；本页上方三版历史成绩仍保留原费用。相同433日HYPE的新费用V3为+536.04%、最大回撤27.26%、17笔；S1/S2为+177.10%/29.98%/19笔，S3为+107.90%/31.13%/21笔。新退出没有替换V3，也没有登记V4。

全市场346币同窗仍多数亏损；长历史账户已回放，但官方来源冲突使完整周期有效性尚未验证。[全市场完整报告](../../asset-portfolios/1d-ma7-cross-atr-generalization/diagnostics/exit-state-machine-results-20260910.md) · [新费用全交易HTML](../../asset-portfolios/1d-ma7-cross-atr-generalization/artifacts/state_machine_20260910/html_current/index.html)。

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

## 四项跨市场改动验证（实验，不改正式版本）

**结论更正：撤回空头优先建议。** 同窗346币的买持结果有320币亏损、中位−66.35%；本次多币比较没有排除共同市场下跌的影响，也不等于跨牛熊验证。方向选择、MA30和退出在其它行情中的优势仍未验证。 [更正说明](../../asset-portfolios/1d-ma7-cross-atr-generalization/diagnostics/regime-interpretation-correction-20260910.md)。

2026-09-10新增9个方案，全611可用币26,199账户计算完成，失败0，V1/V3复用旧结果。完整346币只做空161币盈利、中位−1.91%；MA30过滤105币盈利、中位−20.69%；风险预算0.5%中位−0.273%、回撤2.853%，简单小仓位中位−0.506%、回撤2.934%。刷新高低点后重新等待收紧整体更差，取消空单提前止盈没有一致优势。全部26,199账户及汇总均已独立核验通过，覆盖274,623笔交易、3,003,461条止损更新、1,096,989条入场机会记录和372,919,854个净值点。

仍没有全市场普遍盈利的证据。保持本主账V1/V2/V3定义，不自动合并部件、设立V4或改变生产状态。全部使用原433日主时间、费用和数据分组，真实资金费率和独立未看时间验证仍未完成。

[四问题HTML](../../asset-portfolios/1d-ma7-cross-atr-generalization/artifacts/analysis_four_tests_20260910/index.html) · [完整结果与每项规则](../../asset-portfolios/1d-ma7-cross-atr-generalization/diagnostics/four-tests-results-20260910.md)。

## 已做和未完成的事

已完成三个HYPE版本的历史回测和原结果复现，以及三个版本的全市场比较。2026-09-10只补跑V2的611个可用币，V1/V3直接复用原结果。完整433日346币中，V1/V2/V3分别80/83/93币赚钱，收益中位数−32.73%/−30.61%/−27.76%，最大回撤中位数62.26%/61.50%/59.21%；整体V3较好，但三版均未证明普遍有效。

[三版全市场交互比较](../../asset-portfolios/1d-ma7-cross-atr-generalization/artifacts/comparison_v123_20260910/index.html) · [三版完整报告](../../asset-portfolios/1d-ma7-cross-atr-generalization/diagnostics/v1-v2-v3-market-comparison-20260910.md)。原P1四方案没有V2的历史事实保留，不再作为当前尚未完成项。

真实资金费率、历史市场身份及未参与调参的新时间段验证仍未完成。这些名称用于研究与对话，未登记生产执行版本。

## 历史和登记

- [版本完整规格](specs/versions-v1-v3-20260910.md) · [版本映射和哈希](specs/version-map-20260910.json)
- [原R1—R4研究记录](diagnostics/research-rounds-through-r4-20260910.md) · [决策记录](decision-log.md)
- [原R3结果校验清单](artifacts/r3_price_progress_20260909/artifact_checksums.json) · [原始输入校验清单](artifacts/inputs_20260909/checksums.json)
