# BIN-4H-MA7-RC P0 冻结合同（2026-09-02）

- 家族：`Binance-4H-MA7-Regime-Continuation`（`BIN-4H-MA7-RC`）
- 阶段：`P0`，无条件延续性事件研究和机制 kill test；不是策略版本，不登记 `V1`。
- 状态：`explore / diagnostic-only / not promoted / not live-ready`
- 冻结时间：`2026-09-02T08:30:00Z`
- 配置：[../configs/binance-4h-ma7-regime-continuation-p0.json](../configs/binance-4h-ma7-regime-continuation-p0.json)
- 配置 SHA256：`eb62108271cf1d22992fb53c0c1a7438d605581d96cb079d75b0579143c84642`
- 输入 manifest：[../artifacts/binance_4h_ma7_rc_p0_dataset_manifest_2026-09-02.json](../artifacts/binance_4h_ma7_rc_p0_dataset_manifest_2026-09-02.json)
- 输入 manifest SHA256：`c11074a7a064db42c0a53214e0756f106388c14e683376bc0fcdfb56d94ffd7e`

修订记录：`P0R1` 配置 SHA256 `afdac0134562709dd52b1951c4b91f1d36e185028db3f0a328e18d4f2997da0d` 在读取 MA7 事件/收益 outcome 前被作废。原因是首次运行在 funding 审计阶段发现同一名义资金费时间存在毫秒级 archive offset；`P0R2` 在读取 outcome 前冻结 `date_trunc('second', ts)` 的名义 funding 时间归一，并按源优先级去重。

## 身份边界

本线是全新的 `4h` 独立家族，不是 [`Binance-1D-MA7-Regime-Continuation`](../../1d-ma7-regime-continuation/README.md) 的新版本；不继承 [`HYPE-4H-MA7-Asymmetric-Body-Trend`](../../../hype/4h-ma7-asymmetric-body-trend/README.md) 的参数、收益或结论；不继承 [`Binance-4H-EMA-Cross-LightGBM-Event-Selector`](../../4h-ema-cross-lightgbm-event-selector/README.md) 的 EMA 信号、LightGBM 模型、阈值或结论。`4h SMA7` 只覆盖约 28 小时，不等于日线 `SMA7`；`4h SMA42` 只能作为七日等时钟对照，不得替代或择优淘汰主研究对象。

P0 禁止搜索 MA 长度、入场过滤、止盈、止损、持仓期限、杠杆、仓位或模型参数；禁止 LightGBM、神经网络和其他 ML。P0 只回答：无条件严格穿越后是否存在趋势延续。

## 数据与截止

- 市场：Binance USD-M、USDT perpetual、24/7 UTC。
- 输入：normalized `1h` OHLCV 与 normalized funding rates。
- OHLCV 路径：`data/normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h/` 下的 `date=*`、`source=binance_vision_daily_gap_repair`、`source=binance_fapi_freeze_gap`、`source=binance_fapi_prospective_oos` 分区。
- Funding 路径：`data/normalized/funding_rates/exchange=binance/market_type=perp/` 下的 `date=*` 与 `source=binance_vision_monthly/month=*` 分区。
- Funding 时间：先将 funding `ts` 归一到秒级名义时间，再按 `symbol × nominal_ts` 和冻结源优先级去重；这是为处理 archive 中同一名义时点的毫秒级偏移，不改变资金费日程。
- `audit_as_of`：`2026-09-02T08:30:00Z`。
- 数据截止：`cutoff_exclusive_utc = 2026-08-24T08:00:00Z`。
- 最后一根允许使用的闭合 `1h`：`2026-08-24T07:00:00Z`。
- 最后一根允许使用的完整 `4h`：`2026-08-24T04:00:00Z`。
- 冻结截止之后的数据不得进入本次 P0；之后产生的数据自动成为未来 prospective OOS 候选。

## 4H 聚合

所有 `4h` 都从真实闭合 `1h` 重聚合，不读取已有 `4h` K 线，不插值伪造偏移相位。主相位为 UTC `00:00/04:00/08:00/12:00/16:00/20:00`；相位检查另聚合 `1h/2h/3h` 偏移。

聚合公式：`open=first`、`high=max`、`low=min`、`close=last`，`volume/quote_volume/trade_count/taker_buy_volume/taker_buy_quote_volume=sum`。每根可用 `4h` 必须由恰好四根连续、闭合、OHLC 合法的 `1h` 组成；任一组成 K 缺失、重复、未闭合或 OHLC 非法时，该 `4h` 不得进入研究，并写入审计。

## PIT 币池

币池为 point-in-time 动态全市场池，不使用今天的静态 Top100/Top120 回填历史。

- 合约在事件时点存在且由完整 `4h` 序列支持。
- 上市龄至少 `30` 自然日。
- 30 日 trailing ADV：事件日之前 30 个 UTC 日 `quote_volume` 的均值，必须 `>= 10,000,000 USDT`。
- 30 日覆盖率：事件日之前 30 个 UTC 日完整 `4h` bar 数除以 `30 * 6`，必须 `>= 95%`。
- 每个时点最多保留 PIT trailing ADV 前 `120` 个，排序使用降序 ADV 与确定性 symbol tie-breaker。
- 排除冻结清单中的 stable/fiat、指数与美股样 underlyings；该显式清单来自较新的全市场 MA7 研究口径，因为旧 15m EMAX inventory CSV 在当前 checkout 中不存在。

## 指标与事件

`SMA_N[t] = mean(close[t-N+1:t])`，固定计算 `SMA5/SMA7/SMA10/SMA42`，主指标只看 `SMA7`。`TR[t] = max(high[t]-low[t], abs(high[t]-close[t-1]), abs(low[t]-close[t-1]))`，`ATR20[t] = mean(TR[t-19:t])`。所有指标只使用已闭合 `4h`。

主事件：

```text
long_cross[t]:  close[t-1] <= SMA7[t-1] and close[t] > SMA7[t]
short_cross[t]: close[t-1] >= SMA7[t-1] and close[t] < SMA7[t]
```

相等值归在穿越前一侧，严格穿越后才触发。同一资产每次严格穿越都保留。事件信号时间为 `4h` bar `t` 的收盘，最早可执行价格为下一根 `4h` 的真实 `open[t+1]`，禁止用信号 bar 收盘成交。

## Outcome

执行起点为 `open[t+1]`。障碍缩放固定为 `ATR20[t-1]`，禁止使用未来 ATR 或触发后的波动率。

主 first-hit 标签：long 有利障碍 `entry + 2.0 * ATR_scale`，long 不利障碍 `entry - 1.0 * ATR_scale`；short 有利障碍 `entry - 2.0 * ATR_scale`，short 不利障碍 `entry + 1.0 * ATR_scale`；最大观察期为未来 `30` 根 `4h`。标签为 `favorable_first`、`adverse_first`、`neither`、`incomplete_future`。未来不足 `30` 根完整 `4h` 的事件标为 `incomplete_future`，不得进入主标签统计。

first-hit 顺序优先使用未来真实 `1h` high/low。若同一根 `1h` 同时触及有利与不利障碍，按不利障碍先触发，并统计歧义事件数。P0 不把 first-hit 障碍当成真实止盈止损策略；它只是趋势是否发生的路径标签。

固定期限收益使用未来 `1/3/6/12/18/30` 根 `4h`，假定在对应期限结束后的可执行边界 `open` 平仓。方向对齐收益为 `side * (future_price / entry_price - 1)`，其中 long `side=+1`，short `side=-1`。同时计算 gross、fee+4bps、fee+8bps、funding、full net、MFE、MAE、MFE/MAE 发生时间、首次反穿 SMA7 所需 bar、同侧存活 bar、截尾均值、中位数、胜率、右尾贡献、top 1%/5% 事件贡献和 first-hit 成功率置信区间。

## 成本与 Funding

Binance 默认手续费 `0.001` / fill；基准不利滑点 `4 bps/fill`；压力滑点 `8 bps/fill`；round-trip 包含开仓和平仓两次成本。Funding 按真实事件时间和方向在 `(entry_ts, exit_ts]` 内累计：long 支付正 funding，short 收取正 funding。缺失 funding 不得填 0 后声称净收益完成；若 funding 无法完整获得，结构性 gross diagnostic 可继续，但所有净收益和可交易性结论标为 `BLOCKED_FUNDING`。

## 对照与分组

同侧非穿越基准使用确定性分层加权，不随机抽单点：同 symbol、同 calendar year、同 side、同截至 `t-1` 因果 ATR 百分位五档；信号时点 close 已在对应 SMA 一侧，当根没有同方向严格穿越。非穿越样本按 `symbol × year × side × ATR quintile` 加权，使分层权重与穿越事件一致。

固定对照：`SMA5`、`SMA10` 邻域 strict cross；`SMA42` 七日等时钟 strict cross；phase `0h/1h/2h/3h`。对照不得替代主 `SMA7`，相位表现只作证据强度披露，不作为独立 promotion 硬门禁。

报告必须至少按 long/short、calendar year、symbol、PIT ADV quintile、PIT ADV top20/其余资产、phase、MA5/7/10/42、基准成本/8bps 压力、全样本/leave-one-symbol-out、最近 `1d/7d/1m/3m/6m/1y` 分组。集中度必须报告最大单币、top5 币、最大单年、top 1%/5% 事件贡献，以及去掉 BTC、ETH、最大贡献币、最大贡献年份后的结果。

## 统计与裁决

统计推断处理同币事件和相邻时间事件相关性：报告 symbol 与 UTC 周双向聚类标准误，且按 symbol 与自然周成块做 bootstrap 置信区间。随机种子固定为 `20260902`，bootstrap `1000` 次。first-hit 成功率相对同侧非穿越基准、固定期限收益增量均报告置信区间。对多方向、多期限和多个 MA 对照使用 BH-FDR，同时报告原始 p 值与 q 值。

P0 分别裁决 long 与 short，不设置合并通过。允许裁决：`SUPPORTED_WEAK_CONTINUATION`、`PARTIAL_STRUCTURAL_SEPARATION`、`NO-GO`。`SUPPORTED_WEAK_CONTINUATION` 必须同时满足：MA7 主 first-hit 成功率高于同侧非穿越基准、差值 95% block-bootstrap CI 下界大于 0、BH-FDR 后仍支持、30-bar 可执行 full net 方向收益大于 0、至少四个完整 calendar year 净方向收益为正、结果不由单币/单年/top1% 决定、8bps 压力未完全穿越成本墙、MA5/MA10 邻域没有完全相反机制结论。

无论 P0 裁决如何，家族状态保持 `explore / diagnostic-only / not promoted / not live-ready`；P0 通过也不登记版本、不写 runner、不进入账户组合回测，只决定是否值得进入 P1 突破前状态地图。
