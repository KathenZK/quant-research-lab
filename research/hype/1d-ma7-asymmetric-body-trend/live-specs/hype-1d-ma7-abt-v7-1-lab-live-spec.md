---
schema_version: "1.0"
spec_role: lab_handoff
family_id: HYPE-1D-MA7-ABT
main_status: dry-run
spec_status: active
strategy_id: HYPE-1D-MA7-ABT-V7.1
runner_kind: hype_1d_ma7_abt
peer_spec: crates/quant-runner/src/runner/strategies/hype_1d_ma7_abt/HYPE-1D-MA7-ABT-V7.1-SPEC.md
approval_level_max: dry_run
overlays:
  - handoff
---

# HYPE-1D-MA7-Asymmetric-Body-Trend V7.1 Lab Live Spec

> 状态：`dry-run / not live-ready / approval_level_max=dry_run`。用户于 2026-08-13 授权 dry-run；live 仍禁用，不授权真实下单。

## 身份与边界

- Family / version：`HYPE-1D-MA7-Asymmetric-Body-Trend` / `V7.1`
- Strategy id：`HYPE-1D-MA7-ABT-V7.1`
- Proposed runner kind：`hype_1d_ma7_abt`
- Runner module：`crates/quant-runner/src/runner/strategies/hype_1d_ma7_abt/`。
- Exchange / market / symbol / timeframe：Binance USD-M Futures，`HYPE/USDT:USDT`，UTC `1d`
- Default research exposure：fixed target `1x` equity, one position, no pyramiding, no periodic rebalance
- Approval boundary：本 Lab SPEC 不含任何资金授权；小额资金、子账户、真实下单开关、service 启停和 generated lock 只能由 `quant-runner` 与用户操作决定。

## 完整参数表

### Runner Identity

| Runner field | Value | 说明 |
| --- | --- | --- |
| `strategy_id` | `HYPE-1D-MA7-ABT-V7.1` | 事件、订单、ledger 与通知里的策略身份。 |
| `kind` | `hype_1d_ma7_abt` | runner kind 已在 `quant-runner` 实现；dry-run 已授权，live 仍禁用。 |
| `symbol` | `HYPE/USDT:USDT` | Binance USD-M HYPE perpetual CCXT symbol。 |
| `timeframe` | `1d` | 只用 UTC 已闭合日线做主信号。 |
| `target_leverage` | `1.0` | 每次实际入场以成交后权益近似 `1x` 为目标。 |
| `allow_pyramiding` | `false` | 单仓，不加仓。 |

### Indicator

| Runner field | Value | 说明 |
| --- | ---: | --- |
| `ma_kind` | `sma` | 固定 SMA，不使用 EMA。 |
| `ma_length` | `7` | `SMA7_t = mean(close[t-6:t])`。 |
| `atr_length` | `7` | ATR7，供斜率/距离/保护参数使用。 |
| `rsi_length` | `6` | Wilder RSI6（首窗 SMA 种子），供空头 RSI 止盈使用。runner 使用与研究相同的本地口径，不得替换成公共 `rsi()` 的 EWM 种子。 |

### Long Leg

| Runner field | Value | 说明 |
| --- | ---: | --- |
| `long.entry_mode` | `reclaim` | 前一已闭合日不在 MA7 上方、当前已闭合日重新站上 MA7。 |
| `long.slope_lookback` | `1` | 多头入场看 1 日 MA7 上行斜率。 |
| `long.slope_min_atr` | `0.02` | 入场要求 `MA7` 上行斜率至少 `0.02 * ATR7`。 |
| `long.confirm_days` | `1` | 站上 MA7 单日确认。 |
| `long.entry_buffer_atr` | `0.0` | 不要求高出 MA7 的额外 ATR buffer。 |
| `long.exit_confirm_days` | `1` | MA7 迟滞退出单日确认。 |
| `long.exit_buffer_atr` | `0.75` | 跌至 MA7 下方 `0.75 * ATR7` 外才触发边界退出。 |
| `long.trail_atr` | `1.5` | 多头基础 trailing protection。 |
| `long.max_hold_days` | `90` | 多头最长持有天数。 |
| `long.cooldown_days` | `2` | 多头退出后启动 2 个完整 flat 日的全局冷却。 |

### Short Leg

| Runner field | Value | 说明 |
| --- | ---: | --- |
| `short.entry_mode` | `reclaim` | 前一已闭合日不在 MA7 下方、当前已闭合日跌回 MA7 下方。 |
| `short.slope_lookback` | `2` | 空头入场看 2 日 MA7 下行斜率。 |
| `short.slope_min_atr` | `0.02` | 入场要求 `MA7` 下行斜率至少 `0.02 * ATR7`。 |
| `short.confirm_days` | `1` | 跌破 MA7 单日确认。 |
| `short.entry_buffer_atr` | `0.10` | close 需低于 MA7 至少 `0.10 * ATR7`。 |
| `short.exit_confirm_days` | `1` | MA7 迟滞退出单日确认。 |
| `short.exit_buffer_atr` | `0.75` | 站至 MA7 上方 `0.75 * ATR7` 外才触发边界退出。 |
| `short.slope_exit_lookback` | `1` | 空头持仓中，1日 MA7 下降斜率消失可退出。 |
| `short.hard_stop_atr` | `1.5` | 空头固定保护止损。 |
| `short.trail_atr` | `4.0` | 空头基础 trailing protection。 |
| `short.max_hold_days` | `20` | 空头最长持有天数。 |
| `short.cooldown_days` | `3` | 空头退出后启动 3 个完整 flat 日的全局冷却。 |

### OAPP

| Runner field | Value | 说明 |
| --- | ---: | --- |
| `oapp.entry.kind` | `off` | OAPP 不参与入场过滤。 |
| `oapp.long_exit.mode` | `fraction` | 多头使用 MFE fraction giveback 盈利保护。 |
| `oapp.long_exit.activation_atr` | `0.5` | 多头浮盈达到 `0.5 * ATR7` 后激活。 |
| `oapp.long_exit.giveback` | `0.10` | 从最大浮盈回吐 10% 后满足退出条件。 |
| `oapp.long_exit.confirm_days` | `2` | 多头 OAPP 退出需要 2 日确认。 |
| `oapp.short_exit.mode` | `off` | 不启用通用 short MFE giveback。 |
| `oapp.short_rsi.threshold` | `20.0` | 空头 RSI6 止盈阈值。 |
| `oapp.short_rsi.days` | `2` | RSI6 需连续 2 日低于阈值。 |
| `oapp.roundtrip_guard` | `0.0028` | 约等于 1x 一进一出默认手续费+滑点成本。 |

### PEHC

| Runner field | Value | 说明 |
| --- | ---: | --- |
| `pehc.enabled` | `true` | 启用 profit-exit handoff continuity。 |
| `pehc.entry_enabled` | `true` | 通过复核后允许实际 handoff 入场。 |
| `pehc.expiry_days` | `8` | shadow 资格最多保留 8 日。 |
| `pehc.slope_threshold` | `null` | handoff 不额外要求 MA7 斜率阈值。 |
| `pehc.chase_cap_atr` | `null` / 无上限 | handoff 不设置追价 ATR 上限。runner 用 `Option::None` 表示；不得写成会反序列化失败的 `"inf"`。 |
| `pehc.execution` | `next_utc_open` | 通过复核后下一 UTC 日 open 执行。 |

## 数据与 Warmup

- 主信号必须只使用 Binance USD-M `HYPE/USDT:USDT` 已闭合 UTC `1d` K 线。
- 需要 `1h` K 线用于 dry-run 保护 touch、PEHC shadow 消费、开平仓对账、资金费率时间戳和风险 replay。日线 trailing 仍按已闭合 `1d` close 更新。
- 当前 runner 从 `Hype1dMa7AbtConfig::default()` 绑定 V7.1 参数，不读取实例 TOML 的 nested tables。上面参数表就是合同；实例 TOML 只含 identity/ops。
- 最小 warmup：至少 `30` 个完整日线 bar；若 runner 内部 ATR/RSI 口径需要更长稳定期，应以更长者为准。
- 数据质量门禁：
  - 无缺失日线主 bar；
  - OHLC 合法：`low <= open/close <= high`；
  - 时间戳为 UTC，且只用 closed bar；
  - funding 事件按交易所时间戳结算；
  - 任何缺失日线、重复 bar、非闭合 bar 或交易所断线都必须进入 fail-safe，不允许猜测补值后下单。

## 执行与恢复合同

- 主信号时点：日线 close 后计算，最早下一 UTC 日 open 下单。
- 例外时点：多头保护止损后的 MA-only forced short 在资格成立时按 `Immediate` 以当时成交/mark 价开空。PEHC 研究口径是 `next_utc_open`：`1h` 机会价复核通过后写入下一 UTC 00:00 pending；1h poll 看到该时刻已到后发 `Immediate` 市价单。不得把 PEHC 交给 1d `NextOpen`（那会再等一整日）。
- Flat 评估顺序：PEHC → forced reversal → native reclaim。
- 订单类型：初版 runner 应使用可审计 market order 或明确的 taker-equivalent order；不得引入未在研究中验证的 maker/limit 改善。
- 多头无初始 hard stop；入场到首个日线 trailing reference 形成前由 strategy-managed 状态持有，之后切换为交易所 mark-price market stop。空头入场立即使用 `1.5 * entry_ATR7` hard stop。
- dry-run 保护 touch 只使用已闭合 UTC `1h` mark K 线。该序列或 mark 缺失时必须 fail-closed 等待重试，不得用日线 high/low 回退模拟触发；漏掉的已闭合 `1h` bar 按 `last_protection_poll_ts` 顺序补检。live 在止损挂上后由交易所 mark-price stop 成交。
- dry-run TouchOnly 平仓原因是 `stop`，live REST/user-stream 是 `stop_market`；两者都触发多头保护止损后的 forced short。
- 仓位：单仓；普通 opposite reclaim 不触发持仓中反手。只有多头保护止损后的 MA-only forced short 与 PEHC handoff 可从 flat 进入空头；不得叠加 long/short。
- `pending_forced_short` 与 PEHC `next-open` pending 在发出 Immediate target 后仍保持，直到 `Opened` 成交或资格被拒绝。被平台闸拦住或下单失败时下一根 flat cycle 重试，不得丢状态。拒绝 forced short 后立即 Hold，写入多头腿全局冷却，不得在同一根日线再吃 native reclaim。
- 持仓中的日线软出场不依赖 `1h` 序列；`1h` 失败只阻止 flat 的 PEHC/forced-reversal 评估。
- 数量：按成交后权益目标 `1x` 估算；入场后数量固定到退出或反手。
- Persisted state 至少包括：
  - 当前持仓方向、entry timestamp、entry price、quantity；
  - bars held；
  - 全局 cooldown 剩余完整 flat 日数；
  - 多头 MFE、OAPP 激活/确认状态；
  - trailing high/low 与 stop reference；
  - 保护止损后的 pending forced-short；
  - PEHC shadow origin、stop、expiry、最近处理的 `1h`/`1d` 时间戳与 next-open pending；
  - 最近已处理日线 bar timestamp，防止重启重复下单。
- Missing bar / restart：
  - 缺失日线或无法确认 closed bar 时不得新开仓；
  - 无法恢复 persisted state 时必须 fail-safe flat 或人工介入，不得根据当前行情重建仓位；
  - 重启先做 pending/protect/reconcile；Driver envelope 恢复 cooldown、PEHC 与 last-flat-bar。未消费的日线信号仍可在核对后入场，已处理日线不得因重启重复下单。
- Kill switch：
  - 手动禁用、数据质量失败、订单拒绝、余额/仓位不一致、重复信号或风控检查失败时，runner 必须停止新单并报警。

## 成本与资金

- Research fee：`0.001` of filled notional per fill。
- Research slippage：`4 bps` adverse per fill；压力检查用 `8 bps`。
- Funding：使用真实 Binance funding event timestamp/rate。
- 小额资金边界：本 Lab SPEC 不指定 notional；若用户后续在 runner 侧授权 tiny live pilot，应在 runner ops/launch decision 里记录子账户、最大损失、kill-switch 和服务配置。

## Runner TOML

当前 runner 拒绝实例上的 nested 参数块。真实可加载的是 identity/ops 字段；alpha 参数只存在于 `Hype1dMa7AbtConfig::default()`，必须与上面参数表一致。

```toml
# IMPLEMENTED DRY-RUN: 与 configs/dryrun.toml 当前实例一致。live 仍不授权。

[[strategies]]
name = "hype-1d-ma7-abt-v7-1-dry-run"
enabled = true
group = "dryrun"
kind = "hype_1d_ma7_abt"
mode = "dry_run"
symbol = "HYPE/USDT:USDT"
timeframe = "1d"
account_id = "dryrun"
state_dir = "/home/admin/quant-runner/state/hype-1d-ma7-abt-v7-1-dry-run"
leverage = 1
margin_mode = "isolated"
warmup_bars = 500
dry_run_notional_usdt = 10.0
live_confirm = false
```

## 三个月观察计划

建议在真实资金前至少完成：

1. Runner 实现 SPEC 与本 Lab SPEC 字段逐项对齐。
2. Offline parity：同一段 HYPE 历史数据对拍 V7.1 20 笔交易，entry/exit timestamp、side、reason、price 逐笔一致。
3. Dry-run：至少 90 天或至少 5 笔闭合交易；不改参数。
4. Online open/close reconciliation：抽取 runner DB/订单/日志，与研究期望开平仓逐笔对账。
5. 若用户仍要 tiny live pilot，必须另写 launch decision，明确子账户、最大亏损、kill switch、告警、停止条件和回滚流程。

## 验证与未决缺口

- Runner implementation：已完成，见 `quant-runner/crates/quant-runner/src/runner/strategies/hype_1d_ma7_abt/` 与 runner SPEC。
- Runner config / lock：dry-run 实例 `hype-1d-ma7-abt-v7-1-dry-run` 已 `enabled=true`，lock `enabled_allowed=true`、`approval_level=dry_run`、`parity_status=PASS`。live 实例仍 `enabled=false`、`enabled_allowed=false`、`approval_level=none`。
- Smoke：runner smoke 已通过。来源命令：`cargo clippy -p quant-runner --all-targets -- -D warnings`、`cargo test -p quant-runner`、dryrun/live `validate-config`、`replay-dry-run --config configs/dryrun.toml --name hype-1d-ma7-abt-v7-1-dry-run --limit 300`，并复核 `--limit 500`。公开日线 smoke 分别输出 `+42.18%/-16.85%/17笔` 与 `+29.47%/-24.66%/27笔`；这些不是 Lab canonical 回测收益，不能用于 performance acceptance，只证明 runner 代码路径可跑。证据：[runner smoke artifact](../artifacts/hype_1d_ma7_abt_v7_1_runner_smoke_2026-08-11.json)。
- Offline parity：`PASS`。复核命令：`DINGTALK_WEBHOOK_URL=https://example.com cargo run -q -p quant-runner -- replay-dry-run --config configs/dryrun.toml --name hype-1d-ma7-abt-v7-1-dry-run --limit 500 --start-ts 2025-05-31T00:00:00Z --end-ts 2026-08-06T00:00:00Z`；窗口为 432 根日线、10368 根小时线、2591 条 funding 事件。canonical 20 笔与 runner 20 笔在 side、entry/exit timestamp、entry/exit price、bars held、reason、raw PnL、raw return 全部一致，mismatch 为 0。headline 为 `+711.035936775286%`、1h MDD `-18.395542229660567%`，两项 delta 均为 0；8bps 为 `+698.7499654030659%/-18.52798408021893%`。
- Offline parity evidence：[逐笔 runner tracking](../runner-tracking/hype-1d-ma7-abt-v7-1-strict-parity-2026-08-12.md) · [runner strict parity PASS JSON](../artifacts/hype_1d_ma7_abt_v7_1_runner_strict_parity_2026-08-12.json)；canonical source 为 [V7 frozen artifact](../artifacts/hype_1d_ma7_abt_v7_short_cooldown3_2026-08-11.json)。
- Online open/close reconciliation：未完成。
- Runner SPEC：已创建并回写 strict parity PASS 与 runtime 状态机合同。
- Remaining blockers：
  - Lab V7.1 为 post-reveal registered candidate，尚无 clean prospective；
  - dry-run 已于 2026-08-13 启动，但 90 天/5 笔闭合交易观察和线上开平仓对账尚未完成；
  - live 描述符为 `PilotGuards`：即使以后要 tiny live，仍需 isolated、独立 `account_id`、`warmup_bars >= 2500` 和交易所 `leverage >= 3`，研究仓位仍是 `1x`。当前 live stub `leverage = 1` / `warmup_bars = 500` 不能通过 live 启动校验；
  - 本 spec `approval_level_max=dry_run`，不能作为真实下单许可。

## 外部交付说明

本文件是内部 Lab 交接规格，不是自包含复现包。若要发给同事或外部 AI，请使用同日导出的 external reproduction spec；该外发版在正文内完整包含参数、数据要求、指标公式、执行模型、验收指标和20笔交易锚点，不依赖本地文件。
