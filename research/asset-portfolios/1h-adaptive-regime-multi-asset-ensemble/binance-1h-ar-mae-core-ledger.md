# Binance-1H-Adaptive-Regime-Multi-Asset-Ensemble 主账

## 家族身份

- Full family name：`Binance-1H-Adaptive-Regime-Multi-Asset-Ensemble`
- Short id：`BIN-1H-AR-MAE`
- Market：Binance USD-M Futures perpetual，`TRXUSDT / SOLUSDT / HYPEUSDT / ETHUSDT / BTCUSDT / BNBUSDT`
- Timeframe：`1h`
- 机制：六个单资产 1h adaptive-regime 家族最新登记版本的多资产组合；各 sleeve 保持家族冻结交易路径，不做信号层融合。当前正式登记版 `V1` 采用全账户单仓槽位、先到先得结构。

本家族是组合研究线，不改变、不代表任何成分家族的版本身份。成分版本引用必须带家族全名。

## 当前状态

- 当前版本：`BIN-1H-AR-MAE-V1`。
- 当前状态：`dry-run / not live-ready`；实际实例启用、模式与 live 边界只以 quant-runner 为准。
- Runner：strict replay 选择统计 `522/371/151/22`、逐笔 `371/371` parity PASS；最新状态见 [runner tracking](runner-tracking/binance-1h-ar-mae-v1-runner-status.md)。
- 历史 pre-dry-run 风险：原始 V1 full DD `-21.43%`，账户 overlay 在额外成本下仍越过 `<20%` 门槛；这些 finding 继续约束 live，但不构成当前 `NO-GO`、`not promoted` 或禁止 dry-run 声明。
- Live blockers：持续 dry-run 与 strict replay 语义差异、真实订单/成交、online open/close reconciliation、重启恢复、missing-data fail-closed 与成本/滑点证据。
- 下一决策门：补齐 runner-tracking 与线上开平仓对账后再决定是否申请 live；当前不得启用 live。

## 成分版本冻结表

| Sleeve | 成分版本 | 成分主账 | V1 账户槽位 |
| --- | --- | --- | --- |
| TRX | `TRX-1H-Adaptive-Regime-V3` | `../../trx/1h-adaptive-regime/trx-1h-ar-core-ledger.md` | 候选交易参与全账户单仓竞争；中选时占用全额账户权益 |
| SOL | `SOL-1H-Adaptive-Regime-V2` | `../../sol/1h-adaptive-regime/sol-1h-ar-core-ledger.md` | 候选交易参与全账户单仓竞争；中选时占用全额账户权益 |
| HYPE | `HYPE-1H-Adaptive-Regime-V4` | `../../hype/1h-adaptive-regime/hype-1h-ar-core-ledger.md` | 候选交易参与全账户单仓竞争；中选时占用全额账户权益 |
| ETH | `ETH-1H-Adaptive-Regime-V3` | `../../eth/1h-adaptive-regime/eth-1h-ar-core-ledger.md` | 候选交易参与全账户单仓竞争；中选时占用全额账户权益 |
| BTC | `BTC-1H-Adaptive-Regime-V4` | `../../btc/1h-adaptive-regime/btc-1h-ar-core-ledger.md` | 候选交易参与全账户单仓竞争；中选时占用全额账户权益 |
| BNB | `BNB-1H-Adaptive-Regime-V3` | `../../bnb/1h-adaptive-regime/bnb-1h-ar-core-ledger.md` | 候选交易参与全账户单仓竞争；中选时占用全额账户权益 |

组合回测前逐 sleeve 与成分主账 current full 指标核对，annual/DD/win/trades 全部一致（脚本内硬校验，漂移即抛错）。

## 版本规则

- `V1`：全账户单仓、先到先得的六资产组合版本；六个成分 sleeve 固定为 TRX V3、SOL V2、HYPE V4、ETH V3、BTC V4、BNB V3；候选交易来自各家族冻结路径；同一时间只允许一笔账户级持仓；持仓期间忽略其他所有信号；同小时平手按成分家族冻结 current-full 年化降序裁决；中选交易占用全额权益并按 sleeve 冻结杠杆执行。当前状态为 `dry-run / not live-ready`。
- `BIN-1H-AR-MAE-FIRST-2026-07-07` 是 V1 登记前的等权 `1/6` 组合 diagnostic observation，不是正式版本，不改变 `V1` 身份。
- 后续若用户要求登记 `V2` 或更高版本，必须冻结：成分版本清单、账户级持仓/资金规则、冲突/平手优先级、组合窗口与证据链接，并更新本主账。
- 任何成分家族升级版本（例如 TRX V4）不自动进入本组合；组合成分变更必须作为新 observation 或新版本重新回测并记录。
- 进入 promotion 状态前必须完成组合层 K+2/滑点/成本压力、再平衡/单仓资金结构审计和六资产生产状态机的 live-executable 审计。

## 版本与观察记录

| Version / Observation | Status | 结构 | 关键指标 | Evidence | Live readiness |
| --- | --- | --- | --- | --- | --- |
| `BIN-1H-AR-MAE-FIRST-2026-07-07` | historical pre-dry-run finding | 六 sleeve 等权 `1/6`，小时再平衡主口径 + 不再平衡对照 | full `4.069x / +1284.22% / -4.43% DD / 89.66% win / 522 trades / PF 6.627`；reused holdout `1.625x / +12.72% / 75.38% win` | [首次组合回测](notes/binance-1h-ar-mae-first-combination-backtest-2026-07-07.md) | 登记前历史观察；不代表当前状态 |
| `Binance-1H-Adaptive-Regime-Multi-Asset-Ensemble-V1` (`BIN-1H-AR-MAE-V1`) | dry-run / not live-ready | 全账户单仓槽位、先到先得；持仓期间忽略其他信号；中选交易按 sleeve 冻结杠杆执行 | full `287.01x / -21.43% DD / 90.30% win / 371 trades`；strict replay `371/371` parity PASS | [完整规格](specs/binance-1h-ar-mae-v1-full-reproduction-spec-2026-07-07.md)；[单仓回测](notes/binance-1h-ar-mae-single-position-backtest-2026-07-07.md)；[runner tracking](runner-tracking/binance-1h-ar-mae-v1-runner-status.md) | 实际 dry-run 配置以 quant-runner 为准；历史 DD 与执行缺口继续阻塞 live |
| `BIN-1H-AR-MAE-V1-RISK-OVERLAY-2026-07-09` | historical pre-dry-run finding / not registered | 全局 cap、TRX cap/剔除与成本压力账户 overlay | `cap2.5x` full `122.81x / -18.68% DD`；extra `4 bps/fill` 为 `-19.19% DD`；double-cost 约 `-25.5% DD` | [风险覆盖层诊断](notes/binance-1h-ar-mae-v1-risk-overlay-diagnostics-2026-07-09.md) | 历史风险证据；不覆盖 active dry-run 身份 |
| `BIN-1H-AR-MAE-V1-TRX-TARGETED-TAIL-2026-07-10` | historical pre-dry-run finding / not registered | 只缩放中选 TRX `macd_flip`，非 TRX 暴露不变 | full `231.59x / -19.99% DD`；extra `4 bps/fill` 为 `-20.18% DD` | [TRX 定向尾部诊断](notes/binance-1h-ar-mae-v1-trx-targeted-tail-overlay-2026-07-10.md) | 历史风险证据；不覆盖 active dry-run 身份 |

## Promotion 边界

- 成分家族的 promotion 门槛与失败边界全部继承；组合不清洗 reused holdout 失败、K+2/8bps 压力失败与执行审计缺失。
- 最近三个月对全部六个家族都是已揭盲区间，组合层同样不得当作 fresh OOS 使用。
- 小时再平衡的资金划转摩擦未计入；促升前必须给出实盘可执行的再平衡（或不再平衡）资金结构。
- 本节其余条目是进入 dry-run 前的历史门禁记录。实际 dry-run/live 授权只以 quant-runner 为准；在完成 live-executable 审计、runner 观察与 online open/close reconciliation 前，研究侧不支持 live promotion。

## Evidence Map

- 2026-09-03 README 压缩：完整原文见 [decision-log.md](decision-log.md) 当日条目。
- V1 规格：[完整复现规格](specs/binance-1h-ar-mae-v1-full-reproduction-spec-2026-07-07.md) · [简版规格](specs/binance-1h-ar-mae-v1-single-position-spec-2026-07-07.md)
- Notes：[首次组合回测](notes/binance-1h-ar-mae-first-combination-backtest-2026-07-07.md) · [单仓回测](notes/binance-1h-ar-mae-single-position-backtest-2026-07-07.md) · [风险覆盖层](notes/binance-1h-ar-mae-v1-risk-overlay-diagnostics-2026-07-09.md) · [TRX 尾部根因](notes/binance-1h-ar-mae-v1-trx-tail-risk-optimization-2026-07-10.md) · [TRX 定向尾部](notes/binance-1h-ar-mae-v1-trx-targeted-tail-overlay-2026-07-10.md) · [周度统计](notes/binance-1h-ar-mae-v1-weekly-stats-2026-07-09.md)
- Runner：[runner-tracking](runner-tracking/binance-1h-ar-mae-v1-runner-status.md)
- 脚本：`scripts/research_binance_1h_ar_multi_asset_ensemble_backtest.py`、`scripts/research_binance_1h_ar_mae_single_position_backtest.py`
