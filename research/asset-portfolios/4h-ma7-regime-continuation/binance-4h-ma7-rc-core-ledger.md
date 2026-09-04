# Binance-4H-MA7-Regime-Continuation Core Ledger

## Family Identity

- Full family name / alias：`Binance-4H-MA7-Regime-Continuation` / `BIN-4H-MA7-RC`。
- Market / timeframe：Binance USD-M USDT perpetual，point-in-time 动态全市场币池，UTC `4h`。
- Mechanism：固定 `SMA7` 严格穿越只定义 long/short 事件；P0 无条件检验穿越后 `+2 ATR / -1 ATR / 30 bars` first-hit、固定期限收益、MFE/MAE 与 MA7 同侧生存是否优于同侧非穿越基准。
- Boundary：这是全新的 `4h` 独立家族，不是 `BIN-1D-MA7-RC` 新版本；不继承 `HYPE-4H-MA7-ABT` 的参数、收益或结论；不继承 `BIN-4H-EMAX-LGBM` 的信号或模型。`4h SMA7` 约 28 小时，`4h SMA42` 只作七日等时钟对照。

## Current State

- Current observation：`P0R-GAP-GUARD` 已落地；`P0` 仍是六资产诊断；`P0R-DATA` 全市场绩效尚未写出。
- Status：`explore / diagnostic-only / not promoted / not live-ready`；数据结论仍为 `DATA_SCOPE_INCOMPLETE / six-asset diagnostic-only` 叠加“全市场绩效未写出”。
- Runner / dry-run / live：none；不得创建 runner、live spec、dry-run 或 live 实现。
- Result：P0 六资产 `NO-GO` 不能外推全市场。缺口保护验收为 `PASS`（测试 + 连续窗口一致 + 全量窗口盘点），不是策略有效或可上线。
- Next gate：完整研究必须使用缺口保护后的有效样本分母；仍不得根据六资产结果调参。P0 仍不允许进入 P1。

## Version Rules

- P0 是 observation，不是 `V1`；本线当前没有 registered strategy version。
- 用户明确“登记 / 冻结 Vx”前不得产生版本号；登记也只会进入 `registered`，不自动 promotion。
- 更换 MA 主周期、MA 长度、事件定义、PIT 币池、执行时序、first-hit 障碍、持有期限、成本、funding 或分层基准定义，均须新 observation 合同并先冻结。
- `SMA5/SMA10/SMA42` 只作 P0 对照，不得根据结果改写主研究对象 `SMA7`。

## Version Table

| Observation | Status | Role / Core Idea | Key Frozen Metrics | Evidence | Decision |
| --- | --- | --- | --- | --- | --- |
| `P0` | `explore / diagnostic-only / not promoted / not live-ready` | 无条件 `4h SMA7` strict-cross 延续性 kill test，但输入 1h 非全市场 | 原生 `SMA7` 事件 `5,947` / 6 symbols；六资产样本 long/short `NO-GO`；配置 SHA256 `eb62108271cf1d22992fb53c0c1a7438d605581d96cb079d75b0579143c84642` | [P0 合同](specs/binance-4h-ma7-regime-continuation-p0-contract-2026-09-02.md) · [结果](diagnostics/binance-4h-ma7-regime-continuation-p0-results-2026-09-02.md) · [数据范围修正](diagnostics/binance-4h-ma7-regime-continuation-p0-data-scope-correction-2026-09-02.md) · [summary](artifacts/binance_4h_ma7_rc_p0_summary_2026-09-02.json) | 六资产 `NO-GO` 不得外推全市场 |
| `P0R-DATA` | `explore / diagnostic-only / not promoted / not live-ready` | 全市场数据范围重跑；取数改 catalog derived 4h/1h | 合同已冻结；全市场结果尚未写出 | [P0R-DATA 合同](specs/binance-4h-ma7-regime-continuation-p0r-data-contract-2026-09-03.md) · [脚本](scripts/research_binance_4h_ma7_regime_continuation_p0r_data.py) | 不覆盖 P0；未完成跑批 |
| `P0R-GAP-GUARD` | `explore / diagnostic-only / not promoted / not live-ready` | 研究脚本缺口隔离、分母修正与全量窗口盘点 | 缺口保护 `PASS`；事件 `first_hit_30` 有效 `4,389,839` / `4,405,573`；配置 SHA256 `71306a2b45471f1e8e24fcd0d6a621a94c95be7bc83e65a69c2fa6faa61bd67d` | [合同](specs/binance-4h-ma7-regime-continuation-p0r-gap-guard-contract-2026-09-03.md) · [验收](diagnostics/binance-4h-ma7-regime-continuation-p0r-gap-guard-2026-09-03.md) | 不是策略有效；不覆盖 P0 / P0R-DATA |

## Shared Assumptions

- Data：P0 实际读取的是 `PARTIAL_SCOPE_LEGACY` normalized `1h`，不能代表全市场历史。`P0R-DATA` 必须改用 `binance.perp.ohlcv.4h.from_15m.v1`（必要时辅以 `1h.from_15m.v1`）。
- Universe：PIT 动态全市场池；上市龄 `>=30` 自然日，30 日 trailing ADV `>=10,000,000 USDT`，30 日覆盖率 `>=95%`，每日最多 ADV 前 `120`；不使用当前 TopN 回填历史。
- Execution：信号在 `4h` bar `t` 收盘确认，最早下一根 `4h` `open[t+1]` 成交；first-hit 顺序用未来真实 `1h` high/low，双障碍同一 `1h` 保守记 adverse-first。
- Cost：手续费 `0.001/fill`；基准滑点 `4 bps/fill`，压力滑点 `8 bps/fill`；固定期限 round-trip 包含开平两次成本；funding 按真实事件时间和方向计算，缺失则阻断净收益和可交易结论。

## Evidence Map

- [Family README](README.md)
- [P0 frozen contract](specs/binance-4h-ma7-regime-continuation-p0-contract-2026-09-02.md)
- [P0 frozen config](configs/binance-4h-ma7-regime-continuation-p0.json)
- [P0 dataset manifest](artifacts/binance_4h_ma7_rc_p0_dataset_manifest_2026-09-02.json)
- [P0 results](diagnostics/binance-4h-ma7-regime-continuation-p0-results-2026-09-02.md)
- [P0 data-scope correction](diagnostics/binance-4h-ma7-regime-continuation-p0-data-scope-correction-2026-09-02.md)
- [P0R-DATA handoff](../../platform/data-lake-governance/specs/binance-4h-ma7-rc-p0r-data-handoff-2026-09-02.md)
- [P0R-DATA 合同](specs/binance-4h-ma7-regime-continuation-p0r-data-contract-2026-09-03.md)
- [P0 summary](artifacts/binance_4h_ma7_rc_p0_summary_2026-09-02.json)
- [P0 script](scripts/research_binance_4h_ma7_regime_continuation_p0.py)
- [P0R-DATA 脚本](scripts/research_binance_4h_ma7_regime_continuation_p0r_data.py)
- [P0R-GAP-GUARD 合同](specs/binance-4h-ma7-regime-continuation-p0r-gap-guard-contract-2026-09-03.md)
- [P0R-GAP-GUARD 验收](diagnostics/binance-4h-ma7-regime-continuation-p0r-gap-guard-2026-09-03.md)
- [P0R-GAP-GUARD 脚本](scripts/research_binance_4h_ma7_regime_continuation_p0r_gap_guard.py)
- [Artifacts index](artifacts/README.md)
- [Decision log](decision-log.md)
