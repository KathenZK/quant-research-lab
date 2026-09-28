---
schema_version: "1.0"
spec_role: lab_handoff
family_id: HYPE-EMA-TB
main_status: dry-run
spec_status: active
strategy_id: HYPE-EMA-TB-V35.1
runner_kind: hype_ema_tb
peer_spec: crates/quant-runner/src/runner/strategies/hype_ema_tb/HYPE-EMA-TB-V35.1-SPEC.md
approval_level_max: dry_run
overlays:
  - handoff
---

# HYPE-EMA-TB-V35.1 Runner Handoff Draft

> 状态：`dry-run / not live-ready`。用户于 2026-08-04 授权 quant-runner 实例 `hype-ema-tb-v35-1-dry-run`（lock `enabled_allowed=true`、`approval_level=dry_run`）。promotion review 未通过，不授权 live。

## 身份与边界

- Family / version：`HYPE-EMA-Trend-Breakout` / `HYPE-EMA-TB-V35.1`
- Exchange / market / symbol / timeframe：Binance / USD-M perpetual / `HYPE/USDT:USDT` / `15m`
- Runner kind / module：`hype_ema_tb` / `crates/quant-runner/src/runner/strategies/hype_ema_tb/mod.rs`
- Capability：`DryRunOnly`
- 版本定义：V35 移除样本内冗余的空头 1h EMA 确认；同窗逐笔与 V35 完全等价。

## 完整参数表

| Runner 冻结字段 | 值 |
| --- | ---: |
| `strategy_id` | `HYPE-EMA-TB-V35.1` |
| `entry_delay_bars` | `2` |
| `ema_fast` / `ema_slow` | `96` / `384` |
| `adx_window` / `atr_window` / `volume_window` | `28` / `672` / `192` |
| `h1_adx_window` | `21` |
| `long_adx_min` / `short_adx_min` | `28` / `36` |
| `long_vol_min` / `short_vol_min` | `0.25` / `0.50` |
| `h1_long_adx_min` | `18`（严格大于） |
| `short_use_h1_ema` | `false` |
| `long_target_atr_pct` / `short_target_atr_pct` | `0.020` / `0.018` |
| `max_allocation` | `3.0` |
| `take_profit_atr` / `hard_stop_atr` | `5.0` / `7.0` |
| `adx_exit` / `delayed_bars` | `22` / `3` |
| `disable_after_mfe_atr` | `1.5` |
| `max_hold_bars` | `384` |
| `cost_rate_per_fill` | `0.00085` |
| research / runtime warmup | `1600` / `2500` |
| `cooldown_bars` / same-bar reentry | `0` / `false` |
| 组合/次级腿 | 无；独立单腿 Driver |

策略字段由 runner `HypeEmaTbConfig::default()` 固定；TOML 只配置实例公共字段，不允许覆盖策略参数。

## 数据与 warmup

- 研究数据：标准数据湖 Binance USD-M HYPEUSDT 15m raw/normalized。
- 冻结范围：`2025-05-30T10:30:00Z` 至 `2026-07-17T08:45:00Z`，`39,642` 根已闭合 K。
- 质量结果：缺口、重复、关键空值、非法 OHLC、raw/normalized 差异均为 0；UTC 时间戳。
- 只允许闭合 K 参与 EMA、ADX/DI、ATR、量能、MFE、indicator exit 与 timeout。
- 启动至少预加载 `2500` 根；缺 K、重复、非法 OHLC、stale bar 或依赖拉取失败必须 fail-closed，禁止新风险。

## 执行与恢复合同

- K0 close 确认信号，跳过完整 K1，K2 open 目标入场；entry ATR 取 K1 的 `ATR672`。
- allocation：`min(3.0, side_target_atr_pct / (entry_atr / entry_fill_price))`。
- 入场后固定 `TP5ATR / SL7ATR`；dry-run 按 trade-candle OHLC，双触发 stop-first。
- `MFE < 1.5ATR` 时，`ADX28 < 22` 连续 3 根后在下一根 open 退出；达到 1.5ATR 后关闭 indicator exit。
- 384 根 timeout 收盘确认，下一根 open 退出；同一根出场后不重入。
- Runner 持久化 weak bars、entry ATR、watermarks、MFE、pending exit 与 last exit timestamp；当前为空仓迁移，不导入旧 Python 私有状态。
- Descriptor 使用 `Bracket` + `BarPriceSource::Trade`，因此 K2 入场后会检查 K2 这根 trade candle 的 TP/SL，双触发仍为 stop-first。
- 公共 execution kernel 负责 simulated venue、保护单、重启恢复、manual halt 与 missing-bar fail-closed。
- 旧 Python SQLite/`engine_state.json` 只读归档，不写入 quant-runner 原生 ledger。

## 成本与资金

- 研究成本：每 fill `0.00085`，表示手续费与 4 bps adverse slippage 合并；round trip `0.00170`。
- Python 基准包含 Binance funding；Rust public-kline replay 尚未计 funding，所以 parity 只验交易路径，不用 Rust 权益替代冻结收益。
- dry-run 名义本金拟为 `10 USDT`；它不构成 live sizing 或资金授权。

## Runner TOML

```toml
[[strategies]]
name = "hype-ema-tb-v35-1-dry-run"
enabled = true
group = "dryrun"
kind = "hype_ema_tb"
mode = "dry_run"
symbol = "HYPE/USDT:USDT"
timeframe = "15m"
account_id = "dryrun"
state_dir = "/home/admin/quant-runner/state/hype-ema-tb-v35-1-dry-run"
leverage = 3
margin_mode = "isolated"
warmup_bars = 2500
dry_run_notional_usdt = 10.0
live_confirm = false
```

## 验证与未决缺口

- Smoke / unit：连续 Driver 的 entry index、K0/K2 时间戳、ADX pending next-open、384-bar timeout 边界、入场 K bracket 与旧 Driver evidence fallback 已补直接回归；Runner 全套 `218 passed / 5 ignored`。
- Offline parity：Python/Rust `111/111` 笔；entry/exit 时间、方向、价格、allocation、退出原因零偏差。
- Runtime alignment：已修复首根持仓 K 误触发 timeout、ADX 退出多延迟一根、入场 K 跳过 bracket、ledger 把 K1 误记为 signal timestamp 四项偏差；这只关闭实现缺陷，不改变 promotion 状态。
- Gate 1：V35 全参数消融可继承，且 V35.1 仅删除经逐笔等价证明的冗余条件。
- Gate 3 blocker：既有消融明确判定 `adx_window`、`long_adx_min`、`adx_exit`、`hard_stop_atr`、`atr_window`、`disable_after_mfe_atr` 等多数核心参数位于尖峰；按现行规则不得推进 `live spec`。
- 仍缺 Gate 0 超额收益正式报告、Gate 2 OOS/CPCV、Gate 4 执行压力、Gate 5 真实 1m 相位，以及完整 live-executable promotion review。
- Online open/close reconciliation：dry-run 已于 2026-08-04 授权；线上开平仓对账尚未完成。
- live blocker：当前条件保护单使用 `MARK_PRICE`，研究 TP/SL 为 trade-price OHLC；funding、真实滑点、保护单 working type、重启与拒单故障注入均未关闭。

## 双向链接

- [Core ledger](../hype-ema-tb-core-ledger.md)
- [V35.1 冻结规格](../specs/hype-trend-strategy-v35-1-spec.md)
- [V35 全参数消融](../notes/hype-ema-tb-v35-full-ablation-recent-tune-2026-07-08.md)
- [Python/Rust parity artifact](../artifacts/HYPE-EMA-TB-V35.1_parity_2026-07-20.json)
- [Runner replay artifact](../artifacts/HYPE-EMA-TB-V35.1_runner_replay_2026-07-20.json)
- [Runner SPEC](../../../../../quant-runner/crates/quant-runner/src/runner/strategies/hype_ema_tb/HYPE-EMA-TB-V35.1-SPEC.md)
