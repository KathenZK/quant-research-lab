# BIN-1D-CATL-P0 标签定义和字段字典

## 表

- `p0_asset_day_feature_panel/`：每个 asset-day 一行，只含评估日收盘前可知字段。
- `p0_directional_landmark_panel/`：每个 asset-day-side 一行，future/outcome/label 字段描述下一 UTC open 后路径。

## 关键字段

| 字段 | 含义 | 时点 |
| --- | --- | --- |
| `asset` | Binance perp symbol，如 `BTC/USDT:USDT` | 身份字段 |
| `ts` | 评估 UTC 日开盘时间；特征在该日收盘后可知 | causal |
| `feature_known_at` | 下一 UTC 日 `00:00`，即该日特征最早可用时点 | causal |
| `next_entry_ts` / `entry_ts` | 下一 UTC 日开盘，标签路径起点 | label anchor |
| `tradable_marker_p0` | 冻结资格标记：完整日、上市 60 日、30 日连续性和流动性 | causal |
| `atr_anchor` | 评估日及以前 `ATR14`，作为屏障单位 | causal |
| `future_first_favorable_*atr_hours` | 30 日内顺向屏障首次触及小时；未触及为空 | future primitive |
| `future_first_adverse_*atr_hours` | 30 日内反向屏障首次触及小时；未触及为空 | future primitive |
| `label_entry_success_20d` | 20 日内先触及 `+2 ATR` 且未先触及 `-1 ATR` | label |
| `label_continue_success_5d` | 5 日内先触及 `+1 ATR` 且未先触及 `-0.75 ATR` | label |
| `label_*_success_*_optimistic` | 同小时冲突按有利先触发的敏感性字段 | label sensitivity |
| `label_*_net_return` | 1x、双边 fee/slippage、实际 funding 后的独立事件收益 | outcome |
| `future_mfe_atr_*d` / `future_mae_atr_*d` | 指定 horizon 内顺向/反向最大路径，ATR 单位 | outcome |
| `calendar_month` / `calendar_quarter` | purge/walk-forward 分组辅助字段 | causal grouping |

## 主标签

Entry label：下一 UTC open 进入，20 日内先顺向 `+2 ATR`，且此前没有触及反向 `-1 ATR`。

Continuation label：下一 UTC open 继续暴露，5 日内先新增顺向 `+1 ATR`，且此前没有触及反向 `-0.75 ATR`。
