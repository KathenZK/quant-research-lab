# BIN-1D-MA7-CTP P6 市场环境 × 多空方向的条件排序价值审计

- 状态：`explore / diagnostic-only / not promoted / not live-ready`
- 实验裁决：`MARKET_OR_SIDE_VALUE_ONLY`；新 OOS：`PENDING_FRESH_OOS`
- P6 受已经观察到的 2025+ 启发；2025+ 是 `ITERATIVE_REUSED_VALIDATION_2025_PLUS`，不是首次盲测。

## 大白话结论

- 市场环境与方向能解释裸成功率的表面差异：六格基础成功率见指标表，最高/最低格差异来自市场时段和方向，不等于选币能力。
- 同一天同方向选币主检验：B0 在 2025+ 的 Top5 相对同日同方向随机基准成功率增量为 -0.0015，M1 为 -0.0136；M1 事件标签净收益增量为 -0.0037。
- 已成立：2025+ 不是新盲测，HYPE 仍为 0，市场状态还原 long/short 一致，M1 使用前向 B0 样本外分数训练。
- 仍是线索：任何局部六格或方向优势必须看 paired bootstrap、多重比较和集中度，不能说成全市场选币模型有效。
- 继续/停止：当前裁决为 `MARKET_OR_SIDE_VALUE_ONLY`；若未达到 +5pp 且净收益增量为正的研究预算门槛，应停止或只保留局部观察，不继续扩特征。
- 真正新 OOS：本轮没有合格未揭示标签窗口；若未来继续，必须先走数据湖 canonical dataset 与迁移对账，再按 prospective 协议一次性确认。

## 核心数字

| Scope | Model | AUC | PR-AUC | Top5 success | Top5 uplift |
| --- | --- | ---: | ---: | ---: | ---: |
| `development_oof` | `R_B0_69` | 0.5716 | 0.3734 | 0.4210 | 0.0983 |
| `development_oof` | `M0_MARKET_ONLY` | 0.4861 | 0.3255 | 0.3291 | 0.0064 |
| `development_oof` | `M1_B0_X_SIDE_X_REGIME` | 0.5086 | 0.3346 | 0.3526 | 0.0299 |
| `validation_2025_plus` | `R_B0_69` | 0.5589 | 0.3499 | 0.3463 | 0.0291 |
| `validation_2025_plus` | `M0_MARKET_ONLY` | 0.5175 | 0.3257 | 0.3198 | 0.0027 |
| `validation_2025_plus` | `M1_B0_X_SIDE_X_REGIME` | 0.5410 | 0.3404 | 0.3386 | 0.0214 |
| `validation_2025` | `R_B0_69` | 0.5629 | 0.3542 | 0.3263 | 0.0034 |
| `validation_2025` | `M0_MARKET_ONLY` | 0.4954 | 0.3145 | 0.2403 | -0.0825 |
| `validation_2025` | `M1_B0_X_SIDE_X_REGIME` | 0.5426 | 0.3477 | 0.3518 | 0.0290 |
| `validation_2026` | `R_B0_69` | 0.5529 | 0.3434 | 0.3973 | 0.0925 |
| `validation_2026` | `M0_MARKET_ONLY` | 0.5669 | 0.3584 | 0.4176 | 0.1128 |
| `validation_2026` | `M1_B0_X_SIDE_X_REGIME` | 0.5415 | 0.3278 | 0.3324 | 0.0276 |

## 证据

- [config](../artifacts/binance_1d_ma7_ctp_p6_config.json)
- [exposure ledger](../artifacts/binance_1d_ma7_ctp_p6_exposure_ledger.json)
- [data audit](../artifacts/binance_1d_ma7_ctp_p6_data_audit.json)
- [B0 reproduction audit](../artifacts/binance_1d_ma7_ctp_p6_b0_reproduction_audit.json)
- [predictions](../artifacts/binance_1d_ma7_ctp_p6_predictions.parquet)
- [market state metrics](../artifacts/binance_1d_ma7_ctp_p6_market_state_metrics.parquet)
- [selection metrics](../artifacts/binance_1d_ma7_ctp_p6_selection_metrics.parquet)
- [paired bootstrap stats](../artifacts/binance_1d_ma7_ctp_p6_paired_bootstrap_stats.parquet)
- [summary](../artifacts/binance_1d_ma7_ctp_p6_summary.json)
- [prospective protocol](../specs/binance-1d-ma7-ctp-p6-prospective-oos-confirmation-protocol-2026-09-03.md)
