# Binance-1D-MA7-Cross-Expansion-Regime Core Ledger

## Family Identity

- Full family name：`Binance-1D-MA7-Cross-Expansion-Regime`
- Alias：`BIN-1D-MA7-CER`
- Market / exchange / symbol / timeframe：Binance USD-M USDT 永续，完整 UTC `1d`；动态历史宇宙；封存 `HYPE/USDT:USDT`，保留 `HYPER/USDT:USDT`
- Mechanism summary：MA7 Cross 只作为无方向 expansion event marker；P0 比较 Cross 与同日 non-cross 的未来扩张，不预测 LONG/SHORT。
- Boundary / collision warnings：不是 `BIN-1D-MA7-CTP` 的后续阶段；不得把 CTP 的 directional first-hit 标签、B0 或 69 特征当作本家族证据。

## Current State

- Current version(s)：无登记版本；P0 诊断已完成。
- Current status：`explore / diagnostic-only / not promoted / not live-ready`
- Runner / dry-run / live status：无
- Live-readiness blockers：P0 裁决 `NO_EXPANSION_EDGE`；未形成策略；无 runner。
- Next decision gate：STOP。不进入 P1，不把本家族做成方向或 expansion 交易策略。

## Version Rules

- Registration / freeze：只固定版本身份并更新本表，默认状态 `registered`，不表示 promotion。
- Promotion：必须明确目标 `live spec` / `dry-run` / `live`；不得由“登记 Vx”推断。
- `V1`：尚未登记。
- `Vx.y`：参数或执行契约的小修正。
- Observation / diagnostic rows：P0 为诊断行，不是策略版本。
- New version trigger：只有在 P0 支持 expansion marker 且后续冻结可执行规则时才登记 Vx。

## Version Table

| Version | Status | Role / Core Idea | Key Frozen Metrics | Evidence | Decision / Live Readiness |
| --- | --- | --- | --- | --- | --- |
| `BIN-1D-MA7-CER-P0` | `explore / diagnostic-only / not promoted / not live-ready` | 无方向 expansion event audit | 5D median max excursion Δ=+0.028 ATR（门槛 0.20）；五个 BH Δ mean 的 95% CI 均覆盖 0 | [P0 报告](diagnostics/binance-1d-ma7-cer-p0-direction-agnostic-expansion-audit-2026-09-04.md) · [合同](specs/binance-1d-ma7-cer-p0-direction-agnostic-expansion-audit-contract-2026-09-04.md) · [实现审计](diagnostics/binance-1d-ma7-cer-p0-implementation-audit-2026-09-04.md) | `NO_EXPANSION_EDGE`；STOP；不晋升 |

## Shared Assumptions

- Data：CATL P0R donor panel + P0 asset-day 完整 UTC 日K；事件 identity 与 P5/P7A canonical MA7 Cross 对账。
- Cost：P0 不是账户回测，不使用 fee/slippage/funding 作为主 outcome。
- Execution timing：T0 Cross 收盘已知；未来窗口从下一 UTC 日起。
- Position sizing：无。
- Funding / carry：不进入主 outcome。

## Evidence Map

- Specs：[P0 合同](specs/binance-1d-ma7-cer-p0-direction-agnostic-expansion-audit-contract-2026-09-04.md)
- Diagnostics：[P0 报告](diagnostics/binance-1d-ma7-cer-p0-direction-agnostic-expansion-audit-2026-09-04.md) · [实现审计](diagnostics/binance-1d-ma7-cer-p0-implementation-audit-2026-09-04.md)
- Live specs：无
- Runner tracking：无
- Scripts / artifacts：[scripts/](scripts/) · [artifacts/](artifacts/README.md)

## What Not To Put Here

- 不粘贴完整参数表；放到 `specs/`。
- 不粘贴消融网格、逐笔交易、JSON/CSV、图表或命令输出；放到 diagnostics / artifacts。
- 不把每次研究过程追加成新章节；只更新当前状态、版本表、版本规则和证据链接。
- 不复述 README 的路由信息或 decision-log 的日期流水。
