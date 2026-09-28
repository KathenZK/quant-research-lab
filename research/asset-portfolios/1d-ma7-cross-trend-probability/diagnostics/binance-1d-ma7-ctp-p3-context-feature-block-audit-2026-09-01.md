# BIN-1D-MA7-CTP P3：Independent Context Feature Block Audit

> 状态：`explore / diagnostic-only / not promoted / not live-ready`
> 裁决：`DATA_BLOCK_NOT_READY`

## 结论

P3 在合同锁定后、训练前的数据审计阶段停止，没有训练模型，没有生成 OOF 预测，没有运行 2025+ 历史测试，也没有形成任何策略或 live-ready 产物。

阻断原因是合同要求 `feature_known_at < entry_ts` 必须全部成立；严格样本 `52,563` 行中该条件通过 `0` 行，全部为 `feature_known_at == entry_ts`，因此按 P3 合同裁决 `DATA_BLOCK_NOT_READY`。

## 合同锁

- 合同：[binance-1d-ma7-ctp-p3-context-feature-block-audit-contract-2026-09-01.md](../specs/binance-1d-ma7-ctp-p3-context-feature-block-audit-contract-2026-09-01.md)
- Feature spec：[binance_1d_ma7_ctp_p3_feature_spec.json](../artifacts/binance_1d_ma7_ctp_p3_feature_spec.json)
- Contract lock：[binance_1d_ma7_ctp_p3_contract_lock.json](../artifacts/binance_1d_ma7_ctp_p3_contract_lock.json)
- 合同 SHA256：`0c35994ef38cb571ad71eaa3f16c635484c532fd6d683a96f5c73934c7b740cc`
- Feature spec SHA256：`0862eed0a974684ba16a962ebe146cdefbbc6af7cd6e7532f69c8a4554b61f8b`

## 数据审计

| 项目 | 结果 |
| --- | ---: |
| P0R manifest artifact SHA256 | 全部匹配 |
| `holdout_read` | `false` |
| HYPE 输入行 | `0` |
| HYPER 输入行 | `806` |
| 原始 pre-2025 MA7 事件 | `54,137` |
| 原始 pre-2025 非 MA7 穿越 | `0` |
| 原始 pre-2025 `asset+ts` 重复 | `0` |
| 严格样本行数 | `52,563` |
| 严格样本资产数 | `338` |
| 严格样本 long / short | `26,237 / 26,326` |
| 严格样本日期 | `2019-11-27` 至 `2024-12-10` |
| 严格样本 `label_end_ts_20d` 最大值 | `2024-12-31` |
| 空标签 | `0` |
| 不完整 20 日未来路径 | `0` |
| `feature_known_at < entry_ts` | `0` |
| `feature_known_at == entry_ts` | `52,563` |
| `feature_known_at > entry_ts` | `0` |

## 未执行内容

因数据门禁已失败，以下内容没有执行：

- D1/D2/D3 Logistic 训练；
- B0/B1/B2/B3/B4 增量比较；
- 2,000 次 paired block-bootstrap；
- OOF 预测文件；
- fold metrics / incremental comparisons parquet；
- model card；
- 任何 2025+ 预测或 HYPE reveal。

## 边界说明

P3 没有读取 HYPE 资产行，没有使用 2025 年及以后事件做训练或预测，没有训练 long/short 独立头，没有训练退出、持仓或反手模型。该实验仍是 `explore / diagnostic-only / not promoted / not live-ready`。
