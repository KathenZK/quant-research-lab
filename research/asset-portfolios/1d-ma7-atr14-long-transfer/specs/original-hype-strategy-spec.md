# Spec: HYPE 趋势突破 + 移动止损回测策略

> 目的：基于 HYPE 日K，完整、无歧义地规定一个"MA7 上穿 + 斜率过滤 + ATR 移动止损"做多策略的回测实现。
> 任何实现方在不参考前文对话的前提下，**仅凭本 Spec 应能产出与基线完全一致的结果**。

---

## 1. 策略概述

在日K 周期上，对单一标的（默认 `HYPE` 永续）执行**多头趋势突破 + 移动止损**策略：

- **入场**：昨日收盘跌破 MA7、今日向上穿越 MA7、且 MA7 斜率为正（> 阈值）→ 收盘价全仓买入。
- **出场**：持仓期间维护一个**只上移不下移**的移动止损位 `MA7 - 1.5 × ATR14`；价格日内或收盘触及即离场。
- 同一时间至多一笔持仓；逐笔收益**复利**。

---

## 2. 数据规格

| 项目 | 规格 |
|---|---|
| 标的 | `HYPE`（Hyperliquid 永续合约） |
| 数据源 | Hyperliquid 官方 `candleSnapshot` 接口 |
| 接口 | `POST https://api.hyperliquid.xyz/info` |
| 请求体 | `{"type":"candleSnapshot","req":{"coin":"HYPE","interval":"1d","startTime":<ms>,"endTime":<ms>}}` |
| 周期 | `1d`（日K，UTC 00:00 切日） |
| 必含字段 | `t`(open ms), `o`, `h`, `l`, `c`（开/高/低/收） |
| 数据分块 | 60 天/块，超时或网络错误时最多重试 4 次（指数退避，0.6/1.2/1.8/2.4 秒） |
| 时间范围 | `1732752000000` (2024-11-28 00:00 UTC) → `1788739200000` (2026-09-07 00:00 UTC) |
| 期望条数 | 642 根日K；要求**连续无缺口**（相邻 bar 时间间隔 ≤ 1.5 天），否则视为数据不达标 |

数据按 `t` 升序返回后，按以下结构组织为数组 `bars[]`，下标 `i` 表示第 `i` 根（从 0 开始）：

```text
bars[i] = { ts: int ms, open: float, high: float, low: float, close: float }
```

---

## 3. 参数（全部可调，基线值见下表）

| 参数 | 字段名 | 基线值 | 取值范围 / 说明 |
|---|---|---|---|
| MA 周期 | `ma_period` | **7** | 整数 ≥ 2 |
| ATR 周期 | `atr_period` | **14** | 整数 ≥ 2 |
| ATR 倍数 | `atr_mult` | **1.5** | > 0；典型 1.0–3.0 |
| 斜率阈值 | `slope_thr_pct` | **0.0** | 日 %；0 表示仅要求 MA7 上升 |
| 初始资金 | `init_equity` | **1.0** | 任意正值（用于归一化收益） |

---

## 4. 指标定义（精确公式）

### 4.1 7 日简单移动平均 `MA7[i]`

```
for i in 0..N-1:
    if i < ma_period - 1:                # i < 6
        MA7[i] = None
    else:
        MA7[i] = sum(close[i-6 : i+1]) / 7.0
```

### 4.2 真实波幅 `TR[i]`（Wilders 经典定义）

```
TR[0] = high[0] - low[0]
for i in 1..N-1:
    TR[i] = max(
        high[i] - low[i],
        abs(high[i] - close[i-1]),
        abs(low[i]  - close[i-1])
    )
```

### 4.3 Wilder ATR14（14 日平均真实波幅）

```
# 种子（i = atr_period - 1 = 13）：前 14 根 TR 的算术平均
ATR[0..12] = None
ATR[13] = sum(TR[0..13]) / 14.0
for i in 14..N-1:
    ATR[i] = (ATR[i-1] * 13.0 + TR[i]) / 14.0
```

### 4.4 MA7 斜率（百分比日变动）

```
slope[i] = None                              # i < 1 无意义
for i in 1..N-1:
    if MA7[i-1] is None or MA7[i] is None: slope[i] = None
    else: slope[i] = (MA7[i] - MA7[i-1]) / MA7[i-1] * 100.0
```

---

## 5. 状态机

```
            ┌──────────────────────────────────────┐
            │                                      │
            ▼                                      │
         ┌──────┐   入场三条件全部满足                │
         │ FLAT │ ─────────────────────► ┌──────┐   │
         └──────┘                        │ LONG │   │
            ▲                            └──────┘   │
            │                                │      │
            │  止损触发                       │      │
            └────────────────────────────────┘      │
                  (日内 low 触及或收盘 ≤ 止损)
```

- **同一时间至多一笔持仓**；若仍在 LONG，则**忽略入场信号**。
- 进入 LONG 的**当日不检查出场**（防止当日自成交）；从次日 (`i > entry_i`) 开始检查。

---

## 6. 入场规则（LONG，从 FLAT 转入）

对每一根 bar `i`（`i ∈ [0, N-1]`），**仅在 FLAT 时**评估：

**前置条件**（任一不满足则不可入场）：
- `i ≥ 14`（确保 MA7[0..6] 与 ATR[13] 均已就绪）
- `MA7[i-1] is not None` 且 `MA7[i] is not None`
- `ATR[i] is not None`

**三条件同时满足**才触发买入：

```
1. prev_close_below_ma = close[i-1] < MA7[i-1]
2. cross_up            = close[i]   > MA7[i]
3. slope_above_thr     = (slope[i] is not None) and (slope[i] > slope_thr_pct)
```

**成交**：
- `entry_price = close[i]`（**当日收盘价成交**——乐观口径）
- `entry_idx = i`
- `current_stop = MA7[i] - atr_mult * ATR[i]`（入场即设初始止损位）
- 状态 → LONG

---

## 7. 出场规则（FLAT，从 LONG 转入）

对每一根 bar `i`（`i ∈ [0, N-1]`），**仅在 LONG 且 `i > entry_i`** 时评估：

**Step 1：更新移动止损（只上移不下移）**

```
new_stop = MA7[i] - atr_mult * ATR[i]     # 若 MA7[i] 或 ATR[i] 为 None 则跳过
if new_stop > current_stop:
    current_stop = new_stop
```

**Step 2：触发检测（按顺序判断，先日内后收盘）**

```
exit_price = None

if low[i] <= current_stop:
    exit_price = current_stop        # 假设止损单以止损价成交
elif close[i] <= current_stop:
    exit_price = close[i]            # 否则按收盘价离场
```

**Step 3：成交**

若 `exit_price is not None`：
- 记录 trade `(entry_idx, i, entry_price, exit_price)`
- `equity *= (exit_price / entry_price)`（**复利**）
- 状态 → FLAT

---

## 8. 收益、复利与权益曲线

- `equity` 初始为 `init_equity = 1.0`。
- 每笔交易离场时 `equity *= (1 + return)`，其中 `return = (exit_price / entry_price) - 1`。
- 权益曲线（NAV）`nav[i]`（`i ∈ [0, N-1]`）：

```
if LONG:  nav[i] = equity * (close[i] / entry_price)
else:     nav[i] = equity
```

- **回测结束若仍持仓**：按 `close[N-1]` 强制平仓，参与最后复利，并补记一笔 trade。

---

## 9. 指标计算

```
total_return   = equity - 1.0
buyhold_return = close[N-1] / close[0] - 1.0
days           = (bars[N-1].ts - bars[0].ts) / 86_400_000.0
CAGR           = equity ** (365.0 / days) - 1.0
max_drawdown   = max over i of (peak[i] - nav[i]) / peak[i]    # peak 滚动最大值
n_trades       = len(trades)
n_wins         = count(trades[k] where exit_price > entry_price)
win_rate       = n_wins / n_trades
avg_return     = mean over k of (exit[k] / entry[k] - 1)
avg_hold_days  = mean over k of (exit_idx[k] - entry_idx[k])
```

---

## 10. 边界与必须遵守的约束

1. **不可使用未来数据**：bar `i` 的所有决策只能读 `close[0..i]`、`high[0..i]`、`low[0..i]`、`MA7[0..i]`、`ATR[0..i]`。
2. **入场当日不检查出场**（避免自成交）。
3. **i < 14** 时不可入场（指标未就绪）。
4. **i = 0** 时无 MA7/ATR/斜率可读；`close[-1]` 等下标越界直接视为不满足条件。
5. **None 处理**：任何指标为 `None` 的 bar 不参与入场/出场判断。
6. **若仍有持仓到末尾**：按 `close[N-1]` 强制平仓，计入最后一笔 trade。

---

## 11. 期望输出

### 11.1 控制台

- 数据范围（起止日期、条数）
- 斜率阈值敏感性表（`slope_thr ∈ {0.0, 0.3, 0.5, 1.0}`），每行打印：
  `交易数 | 胜率 | 平均持仓 | 累计收益 | 年化 | 买入持有 | 最大回撤 | 单笔平均`
- 逐笔明细（基线阈值 0.0 下的 14 笔）

### 11.2 文件

- `hype_trades.csv`：列 `entry_date, entry_price, exit_date, exit_price, ret_pct, hold_days`
- 可选：`hype_nav.pkl` 保存 `nav` 数组、buy-hold 数组、trades 列表，供画图脚本使用

---

## 12. 验收测试（必过）

实现完成后必须**逐条复现**以下数值（取 Hyperliquid 官方 642 根日K，参数基线 = 7 / 14 / 1.5 / 0.0）：

| 测试 | 期望值 |
|---|---|
| 数据条数 | 642 |
| 数据首日收盘 | 12.72 |
| 数据末日收盘 | 87.28（或 87.51 ± 0.5，因末日 bar 仍形成中） |
| 买入持有收益 | +585.9% ± 0.5% |
| **总交易数** | **14** |
| **胜率** | **50.0%**（7/14） |
| **累计收益（基线）** | **+464.9% ± 1%** |
| **最大回撤（基线）** | **26.9% ± 0.5%** |
| 平均持仓天数 | 22.4 ± 1 |
| 第 1 笔：入场 2025-01-21 @ 23.18，离场 2025-02-24 @ 21.58，收益 -6.9% | 必现 |
| 第 2 笔：入场 2025-03-18 @ 14.18，离场 2025-03-26 @ 13.07，收益 -7.8% | 必现 |
| 第 3 笔：入场 2025-04-09 @ 13.57，离场 2025-05-30 @ 30.94，收益 +128.0% | 必现 |
| 末笔：入场 2026-08-08 @ 55.07，离场 2026-09-07 @ 87.28，收益 +58.5% | 必现（末日强制平仓） |

**斜率阈值 0.5% 期望**：交易 12、胜率 58.3%、累计 **+493.0%**、最大回撤 26.1%。

---

## 13. 实现建议（不是约束，仅供参考）

- 语言不限；**Python + numpy** 或 **Rust** 均可。
- 数据获取用 `urllib`/`requests` 分块（每块 60 天）+ 重试；**不要**在 shell 里拼 JSON。
- 指标计算向量化；`O(N)` 即可，N ≤ 1000 不需要性能优化。
- 图表（可选）：`matplotlib`，价格 + MA7 + 买卖点 + 权益曲线 vs 买入持有。
- 画图用 PingFang SC / Hiragino Sans GB 渲染中文，**`plt.rcParams['axes.unicode_minus'] = False`**。

---

## 14. 已知不在范围内（可后续扩展）

- 做空信号（"昨日在 MA7 以上、今日向下穿越"）—— 当前 Spec 不含。
- 手续费、滑点、**资金费率**—— HYPE 永续在长持仓期有显著成本，本 Spec 不计。
- 下单按次根 K 线开盘价成交—— 本 Spec 按当日收盘（乐观）。
- 多标的组合、风控仓位—— 不在范围。

---

**Spec 版本**: v1.0  ·  基线参数: `ma_period=7, atr_period=14, atr_mult=1.5, slope_thr_pct=0.0`  ·  数据源: Hyperliquid candleSnapshot
