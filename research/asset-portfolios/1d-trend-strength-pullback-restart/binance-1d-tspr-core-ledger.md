# Binance-1D-Trend-Strength-Pullback-Restart Core Ledger

## Family Identity

- Full name：Binance-1D-Trend-Strength-Pullback-Restart；alias：BIN-1D-TSPR。
- 市场/周期：Binance观测COIN日线。
- 机制：事前趋势强度、顺序回撤与重新穿越MA7的共同机会研究；区分强度关联与重启增量。
- 独立于MTCS/TPSA/CTP；不以同日选币alpha或多数币盈利替代用户目标。

## Current State

- `explore / diagnostic-only / not promoted / not live-ready`；本轮研究完成。
- 12个方向×双期限命题均INSUFFICIENT_EVIDENCE；两个方向均无达标HIGH_PM候选。24指标中只有LONG.HIGH_PM.Late联合下界>0，不能替代完整20日和条件增量。
- 无注册策略版本、runner交接、交易或自动观察。
- 既有历史已揭示；历史PIT、全成本及可交易性未完整证明。
- 下一门槛：在新未读时间/独立合格数据检验时期依赖与共同支持；本轮不继续历史调参，不自动创建后续监控。

## Version Rules

- P0/P1等为研究观察；不自动注册Vx或晋升。
- 新信号或估计定义必须保留旧版；结果后不移动门槛或扩大搜索。
- 多资产研究内核使用独立冻结版本及SHA256，旧MTCS文件不改写。

## Version Table

| 观察 | 状态 | 角色 | 证据 | 决策 |
| --- | --- | --- | --- | --- |
| 2026-09-08联合目标启动 | explore | 强度与回撤重启的中期延续研究 | [目标](specs/user-objective.md)、[输入合同](specs/input-contract.md) | 用户授权独立研究，先定义后计算 |
| P0独立输入 | explore / diagnostic-only | 652请求、648返回，4个不足历史，0启动失败 | [输入审计](diagnostics/p0-inputs-audit.md) | 只具价格诊断资格 |
| P1固定状态与24维推断 | explore / diagnostic-only | 497,435完整方向机会，60/120日各50,000完整复制 | [总报告](diagnostics/research-report-20260908.md)、[统计审计](diagnostics/statistics-independent-review.md) | 12双期限均证据不足，0候选 |
| P2顺序捕获 | explore / diagnostic-only | 10,544账户、78,368交易；完整资金账与分层权益核验 | [捕获审计](diagnostics/p2-independent-audit.md) | 右尾、成本与做空非正权益边界；非净收益资格 |

## Shared Assumptions

- 20日为主研究期限，后半程指第5至20日；方向明确、多空分别报告。
- 事前特征与未来评估分开；缺口按连续段处理，不用未来完整性筛信号。
- 全部旧历史为诊断，不冒充新OOS；资金费缺失不能补0。
- 引擎/统计/捕获共享v1固定，manifest SHA256=`9b8575fb3c3bfd59b314bb805bb6f1cfdba4c26655c01dfb59b09f8e46dd0209`；[计算锁](specs/computation-lock.json)。

## Evidence Map

- [目标](specs/user-objective.md) · [输入](specs/input-contract.md)
- [结果](diagnostics/research-report-20260908.md) · [全状态独立复核](artifacts/p1-independent-verification.json) · [统计独立复核](artifacts/statistics-independent-audit.json)
- [决策](decision-log.md) · [执行](scripts/README.md) · [产物](artifacts/README.md)
- [旧研究边界](../1d-medium-term-continuation-state/diagnostics/research-report-20260908.md)
