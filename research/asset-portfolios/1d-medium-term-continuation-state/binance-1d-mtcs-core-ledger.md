# Binance-1D-Medium-Term-Continuation-State Core Ledger

## Family Identity

- Full family name：Binance-1D-Medium-Term-Continuation-State；alias：BIN-1D-MTCS。
- 市场／周期：Binance COIN观测分类下的USDT永续，完整UTC日线。
- 机制：事前20日方向、MA7穿越及三种穿越前路径状态，评价20日方向位移、后半程延续和相对对照改善。
- 独立于MA7-BTG/TPSA/CTP；旧事实仅用于问题路由，重新可信取数。不以多数币盈利或同日选币alpha替代原目标。

## Current State

- 主状态：explore / diagnostic-only / not promoted / not live-ready。
- 当前阶段：P0–P3本轮有限研究完成。完整比率重算、价格路径与分段捕获均已完成；文件核验以[交付收据](artifacts/delivery-verification.json)为准。
- 无注册策略版本；无runner、dry-run、live或未来监控。
- 已知边界：重复历史、历史PIT和资金费覆盖未完整证明；独立确认尚无新数据。
- 研究裁决：0个达标历史候选；M_LONG为RULE_NOT_SUPPORTED（Δ20同时区间上界约0.1882ATR，小于冻结0.25最低增量）；其余9个INSUFFICIENT_EVIDENCE。全部主统计通过数值可靠性检查，非新时间确认。
- 下一决策：停止本合同下的历史搜索，无可冻结候选所以不启动确认功效规划或未来监控。若另立新研究，先限定不依赖MA7的事前强度关系；这只是待证分支，不是本轮有效策略。

## Version Rules

- P0/P1等为研究阶段。修改输入或标签必须保留旧记录并说明是否使旧运行无效；结果后不得调低阈值或扩搜索。
- 新增交易版本才另行登记；研究合同冻结不等于交易版本晋升。

## Version Table

| 观察 | 状态 | 角色 | 证据 | 决策 |
| --- | --- | --- | --- | --- |
| 2026-09-08启动 | explore | 中期延续性事前识别 | [目标](specs/user-objective.md)、[合同](specs/research-contract.md) | 用户授权执行，结果尚未计算 |
| 2026-09-08 P0–P2 | explore | 可信价格、固定路径与捕获诊断 | [价格输入](artifacts/p0-inputs/summary.json)、[路径](artifacts/p1-research/summary.json)、[捕获](artifacts/p2-capture/completed.json) | 648币；未来缺失、截尾与非正权益风险保留，全成本未验证 |
| 2026-09-08 统计修复 | explore | 原估计量完整计算 | [原失败](artifacts/p1-statistics/report.json)、[修复合同](specs/statistics-exact-computation-repair.md)、[完整重算](artifacts/p1-statistics-exact-r1/report.json) | 原IF近似失败保留；两块各百万次完整比率，未改研究门槛 |
| 2026-09-08研究决策 | explore | 本合同有限裁决 | [主报告](diagnostics/research-report-20260908.md)、[决策摘要](artifacts/decision-summary.json) | 0候选／1个规则未达最低目标／9个证据不足；not promoted，not live-ready |

## Shared Assumptions

- 主期限20日；10/40日仅作期限诊断。方向在收盘确定，下根开盘才可参与。
- 0.25ATR为最小研究效应；四主指标Q20/Δ20/L20/Δlate及附加筛选改善分别判断。
- 原始位移、手续费滑点后、完整资金费净收益分列；缺失不填零。
- 输入按连续段计算，保留所有事前机会和未来删失；观察库存不冒充历史PIT。

## Evidence Map

- [合同](specs/research-contract.md) · [输入请求](specs/input-request.json) · [源码pin](specs/source-pins.json)
- [原审阅方案](../1d-ma7-bidirectional-trend-generalization/notes/research-proposal-medium-term-continuation-20260908.md)
- [决策记录](decision-log.md) · [复现](scripts/README.md) · [产物](artifacts/README.md)
- [独立资金审计](diagnostics/p2-independent-audit.md) · [数据范围](diagnostics/data-scope-and-funding.md) · [验证与交付](diagnostics/validation-and-delivery.md)
