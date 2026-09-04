# BIN-1D-MA7-CTP P7 时间漂移、分数单调性与概率校准归因审计合同

- Family：`Binance-1D-MA7-Cross-Trend-Probability`（`BIN-1D-MA7-CTP`）
- Experiment：`P7 Temporal Drift, Score Monotonicity and Calibration Decomposition`
- 中文名：`P7 时间漂移、分数单调性与概率校准归因审计`
- 日期：2026-09-04
- 主状态：`explore`
- 结论边界：`diagnostic-only / not promoted / not live-ready`
- 合同锁状态：`FROZEN_BEFORE_P7_DECOMPOSITION_OUTPUT_READ`
- 随机种子：`20260901`

## 1. 研究性质与问题

P7 是已揭示历史结果的归因诊断，不是假装新盲测。2025+ 固定标记为 `ITERATIVE_REUSED_DIAGNOSTIC_2025_PLUS`，不得称为 strict OOS、blind holdout、untouched validation、prospective validation 或 final confirmation。

唯一研究对象是 P4/P5/P6 保留下来的完整 69 特征逻辑回归模型 `R_B0_69`。本轮不训练新候选模型，不新增因子，不删除特征，不搜索阈值，不改标签、不改事件、不改执行时序。

P7 只回答：

1. 同一个冻结模型和冻结 raw 阈值为什么在 2025 基本没有筛选价值，在 2026 明显更好。
2. 差异来自输入特征分布变化，还是特征与结果关系变化。
3. 差异来自排序能力，还是概率校准失效。
4. 2026 是否由少数月份、资产、同日市场行情或重叠事件支撑。
5. B0 是单币穿越机会选择器，还是主要识别全市场日期、方向或状态。
6. B0 应继续作为高概率趋势选择器，还是降级为低质量事件风险过滤器。
7. P8 应走唯一哪条分支，或停止历史调参。

## 2. 冻结事件、标签与成本

原始任务不变：完整 UTC 日线收盘后发生严格方向性 SMA7 穿越时，用当时已知信息为事件打分，预测下一 UTC 开盘进入后，未来 20 日内是否沿穿越方向先触及 `+2 ATR`，而不是先触及 `-1 ATR`。

继承并固定：

- 市场：Binance USD-M USDT 永续。
- K 线：完整 UTC 日 K。
- 事件：严格 SMA7 方向穿越。
- 特征已知时点：`feature_known_at == entry_ts == ts + 1 day`。
- 入场参考：下一根 UTC 日线开盘价。
- horizon：20 日。
- ATR：`ATR14`，使用冻结 `atr_anchor`。
- 成功：顺向 `+2.0 * ATR14` first-hit。
- 失败：逆向 `-1.0 * ATR14` first-hit 或未先成功。
- 同小时双触：adverse-first。
- 成本：leverage `1.0x`；入场/退出每次 fill 手续费 `0.001`；入场/退出每次 fill 不利滑点 `0.0004`；真实 funding；`label_entry_net_return` 仅为事件标签净收益。

P7 不生成策略仓位、账户权益、年化收益、Sharpe、交易路径 HTML、live spec 或 runner 改动。

## 3. 输入与样本角色

优先复用冻结产物，不下载数据、不访问网络、不重新读取原始数据湖。允许读取：

- CATL P0R donor directional modeling panel 与 manifest；
- P4 factor group spec；
- P5 OOF predictions、2025+ validation predictions、calibration、model card、summary、manifest、independent acceptance；
- P6 predictions、summary、data audit、manifest、contract/report；P6 没有单独 modeling audit，本轮 input inventory 必须记录缺口；
- P0R/P1/P2/P3R/P4/P5/P6 合同、报告、审计和关键 JSON。

样本角色：

- 完整 pre-2025 开发事件：约 `52,563`，用于特征分布参考、预处理重建、固定分箱边界，不把训练期拟合概率冒充 OOF。
- 严格 development OOF：约 `42,649`，用于 development 排序、校准、分数分箱和阈值基准。
- 2025+ reused diagnostic：`46,892` 主加密事件，其中 2025 `32,111`、2026 `14,781`。
- Known TradFi：约 100 条，不进入主结论，可记录缺失说明。

HYPE 隔离：`HYPE/USDT:USDT` 不读分区、不进临时 DataFrame、不训练、不统计、不校准、不画图；所有 P7 输入、预测和指标中 HYPE 行数必须为 0。`HYPER/USDT:USDT` 必须保留。

## 4. B0 重建与锚点

允许确定性重建 `R_B0_69`，目的仅为恢复冻结预处理参数、模型系数和线性贡献：

- 使用原有 D1/D2/D3 与 final pre-2025 训练范围。
- 使用 P4 冻结 69 特征、P2/P5 预处理：训练折数值中位数填充、训练折类别 one-hot、训练折 `StandardScaler`。
- 使用 `LogisticRegression(penalty='l2', solver='lbfgs', max_iter=1000, random_state=20260901)`。
- 不使用 2025+ 修改任何参数。
- 每折 OOF 和 final 2025+ raw score 必须与 P5/P6 冻结预测逐行一致，最大绝对误差 `<= 1e-8`。

必须复现锚点：2025+ `46,892`；2025 `32,111`；2026 `14,781`；HYPE `0`；HYPER 存在；TradFi 主统计 `0`；raw 阈值 `0.510070`；2025 阈值以上约 `839`、成功率约 `33.1347%`、净均值约 `-0.5073%`；2026 阈值以上约 `511`、成功率约 `41.6830%`、净均值约 `+1.9480%`。关键对齐失败则全局 verdict 为 `DATA_OR_REPRODUCTION_FAILURE` 并停止解释。

## 5. 固定分析口径

固定 raw 阈值：`0.510070`，来自 development OOF raw score 95 分位；它是选择阈值，不等于真实成功概率 51.007%。

固定主分箱边界只从 development OOF raw score 计算：

`0-10, 10-20, 20-30, 30-40, 40-50, 50-60, 60-70, 70-80, 80-90, 90-95, 95-97.5, 97.5-99, 99-100`。

同一套边界应用到 development OOF、2025、2026。年度内相对分位数仅可作为 `RETROSPECTIVE_WITHIN_YEAR_RELATIVE_BINNING` 辅助解释，不形成新阈值。

资产历史年龄和流动性分组边界只能从 pre-2025 开发数据计算。P6 six-grid 仅为诊断分层，不作为 P7 新预测特征。

## 6. 分析、统计与图表

必须输出：

- raw score 分布漂移：描述统计、阈值覆盖率、KS、Wasserstein、PSI、缺失率，按样本、方向、six-grid、seen/new、年龄、流动性、月份、28 日块。
- 69 个冻结特征漂移：逐特征均值/分位、SMD、KS、Wasserstein、PSI、缺失变化、异常比例、类别频率，BH 校正；按 P4 因子组汇总。
- 固定分数箱单调性：成功率、事件标签净收益、正收益率、置信区间、long/short、资产/月集中度、Spearman、相邻倒挂、最高尾部 vs 80-90。
- 校准：raw probability、P5 forward Platt calibrated probability、constant base-rate probability 的 Brier、Brier skill、calibration intercept/slope、ECE、reliability/resolution/uncertainty、reliability table。
- 2025/2026 结构分解：对阈值以上成功率和净均值做对称 Kitagawa/Oaxaca composition / within-cell / residual 分解，cell 固定为 side、P6 six-grid、seen/new、年龄组、流动性组、月份、28 日块。
- 集中度与依赖性：asset、date、month、28 日 block、side、six-grid、episode cluster、seen/new、年龄组、流动性组；leave-one-out、BTC/ETH 排除、long-only、short-only、non-overlap、episode 去重、date-side 聚合。
- 线性贡献漂移：用真实线性模型系数精确还原 logit，按 P4 因子组聚合贡献并比较 2025/2026、阈值以上、成功/失败、方向、six-grid。
- 标签和经济分解：阈值以上事件的成功/失败/timeout、first-hit 天数、事件收益、成本/funding 可用性、long/short 和 six-grid。

统计使用共享 28 日 calendar block bootstrap：`2,000` 次，seed `20260901`，同一 block 保留所有资产/方向/事件，paired comparison 共用 replicate。每个 replicate 完整重建样本和指标，不对月均值二次抽样。69 特征漂移和预注册交互检验分别做 BH 校正。

正式报告至少引用 10 张静态图：score 分布、固定箱成功率、固定箱净收益、raw reliability、calibrated reliability、69 特征漂移热图、因子组贡献漂移、composition/within 分解、月度阈值表现、集中度图。图表保存到 `artifacts/`，不生成交易路径 HTML。

## 7. Verdict 与 P8 路由

全局 verdict 只能是：

- `DATA_OR_REPRODUCTION_FAILURE`
- `RANKING_STABLE_CALIBRATION_DRIFT`
- `REGIME_CONDITIONAL_SIGNAL`
- `FEATURE_OR_UNIVERSE_SHIFT`
- `TAIL_NONMONOTONIC_OVERCONFIDENCE`
- `UNEXPLAINED_TEMPORAL_INSTABILITY`

无论 verdict 为何，状态保持 `explore / diagnostic-only / not promoted / not live-ready`。

P8 只能推荐一个主要分支：

- A：有限前向校准研究；
- B：date-side opportunity 模型；
- C：预定义资产历史和流动性分层；
- D：B0 降级为风险否决器；
- E：停止历史优化，进入冻结观察。

若 P7 发现最高分尾部不稳定、2025/2026 关系差异无法形成可重复解释，或结果被少数时间块支配，应优先停止历史调参，不得继续在已看历史上扩因子救结果。

## 8. 输出与停止条件

所有 P7 产物使用 `binance_1d_ma7_ctp_p7_` 前缀。contract lock 后的科学变更必须另留版本、原因和影响范围，不能覆盖合同假装事前约定。

停止条件：

- P5/P6 锚点或逐行分数对齐失败；
- HYPE 出现在任一输入/输出；
- 2025+ 被错误标成 blind/OOS；
- 生成策略、权益、Sharpe、live/runner 产物；
- manifest 自引用或正式产物 hash 不一致。
