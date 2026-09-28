# BIN-1D-MA7-CTP P2 建模审计

状态：`explore / diagnostic-only / not promoted / not live-ready`。裁决：`SIGNAL_EXPLAINED_BY_MA7_CORE`。

## 输入完整性

- P0R artifact 哈希全部匹配：`True`
- P1 feature spec SHA256 匹配 manifest：`ecf90b1a5bb6e79841d1449a9d12316c63fa2727ffed9482cc8eff1ccf3b63f0`
- HYPE 输入行：`0`
- HYPER 输入行：`806`
- 2025+ 建模读取行：`0`
- 事件过滤与冻结审计值一致：`54137`

## 时间与样本隔离

- D1-D3 每折 `max(train.label_end_ts_20d) < validation_start`。
- P2 OOF、fold metrics、decile metrics 均只含 `<2025-01-01` 事件。
- 只训练 `POOLED_DIRECTION_ALIGNED` 一个模型；long/short 仅作分层评价。
- paired bootstrap 对 selected、F0、F1、SLOPE 使用同一日期块重采样索引。
- D2 校准器只用标签在 D2 开始前结束的 D1 OOF；D3 校准器只用标签在 D3 开始前结束的 D1-D2 OOF。
- 最终校准器方法：`platt`；选择依据：`forward_oof_D2_D3`；最终拟合标签截止：`2024-12-31 00:00:00+00:00`。
- 原始排序概率与前向交叉校准概率分列保存；没有用同一验证标签拟合并评价其校准器。

## 禁止产物

- 无 2025+ 预测、无 HYPE reveal、无策略、仓位、账户、live-ready。
