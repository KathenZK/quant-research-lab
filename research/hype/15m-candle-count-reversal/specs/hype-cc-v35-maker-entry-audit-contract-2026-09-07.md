# HYPE-CC-V35 极值 Maker 入场审计契约（2026-09-07）

## 1. 研究问题与边界

本轮只验证同事截图中的可检验部分：在 `HYPE-Candle-Count-Reversal` 的 `10/8`
信号出现后，不再立即提交 IOC / 下一根开盘成交，而是在信号使用的最近 10 根闭合
`15m` K 线极值挂 post-only maker，最长保留 4 小时。截图中的“均线过滤”没有给出
类型、周期和方向规则，因此不能作为 exact reproduction；只允许做预先声明的敏感性对照。

本轮不是新版本登记，不修改 `HYPE-CC-V35`、runner、dry-run 或 live 状态，也不从
收益结果反推上线许可。

## 2. 冻结数据与窗口

- 市场 / 标的 / 周期：Binance USD-M Futures `HYPE/USDT:USDT` / `15m`。
- 本地冻结底座：`binance.perp.ohlcv.15m.history.v3`，物理 manifest SHA256 与
  parquet inventory fingerprint 必须写入产物。
- 当前已知门禁：catalog registry 的该数据集 fingerprint 与物理 manifest 不一致，
  `load_trusted_research_dataset()` 会拒绝。因此本轮可以生成只读、manifest-bound 的
  diagnostic，但在 registry parity 修复并重新严格读取前，正式结论必须标记
  `DATA_OR_REPRODUCTION_FAILURE`。
- 若需要覆盖本地截止后的“现在”，只允许从 Binance 官方公开 REST
  `/fapi/v1/klines`、`/fapi/v1/markPriceKlines`、`/fapi/v1/fundingRate` 读取尾部；
  不回写或覆盖 data lake。产物记录抓取时间、请求范围、闭合截止、重复、缺口与
  OHLC 合法性。
- 主张窗口：`2026-08-01T00:00:00Z` 到运行时最后一根完整闭合 `15m` K 的 open time。
- 指标 warm-up：从 HYPE 本地首根 K 开始计算；主张窗口在 8 月 1 日以 flat、
  `risk_multiplier=1`、无 cooldown、无 pending order 的新状态启动。
- 连续状态敏感性：另从本地首根 K 启动状态机并在 8 月 1 日归一化，但不得替代主张窗口。
- 审计切片：以数据尾端锚定最近 `1d / 7d / 1m / 3m / 6m / 1y`；不用于选参。

## 3. 共同策略规则

除入场方式外，沿用冻结 `HYPE-CC-V35`：

- 最近 10 根闭合 K 中阳线不少于 8 根做空；阴线不少于 8 根做多；仅在信号新出现时处理。
- `ATR672` 动态 allocation，最大 `3x`，`target_atr_pct=0.006`。
- 止损 `clamp(5.0 * ATR672/close, 2.5%, 3.5%)`；止盈
  `clamp(5.5 * ATR672/close, 2.0%, 3.5%)`。
- 保留原 `96` 根 / `5%` 逆趋势禁入、反向信号间隔 `8` 根、平仓后 cooldown `8` 根。
- 保留 `3/3` 反向 early exit、`12/9` 反向与顺向 counter exit。
- 止损使 risk multiplier 减半，最低 `0.0625`；止盈重置为 `1`；early exit 不改变。
- 信号、ATR、过滤与 allocation 只能使用信号 K 收盘时已闭合的数据。

## 4. 冻结入场变体

### B0：下一根开盘 Taker 基线

信号 K 闭合后，在下一根 K 的 open 建仓；同一入场 K 的保护触发按保守顺序处理，
止损优先于止盈。它是当前 handoff 的可执行时间基线。

### M0：10 根极值 Maker

- 多单限价：信号窗口 10 根 K 的最低 `low`。
- 空单限价：信号窗口 10 根 K 的最高 `high`。
- 信号 K 闭合后才提交；信号 K 自身不得用于判定成交。
- 从下一根 K 起最多检查 16 根 `15m` K；第 16 根结束仍未成交则撤单。
- pending 期间不接受新信号；成交或到期前都不启动 cooldown。
- allocation、止盈止损百分比及均线判定冻结在信号 K；止盈止损价格以实际限价成交价计算。
- 同一 bar 内成交并触发保护时，按保守顺序视为先成交、再止损、最后止盈。
- `touch`：价格触及限价即全额成交。这是乐观队列模型。
- `trade_through_1tick`：必须越过限价至少一个当时 Binance `tickSize` 才全额成交。
  这是主判定模型，但仍不证明排队位置、部分成交或真实 maker fill。

## 5. 均线敏感性（非 exact reproduction）

使用此前同家族、在当前 8 月窗口揭示前已经研究过的 `EMA24/672`，避免在本轮结果上
搜索周期：

- `M1-dual`：多单只在 `EMA24 > EMA672`，空单只在 `EMA24 < EMA672` 时允许挂单。
- `M1-short-only`：仅空单要求 `EMA24 < EMA672`，多单不加均线条件。

二者只回答“一个已预声明的均线规则会怎样”，不能证明截图中同事使用的均线就是它。

## 6. 成本、资金费与收益口径

- 可比主口径沿用 V35 明示成本：每次成交 fee `0.00045 * allocation`；taker 入场和
  所有退出另计 adverse slippage `0.0004 * allocation`；maker 入场不计滑点。
- 另报仓库 Binance 默认保守成本敏感性：fee `0.001/fill`，其余滑点相同。
- Maker 必须实际成交才计费用；撤单不计交易费。
- 资金费按事件时间和持仓方向计入。只有覆盖证据完整的子窗口可称为 verified net；
  官方 API 尾部事件只作 observed-funding sensitivity，缺失不得填零冒充完整净收益。
- 收益采用逐 bar 复利权益，`+300%` 表示期末权益至少为初始的 `4.0x`，不是成交名义金额。
- 未平仓在数据末端按最后 close 强制估值平仓并单列 `terminal_mark`；该笔不作为自然胜负。

## 7. 结论门禁

- `+300%` 数值复现：主张窗口、V35 明示成本、observed funding 下，M0 的
  `touch` 与 `trade_through_1tick` 都必须达到 `return >= +300%`。
- Maker 改善：M0 两种成交模型都必须同时高于 B0 收益；回撤变化另报，不以收益遮蔽风险。
- 均线结论：只报告冻结的两种 EMA24/672 敏感性，不从中挑选“最优策略”。
- 只要 catalog trusted read 失败、完整 mark K 缺失、完整 funding 证据缺失、同事均线
  规格缺失或 maker 队列无法验证，最终就不能写“发现已确认”；正式结论保持
  `DATA_OR_REPRODUCTION_FAILURE`，同时允许报告数值上是否支持或否定 `+300%`。
- 不得登记新版本、promotion、修改 runner 或给出 live-ready 结论。
