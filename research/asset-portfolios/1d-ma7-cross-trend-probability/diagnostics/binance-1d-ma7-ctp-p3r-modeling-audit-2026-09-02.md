# BIN-1D-MA7-CTP P3R 建模审计

状态：`explore / diagnostic-only / not promoted / not live-ready`。裁决：`SUGGESTIVE_CONTEXT_INCREMENT_ONLY`。

## 机械修复记录

- 原 P3 合同要求 `feature_known_at < entry_ts`，严格样本全部为等于关系，故 P3 训练前停止。
- P3R 只修复为 `feature_known_at == entry_ts == ts + 1 day`；没有修改标签、样本、特征、模型候选或裁决门槛。
- 前向校准调用 P2 修复后的逻辑：只有更早 OOF 可参与当前 fold 校准，且若前向 Brier/LogLoss 未改善则冻结 raw。

## 输入完整性

- P0R manifest SHA256：`033e12bf77c5d67f4871845e3fc2650dfa26a09ca8f74983f379d84e388f93ef`；artifact 哈希全部匹配：`True`。
- P2 feature spec SHA256：`ac4feb1270bb2d0b1da4d1523a84763ada808ec02b409559a603608cceec2c68`；原 P3 feature spec SHA256：`0862eed0a974684ba16a962ebe146cdefbbc6af7cd6e7532f69c8a4554b61f8b`。
- B0 精确复用 P2 F1：`True`；P3R feature arrays 与原 P3 一致：`{'feature_blocks': True, 'candidate_feature_blocks': True, 'categorical_features': True, 'derived_features': True}`。

## 隔离与样本

- HYPE 输入/事件/OOF/模型卡：`0/0/0/0`。
- 2025+ 事件读取/预测写出：`0/0`。
- 已知 TradFi 严格样本事件：`0`；底层 post-2025 可用行只记录为 `550036`，不进入建模。

## 模型与审计

- 所有候选使用同一严格样本行；只训练 pooled Logistic Regression，不训练 long/short heads，不训练 LightGBM。
- 数值中位数、类别 one-hot 与 StandardScaler 均只在训练折拟合；D1-D3 purge 全部通过。
- 28 日 paired bootstrap 使用同一重采样索引，draw hash：`fb08ba2b319f7f2e2a2ef11844824b0638031992d4129a55cef9496c39a762d6`。

## 禁止产物

- 无 HYPE、无 2025+ 预测、无策略、无仓位、无权益曲线、无 live spec、无 live-ready。
