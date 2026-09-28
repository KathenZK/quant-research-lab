# HYPE-EMA-X 决策日志

这是 HYPE EMA golden/death cross 研究的家族级阅读路径。

## 2026-09-03 — parity grandfather 续期至 2026-12-24

决定：用户已在 quant-runner 提交 `a5a3b2a` 将 `HYPE-EMA-X-V18`（`hype-ema-x-dry-run`）的 `parity_grandfather_until` 由 `2026-09-24` 续期至 `2026-12-24T00:00:00Z`。到期前须补标准 parity JSON（`conclusion=PASS`），否则 runner CI 将拒绝 `enabled`。主状态仍为 `dry-run`，本条不改变授权。

## 2026-08-18 — 同组 halt，观察窗口再断

- `hype-ema-x-dry-run` 再次被共享 HYPE 15m 组 `group_halted` 拖停（本次触发在 EMA-TB，不是 EMA-X 状态机）。自 `2026-08-17 19:19Z` 起 dry-run 观察窗口断裂。证据：[hype-15m-group-halt-2026-08-17.md](../15m-ema-trend-breakout/runner-tracking/hype-15m-group-halt-2026-08-17.md)。

## 当前边界

- 这是本仓库四个核心研究方向之一。
- 它通过仓库 Markdown ledgers 和 archived scripts 保留，而不是通过打磨后的 specs 保留。
- 不应把它视为已经失败的浅层尝试。
- 不应将它合并进 `HYPE-EMA-TB`。

## 版本记录

- `HYPE-EMA-X-V2/V4`：早期 EMA cross comparisons。
- `HYPE-EMA-X-V5`：regime-hold variant。
- `HYPE-EMA-X-V7`：volume exhaustion。
- `HYPE-EMA-X-V8`：volume overlay。
- `HYPE-EMA-X-V9`：higher-timeframe RSI exit。
- `HYPE-EMA-X-V10`：oscillator top exit。
- `HYPE-EMA-X-V11`：trade-path diagnostics。
- `HYPE-EMA-X-V12`：state-machine variants。
- `HYPE-EMA-X-V13`：late re-entry and missed-trend diagnostics。
- `HYPE-EMA-X-V14`：main late-entry/backfill/ablation checkpoint。
- `HYPE-EMA-X-V15`：已登记的 high-win-rate / low-drawdown 版本。Source search row：`V17_atr18_trend7_base_age384_d075_pnlm03_either2_stop8`。Metrics：`+2303.65% / -17.79% / 90.32% / 31 trades`。
- `HYPE-EMA-X-V16`：已登记的 high-return 版本。Source search row：`V17_atr18_base_age384_pnlm03_either2_stop8`。Metrics：`+3202.92% / -28.19% / 86.84% / 38 trades`。
- `HYPE-EMA-X-V17`：已登记的 V15/V16 hybrid 版本。Source row：`HYBRID_score5_dist04_atr11` / `HYPE_EMA_X_V17`。Metrics：`+2910.74% / -17.79% / 90.91% / 33 trades`。
- `HYPE-EMA-X-V17.1`：已登记的 V17 sizing-enhanced 版本。Source row：`HYPE_EMA_X_V17__hq_scale=1p1`。Metrics：`+3861.48% / -19.44% / 90.91% / 33 trades`。
- `HYPE-EMA-X-V18`：V17.1 干净参数规格。交易逻辑与 V17.1 相同；146 项消融后剔除 noop 与默认关闭模块，只保留有效参数表。Metrics 与 V17.1 相同。规格见 `specs/hype-ema-x-v18-baseline-spec.md`。

这些已提升版本的 main ledger 是 `hype-ema-x-core-ledger.md`。旧 Cursor canvas 仅作为 legacy source 保留。

## 研究批次记录

- `2026-07-20`：按用户决定，将 `HYPE-EMA-X-V18` 的 parity 补证期限延至 `2026-09-24T00:00:00Z`，当时仅维持 dry-run；live 实例不获得授权。当前实际授权以 quant-runner 为准，待补证据见 [`HYPE-EMA-X-V18_parity_pending_2026-07-11.json`](artifacts/HYPE-EMA-X-V18_parity_pending_2026-07-11.json)。
- `research_hype_v15_effective_cross.py`：effective-cross quality probe；仅作为证据，不是已提升的 `HYPE-EMA-X-V15`。
- `research_hype_v16_indicator_expansion.py`：indicator-expansion probe。Early indicator entries 增加了交易数，但稀释了 V14 quality；OKX 没有确认足够稳定性。
- `research_hype_v17_trend_state_search.py`：覆盖 common indicator families 的 broad trend-state search。没有 candidate 同时满足 `50x return`、`<20% max drawdown` 和 `>80% win rate`。其中最佳低回撤行和高收益行现在已提升为 `HYPE-EMA-X-V15` 和 `HYPE-EMA-X-V16`。
- `research_hype_v17_hybrid_ablation.py`：围绕 `HYPE-EMA-X-V17` 的完整 single-parameter/single-module ablation。Baseline V17 仍是 signal-layer official version；最佳消融行为 `hq_scale=1.1`，指标为 `+3861.48% / -19.44% / 90.91% / 33 trades`，现记录为 `HYPE-EMA-X-V17.1`。
- `research_hype_ema_x_v17_1_strict_live_audit.py`（2026-07-01）：`HYPE-EMA-X-V17.1` 严格口径复审。在台账切片 `<= 2026-06-01 03:00 UTC` 上复现 `+3861.48% / -19.44% / 33 trades`；126 个 feature-point 因果性检查失败 `0`；信号时序异常 `0`；`stop_gap_open` / `stop_delay_1bar` / `stop_market_extra_slip` 与 baseline 相同（样本内 `0` 笔 stop_loss）。结论：未发现未来函数或 PBTR 式 stale stop 穿价补成交；硬止损仍属 stop-price 乐观上界，不得 live-approved。见 `diagnostics/hype-ema-x-v17-1-strict-live-audit-2026-07-01.md`。
- `research_hype_v17_1_full_ablation.py` + `research_hype_v17_1_parameter_prune_audit.py`（2026-07-01）：`HYPE-EMA-X-V17.1` 146 项单参数消融。结论：3 项 noop；多项默认关闭模块打开伤收益；`stop_atr` 8–12 样本内等价。剔除证据见 `diagnostics/hype-ema-x-v17-1-parameter-prune-audit-2026-07-01.md`；干净参数升格为 **`HYPE-EMA-X-V18`**，见 `specs/hype-ema-x-v18-baseline-spec.md`。
- `research_hype_ema_x_v18_retest.py`（2026-07-01）：按 `HYPE-EMA-X-V18` 干净规格重新回测并增加固定步长滚动窗口。台账切片 `<= 2026-06-01 03:00 UTC` 复现 `+3861.48% / -19.44% / 90.91% / 33 trades / 7 late`；30D 滚动窗口 `13` 段中 `1` 段负收益，90D/180D/365D 滚动窗口均为正收益，但短窗口交易数少。结论：复测确认 V18 台账指标，当时维持 `registered / not live-ready` 状态。见 `diagnostics/hype-ema-x-v18-retest-and-rolling-windows-2026-07-01.md`。
- `2026-07-08`：确认 `HYPE-EMA-X-V18` 确实在 quant-runner 以 `hype_ema_x` dry-run 配置运行（`configs/dryrun.toml`），状态更新为 `dry-run / forward-test required`，并建立 [runner-tracking/README.md](runner-tracking/README.md)。首份 runner 观察报告缺失前不得升级 `live`，也不得据此给出 `NO-GO`。
- `2026-07-08`（live-specs 缺口记录）：治理审计发现 V18 进入 runner 早于 `lab-runner-handoff` 契约成文，lab 侧没有 `live-specs/` 交接规格，runner 侧以 `HYPE-EMA-X-V18-SPEC.md` 为实现事实源，属 grandfathered 例外。升级 `live` 前必须按 handoff 契约补写 `live-specs/` 交接规格并与 runner SPEC 互链；在此之前该缺口保持为 live-readiness blocker。

## 证据政策

使用 `hype-ema-x-core-ledger.md`、`legacy-canvas/` 和 archived script names 重建谱系。干净官方参数规格见 `specs/hype-ema-x-v18-baseline-spec.md`。
