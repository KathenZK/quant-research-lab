# BIN-1D-MA7-CTP P5 RSI6、完整周线趋势增量与2025+验证审计

- 状态：`explore / diagnostic-only / not promoted / not live-ready`
- 全局裁决：`NO_NEW_INCREMENT_B0_REMAINS_REFERENCE`
- 研究问题：严格 MA7 方向穿越后，从下一 UTC 日 open 开始，未来 20 日是否先触及顺向 `+2 ATR` 而非逆向 `-1 ATR`。
- 2025+ 数据角色：`ITERATIVE_REUSED_VALIDATION_2025_PLUS`；P1 已观察过，不是最终盲测；P5 仅用于预注册候选的迭代验证，不参与训练、校准或阈值拟合。

## 数据切分

- 开发集复现 P4 严格样本：52563 事件，338 资产，long/short 26237/26326，日期 2019-11-27 00:00:00+00:00 至 2024-12-10 00:00:00+00:00，最大标签结束 2024-12-31 00:00:00+00:00。
- HYPE：开发集 0 行，2025+ 验证 0 行；HYPE 原始 price 分区未读取。
- 2025+ 总事件 46992，其中主加密验证 46892，known TradFi 排除 100。
- 2025+ 分年主加密事件：{'2025': 32111, '2026': 14781}。

## 候选表现

| Candidate | Dev Macro AUC/Top10 | 2025+ AUC/Top10 | 2025 | 2026 | vs B0 AUC CI | vs B0 Top10 CI | Verdict |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `R_B0_69` | 0.5716/0.4160 | 0.5589/0.3511 | 0.5629/0.3440 | 0.5529/0.3665 | ref | ref | `NO_NEW_INCREMENT_B0_REMAINS_REFERENCE` |
| `C_NO_G3_58` | 0.5710/0.4504 | 0.5614/0.3701 | 0.5713/0.3739 | 0.5407/0.3617 | -0.0099/0.0162 | -0.0083/0.0466 | `NO_NEW_INCREMENT_B0_REMAINS_REFERENCE` |
| `C_B0_PLUS_RSI_79` | 0.5620/0.4134 | 0.5551/0.3613 | 0.5582/0.3443 | 0.5508/0.3982 | -0.0124/0.0044 | -0.0217/0.0434 | `NO_NEW_INCREMENT_B0_REMAINS_REFERENCE` |
| `C_B0_PLUS_WEEKLY_80` | 0.5731/0.4361 | 0.5640/0.3615 | 0.5718/0.3627 | 0.5500/0.3590 | -0.0042/0.0148 | -0.0092/0.0213 | `NO_NEW_INCREMENT_B0_REMAINS_REFERENCE` |
| `C_B0_PLUS_RSI_WEEKLY_90` | 0.5651/0.4333 | 0.5602/0.3662 | 0.5664/0.3633 | 0.5494/0.3725 | -0.0095/0.0125 | -0.0168/0.0428 | `NO_NEW_INCREMENT_B0_REMAINS_REFERENCE` |
| `C_NO_G3_PLUS_RSI_WEEKLY_79` | 0.5623/0.4596 | 0.5599/0.3782 | 0.5702/0.3833 | 0.5387/0.3671 | -0.0133/0.0165 | -0.0180/0.0722 | `NO_NEW_INCREMENT_B0_REMAINS_REFERENCE` |

## 主要增量结论

- `C_NO_G3_58` 验证期 AUC diff CI：-0.0099 至 0.0162；Top10 success diff CI：-0.0083 至 0.0466。G3 删除假设裁决：`NO_NEW_INCREMENT_B0_REMAINS_REFERENCE`。
- `G7_RSI6_OSCILLATOR` 单独增量候选 `C_B0_PLUS_RSI_79` 验证期 AUC diff CI：-0.0124 至 0.0044；Top10 diff CI：-0.0217 至 0.0434。
- `G8_COMPLETED_WEEKLY_REGIME` 单独增量候选 `C_B0_PLUS_WEEKLY_80` 验证期 AUC diff CI：-0.0042 至 0.0148；Top10 diff CI：-0.0092 至 0.0213。
- 本轮仍只评估弱排序器；未生成策略、权益曲线、Sharpe、live spec、runner handoff、交易路径 HTML 或 HYPE reveal。

## 证据文件

- [feature spec](../artifacts/binance_1d_ma7_ctp_p5_feature_spec.json)
- [data audit](../artifacts/binance_1d_ma7_ctp_p5_data_audit.json)
- [fold metrics](../artifacts/binance_1d_ma7_ctp_p5_fold_metrics.parquet)
- [pre-2025 OOF predictions](../artifacts/binance_1d_ma7_ctp_p5_pre2025_oof_predictions.parquet)
- [2025+ validation predictions](../artifacts/binance_1d_ma7_ctp_p5_validation_2025_plus_predictions.parquet)
- [paired comparisons](../artifacts/binance_1d_ma7_ctp_p5_paired_comparisons.parquet)
- [strata](../artifacts/binance_1d_ma7_ctp_p5_strata.parquet)
- [summary](../artifacts/binance_1d_ma7_ctp_p5_summary.json)

## 下一步

若本轮未出现可复现的线性增量，应停止在同一线性候选空间继续微调；若存在稳定尾部改善但整体 AUC 仍弱，可把结论限定为非线性建模候选输入，而不是 promotion 或策略登记。
