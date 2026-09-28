# BIN-1D-MA7-CTP P1 建模审计

状态：`explore / diagnostic-only / not promoted / not live-ready`。裁决：`UNSTABLE_MA7_EVENT_SIGNAL`。

## 输入完整性

- P0R artifact 哈希全部匹配：`True`
- HYPE 输入行：`0`
- HYPER 输入行：`806`
- 事件过滤与冻结审计值一致：`101187`
- 全部训练行 `probe_raw_ma7_cross_dir=true`
- T1 特征来自前一有效日；EVENT_T0 仅当日收盘可知字段。

## 时间隔离

- D1-D3 每折 `max(train.label_end_ts_20d) < validation_start`
- 2025+ 未参与特征、参数、轮数、校准选择
- prehistorical lock SHA256：`80bf270e9741bab9c7d2f6372d0b72853c73a472a8b1e4ed17fcf7a6c4e207e4`

## 样本串用

- LONG 只用向上穿越，SHORT 只用向下穿越，POOLED 是控制组且 `side` 不进 X。
- OOF 每行只预测一次。
- paired bootstrap 共享同一日期块重采样索引。

## 禁止产物

- 无策略、仓位、账户、live-ready、HYPE reveal。

