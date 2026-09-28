# BIN-1D-CATL-P0 Dataset and Label Atlas 冻结合同

- Family：`Binance-1D-Cross-Asset-Trend-Lifecycle`
- Alias：`BIN-1D-CATL`
- 实验：`P0 Dataset and Label Atlas`
- 日期：2026-08-31
- 主状态：`explore / diagnostic-only / not promoted / not live-ready`
- 裁决集合：`DATASET_READY_FOR_MODELING_RESEARCH`、`BLOCKED_DATA_ACCESS`、`DATASET_INTEGRITY_FAILED`

## 研究边界

本轮只回答：能否构造一个无泄漏、跨资产可比较、能够支持后续“值得入场”和“值得继续持有”学习的 Binance 全市场日频数据集。

本轮禁止事项：

- 不训练 LightGBM、ExtraTrees、神经网络或任何机器学习模型。
- 不选择概率阈值，不搜索 MA 参数，不生成交易策略或组合回测。
- 不比较最终账户收益，不报告 AUC、feature importance、Sharpe、最优参数、最优均线、最优持有期。
- 不读取、不使用 HYPEUSDT `2026-05-31 00:00 UTC` 及之后的 K 线、funding、标签、交易路径或验证结果。
- 不修改 HYPE P0-P8、exact V7.1 或任何 HYPE 后 81 日 holdout 产物。

## 数据范围

- 市场：Binance USD-M USDT 永续合约。
- 资产集合：历史点位真实存在的合约；保留下架合约历史，避免只用当前存活币种。
- 源数据：优先使用数据湖 normalized Binance perp `15m` closed K，由四根完整 `15m` 聚合为闭合 `1h`，再由 24 根连续 `1h` 聚合完整 UTC 日 K。
- 截断：所有资产物理截断到 `2026-05-31 00:00 UTC`，最后可用特征日为 `2026-05-30`。
- 特征时点：日线收盘后形成，最早下一 UTC 日开盘成交。
- 标签路径：first-hit 先后只使用真实重聚合 `1h` 路径，不用日 K 高低价猜测。

## 资产资格冻结

P0 不按未来标签筛选资产。每个资产日保留：

- 上市年龄、过去 30 日 quote volume、完整日标记、过去 30 日完整率、缺口数量。
- `tradable_marker_p0`：`complete_day=true`、上市年龄不少于 60 日、过去 30 日完整率不低于 `0.95`、过去 30 日 quote volume 为有限正数。
- 横截面环境特征只在当日 `tradable_marker_p0=true` 的 point-in-time universe 内计算。

## 输出表

### Asset-Day Feature Panel

每个资产、每个完整 UTC 日一行。只允许保存 `ts` 收盘前已知字段，至少包含：

- 身份与时点：`asset`、`ts`、`feature_known_at`、`next_entry_ts`。
- 数据质量：`complete_day`、`hours_in_day`、`hours_with_4x15m`、`listing_age_days`、`quote_volume_30d`、`tradable_marker_p0`。
- 因果特征：多周期收益/路径、MA7/14/30/60、波动与 K 线质量、成交量与 funding、全市场环境、预注册探针。

### Directional Landmark Panel

每个资产日生成 long/short 两行，描述“如果下一 UTC open 沿该方向暴露，未来路径会怎样”。未来字段必须以 `label_`、`future_` 或 `outcome_` 前缀命名。

至少包含：

- `asset`、`ts`、`side`、`entry_ts`、`entry_ref`、`atr_anchor`。
- 方向化特征、future path 完整性、first-hit 原语、MFE/MAE、终点收益、成本后假设收益、观察终点、calendar month/quarter。

## 因果特征块

固定构建以下块，不在 P0 中筛选赢家：

- 多周期收益与路径：`1/3/7/14/30/60d` 收益、近期高低点/回撤、`30/60d` 区间位置、ATR 距离、ER、连续涨跌、冲击/修复/横盘/扩张状态。
- MA 体系：`MA7/14/30/60` 的价格距离、`1/3/5d` 斜率、斜率变化/加速度、上下方、最近穿越方向、距穿越天数、`7/14d` 穿越次数、MA 排列与快慢一致性。
- 波动与 K 线质量：`ATR7/14/30`、ATR 占比、波动率比例、压缩/扩张、实体/上下影线/ATR、收盘位置、大幅穿越程度。
- 成交与衍生品：成交量相对 `7/30d`、成交量变化、funding 当前值/均值/变化；OI 若无可靠历史点位数据则不加入。
- 全市场环境：BTC `7/30d` 趋势、MA7/MA30 breadth、上涨比例、横截面离散度、相对 BTC 强弱、相对市场中位数强弱、流动性横截面排名。

## First-Hit 原语与主标签

每个 asset-day-side 从下一 UTC open 开始，用 `1h` 路径计算：

- 有利屏障：`+0.5/+1.0/+1.5/+2.0/+3.0 ATR`。
- 不利屏障：`-0.5/-0.75/-1.0/-1.5/-2.0 ATR`。
- 观察期：`3/5/7/14/20/30d`；原语保存 `30d` 内首次触及小时，短 horizon 标签由原语截断复原。
- 同一根 `1h` 同时触及有利和不利屏障时，保守主标签按不利先触发，同时保存有利先触发敏感性字段并统计模糊比例。

Primary Entry-Value Label：

```text
下一 UTC open 进入；未来 20 日内先达到顺向 +2 ATR，且此前没有触及反向 -1 ATR。
```

Primary Continuation-Value Label：

```text
下一 UTC open 继续暴露；未来 5 日内先增加顺向 +1 ATR，而不是先发生反向 -0.75 ATR。
```

成本模型固定：

- leverage `1.0x`
- 每次 fill 手续费 `0.001`
- 每次 fill 不利滑点 `4 bps`
- 入场、退出均计成本
- 使用真实 funding；每个 landmark 独立计算，不复利，不构成策略账户

## 预注册诊断探针

只统计标签分布，不形成规则：

- 全部资产日
- raw MA7/MA14/MA30/MA60 cross
- 20 日价格区间突破
- 位于 MA7 同侧但当天未穿越
- 位于 MA30 同侧但当天未穿越
- MA7 与 MA30 方向一致
- MA7 刚穿越但 MA30 方向相反
- 高/中/低波动状态
- long/short 分开统计

## 重叠样本与独立性

报告必须声明：

- 行数不等于独立样本数，20 日标签相邻日期高度重叠。
- 保存 `label_start_ts`、`label_end_ts`、calendar month/quarter。
- 报告 `1/3/5/10d` 标签自相关、asset × calendar-month/quarter 数量、严格非重叠 20 日 landmark 敏感性。
- 后续模型必须使用时间切分、purge 和 embargo，禁止随机拆分。

## P0 验证要求

脚本和测试至少验证：

- UTC 日 K 恰好 24 根 `1h`，`1h` 由四根闭合连续 `15m` 聚合。
- next-open 执行时序；ATR 锚点只来自评估日及以前。
- first-hit 先后正确；同小时冲突不利优先；long/short 方向对称。
- 标签矩阵可由首次触及时间原语复原；特征无未来字段。
- 横截面特征只使用当日 point-in-time universe。
- HYPE cutoff 正确、`holdout_read=false`、不存在 validation artifact。
- artifact 哈希一致；HTML 自包含、不依赖互联网且有交互功能。

## 交付物

- 家族 `README.md`、core ledger、decision log。
- P0 冻结合同、可复现脚本。
- 分区 Parquet：Asset-Day Feature Panel、Directional Landmark Panel。
- 标签定义和字段字典、数据质量报告、标签分布诊断报告。
- 数据/脚本/合同哈希 manifest。
- 标签质量检查 HTML 与针对性测试。
