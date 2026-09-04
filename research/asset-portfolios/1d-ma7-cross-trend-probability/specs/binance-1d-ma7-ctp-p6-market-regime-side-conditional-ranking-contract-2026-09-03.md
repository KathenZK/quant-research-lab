# BIN-1D-MA7-CTP P6 市场环境 × 多空方向的条件排序价值审计合同

- Family：`Binance-1D-MA7-Cross-Trend-Probability`（`BIN-1D-MA7-CTP`）
- Experiment：`P6 Market-Regime x Side Conditional Ranking Value Audit`
- 中文名：`P6 市场环境 × 多空方向的条件排序价值审计`
- 日期：2026-09-03
- 状态：`explore / diagnostic-only / not promoted / not live-ready`
- 固定随机种子：`20260901`
- 合同锁状态：`FROZEN_BEFORE_P6_LABEL_METRIC_AND_2025_VALIDATION_REUSE`

## 1. 研究问题

P6 只回答三件事：

1. 不同市场环境、不同方向下，裸 MA7 穿越的成功率如何变化。
2. 在相同市场环境、相同方向，尤其同一天的机会之间，B0 是否能挑出更好的事件。
3. 一个很小的 `市场环境 × 方向 × B0 分数` 模型是否比只看市场环境更有价值。

解释必须拆开：

- 选对市场时段；
- 选对多空方向；
- 在相同机会条件下选对币。

前两项不能包装成第三项。`B0_WITHIN_REGIME` 是评价口径，不是新模型。

P6 是一次有停止条件的研究，不因为结果不好追加指标、修改标签、搜索模型或筛漂亮子样本。P6 受到已经观察到的 2025+ 结果启发，不是对这段历史的首次预注册。

## 2. 不可更改的事件、标签和成本

继承并固定：

- 市场：Binance USD-M USDT 永续。
- K 线：完整 UTC 日 K；P0 由 closed `15m` 聚合为 `1h`，再由 24 根连续 `1h` 聚合日 K。
- 事件：完整 UTC 日 K 收盘时发生严格 SMA7 方向穿越。
- 特征已知时点：`feature_known_at == entry_ts == ts + 1 day`，信号日结束后可知，下一 UTC open 作为入场参考。
- ATR 锚点：P0R/P4/P5 使用的 `atr_anchor`，来自事件日及以前；ATR 周期为 14。
- horizon：20 个有效交易日。
- 成功标签：从下一 UTC open 起，20 日内先顺向触及 `+2.0 * ATR14`。
- 失败标签：在成功前先逆向触及 `-1.0 * ATR14`。
- 同一小时双触：不利端优先。
- 成本：leverage `1.0x`；入场和退出均计手续费 `0.001` of filled notional per fill；入场和退出均计不利滑点 `0.0004` of filled notional per fill；使用真实 funding；`label_entry_net_return` 只作事件标签净收益诊断，不构造账户权益。
- 未完成 20 日未来路径必须排除。

禁止修改 MA 周期、屏障、horizon、ATR、成本、funding、事件定义，禁止把非穿越日加入模型。

## 3. 输入、历史证据和数据角色

允许读取：

- CATL P0R donor-only directional modeling panel；
- P4 factor group spec，用于复现 `R_B0_69` 的 69 字段身份；
- 修复后有效的 P5 artifacts，包括 pre-2025 OOF、2025+ validation predictions、summary、manifest 与独立验收；
- P0/P0R/P2/P3R/P4/P5 合同、报告、审计、脚本、测试和 manifest。

必须核验 P5 manifest 和列入文件 SHA256；不能仅凭报告或模型结构相同声称 B0 预测一致。

数据角色：

- 模型参数、预处理、校准和数值阈值只能用严格 pre-2025 样本拟合。
- 2025+ 标记为 `ITERATIVE_REUSED_VALIDATION_2025_PLUS`，可用于本轮冻结候选比较与研究决策，但不能称为盲测，不得据其结果临时增加候选、改阈值或改主指标。
- 若历史审计选择未来待确认方案，必须承认这属于开发过程，并另写 prospective OOS 协议。

HYPE 隔离：

- `HYPE/USDT:USDT` 不读行情、标签、结果，不进入训练、验证、校准、阈值、市场广度分子分母或预测，不自动 reveal。
- `HYPER/USDT:USDT` 正常保留。
- known TradFi 与主加密样本分开，不混入主结论。

## 4. 新 OOS 曝光审计

P6 不自动把 `2026-06` 以后称为新 OOS。必须先根据合同、运行日志、输入范围和已发表产物建立 exposure ledger：

- 已参与训练的日期和资产；
- 已被预测、汇总或用于研究选择的日期和资产；
- 确认未揭示的证据；
- 无法确认的历史段。

审计时先读元数据；不得为了判断是否未见而先打开候选新窗口价格走势、标签或收益。无法确认的历史段不得标为严格盲测。若没有合格未见历史，P6 只完成历史审计和前瞻确认协议，报告 `PENDING_FRESH_OOS` 或关闭条件，不创建定时任务。

任何新增或扩窗 OHLCV 必须走数据湖第 16 节的“查询 → 选版本 → 验证 → 读取 → 固定输入”，记录 `dataset_id`、manifest/fingerprint、UTC 截止、质量状态。新研究必须使用 `binance.perp.ohlcv.1d.from_15m.v1` 等 canonical trusted/derived 数据；不得把旧 family cache 或任意 parquet 当全市场标准数据。若迁移来源，必须先重叠对账事件键、OHLCV、69 个 B0 字段、ATR、小时 first-hit、funding 和 B0 预测；差异未解释前裁决数据迁移阻塞。

## 5. 固定市场状态

P6 固定主阈值：

- `BULL`：原始市场 MA30 广度 `>= 0.60`，且 BTC 收盘严格高于自身 SMA30。
- `BEAR`：原始市场 MA30 广度 `<= 0.40`，且 BTC 收盘严格低于自身 SMA30。
- `MIXED`：有效数据下其他情况，含 BTC 恰好等于 SMA30。
- `UNKNOWN`：BTC 或广度必要输入缺失。

P0R 市场字段是方向对齐字段，必须还原为原始状态：

```text
raw_breadth_ma30 = dir_market_breadth_ma30_p0r                      if side == long
raw_breadth_ma30 = 1 - dir_market_breadth_ma30_p0r                  if side == short
raw_btc_price_side_ma30 = dir_btc_price_side_ma30                   if side == long
raw_btc_price_side_ma30 = -dir_btc_price_side_ma30                  if side == short
```

必须测试同一 UTC 日 long/short 还原出的原始市场状态一致。完整报告六格：

- `BULL × LONG`
- `BULL × SHORT`
- `MIXED × LONG`
- `MIXED × SHORT`
- `BEAR × LONG`
- `BEAR × SHORT`

`UNKNOWN` 单独报告，不并入 `MIXED`。`35/65` 和 `45/55` 只做预登记稳健性诊断，不参与晋级或择优。

## 6. 候选对象

只允许三个对象：

### `R_B0_69`

修复后有效 P5 的 B0 参考。P6 必须核验 69 字段身份、P5 manifest 与 B0 OOF/validation prediction 文件哈希。`B0_WITHIN_REGIME` 仅为分层评价。

### `M0_MARKET_ONLY`

只输入六格编码，回答市场环境和方向本身解释多少成功率变化。不得输入资产自身价格结构、B0 分数、资产身份或结果变量。

### `M1_B0_X_SIDE_X_REGIME`

只输入：

- B0 raw probability 的 logit，裁剪到 `[1e-6, 1 - 1e-6]` 后转换；
- 六格编码，一个参考格加五个哑变量；
- B0 logit 与五个哑变量的交互项。

模型固定为 `LogisticRegression(penalty="l2", C=1.0, solver="lbfgs", max_iter=1000, random_state=20260901)`。B0 logit 使用训练折 `StandardScaler` 标准化；M0/M1 的缺失/UNKNOWN 规则在运行前固定；不得加入原始 69 字段、RSI、周线、BTC 其他指标或 LightGBM。

如果格内交互只对 B0 做正向单调变换，它改变的是校准或跨格优先级，不是格内选币排序；报告中必须说明。

## 7. 二层模型防泄漏

M1 训练所用 B0 分数必须来自时间前向、样本外的第一层预测：

- 外层沿用 D1/D2/D3；
- 外层训练范围内再做年份前向 inner OOF B0；
- inner train 的 `label_end_ts_20d` 必须早于 inner validation 起点；
- 不足以形成 inner train 的早期样本作为 warm-up 排除；
- 2025+ M1 训练只能使用 pre-2025 D1-D3 B0 OOF 分数，预测使用 P5 final B0 validation raw 分数。

必须输出外层、内层、warm-up 样本数、最大标签结束时间和 B0 score provenance。禁止随机交叉验证。

## 8. 四种评价口径

`Top1/Top5/Top10` 均为前 `1%/5%/10%`，不是每天选 1/5/10 个币。

### A. 年度全局排名后分格

在每个自然年全体事件中取 Top1/5/10，再合并并展示这些事件在六格中的表现。必须标记为“年度全局排名后分格”，不是每格内部 Top。

### B. 真正格内排序

在每个 `year × side × market_state` 内单独排名，报告 Top1/5/10、Bottom5、基础成功率和 uplift。六格全部展示，不筛好看的格。

### C. 同日同方向选币主检验

同一 UTC 事件日、同一方向内评价 B0 和 M1 的排序。主口径为日内前 5%：

- 至少 20 个合格事件才纳入；
- 入选数为 `ceil(0.05 × 当日同方向事件数)`；
- 不足 20 个的日期单列覆盖；
- 并列用冻结的 outcome-blind 规则：score 降序、`asset` 升序、`ts` 升序、`side` 升序。

每个模型建立同日、同方向、相同入选数量的 `MARKET_ONLY` 随机选择期望基准：该日所有合格事件等概率入选，以当日同方向基础成功率和事件净收益均值计算期望。不能用 M0 任意排序打破并列。主指标是日内 Top5 相对同日同方向基准的成功率增量和事件标签净收益增量，同时报告六格分解和同日横截面 AUC；单一标签日期 AUC 为 N/A。

### D. 历史冻结阈值

用 pre-2025 前向 OOF raw 分数冻结 95 分位阈值，应用到后续数据，报告覆盖率、成功率和事件标签净收益。年度 Top5 是回顾性排名，不得冒充当时已知全年阈值。P6 默认不使用概率校准；若后续启用，阈值与待测概率必须在同一最终映射空间。

## 9. 指标、统计和裁决

报告训练、严格 OOF、2025、2026 和合格新 OOS（若无则写无），包括事件数、资产数、事件日数、28 日块数、基础成功率、AUC、PR-AUC、Top1/5/10、uplift、覆盖率、事件标签净收益均值/中位数/5%尾部、Brier、LogLoss、校准、long/short、六格、seen/new assets、月度、日期块、资产贡献集中度、20 日 non-overlap。

统计使用按日历时间共同抽取的 28 日块 paired bootstrap，2,000 次，固定种子，保留抽样记录。同一抽样块内保留当日跨资产关联，所有候选共用抽样。每次在完整重采样集合上重算指标，不以块 AUC/Top5 先算后平均替代。已冻结阈值不在重采样中重拟合。主比较和六格结论都做多重比较控制。

研究投入门槛：同日同方向 Top5 成功率相对基准点估计至少 +5pp，且事件标签净收益及相对基准增量为正，不由单月/少数资产/重复事件支撑，并在声明适用方向和环境中稳定。它是研究预算门槛，不是盈利保证。

允许裁决：

- `DATA_OR_IMPLEMENTATION_AUDIT_FAILED`
- `NO_STABLE_EXTRA_COIN_SELECTION_VALUE`
- `MARKET_OR_SIDE_VALUE_ONLY`
- `LOCAL_CONDITIONAL_VALUE_NEEDS_FRESH_OOS`
- `FRESH_OOS_CONFIRMED_CONDITIONAL_VALUE`
- `INSUFFICIENT_POWER_OR_SAMPLE`
- `PENDING_FRESH_OOS`

这些是 P6 实验裁决，不替代仓库正式状态词；即使确认条件价值，也不等于策略通过或可实盘。

## 10. 输出

P6 产物统一前缀 `binance_1d_ma7_ctp_p6_`，至少包含合同、机器可读配置、contract lock、exposure ledger、data audit、B0 reproduction audit、fold/inner-stage metrics、predictions、market state metrics、selection metrics、paired bootstrap stats、concentration/non-overlap diagnostics、summary、manifest、中文报告和 prospective OOS protocol。不得生成策略、权益、Sharpe、live spec、runner handoff、交易路径 HTML 或 HYPE reveal。
