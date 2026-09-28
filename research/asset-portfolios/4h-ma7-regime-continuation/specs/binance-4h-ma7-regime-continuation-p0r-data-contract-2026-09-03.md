# BIN-4H-MA7-RC P0R-DATA 冻结合同（2026-09-03）

- 家族：`Binance-4H-MA7-Regime-Continuation`（`BIN-4H-MA7-RC`）
- 观察：`P0R-DATA`，数据范围重跑；不是调参，不是 `V1`，不登记、不晋升。
- 状态：`explore / diagnostic-only / not promoted / not live-ready`
- 冻结时间：`2026-09-03T02:14:00Z`
- 配置：[../configs/binance-4h-ma7-regime-continuation-p0r-data.json](../configs/binance-4h-ma7-regime-continuation-p0r-data.json)
- 配置 SHA256：`4b4ceadcffea866a2783f4acfc06ecc445c4ad533c130a8ce94447bad5b55ff5`
- 输入 manifest：[../artifacts/binance_4h_ma7_rc_p0r_data_dataset_manifest_2026-09-03.json](../artifacts/binance_4h_ma7_rc_p0r_data_dataset_manifest_2026-09-03.json)
- 输入 manifest SHA256：`651bd88b5e349091c36b0de74b2a480b3f44383c22a1f58e11177e33dc9155ae`
- 父观察 P0 合同：[binance-4h-ma7-regime-continuation-p0-contract-2026-09-02.md](binance-4h-ma7-regime-continuation-p0-contract-2026-09-02.md)
- 数据交接：[../../../platform/data-lake-governance/specs/binance-4h-ma7-rc-p0r-data-handoff-2026-09-02.md](../../../platform/data-lake-governance/specs/binance-4h-ma7-rc-p0r-data-handoff-2026-09-02.md)

本文件冻结**数据入口替换**。机制、事件定义、PIT 规则、成本、first-hit、持有期和 PASS/NO-GO 口径全部沿用 P0，不得因六资产 `NO-GO` 增加过滤器、改 MA、改方向或改持仓期。

## 为什么重跑

P0 行级质量通过，但读取的是 `binance.perp.ohlcv.1h.normalized.legacy` / `PARTIAL_SCOPE_LEGACY`。主 `SMA7` 只有 6 个长期历史币。该 `NO-GO` 只能记为 `DATA_SCOPE_INCOMPLETE / six-asset diagnostic-only`，不能外推全市场。

P0 产物与 `.sha256` 全部保留，本观察不得覆盖。

## 数据入口（唯一允许变更）

- 禁止读取 `binance.perp.ohlcv.1h.normalized.legacy`，禁止 glob `data/normalized/ohlcv/.../timeframe=1h`。
- 原生 `0h` 主面板必须通过 `dataset_id` 加载 `binance.perp.ohlcv.4h.from_15m.v1`，`requested_scope=FULL_MARKET`。
- first-hit 的 `1h` 路径与 phase `1/2/3` 的 1h→4h 重聚合只允许 `binance.perp.ohlcv.1h.from_15m.v1`。
- Funding 仍用 P0 的 normalized funding 路径与秒级名义时间归一。
- 截止不变：`cutoff_exclusive_utc = 2026-08-24T08:00:00Z`；最后允许闭合 `1h` `2026-08-24T07:00:00Z`；最后允许完整 `4h` `2026-08-24T04:00:00Z`。

原生 `4h` 已由 accepted `15m` 按 `ohlcv_resample_from_15m_v1` 生成（每根完整 `4h` = 16 根连续闭合合法 `15m`）。PIT ADV 必须使用该衍生 `4h` 的 `quote_volume`，不得混用 legacy `1h` 成交额。

## 沿用且不得改写的 P0 假设

见 P0 合同。摘要：固定 `SMA5/7/10/42`，主研究 `SMA7` 严格穿越；信号在 `4h` 收盘，下一根 `4h` open 成交；first-hit `+2/−1 ATR / 30 bars`，`ATR_scale=ATR20[t-1]`，同一 `1h` 双击 adverse-first；手续费 `0.001`/fill，滑点 `4/8 bps`；PIT 上市龄 30 日、ADV≥10M、覆盖率≥95%、每日最多 120；统计种子 `20260902`、1000 次 symbol×UTC 周 block bootstrap、BH-FDR；long/short 分侧裁决。

## 明确不修复的统计 blocker

本轮**不改**下列 P0 统计代码，除非用户另行授权。报告必须复述：

1. 完整年度窗口只统计 `2023–2025` 三个日历年，PASS 却要求至少四个正年度，故 `SUPPORTED_WEAK_CONTINUATION` 在现口径下不可达。
2. horizon 表先写入 bootstrap `p_value`，随后 `**cluster` 用同名 `p_value` 覆盖，导致 CI 与 p/q-value 检验对象不一致。

## 输出与禁令

- 新文件名必须含 `p0r_data` / `p0r-data`，不得写入任何 `*p0*2026-09-02*` 路径。
- 无论裁决如何，家族状态保持 `explore / diagnostic-only / not promoted / not live-ready`。
- 不得登记 `V1`、不得 promotion、不得写 `quant-runner`、不得创建 live spec。
