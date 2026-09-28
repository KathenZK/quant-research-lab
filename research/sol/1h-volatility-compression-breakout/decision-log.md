## 2026-09-03 — 家族 README 压缩为路由页

- 决定：按家族 README ≤30 行路由页合同压缩 `README.md`（压缩前 88 行）。下列原文从 README 下沉到本决策记录，信息不删除、研究结论不变。

<details>
<summary>压缩前 README 全文</summary>

````markdown
# SOL-1H-Volatility-Compression-Breakout

- Full family name：`SOL-1H-Volatility-Compression-Breakout`
- Short id：`SOL-1H-VCB`
- 市场/周期：Binance USD-M Futures `SOLUSDT` perpetual `1h`
- 机制：多 K 波动压缩 arm、冻结区间、有限窗口突破确认、下一根 open 入场、ATR fixed/trailing exit 与风险预算仓位。
- 当前状态：首轮扩展搜索 `0` hard-gate 命中；`explore / not promoted / not live-ready`。

## Family 边界

本 family 与 `SOL-1H-Adaptive-Regime` 独立，不继承其 V1/V2 版本号。Adaptive-Regime 已覆盖单 K squeeze、Donchian、VWAP 等通用信号；本 family 的身份是显式多 K 压缩区间状态机与正偏趋势收益结构。

## 研究口径

- 数据：2026-07-13 刷新的最近两年闭合 `1h` K，独立保存在本 family artifacts，不覆盖旧 family 冻结证据。
- 成本：fee `0.001`/fill、slippage `4 bps`/fill、真实 Binance funding。
- 执行：闭合 K 确认，下一根 open 市价成交；初始保护 stop 即时有效；stop-first；跳空按 open；trailing 闭合后更新次 K 生效。
- 选择：仅使用 train/validation/prefit。
- `2026-04-03` 至 `2026-07-03` 为旧 SOL 研究已揭盲的 reused holdout，只审计。
- `2026-07-03` 至 `2026-07-13` 为约 10 天 fresh-forward 观察，样本不足以 promotion。

## 入口

- 主账：`sol-1h-vcb-core-ledger.md`
- 决策记录：`decision-log.md`
- 首轮搜索：`diagnostics/sol-1h-vcb-search-2026-07-13.md`
- 数据抓取：`scripts/fetch_sol_1h_vcb_data.py`
- 搜索脚本：`scripts/research_sol_1h_vcb_search.py`
- 机器证据：`artifacts/`

# SOL-1H-Volatility-Compression-Breakout

- Full family name：`SOL-1H-Volatility-Compression-Breakout`
- Short id：`SOL-1H-VCB`
- 市场/周期：Binance USD-M Futures `SOLUSDT` perpetual `1h`
- 当前状态：`explore / no registered version / not promoted / not live-ready`

## 机制

本家族独立于 `SOL-1H-Adaptive-Regime`。它不使用 V1/V2 的同类单 K 指标回穿或高胜率小 TP 结构，而采用：

1. 多 K Bollinger width + ATR ratio 压缩状态；
2. 压缩成立后冻结价格箱体并 arm；
3. 在有限窗口内等待箱体突破、成交量和方向化 close location 确认；
4. 闭合 K 确认，下一根 `1h` open 入场；
5. ATR fixed/trailing exit；
6. fixed 或 risk sizing，最高杠杆 `3x`。

研究目标是提高 payoff 和正向尾部，而不是继续追求高胜率。

## 数据与验证纪律

- 数据：独立刷新 Binance FAPI 最近两年 `17520` 根闭合 `1h` K，UTC `2024-07-13T07:00:00Z` 至 `2026-07-13T06:00:00Z`。
- 数据质量：missing `0`、duplicate `0`、critical null `0`、OHLCV violation `0`、raw/normalized mismatch `0`。
- 成本：fee `0.001`/fill、slippage `4 bps`/fill、真实 Binance funding。
- selection：仅使用 train + validation，结束于 `2026-04-03T05:00:00Z`。
- reused holdout：`2026-04-03` 至 `2026-07-03`，已被旧 SOL family 揭盲，只审计。
- fresh forward：`2026-07-03` 至 `2026-07-13`，仅约 10 天，只作观察。

## 首轮结论

2026-07-13 首轮搜索：

- entry configs `800`；
- generated candidates `2940`；
- eligible `341`；
- `10x / 80% / <20% DD` prefit hard pass `0`；
- 当前结论 `explore / not promoted / not live-ready`。

prefit-only 最佳观察：

- prefit annual `1.3048x`、DD `-18.77%`、win `25.23%`、trades `107`；
- payoff `4.700`、avg win `+4.58%`、avg loss `-0.97%`；
- reused holdout return `+9.48%`、DD `-6.45%`；
- fresh forward return `-1.92%`，`2` 笔均亏损；
- full annual `1.3031x`、DD `-18.77%`。

新机制成功改变了 V2 的负偏收益结构，但收益强度低、fresh forward 未确认，不登记版本。

## 入口

- 主账：`sol-1h-vcb-core-ledger.md`
- 决策记录：`decision-log.md`
- 首轮报告：`diagnostics/sol-1h-vcb-search-2026-07-13.md`
- 数据抓取：`scripts/fetch_sol_1h_vcb_data.py`
- 首轮搜索：`scripts/research_sol_1h_vcb_search.py`
- 产物说明：`artifacts/README.md`
````

</details>

# SOL-1H-Volatility-Compression-Breakout Decision Log

## 2026-07-13：建立独立 family 并刷新数据

- 新建 `SOL-1H-Volatility-Compression-Breakout`（`SOL-1H-VCB`），不继承 `SOL-1H-Adaptive-Regime` 的 V1/V2。
- 机制固定为多 K 波动压缩 arm、冻结区间、有限窗口突破确认和 ATR 正偏退出，排除 V2 邻域继续微调。
- 从 Binance FAPI 刷新最近两年闭合 `SOLUSDT` perpetual `1h` K：`2024-07-13T07:00:00Z` 至 `2026-07-13T06:00:00Z`，`17520` 根；missing、duplicate、critical null、OHLCV violation、raw/normalized mismatch 均为 `0`。
- 成本固定为 fee `0.001`/fill、slippage `4 bps`/fill，并逐笔计真实 funding。
- 旧 SOL 研究已揭盲的 `2026-04-03` 至 `2026-07-03` 只作 reused-holdout audit；新增 `2026-07-03` 至 `2026-07-13` 仅作短 fresh-forward 观察。

## 2026-07-13：首轮扩展搜索 NO-GO

- 搜索 `3000` 组 entry state，生成 `14848` 个候选，`1579` 个通过 train/validation 基础门槛；`10x / 80% / <20% DD` prefit hard pass 为 `0`。
- prefit-only 最佳观察 `SOL_1H_VCB_R002346`：prefit annual `1.5279x`、DD `-16.69%`、win `37.84%`、trades `37`，payoff `3.868`。
- reused holdout annual `0.8870x`、return `-2.94%`、DD `-8.87%`；fresh forward `0` 笔。
- current full annual `1.4126x`、DD `-16.69%`；K+2 full annual `1.0425x`、DD `-27.65%`，延迟稳健性失败。
- 决策：首轮 `NO-GO / explore / not promoted / not live-ready`；不登记 V1，不继续扩大同一参数空间。

