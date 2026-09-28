# BIN-1D-MA7-CTP P7A 实现审计

- 状态：`explore / diagnostic-only / placebo-audit / not promoted / not live-ready`
- 全局裁决：`CROSS_MOVEMENT_EFFECT_WITHOUT_DIRECTIONAL_EDGE`
- 合同锁：`FROZEN_BEFORE_P7A_PLACEBO_OUTPUT_READ`
- config sha256：`ecefe83ef8615936bdb6aa2aefb57e23b111217950f134119457ecd7df6f45f9`
- contract sha256：`6873b117cd3e341f9e66831cf43783cfb1b9e612a9ef607f8480543a5b9ecd76`
- manifest sha256：`4fb047d6ad91e96303a650a28e04e5c6198e379f678d3ef2f46262e4407a5f6c`

## 输入隔离

- P7 输入文件数：`0`（必须为 0）
- HYPE 原始分区读取：`False`
- HYPE 行数：`0`
- HYPER 行数：`76`
- files_read 含 `hype_usdt_usdt`：`False`

## Canonical first-hit

- 主结果使用 P0R 冻结 `label_entry_success_20d` / `label_entry_net_return` / `label_entry_result`。
- 敏感性调用 CATL P0 `result_from_hours` 与 `hit_net_return`，同一 entry/ATR/未来小时路径。
- 小时路径 2/1/20D 与冻结标签比对：compared=932024 mismatches=0。
- same-hour 双触使用 adverse-first。
- random-side 主结果是 0.5×long+0.5×short 精确期望。
- 日期加权使用真实 Cross 的 `n_real_cross[d]`。

## 未做的事

- 无 ML 模型、无策略权益曲线、无 Sharpe/CAGR、未改 P0–P7 冻结产物、未改共享 README/ledger/decision log。

运行命令：`/Users/ZK/OpenCode/quant-strategy-lab/.venv/bin/python research/asset-portfolios/1d-ma7-cross-trend-probability/scripts/run_binance_1d_ma7_ctp_p7a_placebo_base_rate_audit.py`

