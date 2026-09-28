# ResearchIntegrityAssessment/v1

本接口控制**结论强度**，不阻止正常计算、学习、历史复现或探索。Python 包继续名为 `strategy_lab`。调用方无需导入 `research/` 中的旧脚本；不依赖 QuantGraph 服务或执行系统。

## 1. 研究类型与状态

| study_kind | 能保留的成果 | 不能自动声称 |
| --- | --- | --- |
| `HISTORICAL_REPLICATION` | 正式、可复现的历史结果；原数据准入规则仍适用 | 独立确认一个新发现 |
| `EXPLORATORY_ANALYSIS` | 探索结果、参数面、失败诊断、条件性统计 | 未观察样本的确认性检验 |
| `CONFIRMATORY_HOLDOUT_TEST` | 满足记录协议、范围和方法要求后的条件性独立确认 | 证明研究者从未在其他地方见过数据 |

未提供或未知研究类型默认探索。`computation_permitted=True` 只代表完整性接口允许计算，不替代数据权限、输入质量或账户规则。

保留 V4 外部 schema，避免与公开接口漂移。合同仍可使用旧 `holdout_status`；`UNOBSERVED_AT_FREEZE` 只是声明，评估可返回 `UNKNOWN`。新字段保存在结果报告和统计节中。旧 `trial_count` 继续表示该报告的参数网格规模，不得用作独立试验数。

## 2. TrialRegistry/v1

实现：[`strategy_lab.research.trials`](../../src/strategy_lab/research/trials.py)。复用 [`exposure.py`](../../src/strategy_lab/research/exposure.py) 的本地文件锁、真实登记时间、哈希链与 fsync。使用调用方自己的 JSONL 路径；无需建立另一套数据库。

```python
from strategy_lab.research.trials import TrialRegistry

registry = TrialRegistry('/absolute/path/to/task-local/trials.jsonl')
registry.register_campaign(
    'selection-2026-01',
    selection_goal='在同一数据与收益目标下选一个策略',
    scope_definition='本次选优涉及的所有家族、模型、标签与参数；不只最终获胜家族',
    history_completeness='UNKNOWN',
    history_reason='旧搜索和人工查看记录不完整',
)
spec = {
    'hypothesis_family_id': 'trend-family',
    'selection_campaign_id': 'selection-2026-01',
    'identity': {'strategy': 'trend', 'version': 'v1', 'model': 'rule'},
    'parameters': {'lookback': 20},
    'label_horizon': 'NO_PREDICTIVE_LABEL',
    'objective': 'net return Sharpe',
    'selection_rule': '预先约定的选优规则',
    'dataset_fingerprint': dataset_sha256,
    'sample_fingerprint': sample_sha256,
    'code_hash': code_sha256,
    'config_hash': config_sha256,
    'parent_experiment_id': None,
}
attempt = registry.plan('experiment-001', spec)
registry.record(attempt, event_id='start-1', state='started',
                results_observed='UNOBSERVED', affects_selection='NO', reason='开始运行')
# 执行后，无论结果好坏都登记；失败用 failed，人工停止用 aborted。
registry.record(attempt, event_id='complete-1', state='completed',
                results_observed='OBSERVED', affects_selection='YES',
                reason='结果已可供后续研究使用', result_refs={'report_sha256': report_sha256})
scope = registry.snapshot(['selection-2026-01'])
```

- `experiment_id + spec` 的内容哈希确定 attempt。同配置崩溃后复用 experiment，重试不增加独立试验；传输重试复用 `event_id`。状态转换可以增加事件，但失败/放弃事件不删除。
- 参数、模型身份、标签期限、目标函数、选择规则、数据或代码变化，spec 改变，从而生成新 attempt。不要为相同重试生成新 experiment ID。
- `planned` 只表示采集或准备，没有运行不计已完成回测。`raw_attempts / completed_trials / observed_trials` 分开。
- 失败或放弃时如果已看到部分结果，仍计入选优范围。未知的观察或影响状态保持 `UNKNOWN`，阻止授予更强结论。
- 默认包含所有已完成候选、观察过的结果和影响选择的尝试。预先定义的压力测试可标 `trial_role=PRESPECIFIED_DIAGNOSTIC` 且明确 `affects_selection=NO`，它的完整记录和排除 ID 仍保留；如果用于选择，必须追加 `YES`，此后不可撤回。
- snapshot 以 selection campaign 为单位，没有 family 过滤器。同一选优过程不能拆成狭窄 family 隐藏其他尝试。确属同一过程的旧 campaign 必须显式链接到 `snapshot([id1, id2])`；完全无关研究不能机械合并。
- `COMPLETE_DECLARED` 是带依据的范围完整性声明，仍非全历史证明；另有 `INCOMPLETE / UNKNOWN`。导入旧记录使用 `historical_import=True, import_source=..., import_completeness=...`，不知道的时间/次数不回填。旧来源声称的时间放 `occurred_at`，实际登记时间由工具生成。
- POSIX 本地多进程文件锁保证读改写串行和幂等。不是网络分布式账本。崩溃若留下截断尾行，拒绝继续写入，需依据保留证据人工恢复，不能静默删除失败记录。拥有写权限的人可以重写整本账；需独立保留检查点。

## 3. Holdout 证据

`registry.freeze_holdout(holdout_id, plan)` 在结果前登记计划，保存实际 `registered_at`。plan 必含：

| 字段 | 含义 |
| --- | --- |
| `contract_hash / plan_frozen_at` | `digest(frozen_contract)` 规范化内容哈希与声明的冻结时间 |
| `dataset_version / sample_fingerprint` | 逻辑数据版本与样本身份 |
| `sample_start / sample_end` | 左闭右开的完整验证窗口 |
| `protocol / max_uses` | 验证协议与最多使用次数 |
| `known_access_records` | 已知访问/研究记录；不能删除不利记录 |
| `access_history_status / evidence_refs` | 对已知记录的审阅状态与依据位置 |

每次揭示之前调用 `use_holdout(..., use_id=..., dataset_fingerprint=..., reason=...)`。相同执行原样恢复复用 use ID；新的查看使用新 ID。超过限制仍登记并允许研究，但不给确认性结论。同一逻辑数据版本上的重叠窗口会合并使用记录，改名或换样本哈希不能重置计数。

v1 只支持 `PROSPECTIVE_AFTER_FREEZE_SINGLE_USE` 的决定用途：合同冻结时间 ≤ 实际登记时间 < 样本开始，实际使用在样本结束之后，使用一次且限制为一次，实际数据指纹匹配，已知访问记录为空且 `KNOWN_RECORDS_REVIEWED` 有依据。其他封存协议可记录，但尚未自动验证，返回 `UNKNOWN`。旧曝光账本通过 `exposure_records` 传入；任意已知重叠曝光优先返回 `OBSERVED`。

这不是“从未见过”的认证。工具不能监测账本之外的浏览、截图、其他数据副本或隐瞒的研究，也不能认证自报依据的真实性。`DOCUMENTED_PROSPECTIVE_PROTOCOL` 只表示**记录层面的协议和时间线满足检查**。

## 4. DSR 输入和数学口径

[`assemble_dsr`](../../src/strategy_lab/research/statistics.py) 按 campaign snapshot 中的全部 `selection_trial_ids` 组装，输入 ID 必须完全相等，不能只取当前网格。每个 ID 提供：

```python
returns_by_attempt[attempt] = {
    'kind': 'STRATEGY_RETURNS',  # 因子 IC / score 不适用
    'values': per_bar_net_returns,
    'dataset_fingerprint': dataset_sha256,
    'sample_fingerprint': sample_sha256,
    'periods_per_year': 252,
}
```

不同数据、不同窗口或频率不机械合并。v1 拒绝跨这些边界估计，保留范围与原因。未知失败结果、缺历史收益、常数收益、缺值和不足样本都不得假装可靠估计。

```python
from strategy_lab.research.statistics import assemble_dsr

dsr = assemble_dsr(
    scope, returns_by_attempt, selected_attempt_id=attempt,
    dependence={
        'method': 'SENSITIVITY',
        'effective_trials': [2, 5, 10],  # 仅示例，须不大于该范围内已提供收益的数量
        'rationale': '依赖性无法可靠估计，报告给定假设下的敏感性',
        'evidence_refs': ['研究协议的假设与限制'],
    },
    return_assumptions={'sampling': 'IID_APPROXIMATION', 'evidence_refs': ['收益依赖性审阅']},
)
```

默认依赖性 `UNKNOWN` → `NOT_ESTIMABLE`。`INDEPENDENT` 必须有独立性假设的理由和依据，此时才使用已登记范围的数量；不是无条件令 N 等于网格规模。`EXPLICIT_ESTIMATE` 接受一个有效独立试验估计，`SENSITIVITY` 接受多个，均为条件性诊断。v1 不实现新的依赖性估计器，不声称解决复杂非线性依赖；有效 N 小于 2 不使用本近似，返回不可估计。

数学保留 [Bailey 与 López de Prado 的 DSR 论文](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf) 式 2：用每期 Sharpe、跨试验 Sharpe 的样本方差、样本长度、偏度和 Pearson 峰度。年化 Sharpe 转每期除以 √年期数，方差除以年期数。附录 3 区分相关试验与有效独立数量；这里只提供明确假设和敏感性入口，不把数量当依赖性估计。

`full_historical_correction=False` 始终保留。即使给定范围内可作 `DECISION_SUPPORT`，也只是对记录范围和假设成立时的支持，不是完整校正所有历史研究偏差。小样本、序列依赖、偏度/峰度估计误差及收益定义仍是限制。

## 5. PBO 的适用性

[`evaluate_pbo`](../../src/strategy_lab/research/statistics.py) 封装原固定收益矩阵 CSCV 数学：同步的候选净收益列、等长分块、对全部组合计算 IS 赢家的 OOS 排名；并列赢家等权、OOS midrank、logit ≤ 0 计作过拟合。原固定数值测试继续保留。

依 [PBO 原论文](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf) §2.2、§4–5，决定用途另需：候选 ID 与 selection scope 一致、完整性声明、因果收益、预处理无跨测试拟合、标签重叠审阅、连续账户边界、分块/时间依赖说明和观察结果前冻结的协议。输入列顺序由 `trial_ids` 明确。

- 持仓跨 block 不自动等于监督学习标签泄漏，本次固定规则引擎不在 fold 内拟合模型；保持真实连续账户收益，不发明统一 purge。
- fold 拟合后产生的预测收益、跨全样本拟合预处理或已知未来信息，对此实现返回 `NOT_APPLICABLE`，可保留数值诊断；需要另行验证对应训练协议，本次不声称实现了标准 purged PBO。
- 数值可算与决定用途分开：`status / applicability_status / decision_use / reasons / limitations / method_version` 全部保留。
- v1 数值实现延续 4–12 个偶数块、每块至少两条；统计充分性不由这个最低计算条件保证。至多 10 个候选限制为 diagnostic 是本接口的保守使用政策，不是论文通用阈值。少块、粗排名、长周期相关和选择过程中反复使用 PBO 仍有限制。
- `NOT_APPLICABLE` 既不等于数值通过，也不等于策略必然失败。

## 6. 统一评估与判定

```python
from strategy_lab.research.integrity import assess_research_integrity, adjudicate_research

assessment = assess_research_integrity(
    study_kind='HISTORICAL_REPLICATION',
    contract=frozen_contract,
    selection_scope=scope,
    statistical_methods={'dsr': dsr, 'pbo': pbo_result},
    holdout_evidence=registry.holdout_evidence('holdout-id'),
    exposure_records=known_exposure_records,
    dataset_fingerprint=dataset_sha256,
)
status = adjudicate_research(results, assessment)
```

返回 `assessment_sha256`、assessment 版本、研究类型、registry/selection scope、holdout 证据及状态、统计方法适用性、允许结论、blockers/warnings。方法结果和 scope 必须与评估一致，不能拿另一轮评估给当前数值背书。旧阈值不变：OOS 至少 3 期/30 笔交易、正收益和 Sharpe、回撤不超过 30%、DSR ≥ .95/PBO ≤ .1；增加的是证据要求。

历史/探索可以完成正式可复现研究，`permitted_conclusion_level` 保留相应身份，`research_status=INCONCLUSIVE` 表示尚不能确认新发现。可测的经济阈值失败仍为 `RESEARCH_FAILED`；材料充分的确认性案例可 `RESEARCH_PASSED`，不是永远拒绝。该状态从不授权部署。

`write_assessment_revision(new_path, original_result_path=..., assessment=..., research_status=...)` 只创建新文件，关联原文件路径和 SHA256；已存在目标拒绝覆盖。历史 artifact 不原地修改。

## 7. V3/V4 迁移

V3 `study(..., trial_context=...)` 和 V4 `run(..., integrity_context=...)` 接受相同的 registry/campaign 配置。V4 CLI 可传 `--integrity-context path.json`。字段：`registry_path / experiment_id / selection_campaign_id / selection_campaign_ids / dependence / return_assumptions / study_kind / exposure_ledgers / holdout_id / holdout_use_id`。`selection_campaign_ids` 用于包含同一选优过程的多个既有 campaign，必须包括当前 campaign。先用包 API 登记 campaign/计划；外部合同不变。

省略 sidecar 时仍可运行：在输出父目录建立 `trial-registry.jsonl`，以该配置识别 legacy 实验，完整性为 UNKNOWN，不声称覆盖全历史。历史 V4 合同默认 `HISTORICAL_REPLICATION`；其他默认探索。正式结果仍经过原有数据准入；统计诊断不会阻塞账户计算。V4 当前 PBO 缺适用性证据，固定为 diagnostic，数值不再触发确认性通过。

同配置重跑须选择新的输出目录，复用 registry 和 experiment。旧产物保留。为了追踪统计代码变化，新增包模块也进入 code manifest。历史共享内核、数据、原 reference fixtures 均不变；包内保留同口径数学并同时对照冻结 fixture 验证。
