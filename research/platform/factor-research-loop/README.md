# factor-research-loop

research_classification: diagnostic_topic

本主题把已有公开 Graph 定义接到 Lab 的真实因子计算、探索性统计和 Graph 私有结果。
它不是策略家族，不建立策略主账，不提供组合、下单或晋级能力。

## 冻结定义与计数

来源为 Microsoft Qlib `be725493eb1a6bbb42bf11b37aa7669f59610ff1` 的
[Alpha158 loader](https://github.com/microsoft/qlib/blob/be725493eb1a6bbb42bf11b37aa7669f59610ff1/qlib/contrib/data/loader.py)，
定义来源摘要 `814b7f7ab3d418ae3c87ce352220080b239eba2670eac9e38376b794be4075cb`。
原始 Graph ID、来源原生 ID、参数和完整公开快照见 [选择清单](specs/graph-selection-v1.json)，
研究设置见 [settings-v1.json](specs/settings-v1.json)。清单在预测结果之前确定。

| 定义 | 计算结构 | 宽泛机制组 |
|---|---|---|
| KMID、KLEN、KUP、KLOW、KSFT | 当前 OHLC 比值及两字段极值 | K 线形态 |
| ROC5 | 滞后 close / 当前 close（不是过去收益率） | 历史价格关系 |
| MA5 | 滚动均值 / 当前 close | 历史价格关系 |
| STD5 | 价格样本标准差 / 当前 close | 价格离散程度 |
| MAX5、MIN5 | 滚动 high/low 极值 / 当前 close | 区间位置 |
| RANK5 | 单资产窗口内的百分位排名 | 区间位置 |
| RSV5 | 当前 close 在过去 high/low 区间中的位置 | 区间位置 |

选定 12 个 Graph concept（原有特征族）、12 个唯一公式 definition、12 个 variant，
归为 4 个研究用宽泛机制组。这不代表 12 个独立经济因子。每族只选一个窗口，
不以多 lag 凑数。ROC5 的 Graph 显示名是 CLOSE5；已有去重保留
`Alpha158:ROC5` 和 `Alpha360:CLOSE5`，本任务按原生 ID、公式与快照建立映射，未改 ID。
简单基准是 Lab 自建的上一根收益，只标 INTERNAL_BASELINE，不计为公开映射。

## 准入与语义

复用 `FactorRegistry`、`compute_factor_bundle` 和现有 Trusted Market Data
`read_market_dataset`。不使用表达式 eval，也不改 `research_v4.adjudicate`。
输入 DRAFT 经过定义、版本、许可、字段、标签、范围、预热、时间网格核验后，
才生成带内容摘要的独立冻结计划。因子诊断不要求策略止损、仓位或交易规则。

- COMPUTATION_CHECK：手算、固定官方 oracle、边界和无未来信息检查。
- FACTOR_DIAGNOSTIC：计算语义通过后，在合法可信真实行情上研究标签关联。
- PORTFOLIO_BACKTEST：另需完整执行、持仓与成本规则；本模块拒绝。
- CONFIRMATORY_VALIDATION：另需任务 C 的登记、holdout 与统计证据；本模块拒绝。

Qlib 原算子 `min_periods=1`；研究另外要求足额预热，不能把部分窗口冒充完整窗口。
Std 的 ddof=1；RANK5 按时间窗口排名、并列用平均名次，绝不冒充截面排名。
Ref 的方向、闭合 bar、缺失值、不填充、价格复权、volume 单位、universe 和
行业中性化边界均写入映射。未核定 volume 单位、RSI 平滑算法或截面输入的定义不纳入。

[官方 oracle fixture](../../../tests/fixtures/factor_study/qlib-golden.json)
由固定版本 Qlib 的经过检查的算子类生成，包含 NaN、相同值、短窗口；手算期望和
独立 NumPy 循环另作核对。合成夹具不计为市场研究。真实帧逐值对拍并检查前缀不变性。
运行入口拒绝混合市场身份、不连续时间网格和不受支持的轴，不沿时间排序模拟截面。

## 数据与统计范围

第一批使用已接受的私有 Bit2Me BTC/EUR spot 日线包。这是把股票来源的数学定义
移到加密资产上的探索；不改 Graph 的 equity 来源分类，也不声称复现股票经济效应。
保留原采集合同只是为了验证已有数据的来源和字节，不把该策略采集合同的止损、
仓位要求施加到新因子计划。新因子计划单独冻结，输入每次重新从原始页重建核验。

OHLC 原生未复权；标签是闭合 close[t] 到 close[t+h] 的价格收益，h=1、5。
bar 时间为开盘时间，因子最早在该 bar 收盘后可用；没有历史 received_at 证据，
不假装历史值曾实时可得。预热、标签尾部和跨分段标签均排除。

研究包括逐段 TS Pearson/Spearman、成对 20 根区块 bootstrap 95% 区间、
样本量/覆盖/常数/无穷检查、因子成对冗余，以及逐因子相对 INTERNAL_BASELINE
的后段 MSE 增量。基准与增强模型只在前段标准化和拟合，训练标签不能进入后段。
后段是历史描述性检验，不能称为全新 OOS。bootstrap 仍依赖局部平稳假设，未作
多重比较确认；普通相关不代表因果。没有组合收益，不计算 Sharpe、DSR 或 PBO。

完整实验清单和失败/无效记录分别导出 `experiments.json`、`trial-outcomes.json`、
`runs/*/result.json` 和 `failed-attempt-*.json`。已有曝光账本只读查询；本任务另用
自己的 append-only exposure 记录，空查询不证明未曝光。`TrialAdapter` 仅定义
`register(plan, experiments)` / `evaluate(registration, outcomes)` 适配口，不复制
TrialRegistry。C 缺席时明确 UNAVAILABLE / NOT_ADJUDICATED，结果恒为
EXPLORATORY_RETROSPECTIVE，不产生 RESEARCH_PASSED。

## 运行与结果查询

先在两个独立 worktree 安装各自锁定环境；Lab 的集成运行额外安装本地 Graph SDK：

```sh
uv sync --locked --extra dev --extra ml
uv pip install --python .venv/bin/python -e ../quant-knowledge-graph
```

随后使用 `.venv/bin/python`，避免普通 `uv run` 的精确同步移除可选本地 SDK。
Graph SDK 是集成时的显式依赖，Lab 的基础测试/因子库不依赖它；没有改两仓库锁文件。

一个命令完成选择 → 冻结 → KMID 首条闭环 → 扩展 → 回写/读回：

```sh
.venv/bin/python research/platform/factor-research-loop/scripts/reproduce.py \
  --graph-root ../quant-knowledge-graph \
  --manifest /private/accepted/manifest.json \
  --acquisition-contract /private/original/contract.json \
  --exposure-ledger /private/research-exposure-ledger.jsonl \
  --output research/platform/factor-research-loop/artifacts/local/new-study \
  --journal ../quant-knowledge-graph/datasets/factor_studies/new-study.sqlite
```

输入必须已通过现有可信数据审查；脚本不下载、不制造许可、不写共享数据库，
新输出目录不得已存在。也可分别运行 `python -m strategy_lab.factor_study freeze/run`，
`run --only KMID` 用于首条验收，重复 run 会核对 artifact 后幂等提交同一 run。

原始 bytes、采集/许可/数据摘要、代码快照、环境版本、冻结计划、逐日因子/标签、
全部统计、报告、回执和读回结果保留在独立本机目录；Git 排除所有本主题 artifacts，
包括 Markdown 报告。对外 Git 只有代码、公开定义快照、事前设置和合成 fixture。
Bit2Me 行情及其衍生结果仅允许私有内部使用，不能因自行计算而公开。
两端共同遵循 Graph 的 `contracts/factor-study/v1`；Graph 权限默认 commercial，
私有查询必须显式 research，HTTP 还需要研究 scope 的认证。

## 工作区与验收入口

Graph 基线：`725586657c48d1fc708427ed4d5960b54ae27768`，分支 `feat/factor-study-bridge-v1`。
Lab 基线：`a94f426ff1d521fc81b095dc8bc39d34a39be93d`，分支 `feat/factor-study-pipeline-v1`。
完整本机工作区路径、运行摘要、实际统计与验收日志留在私有交付记录，不进入公共 Git。
原有测试和治理入口继续使用；新增测试为 `tests/test_factor_study.py`，
覆盖官方语义、泄漏、资产串扰、缺失、标签尾部和准入边界。
