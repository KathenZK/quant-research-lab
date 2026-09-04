# BIN-1D-MA7-CTP P7 建模审计

- 状态：`explore / diagnostic-only / not promoted / not live-ready`
- 对象：`R_B0_69`
- 结论：P7 未训练新候选、未调阈值、未添加特征；只重建 P5/P6 冻结 B0 用于贡献审计。

## 锚点与重建

- 锚点全部通过：`False`
- OOF 最大 raw probability 误差：`0.00929`
- 2025+ final raw probability 最大误差：`0.000208`
- 总最大误差：`0.00929`
- HYPE 行数：`0`
- HYPER 保留：`True`

## 冻结边界

- 固定 raw 阈值：`0.510070`
- 固定分箱边界来源：development OOF raw score。
- P5 frozen Platt calibration 未在 2025/2026 重新拟合。
- 2025+ 数据角色：`ITERATIVE_REUSED_DIAGNOSTIC_2025_PLUS`。
- 禁止产物检查：未生成交易路径 HTML、策略权益曲线、Sharpe、live spec、runner handoff。

## 统计说明

主要年度差异使用 seed `20260901`、`2000` 次、28 日 calendar block bootstrap；同一 replicate 保留抽中 block 内所有资产/方向/事件。特征漂移使用 BH 校正；PSI 仅作连续效应量，不作正式显著性阈值。
