# 数据与回测基础设施只读审计

日期：2026-09-08。仓库：`/Users/ZK/OpenCode/quant-strategy-lab`。

结论：数据与执行基础设施确实造成过虚假收益和无效结论，是重要原因；但不能解释全部失败，也不能据此证明技术指标中低频策略整体无效。目前价格底座已经显著改善，主要缺口转向历史可交易身份、持仓资金费用、研究脚本到正式结果的贯通，以及独立验证不足。继续全市场补数据或扩建大平台不应成为找不到策略的新替代目标。

本次只读查看规范、现有研究报告、当前源码及少量真实汇总 JSON，运行已有定向测试和不写文件的内存反例。未下载/修复行情、改策略、重训练或重回测。所有下文文件路径均相对仓库根。除本临时审计交付文件外未新增文件；测试工具可能使用其正常临时缓存。

## 一、十条证据与解释边界

### 1. 错误空头收益公式曾把负收益包装成极强 OOS

`BIN-1H-CSLGBM` 原 OOS `+221.84%`、回撤 `6.09%` 已作废。错误使用 `entry/exit - 1`，修正为线性永续正确公式 `1 - exit/entry` 后，保持原模型分数、选币与仓位，OOS 变为 **-37.04%**。污染也涉及 prefit 组合搜索和规则基线。

- 证据：[research/asset-portfolios/1h-cross-sectional-lightgbm-selector/diagnostics/binance-1h-cslgbm-v1-oos-2026-07-17.md:7-15](../../../asset-portfolios/1h-cross-sectional-lightgbm-selector/diagnostics/binance-1h-cslgbm-v1-oos-2026-07-17.md)，以及 `:27`、`:35-54`。
- 当前共享公式已正确：[src/strategy_lab/data/linear_contract_returns.py:9-28](../../../../src/strategy_lab/data/linear_contract_returns.py)；本次对应测试通过。
- 已证实影响：原 CSLGBM 的错误空头标签用于 portfolio search、前沿选择、prefit/OOS、规则基线和压力测试；不能从这次修复推断其他家族全部修复或全部受影响。
- 含义：这是工程事故，但纠错后的负收益又是真实模型/组合问题。报告 `:47-60` 还明确长短腿都亏、低分不等于适合做空、强制 Top/Bottom 与 squeeze 尾部风险未被标签控制。

### 2. 月频 Top10 的收益至今没有获得可执行性背书

旧引擎允许同 bar 成交、零成交占位 K 入选、不可成交退出、持仓缺价 `.fillna(0)`。原路径 **41 个 blocker**；改为 `00:15` 可成交重选仍 **15 个**。

- 证据：[research/asset-portfolios/1d-monthly-cs-momentum-long10/diagnostics/binance-1d-mcsm-long10-liveability-audit-2026-08-20.md:58-86](../../../asset-portfolios/1d-monthly-cs-momentum-long10/diagnostics/binance-1d-mcsm-long10-liveability-audit-2026-08-20.md)。
- 本次读取的真实汇总 JSON：[research/asset-portfolios/1d-monthly-cs-momentum-long10/artifacts/binance-1d-mcsm-long10-target12-execution-timing-2026-08-20-summary.json:198-207](../../../asset-portfolios/1d-monthly-cs-momentum-long10/artifacts/binance-1d-mcsm-long10-target12-execution-timing-2026-08-20-summary.json)，仍为 `PERFORMANCE_INVALIDATED / performance_valid=false`；`:203-204` 为 41/15 计数。
- 当前主账：[research/asset-portfolios/1d-monthly-cs-momentum-long10/binance-1d-mcsm-l10-core-ledger.md:15-16](../../../asset-portfolios/1d-monthly-cs-momentum-long10/binance-1d-mcsm-l10-core-ledger.md) 保留 blocker。
- 含义：不能拿旧 CAGR 决定投钱，也不能把旧引擎调风控后未达门槛当成已经严格否定动量机制。必须先有真实持仓生命周期账。

### 3. 部分全市场研究实际只读到 6 个长期资产

4H MA7 P0 共 5,947 个原生事件、6 symbols；主账明确旧 normalized 1h 是 `PARTIAL_SCOPE_LEGACY`，全市场 P0R 正式收益尚未写出。

- 证据：[research/asset-portfolios/4h-ma7-regime-continuation/binance-4h-ma7-rc-core-ledger.md:12-16](../../../asset-portfolios/4h-ma7-regime-continuation/binance-4h-ma7-rc-core-ledger.md)、`:29-38`。
- 含义：这里的 NO-GO 是六资产样本结论，不是全市场技术指标检验已经失败。家族名称/原计划不能替代实际输入范围。

### 4. 4H 研究存在人为不可达的最高支持门槛

代码只取 **2023–2025 三个完整年**，但 `SUPPORTED_WEAK_CONTINUATION` 要求 **正年度 ≥4**。

- 精确源码：[research/asset-portfolios/4h-ma7-regime-continuation/scripts/research_binance_4h_ma7_regime_continuation_p0.py:1451-1452](../../../asset-portfolios/4h-ma7-regime-continuation/scripts/research_binance_4h_ma7_regime_continuation_p0.py) 只取三个年；`:1468-1476` 定义 supported，其中 `:1473` 要求 `positive_complete_years >= 4`。
- 另一个确证统计问题：同脚本 `:1236` 写 bootstrap `p_value`，`:1237` 随后展开 `**cluster`，其同名值会覆盖前者；cluster 返回 p_value 见 `:1056-1060`。置信区间和 p/q 因此可能来自不同推断口径。
- 已有验收承认仍未修复：[research/asset-portfolios/4h-ma7-regime-continuation/diagnostics/binance-4h-ma7-regime-continuation-p0r-gap-guard-2026-09-03.md:65-67](../../../asset-portfolios/4h-ma7-regime-continuation/diagnostics/binance-4h-ma7-regime-continuation-p0r-gap-guard-2026-09-03.md)。
- 边界：它仍可能获得 PARTIAL；同脚本 `:1478-1496` 有独立 partial 路径，不能说所有结果必然 NO-GO。严格说，四正年问题为当前源码的确定性逻辑审查，没有额外运行裁决函数或真实策略。

### 5. helper 测试通过和正式研究贯通之间仍有缺口

P0R-DATA 仍调用旧 `P0.enrich_outcomes`、原 first-hit/horizon/yearly/phase 等汇总，而非统一 gap-aware 正式汇总链。

- 正式消费者：[research/asset-portfolios/4h-ma7-regime-continuation/scripts/research_binance_4h_ma7_regime_continuation_p0r_data.py:756-780](../../../asset-portfolios/4h-ma7-regime-continuation/scripts/research_binance_4h_ma7_regime_continuation_p0r_data.py)；`:761`、`:766` 使用 P0.enrich_outcomes，`:773-781` 使用旧各汇总函数。
- helper 当前问题一：[research/asset-portfolios/4h-ma7-regime-continuation/scripts/binance_4h_ma7_rc_gap_guard.py:127-131](../../../asset-portfolios/4h-ma7-regime-continuation/scripts/binance_4h_ma7_rc_gap_guard.py) 先排序再检验单调，因此原始乱序输入被接受，本次已用内存反例复现。
- helper 当前问题二：同文件 `:333-341` 提前反穿就返回 `complete`，后续计划窗口缺口未检查，本次已用内存反例复现。按原 full-planned-window 保守验收要求，后续缺口应使 primary survival 无效；提前观察到反穿可保留诊断。该规则属于此家族特定契约，不自动推广为所有 first-passage survival 方法的通用定理。
- 已有报告 [research/asset-portfolios/4h-ma7-regime-continuation/diagnostics/binance-4h-ma7-regime-continuation-p0r-gap-guard-2026-09-03.md:44-46](../../../asset-portfolios/4h-ma7-regime-continuation/diagnostics/binance-4h-ma7-regime-continuation-p0r-gap-guard-2026-09-03.md) 明确盘点仅为候选/连续性/窗口，不是收益或显著性。
- 含义：88 个测试通过不构成真实研究通过；需验收实际输出链、反例和契约，而非只数测试数量。

### 6. 共享因子库仍有跨币串算缺陷，但未证明污染既有家族

`RelativeStrengthFactor` 标记 `cross_sectional=True`，引擎因此跳过按 symbol 分组，compute 却直接整列 `pct_change()`。

- 因子：[src/strategy_lab/data/factors/cross_sectional.py:18-32](../../../../src/strategy_lab/data/factors/cross_sectional.py)，其中 `:26` 为标记，`:30-31` 为整列变化率。
- 引擎：[src/strategy_lab/data/factors/engine.py:24-33](../../../../src/strategy_lab/data/factors/engine.py)，其中 `:24` 决定是否按 symbol 分组。
- 本次内存反例：A 价格 `[100,110]`，B `[1000,1100]`，benchmark 不变；B 第一行得到 **+809.09%**，本应缺乏历史而为 NaN。
- 消费者范围：本次 `rg` 搜索发现 provider 注册、公共导出和 [tests/test_factors.py:174-181](../../../../tests/test_factors.py) 单序列测试；未证明现有策略家族实际通过这条公共函数构建面板。研究脚本中同名 relative_strength 字段也有自行按侧/市场中位数等计算的独立实现，不能只凭词同名归因。故这是当前复用风险，不能直接归因历史全部亏损。

### 7. 现在不能笼统说价格数据全部坏，近期治理已完成有价值的底座

9 月 7 日最近验收记录：V3 有 **61,577,807 根 15m / 874 历史代码**，配套高周期由完整 15m 桶聚合；10 个已发布数据集内容指纹与 manifest 一致。规范明确不填 K、不跨缺口拼接。

- 最近验收：[research/platform/data-lake-governance/diagnostics/data-lake-structure-readiness-cleanup-audit-2026-09-07.md:5-7](../../data-lake-governance/diagnostics/data-lake-structure-readiness-cleanup-audit-2026-09-07.md)、`:34-46`。
- 当前实际分段代码：[src/strategy_lab/data/research_inputs.py:76-102](../../../../src/strategy_lab/data/research_inputs.py)；`:82` 将零成交/非法价格标为无效，`:100-102` 按缺口与身份边界分段。
- 限制：截止固定在 9 月 5 日；874 不代表 874 个币或当前可交易标的；仍有 12 个边界、1,024 网格空位、5,163,158 原生零成交记录，见结构审计 `:63`。
- 核查边界：本次未重新做全湖内容指纹认证或远端全历史认证；这里引用的是最新现有验收记录。

### 8. 资金事件质量 PASS 不等于持仓资金成本完整，历史 PIT 仍未完备

资金 v2 有 2,654,430 事件，但历史频率证据仅覆盖 **585 标的的 639 个部分片段**，不是这些币全历史均可用。API-only 九月尾部、股票特殊结算等仍不能无条件净收益回测。

- 证据：[docs/data-lake-spec.md:584-590](../../../../docs/data-lake-spec.md)；[research/platform/data-lake-governance/diagnostics/data-lake-structure-readiness-cleanup-audit-2026-09-07.md:52-67](../../data-lake-governance/diagnostics/data-lake-structure-readiness-cleanup-audit-2026-09-07.md)。
- 新 bundle 已区分价格诊断与净收益研究，本次 funding/bundle 单元测试通过；旧消费者迁移仍 partial，最近验收记录 6 处未登记消费者：[research/platform/data-lake-governance/diagnostics/binance-research-bundle-v2-startup-2026-09-07.md:21-36](../../data-lake-governance/diagnostics/binance-research-bundle-v2-startup-2026-09-07.md)。本次没有重新运行全仓 consumer scan，不把这个最近验收数称为现场最新全仓计数。
- 含义：修补应围绕拟测试策略真正需要的标的/窗口，不必先追求 874 代码全历史完美。

### 9. 缓存/旧源不能自动跟随新数据升级，这是复现债务

旧日线 cache 的输入 manifest 和参数 hash 为 `LINEAGE_INCOMPLETE`；无法无损补出当时信息，用今天 hash 回填会伪造 lineage。

- 规范：[docs/data-lake-spec.md:390-398](../../../../docs/data-lake-spec.md)。
- legacy 1h quote-volume 有 18 个实质差异小时，来源修订、语义不同、错误取首 15m 分量及 proxy 都出现；独立重聚的 derived 4h 通过预定容差：[research/platform/data-lake-governance/diagnostics/binance-ohlcv-volume-rca-r3-2026-09-03.md:31-44](../../data-lake-governance/diagnostics/binance-ohlcv-volume-rca-r3-2026-09-03.md)、`:69-73`。
- 含义：新研究锁新 bundle，旧复现锁旧输入；不能说旧数据都错，也不要静默拿新源重算旧结果后称精确复现。

### 10. 传统期货部分停在数据/执行证据不足，不能等同技术指标彻底失败

黄金仍为 `raw_unaccepted`，roll/adjustment、日历未核验；多资产固定 12M 在两个代理表面较稳定，但未具备逐合约映射、换月和成本账本。

- 黄金：[research/gold/1d-multi-speed-tsmom/gold-1d-ms-tsmom-core-ledger.md:14-17](../../../gold/1d-multi-speed-tsmom/gold-1d-ms-tsmom-core-ledger.md)。
- 多资产期货：[research/asset-portfolios/1d-tradfi-futures-tsmom/tf-1d-fut-tsmom-core-ledger.md:43-62](../../../asset-portfolios/1d-tradfi-futures-tsmom/tf-1d-fut-tsmom-core-ledger.md)。
- 12M 连续代码表面 Sharpe 0.618，长期代理 0.666；属于可有限验证的方向证据，不能作为有效净收益或实盘可用证明。

## 二、实际运行的测试命令与完整输出

工作目录为仓库根，命令：

```sh
uv run pytest -q tests/test_linear_contract_returns.py tests/test_funding_v2.py tests/test_research_bundle.py tests/test_binance_4h_ma7_regime_continuation_p0r_gap_guard.py
```

实际输出全文：

```text
........................................................................ [ 81%]
................                                                         [100%]
88 passed in 2.19s
```

执行退出码 0。这是四个指定文件的现有定向回归；未运行全套测试，也不是全湖或策略真实性验证。上述反例缺陷与 88 项绿灯同时存在。

## 三、最小反例一：跨币串算（实际运行脚本和输出）

命令：

```sh
uv run python - <<'PY'
import pandas as pd
from strategy_lab.data.factors.cross_sectional import RelativeStrengthFactor
from strategy_lab.data.factors.engine import compute_factor_frame
f = pd.DataFrame({'symbol':['A','A','B','B'],'ts':pd.to_datetime(['2026-01-01','2026-01-02','2026-01-01','2026-01-02'], utc=True),'close':[100.,110.,1000.,1100.],'benchmark_close':[100.,100.,100.,100.]})
print(compute_factor_frame(f, RelativeStrengthFactor(periods=1)).to_string(index=False))
PY
```

实际输出全文：

```text
                       ts symbol  relative_strength_1
2026-01-01 00:00:00+00:00      A                  NaN
2026-01-02 00:00:00+00:00      A             0.100000
2026-01-01 00:00:00+00:00      B             8.090909
2026-01-02 00:00:00+00:00      B             0.100000
```

退出码 0。B 首行使用 A 前一行 110 作为分母，即 `1000/110 - 1 = 8.090909`，构成确定性跨币污染。由于未证明既有家族消费此函数，不给任何具体策略追加 PERFORMANCE_INVALIDATED 裁决。

## 四、最小反例二：原始乱序被接受、提前反穿跳过后续缺口（实际运行）

命令：

```sh
uv run python - <<'PY'
import importlib.util
import numpy as np
import pandas as pd
from pathlib import Path
p=Path('research/asset-portfolios/4h-ma7-regime-continuation/scripts/binance_4h_ma7_rc_gap_guard.py')
spec=importlib.util.spec_from_file_location('gap_audit',p)
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
t=pd.date_range('2026-01-01',periods=4,freq='4h',tz='UTC')
f=pd.DataFrame({'symbol':['A']*3,'ts':[t[1],t[0],t[2]]})
r=m.validate_time_grid(f,step=pd.Timedelta(hours=4),name='synthetic',phase_hour=0)
print('Nonmonotonic accepted:',len(r)==3)
ns=np.array([t[i].value for i in [0,1,3]],dtype='int64')
r=m.recross_survival_on_grid(signal_bar_ns=int(t[0].value),side=1,fourh_ts=ns,close=np.array([2.,0.,2.]),sma7=np.array([1.,1.,1.]),max_bars=3)
print('Recross then later missing bar:',r)
PY
```

实际输出全文：

```text
Nonmonotonic accepted: True
Recross then later missing bar: {'ma7_recross_bars': 1.0, 'same_side_survival_bars': 0.0, 'recross_complete': True, 'recross_status': 'recross_observed', 'observed_same_side_bars_before_interrupt': 1, 'recross_observed_before_interrupt': True, 'recross_after_gap_bars': nan, 'internal_gap': False, 'right_censor': False, 'indicator_undefined': False, 'exclusive_reason': 'complete'}
```

退出码 0。这个反例没有读取市场数据或改文件。第二个调用计划观察 3 个未来 4H bar，实际缺第 2 个 bar；第 1 个 bar 已反穿，函数立即返回 complete。能否允许这样的终止取决于 survival 定义；在该家族已经指定的整计划窗口保守有效性规则下，它未满足规则。它不构成所有 survival/first-hit 统计方法都必须观察事件后窗口的主张。

## 五、最小反例三：四个正年度门槛（源码确定性证明，未运行新回测）

实际读取源码：

```sh
nl -ba research/asset-portfolios/4h-ma7-regime-continuation/scripts/research_binance_4h_ma7_regime_continuation_p0.py | sed -n '1225,1244p;1438,1496p'
```

最相关源码输出：

```text
  1450        y = yearly.loc[yearly["direction"].eq(direction)]
  1451        complete_years = y.loc[y["calendar_year"].between(2023, 2025)]
  1452        positive_complete_years = int(complete_years["net_return_4bps_30_mean"].gt(0).sum())
...
  1468        supported = (
  1469            fh["event_favorable_rate"] > fh["control_favorable_rate"]
  1470            and fh["ci_low"] > 0
  1471            and fh["q_value_bh"] < 0.05
  1472            and h30["event_mean"] > 0
  1473            and positive_complete_years >= 4
  1474            and no_concentration_flip
  1475            and (h30_stress["event_mean"] > 0)
  1476            and not neighbor_opposite
  1477        )
```

最小输入思想实验为方向相同、年份为 2023、2024、2025，每年净收益都严格大于零：`positive_complete_years = 3`，`3 >= 4` 为 false。只有年度汇总发生重复行才可能把行数误计成四个年，重复本身也不构成四个正年度。该结论由源码直接证明，**本次没有额外运行一个四正年 Python 脚本，也没有声称执行真实研究裁决函数**。本节保存实际读取命令与精确源码片段，不能混称成第三个运行过的策略测试。

当前正式消费者仍为 P0R-DATA 对 P0.side_verdicts 的调用：[research/asset-portfolios/4h-ma7-regime-continuation/scripts/research_binance_4h_ma7_regime_continuation_p0r_data.py:809-813](../../../asset-portfolios/4h-ma7-regime-continuation/scripts/research_binance_4h_ma7_regime_continuation_p0r_data.py)。同一 P0 函数仍可走 PARTIAL，边界如证据四。

## 六、建议

1. 将失败至少分为收益计算/复现失败、研究范围未完成、真实经济效果失败、尚无前瞻证据。不要全部统计为策略无效，也不能用前两类替真实经济失败开脱。
2. 下一轮先建立一条小而完整的验证链：预先选研究问题和输入范围 → 逐窗口身份/资金费用 → 闭合信号和真实可成交时点 → 持仓/成交/费用/权益账 → 独立手算反例和历史几笔交易核对 → 前瞻记录。先贯通一个候选，公共化已反复使用的部分。
3. 避免再造全能平台成为新主线。共享线性 PnL、分段输入、bundle 门禁已存在；优先补持仓生命周期账、实际输出链验收、不可达门槛检查、全局试验次数/研究历史记录。前三项直接减少假结论，最后一项帮助识别重复试验带来的乐观偏差。这里全局试验记录不足主要来自此前平台审计，不是本次穷尽全仓所有新实现后的否定。
4. 成交模拟细节与持有期匹配：日/月频不必全湖 1m；但需处理月初延迟、停牌/改名/下市、缺价、费率、保证金与强平边界。固定费率和滑点工具不能自动代表实际成交能力。
5. 当前资金/PIT 治理优先修拟测试候选需要的标的与时间窗口，不能用今天的币池回填历史后冒充无幸存者偏差。新研究使用显式冻结 bundle；旧复现保留其原输入与限制。

## 七、历史记忆的使用边界

为定位既有审计使用过 `/Users/ZK/.codex/memories/MEMORY.md`，随后重新读取对应当前源码/报告/指定真实 JSON，并运行本文件记录的测试反例。最终结论不依赖记忆中的过时 1h 覆盖数字或曾经的状态作为当前实测。

用于定位的记忆行：`MEMORY.md:1020-1030`（平台与因子风险）、`:157-166`（4H gap guard）、`:387-389`（Top10 invalidation）。对应已知任务 ID：`01a0150e-4d3b-7953-a0fc-e9f9cd240f1f`、`01a06111-537c-7a42-bc3a-c1bd45bd74e9`。
