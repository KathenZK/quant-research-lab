# PUBLIC-M0233-ZSCORE-MEANREVERSION Core Ledger

## Family Identity

catalog M0233，单资产z分数反向，参数20/1.5/0.5。BTCUSDT spot/1d是本次实例；原源码多空，本次只多，分类ADAPTATION。

## Current State

`explore / not promoted / not live-ready`；不涉及runner。

| Version | Status | 结果 | Evidence |
| --- | --- | --- | --- |
| M0233-BTCUSDT-Z20-15-LONGONLY-20261003（未登记Vx） | explore | 收益9.52%，MDD11.73%，23往返；lag2收益33.24%，时序敏感 | [报告](diagnostics/M0233-20261003.md) |

## Shared Assumptions

[冻结规格](specs/M0233-first-replay.json)保留源码逐日重置仓位语义；z_exit不是滞后退出阈值。负仓位映射现金，下一开盘执行，95%现金名义金额，8bps费用/2bps滑点各单边。历史曝光窗口，不声称OOS。

## Evidence Map

[清单](artifacts/20261003-first-replay/result-manifest.json) · [独立账本](artifacts/20261003-first-replay/validation.json) · [原源码信号验证](artifacts/20261003-first-replay/source-validation.json) · [本地重建](artifacts/20261003-first-replay/local-recovery.json)。

下步仅可新规格考察其他时段和符合借贷数据条件的原多空实现；当前结果不足晋级。
