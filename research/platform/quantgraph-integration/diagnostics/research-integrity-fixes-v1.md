# research-integrity-fixes：当前 main 的有限范围修复

本轮在独立 worktree `research-integrity/quant-research-lab`、分支 `fix/research-integrity-v1` 完成。复现基线是 `a94f426ff1d521fc81b095dc8bc39d34a39be93d`，开始时通过 GitHub API 确认与 main 一致。所有输入都是合成测试；没有真实策略优化，没有重写冻结市场数据、共享内核或旧研究 artifact。未读取、修改或运行真实 quant-runner，未修改 QuantGraph、主 checkout、remote 配置或其他任务分支。

结论：A/B/C 均复现了**结论或输入组装问题**；原 DSR/CSCV 数学 reference tests 通过，没有复现原论文公式数值错误。修复允许历史复现和探索完成，只收紧可声称的结论。

## 最小复现与处理

位置以基线提交为准；修复后的独立 API 见 [接口文档](../../../../docs/research/ResearchIntegrityAssessment-v1.md)。

| 问题 | 基线位置 | 最小复现与旧结果 | 修复与回归 |
| --- | --- | --- | --- |
| A：结论未使用 holdout 证据 | `scripts/research_v4.py:63–82`、最终 `adjudicate(result)` 调用；合同 schema 的 `holdout_status` 未进入判定 | 给 OOS 1000 期、40 笔、收益 .2、Sharpe 1.5、回撤 .1，DSR .99/PBO .01；分别填已观察、未观察、UNKNOWN，全部 `RESEARCH_PASSED` | `integrity.py` 区分三种研究类型；缺证据 UNKNOWN，历史/未知不确认；已知曝光优先、真实登记时间、数据指纹、重叠窗口使用次数均参与。测试 `test_known_observation_cannot_be_upgraded`、`test_late_freeze_never_establishes_prospective_holdout`、`test_contract_unobserved_claim_or_missing_evidence_is_unknown` |
| B：试验范围仅当前网格 | `scripts/research_v3.py:125–128`；V4 只补充 prior_trial_count 到输出，没有进入估计 | 对旧提交的 study 运行 128 根合成日线、3 个 SMA 参数，声明 prior_trial_count=500，并在数学入口拦截入参；收到 3 个 Sharpe、effective_trials=3 | `trials.py` 复用本地曝光账本的锁/哈希链；`statistics.assemble_dsr` 必须按 campaign 全范围组装并保留依赖假设。测试跨 family/隔离无关 campaign、缺收益、历史不完整、同实验重试、标签参数变化、24 个多进程登记请求 |
| C：描述性 PBO 被当通过依据 | `scripts/research_v3.py:132–133` 写 descriptive only；`scripts/research_v4.py:76–81` 只读 COMPUTED/value | A 的输入额外写 PBO `limitation='descriptive only'`、DSR `limitation='not a correction for all prior research'`，仍 PASS | `statistics.evaluate_pbo` 返回适用性与决定用途；`adjudicate_research` 校验两者、版本和 scope。测试 diagnostic/NOT_APPLICABLE/缺方法元数据/不一致评估都不能 PASS，充分证据的合成正例仍能 PASS |

A/C 原始最小输入：

```python
result = {
    'oos': {'observations': 1000, 'closed_trades': 40,
            'total_return': .2, 'sharpe': 1.5, 'max_drawdown': .1},
    'deflated_sharpe': {'status': 'COMPUTED', 'value': .99,
                       'limitation': 'not a correction for all prior research'},
    'pbo': {'status': 'COMPUTED', 'value': .01, 'limitation': 'descriptive only'},
}
# 基线 adjudicate(result) -> RESEARCH_PASSED
# 当前 adjudicate(result) -> INCONCLUSIVE
```

旧代码从 `git show <上述基线>:research/platform/quantgraph-integration/scripts/research_v3.py` 读入隔离模块；没有切换或修改 main。B 使用与 `tests/test_research_integrity.py::synthetic_study_input` 相同的合成样本。注册回归则实际走当前 study，检查第一轮候选/压力测试依次登记、原样重试不增加 attempt、同 campaign 的另一家族不能被隐藏。

## 未复现与不扩大修复的部分

- 原论文 DSR 数值例（N=100/46/88）、偏度/Pearson 峰度 fixture、全部六个 CSCV split 的 logit、并列质量和既有样本边界均通过。冻结 v2 数学不改写；新包复用公式并通过同一独立基准。
- 当前输入是固定规则候选的连续账户净收益矩阵，IS 分块后比较 Sharpe；不是各 fold 重新拟合模型产生的收益。没有监督标签，也没有跨 train/test 拟合预处理。引擎已有闭合 bar 与未来扰动测试。
- 跨 bar/block 持仓本身未证明存在训练标签泄漏。本轮没有添加统一 purge/embargo，更没有把自创改法称为标准 PBO。
- 原八块和有限候选数不足以自动证明方法适用，历史使用完整性未知，因此现有 V4 PBO 继续保留为诊断。

## 新旧结论示例

| 场景 | 旧行为 | 当前行为 |
| --- | --- | --- |
| 已观察历史 + 高 DSR/低 PBO | 可 `RESEARCH_PASSED` | `INCONCLUSIVE` 于新发现确认；历史成果仍可 `REPRODUCIBLE_HISTORICAL_RESULT` |
| 自填 UNOBSERVED，无留存证据 | 可 PASS | holdout `UNKNOWN`，可继续探索 |
| 未知历史次数 + 当前网格 | 默认把网格数当有效 N | 默认 DSR `NOT_ESTIMABLE`；给出文档化假设后可报告 `CONDITIONAL`/敏感性 |
| diagnostic-only PBO=.01 | 可 PASS | 不作为确认性证据；缺充分证据 `INCONCLUSIVE` |
| PBO 不适用 | 混同不可计算/限制 | 保留 `NOT_APPLICABLE` 身份，可留数值诊断，不判数值成功，也不据此判策略必败 |
| 满足记录协议、范围、适用方法且通过原数值阈值 | 缺独立证据核验 | 合成正例 `RESEARCH_PASSED`；明确限定于已记录协议 |
| 足够交易但经济收益为负 | FAILED | 保留 `RESEARCH_FAILED`，不把失败原因改成 holdout 问题 |

## 变更与调用

- [`trials.py`](../../../../src/strategy_lab/research/trials.py)：TrialRegistry/v1；不可变 campaign、attempt、生命周期和 holdout 计划/使用记录。
- [`exposure.py`](../../../../src/strategy_lab/research/exposure.py)：抽取共享锁定追加事务，增加一致性读取；原曝光/前瞻记录语义保留。
- [`statistics.py`](../../../../src/strategy_lab/research/statistics.py)：DSR 范围组装、依赖/完整性状态、PBO 适用性封装；不用于因子 IC 显著性。
- [`integrity.py`](../../../../src/strategy_lab/research/integrity.py)：任务 A 可直接 import 的 ResearchIntegrityAssessment/v1、兼容判定、只新增 assessment revision。
- [`research_v3.py`](../scripts/research_v3.py)、[`research_v4.py`](../scripts/research_v4.py)：真实入口接线；先登记再回放，保留失败、压力诊断和每轮 code manifest。V4 报告携带 assessment，不更改外部合同 schema。
- [`test_research_integrity.py`](../../../../tests/test_research_integrity.py)：新增回归；运行只使用临时合成数据和自己的账本。

完整字段与 Python 示例见 [调用、迁移和限制](../../../../docs/research/ResearchIntegrityAssessment-v1.md)。旧合同无需补造历史记录。旧 artifact 的纠正使用 `write_assessment_revision` 新建文件并绑定原 SHA256；本轮没有改动任何已有冻结研究结果。对本轮合成复现输入已实际生成一个独立 assessment revision，原始输入 SHA256 为 `d8c109787ece6b0aef63c196c8a79ca76e13103c531b61fe76f6269063c05855`，新状态 INCONCLUSIVE；这不是对真实策略的新结论。

## 验证

环境：本 worktree 的 `.venv`，`uv sync --locked --extra dev --extra ml`。未启动服务器或真实数据采集。

- 修改前：原统计 reference tests 和 QuantGraph integration，共 **34 passed**。
- 修改后：最终完整无本地数据测试 **2203 passed, 1 skipped, 264 deselected**；skip/deselect 是既有条件测试/私有数据测试。
- 扩展定向测试包括旧数学、账户/市场接口、曝光账本和新增完整性，一次定向运行 **117 passed**；最终全套另包含后来增加的 8 项边界/入口测试。
- `ruff check src tests scripts/governance` 及本次研究脚本通过，`git diff --check` 通过。
- governance preflight 通过。为遵守本任务边界，环境变量 `QUANT_RUNNER_ROOT` 显式设成本 worktree 内不存在的路径，跨仓 peer 校验跳过；没有读真实 runner。既有 Lab 文档过期与制品体积警告保留，不扩展修复。
- CI 继续使用原 `governance-gates.yml` 的 locked 依赖和无本地数据测试；运行状态以 PR 检查为准。

复验命令（输出目录必须属于当前任务）：

```bash
uv sync --locked --extra dev --extra ml
QUANT_RUNNER_ROOT="$PWD/.local/integrity/absent-peer" \
  .venv/bin/pytest -q -m 'not local_data' \
  --basetemp=.local/integrity/test-tmp -o cache_dir=.local/integrity/pytest-cache
.venv/bin/ruff check src tests scripts/governance
QUANT_RUNNER_ROOT="$PWD/.local/integrity/absent-peer" \
  .venv/bin/python scripts/governance/preflight.py --governance-only
```

## 尚未解决的统计与证据限制

完整历史、人工查看、跨 campaign 的未申报选择无法自动恢复；有效独立次数依赖显式假设或敏感性，复杂依赖不由本修复解决。DSR 的 IID 近似和收益矩误差仍在；PBO 的分块选择、时间依赖、有限候选与重复使用仍有限制。v1 仅自动检查单次前瞻 holdout 协议，历史封存、多次确认的序贯检验及 fold 训练协议尚不支持决定用途。需要时保留 UNKNOWN/CONDITIONAL/NOT_ESTIMABLE，不以“全部偏差已校正”替代缺失证据。
