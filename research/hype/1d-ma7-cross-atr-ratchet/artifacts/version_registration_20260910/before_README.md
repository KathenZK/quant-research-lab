# HYPE 日线 MA7 穿越与 ATR 单向移动止损

- 独立家族：`HYPE-1D-MA7-Cross-ATR-Ratchet` / `HYPE-1D-MA7-CAR`。
- 本次用户规则：日收盘穿越 SMA7 + 斜率过滤；1.5 ATR14 止损只收窄；止损前5日出现有效反向穿越可以反手；盈利空单在加速下跌且 RSI6 超卖时退出。
- 当前：R4，`explore / diagnostic-only / not promoted / not live-ready`。R1的32组、R2的28组、R3的14组及R4的9组已完成；全历史资金费率完整性及独立历史身份未通过，结果不称完整净收益。
- **R4收盘价比较已完成9组、27区间结果、36压力及全部169笔路径。收盘价1天未刷新即收紧：+151.72%、回撤32.60%、21笔，明显弱于旧高低价4天；收盘价3天：+505.72%、回撤25.92%、19笔，少赚一些、回撤小一点。** 同期2025-06-29—2026-09-04，单边手续费0.05%＋滑点0.03%，未计资金费率。[完整报告与169笔全表](diagnostics/r4-close-progress-backtest-20260909.md) · [全部9组交易图](artifacts/r4_trade_paths_20260909/hype-ma7-r4-trade-paths.html) · [收盘价3天路径](artifacts/r4_trade_paths_20260909/hype-ma7-r4-trade-paths.html#C3_ma) · [规则](specs/r4-close-progress-20260909.md)
- **R3已按日K最高/最低价实际改策略并检查全部交易。4日不刷新后永久每天减0.2、最低0.5、仍用MA止损，关闭反手：+548.65%，回撤26.99%，17笔；全部14组312条交易均已画图。** 2025-06-29—2026-09-04，手续费0.05%＋滑点0.03%/次，未计资金费率。[R3完整报告与17笔全表](diagnostics/r3-global-backtest-20260909.md) · [直接看P4_ma全交易图](artifacts/r3_trade_paths_20260909/hype-ma7-r3-trade-paths.html#P4_ma) · [全部14组](artifacts/r3_price_progress_20260909/all_results.csv) · [规则](specs/r3-price-progress-20260909.md)
- **R2结果：减速放宽入口变差；保留原入口、仅盈利停滞日收紧0.2ATR，反手开+411.48%/回撤34.89%，反手关+449.61%/回撤27.42%。全段最大回撤没有下降。** 同期2025-06-29—2026-09-04，单边手续费0.05%＋滑点0.03%，未计资金费率。[R2报告](diagnostics/r2-slowdown-tightening-20260909.md) · [R2规则](specs/r2-slowdown-tightening-20260909.md) · [8组日K交易路径对照](artifacts/r2_trade_paths_20260909/hype-ma7-r2-trade-paths.html) · [R2全84行](artifacts/r2_slowdown_tightening_20260909/all_results.csv)
- [报告](diagnostics/backtest-20260909.md) · [主账](hype-1d-ma7-car-core-ledger.md) · [规则](specs/contract-20260909.md) · [决策记录](decision-log.md)
- [图表与逐笔交易](artifacts/results_20260909/charts.html) · [全32组×3窗口](artifacts/results_20260909/all_results.csv) · [输入检查](artifacts/inputs_20260909/data_audit.json)
- [日K交易路径：可拖动、缩放与逐笔定位](artifacts/trade_paths_20260909/hype-ma7-trade-paths.html) · [主方案总览图](artifacts/trade_paths_20260909/primary-trade-paths.png) · [关闭反手总览图](artifacts/trade_paths_20260909/no_reverse_accel1-trade-paths.png) · [画图说明](diagnostics/trade-paths-20260909.md)

本家族不继承 HYPE-1D-MA7-ABT、MLT、SNC02、V7.1 的参数、版本或结论。数据和代码均保存于本目录；本次没有运行生产交易。

用户指出只改止损方案的#1/#4/#9不符合“不再创新高/低后加速收紧”的预期，已逐日核对：[停滞定义与三笔说明](diagnostics/r2-stall-definition-case-review-20260909.md)。随后R3已完成全局修订回测；R2原结果保留。更积极的2日＋极值保护也完整展示：+106.24%、回撤33.83%，没有因个别提前退出就被称为更好。
