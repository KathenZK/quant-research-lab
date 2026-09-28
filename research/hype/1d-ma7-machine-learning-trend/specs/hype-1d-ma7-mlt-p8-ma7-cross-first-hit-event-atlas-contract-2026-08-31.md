# HYPE 1D MA7 MLT P8：MA7 Cross First-Hit Event Atlas 合同

> 2026-08-31 冻结。状态：`explore / diagnostic-only / not promoted / not live-ready`。本轮不训练机器学习模型，不优化交易参数，不读取 HYPE 后 81 日，不修改 P0-P7，也不修改 `HYPE-1D-MA7-ABT-V7.1`。

## 1. 研究问题

P8 只回答基础现象：前一日收盘位于 `SMA7` 一侧、当日收盘 raw cross 到另一侧后，未来是否更容易形成一段可交易同向趋势；并检查该现象是否跨 `HYPEUSDT`、`BTCUSDT`、`ETHUSDT`、`BNBUSDT`、`SOLUSDT` 成立。

本轮不做：

- 不训练 ML / LightGBM / ExtraTrees；
- 不搜索屏障、观察期、分箱或交易阈值；
- 不使用 V7.1 入场过滤、退出规则或任何 P7 survival 结论生成事件；
- 不读取、画图、统计或使用 HYPE `2026-05-31` 至 `2026-08-20` reused holdout；
- 不登记策略版本，不 promotion，不交接 runner。

## 2. 数据与边界

- 市场：Binance USD-M perpetual。
- 资产：`HYPEUSDT`、`BTCUSDT`、`ETHUSDT`、`BNBUSDT`、`SOLUSDT`。
- K 线：可信闭合 `1h`，聚合为完整 UTC `1d`；每个 UTC 日必须恰好 24 根闭合小时 K。
- HYPE 特征日严格为 `2025-05-31` 至 `2026-05-30`，训练终点开盘 `2026-05-31 00:00 UTC`；manifest 必须记录 `holdout_read=false`。
- BTC/ETH/BNB/SOL 复用 P7 已冻结两年闭合 `1h` artifacts，同样物理截断 `2026-05-31 00:00 UTC`，不得读取之后数据。
- `SMA7`、`ATR7`、RSI、ER、成交量状态和分箱只能使用穿越日收盘及以前数据。
- raw cross 信号在穿越日 UTC 收盘后形成，最早下一 UTC 开盘成交。

## 3. Raw MA7 Cross 事件

`SMA7[t] = mean(close[t-6:t])`。多头 raw cross：

```text
close[t-1] <= SMA7[t-1]
close[t]   >  SMA7[t]
```

空头 raw cross：

```text
close[t-1] >= SMA7[t-1]
close[t]   <  SMA7[t]
```

每一次 raw cross 都保留；同一震荡区间的反复穿越不删除。另生成 14 日内同资产同方向只保留第一笔的去重敏感性视图，但它不能替代完整事件表。

## 4. First-Hit 标签

ATR 锚点固定为穿越日收盘已知的 `ATR7[t]`。从下一 UTC 开盘开始观察真实 `1h` 高低价路径。屏障以入场参考价为原点，方向化计算：

- 有利屏障：`+1.0 / +1.5 / +2.0 / +3.0 ATR`
- 不利屏障：`-0.5 / -1.0 / -1.5 / -2.0 ATR`
- 观察期：`7 / 14 / 21 / 30` 日

完整保存 `4 × 4 × 4 = 64` 组结果。Primary label 冻结为：

```text
有利 +2.0 ATR；不利 -1.0 ATR；观察期 14 日
```

Primary success：14 日内先达到 `+2 ATR`，且在此之前没有触及 `-1 ATR`。Primary failure：先触及 `-1 ATR`，或 14 日结束仍未达到 `+2 ATR`。

若同一根 `1h` 同时触及有利与不利屏障，主结果采用保守的“不利先触发”；另保留“有利先触发”敏感性列。报告模糊事件数量和占比。不得用日 K 高低价推断同日屏障先后。

## 5. 事件收益与路径指标

每个事件独立计算，不复利、不组合。入场为下一 UTC open。若 first-hit 触发，退出参考价为触发屏障；若未触发，退出为观察期最后一根 `1h` close。净收益使用固定 `1.0x`、入场和退出均计费、手续费 `0.001`、每次 fill 不利滑点 `4 bps`、真实 funding。多空方向对称。

每个事件至少保存：

- 未来 `7/14/21/30` 日 MFE/ATR、MAE/ATR；
- MFE/MAE 首次发生小时；
- primary first-hit 结果与耗时；
- terminal direction return 与成本后净收益；
- 到达 `+1/+1.5/+2/+3 ATR` 所需小时；
- 从最大 MFE 回吐幅度；
- 最长连续同向日数；
- 方向效率；
- 是否出现反向 MA7 cross。

## 6. 因果状态字段

至少保存以下穿越日已知字段：

- MA7 几何：`side`、`ma7`、`atr7`、`aligned_ma_gap_atr`、`pre_cross_gap_atr`、`cross_jump_atr`、`aligned_slope1_atr`、`aligned_slope2_atr_per_day`、`aligned_slope3_atr_per_day`、`aligned_slope_acceleration`、`initial_cross_gap_atr`；
- 穿越前路径：`aligned_return_1d`、`aligned_return_3d`、`aligned_return_7d`、`aligned_return_14d`、`prior_opposite_run`、`same_side_ratio3`、`same_side_ratio7`、`cross_count7`、`cross_count14`；
- K 线和趋势质量：`aligned_body_atr`、`aligned_close_location`、`range_atr`、`aligned_rsi6`、`er7`、`atr_pct`、30 日区间位置、距 30 日方向极值 ATR 距离、7/30 日波动率比例、最近 3 日成交量变化。

未来 MFE、MAE、趋势 episode、未来斜率或未来收益不得进入状态字段。

## 7. 预注册分箱

- 方向化 MA7 一日斜率：`<=0`、`(0,0.03]`、`(0.03,0.06]`、`(0.06,0.10]`、`>0.10`
- `cross_jump_atr`：`<=0.10`、`(0.10,0.25]`、`(0.25,0.50]`、`>0.50`
- 穿越前反侧持续：`1日`、`2-3日`、`4-7日`、`>=8日`
- 最近 14 日穿越次数：`1次`、`2次`、`3次`、`>=4次`
- RSI6：`<30`、`30-45`、`45-55`、`55-70`、`>70`
- ER7：`<0.2`、`0.2-0.4`、`0.4-0.6`、`0.6-0.8`、`>0.8`
- 波动率：每个资产内只用事件以前 `atr_pct` 历史计算因果分位，分为 `low / mid / high`。

二维矩阵固定为：MA7斜率 × 穿越幅度、MA7斜率 × 反侧持续、MA7斜率 × 最近3日方向收益、MA7斜率 × 14日穿越次数、MA7斜率 × 波动率、MA7斜率 × RSI6、方向 × MA7斜率、资产 × 方向、资产 × MA7斜率、穿越幅度 × 反侧持续。`n<30` 的格子标记 `INSUFFICIENT_SAMPLE`。

## 8. 匹配基准与独立性

Baseline A 为全部 raw MA7 cross。Baseline B 为同资产、同方向、同季度、同波动率 regime、同 MA7 斜率档且当日没有 raw cross 的 MA7 同侧日期。Baseline C 为同资产、同季度、同波动率 regime 下由过去 7 日收益符号给出同方向的简单动量日期。Baseline D 为同资产、同方向、同季度、同波动率 regime 的随机非穿越日期。固定随机种子 `20260831`，每个 cross 目标匹配至少 5 个 control，缺额必须记录。

比较 primary first-hit 成功率、MFE/MAE、净收益、达标速度，并使用 asset × raw-cross episode cluster bootstrap 报告 95% 置信区间。另报告按资产聚类、raw-cross episode 聚类、日历时间块聚类、14 日去重敏感性、多头/空头 bootstrap。

## 9. 裁决规则

`MA7_CROSS_OCCURRENCE_SUPPORTED` 需要同时满足：primary first-hit 相对匹配非穿越基准有正提升；cluster bootstrap 95% 下界大于 0；至少 3 个供体资产提升方向一致；HYPE 前 365 日提升方向一致。若只有单侧成立，必须限定为单侧现象。

`MA7_CROSS_NO_INCREMENTAL_EDGE` 适用于：raw cross 不优于匹配非穿越基准；优势可被简单 7 日动量解释；跨资产方向不稳定；14 日去重后优势消失；或扣除成本后净期望不为正。

`INSUFFICIENT_SAMPLE` 适用于：独立 cluster 不足、置信区间过宽、HYPE 训练期事件不足或关键方向/资产样本不足。

即使现象被支持，也只表示值得进入下一轮机器学习筛选；不登记版本、不 promotion。
