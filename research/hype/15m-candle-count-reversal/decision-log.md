# HYPE-CC 决策日志

这是 HYPE candle-count reversal 研究的家族级阅读路径。

## 2026-09-03 — parity grandfather 续期至 2026-12-24

决定：用户已在 quant-runner 提交 `a5a3b2a` 将 `HYPE-CANDLE-COUNT-V35`（`hype-candle-count-v35-dry-run`）的 `parity_grandfather_until` 由 `2026-09-24` 续期至 `2026-12-24T00:00:00Z`。到期前须补标准 parity JSON（`conclusion=PASS`），否则 runner CI 将拒绝 `enabled`。主状态仍为 `dry-run`，本条不改变授权。

## 当前边界

- 本家族属于策略规格与归档材料。
- 它不是 active package code 的事实来源。
- 需要复现逻辑时，应使用 specs 在一次性脚本或生产 runner 中重建。

## 版本记录

- `HYPE-CC-V10`：ATR dynamic stop 基线。
- `HYPE-CC-V13`：全 ATR288 双向限价规格。
- `HYPE-CC-V18`：ATR672 稳健基线。
- `HYPE-CC-V19`：仅多头 three-opposite-candle early exit。
- `HYPE-CC-V20`：inclusive opposite-three exit 变体。
- `HYPE-CC-V21`：双向 opposite-three exit 变体。
- `HYPE-CC-V35`：可复现性与过拟合诊断检查点。

## 决策记录

- `2026-09-07`：[极值 Maker 入场审计](diagnostics/hype-cc-v35-maker-entry-audit-2026-09-07.md)
  未复现“2026-08-01 至今收益 300%+”。按 V35 明示成本，单改为 10 根极值、最长
  4 小时 maker 后收益由 `+30.64%` 变为 `-19.45%`；预声明 `EMA24/672` 过滤的
  maker 变体最高 `+77.59%`，同规则 next-open / maker 全拆分最高 `+80.51%`，主要
  改善来自过滤空单，不是稳定 maker 优势。因截图缺少精确均线规格、
  完整 funding calendar 未验证且 K 线无法证明 maker 队列 / 部分成交，正式结论为
  `DATA_OR_REPRODUCTION_FAILURE / NUMERIC_CLAIM_NOT_REPRODUCED`。本条仅为 diagnostic，
  不登记新版本，不修改 V35 runner、dry-run 或 live 状态。
- `2026-08-18`：共享 HYPE 15m 组再次 halt。`hype-candle-count-v35-dry-run` 自 `2026-08-17 19:19Z` 起观察窗口断裂，且 halt 时留有模拟空仓（`2026-08-17T03:00Z` short @ `58.9004304`，qty `0.509`）未再维护。研究身份不变。证据：[hype-15m-group-halt-2026-08-17.md](../15m-ema-trend-breakout/runner-tracking/hype-15m-group-halt-2026-08-17.md)。
- `2026-07-20`：按用户决定，将 `HYPE-CANDLE-COUNT-V35` 的 parity 补证期限延至 `2026-09-24T00:00:00Z`，当时仅维持 dry-run；不恢复历史 live，也不获得新的 live 授权。当前实际授权以 quant-runner 为准，待补证据见 [`HYPE-CANDLE-COUNT-V35_parity_pending_2026-07-11.json`](artifacts/HYPE-CANDLE-COUNT-V35_parity_pending_2026-07-11.json)。
- `2026-06-29`：`diagnostics/hype-cc-v35-live-underperformance-review-2026-06-29.md` 在 Binance live 表现不佳、6 月 OHLCV-proxy OOS replay 和阿里云 HypePulse live DB / 日志 / 交易所快照审计后，将 `HYPE-CC-V35` 下调为 live-underperformance / execution-risk diagnostic。当前归因优先级是策略 / 行情样本外亏损，其次是实盘成交摩擦放大；远端审计未发现服务卡死、当前保护单缺失、warning storm 或大幅入场滑点等足以把亏损主因改判为代码 bug 的证据。在补齐 2026-06-01 之后 mark-price replay 和 live-realistic replay 前，不要把 `+8357.56%` 或 `58.53%` 胜率作为 live expectation 引用。
- `2026-06-29`：`diagnostics/hype-cc-v35-parameter-overfit-rediagnosis-2026-06-29.md` 将 V35 参数级风险重新分层：`10/8` 核心信号和 `trend_window_bars=96` 是高风险样本内尖点，双向 `12/9` counter 和 `target_atr_pct=0.006` 是后期收益增强 / 放大层；ATR672、TP 5.5、cooldown 8、gap 8 等机制可保留研究，但具体数值需重新做 live-realistic OOS。不要从 V35 继续微调，应回退到更少后期增强层的基线重新评估。
- `2026-07-08`：确认 `HYPE-CC-V35` 确实在 quant-runner 以 `hype_candle_count` dry-run 配置运行（`configs/dryrun.toml`），状态更新为 `dry-run / forward-test required`，并建立 [runner-tracking/README.md](runner-tracking/README.md)。历史 live underperformance 继续作为 execution-risk 证据保留；当前 dry-run 是重新观察/对账状态，不等于 live 批准。首份 runner 观察报告缺失前不得升级 `live`，也不得据此给出新的 `NO-GO`。
- `2026-07-08`（live-specs 缺口记录）：治理审计发现 V35 进入 runner 早于 `lab-runner-handoff` 契约成文，lab 侧没有 `live-specs/` 交接规格，runner 侧以 `HYPE-CANDLE-COUNT-V35-SPEC.md` + [specs/hype-v35-reproducible-params.md](specs/hype-v35-reproducible-params.md) 为实现事实源，属 grandfathered 例外。升级 `live` 前必须按 handoff 契约补写 `live-specs/` 交接规格并与 runner SPEC 互链；在此之前该缺口保持为 live-readiness blocker。
- `2026-07-14`：[`diagnostics/hype-cc-v35-dual-ema-trend-filter-2026-07-14.md`](diagnostics/hype-cc-v35-dual-ema-trend-filter-2026-07-14.md) 对 V35 叠加 13 组双 EMA 顺趋势禁入进行滚动 OOS 与后段 holdout；相对最优 `EMA24/672` 虽改善 2026-06-01 后亏损，但训练段 OOS 收益、Sharpe 与最差回撤均弱于 V35，长期收益衰减明显。结论为候选失败，不登记 `HYPE-CC-V36`，不修改 V35 runner / dry-run。
- `2026-07-14`：[`diagnostics/hype-cc-v35-adx-di-trend-block-2026-07-14.md`](diagnostics/hype-cc-v35-adx-di-trend-block-2026-07-14.md) 改用“仅在 ADX 强趋势中按 `+DI/-DI` 禁止逆向开仓”的较弱过滤；训练段相对最优 `ADX28 >= 25` 略有改善，但未形成参数高原，最终 holdout 从 V35 的 `-17.49%` 恶化至 `-19.93%`。结论仍为候选失败，不登记 `HYPE-CC-V36`，不修改 V35 runner / dry-run。
- `2026-07-15`：[`diagnostics/hype-cc-v35-replace-24h-with-adx-di-2026-07-15.md`](diagnostics/hype-cc-v35-replace-24h-with-adx-di-2026-07-15.md) 删除原 `96` 根 / `5%` 趋势禁入并以 ADX/DI 替换；训练段相对最优 `ADX14 >= 35` 仍弱于原 V35且无参数高原，最终 holdout 为 `-40.00% / -54.37%`，显著差于原 V35 的 `-17.49% / -36.24%`。确认原 24h 位移过滤是关键风险层，保留原规则，不登记 `HYPE-CC-V36`。
- `2026-07-15`：[`diagnostics/hype-cc-v35-1h-consensus-trend-filter-2026-07-15.md`](diagnostics/hype-cc-v35-1h-consensus-trend-filter-2026-07-15.md) 保留原趋势禁入并叠加无前视的 1h EMA24/72 或 EMA24/96、ADX14/DI 共识与迟滞；相对最优 `EMA24/72 + ADX30/25` 的训练段收益中位数从 `+42.43%` 降至 `+20.96%`，最终 holdout 没有拦截任何信号。其全窗口回撤改善约 3.66 个百分点但收益减少约 53%，风险收益交换不合格，不登记 `HYPE-CC-V36`。
- `2026-07-16`：[`diagnostics/hype-cc-v35-tp-2-5-atr-check-2026-07-16.md`](diagnostics/hype-cc-v35-tp-2-5-atr-check-2026-07-16.md) 仅将 V35 `take_profit_atr_multiplier` 从 `5.5` 改为 `2.5`，保留 `2%–3.5%` 上下限；最近 30 天收益从 `-19.38%` 恶化至 `-46.70%`，回撤从 `-30.30%` 扩大至 `-49.40%`。胜率虽升至 `41.38%`，但亏损笔数未减少、平均 TP 降至 `2.09%`，拒绝该修改，不登记新版本。
- `2026-07-20`：正式建立 [HYPE-CC core ledger](hype-cc-core-ledger.md)，并确认现有 [V35 handoff](live-specs/hype-cc-v35-handoff-not-live-ready.md) 已满足 lab 侧交接入口要求；2026-07-08 记录的“缺少 live-specs” grandfathered gap 已关闭，可从治理 grandfather 清单移除。当前状态仍为 `dry-run / not live-ready`，不构成 live 升级。

## 证据政策

优先使用家族文档，而不是 archived code。如果代码与文档不一致，先引用文档，再通过重新生成一次性回测进行验证。
