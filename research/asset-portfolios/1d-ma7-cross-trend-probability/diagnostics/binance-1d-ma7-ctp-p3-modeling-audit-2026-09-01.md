# BIN-1D-MA7-CTP P3 建模审计

状态：`explore / diagnostic-only / not promoted / not live-ready`。裁决：`DATA_BLOCK_NOT_READY`。

## 输入完整性

- P0R manifest artifact SHA256：全部匹配。
- P0R `holdout_read=false`，`hype_asset_excluded='HYPE/USDT:USDT'`。
- P2 feature spec SHA256：`ac4feb1270bb2d0b1da4d1523a84763ada808ec02b409559a603608cceec2c68`。
- B0 已在 P3 feature spec 中冻结为 P2 `F1_MA7_PATH` 原字段集合。
- HYPE 输入行：`0`；HYPER 输入行：`806`。

## 训练前停止点

P3 脚本已按顺序完成：

1. 校验 P0R manifest 与 HYPE/HYPER 输入边界；
2. 只统计未读标签的 pre-2025 MA7 事件：`54,137` 行；
3. 写入 `FROZEN_BEFORE_P3_LABEL_READ` contract lock；
4. contract lock 后加载严格样本并检查标签完整性与因果时点。

严格样本通过了行数、资产数、日期、非穿越、重复键、空标签、不完整未来路径和 HYPE 隔离检查，但没有通过 `feature_known_at < entry_ts`：

| 条件 | 行数 |
| --- | ---: |
| `feature_known_at < entry_ts` | `0` |
| `feature_known_at == entry_ts` | `52,563` |
| `feature_known_at > entry_ts` | `0` |

因此按合同停止，没有训练任何候选模型。

## 禁止产物确认

- OOF 预测：未生成。
- 2025+ 预测：`0`。
- HYPE reveal：未执行。
- long/short 独立头：未训练。
- LightGBM：未训练。
- 策略、仓位、账户权益、live spec、live-ready：均未生成。
