# MA7-Bidirectional-Trend-Generalization Core Ledger

## Family Identity

- Full family name：MA7-Bidirectional-Trend-Generalization；alias：MA7-BTG。
- 市场：加密永续、真实股票合约；周期：日线 SMA7。
- 机制：因果入场、持有、退出、保护、再入场与有条件反手；跨标的泛化和事前适用性。
- 边界：原 MA7-ATR14 迁移与多空审计保持冻结；股票现货代理另列，不能充当合约证据。

## Current State

- 当前阶段：本轮P0–P5有限研究交付完成；无登记版本。C3是开发选中的失败对照。
- 主状态：`explore / not promoted / not live-ready`。
- 无 runner、dry-run、live；目标不包括上线。
- 主要证据：主205币C3正收益34个、严格价格合格7个；没有双向多数盈利证据。低ER空头有有限价格线索，未达可靠范围门槛。
- 就绪阻碍：无完整主窗funding/身份链、无足够股票长窗、无新增未揭示OOS；并有明显收益/风险失败。
- 下一决策门槛：新增可接受证据再讨论独立确认；停止同一已揭示历史上的参数搜索，不安排实盘或监控。

## Version Rules

- P0/P1 等为研究阶段，不是策略版本。正式登记 Vx 时另增主账版本行。
- 机制或执行改变单独记录，不重写已揭示合同；不继承其他家族身份或参数结论。

## Version Table

| 观察 | 状态 | 角色 | 证据 | 决定 |
| --- | --- | --- | --- | --- |
| P0–P5，2026-09-08研究观察 | explore | MA7多空与跨市场泛化；C3冻结失败对照 | [完整结论](diagnostics/final-report-20260908.md)、[验收](diagnostics/delivery-verification-20260908.md) | 有限搜索未获稳定双向或可靠范围证据；not promoted / not live-ready |

## Shared Assumptions

- 单标的独立本金为主分母；资产类别分别裁决；组合仅作辅助。
- 已揭示历史不能称盲测；缺资金费不得补零；价格诊断与全成本结果分列。
- 639日完整主窗+121根预热；信号收盘、次日开盘、1倍入场上限，默认手续费10bp/滑点4bp每次成交。
- 断档分段不填平，段尾截尾不是可执行清算认证；经济NAV归零不等于交易所保证金强平模型。

## Evidence Map

- [用户目标](specs/user-objective-20260908.md)
- [冻结合同](specs/research-contract-p1-20260908.md)
- [数据范围](diagnostics/data-and-market-scope-20260908.md)
- [复现修复与字段澄清](diagnostics/implementation-repair-20260908.md)
- [复现说明](scripts/README.md)
- [启动记录](diagnostics/startup-20260908.md)
- [决策记录](decision-log.md)
- [产物索引](artifacts/README.md)
