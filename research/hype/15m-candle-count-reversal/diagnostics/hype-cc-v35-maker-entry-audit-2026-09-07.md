# HYPE-CC-V35 极值 Maker 入场审计（2026-09-07）

## 结论

截图中的“从 8 月 1 日至今收益 300%+”没有复现。按当前家族冻结的
`HYPE-CC-V35` 信号、风险与退出规则，单独把下一根开盘成交改成“最近 10 根极值挂
maker、最长 4 小时”，收益从 `+30.64%` 降至 `-19.45%`。即使叠加在当前窗口揭示前
已经研究过的 `EMA24/672` 过滤，最高也只有 `+80.51%`；在完全不计交易成本和资金费的
反事实口径下，最高为 `+100.28%`，仍远低于 `+300%`。

因此，本轮数值判断为 `NUMERIC_CLAIM_NOT_REPRODUCED`。截图没有给出均线类型、周期、
方向条件及其他实现细节，K 线也不能证明真实 maker 队列位置与部分成交，完整主张窗口的
funding calendar 尚未被数据集证明完整，所以 exact reproduction 的正式状态保持
`DATA_OR_REPRODUCTION_FAILURE`。这不是新版本登记，不修改 V35 runner、dry-run 或
live 状态。

## 冻结问题与方法

- 市场：Binance USD-M Futures `HYPEUSDT`，`15m`。
- 主窗口：`2026-08-01 00:00:00 UTC` 至最后一根冻结闭合 K
  `2026-09-07 07:30:00 UTC`。
- 截图未写时区；另将起点解释为北京时间 `2026-08-01 00:00:00+08:00` 复跑，
  所有主表收益、回撤和交易数均不变。
- B0：V35 信号后下一根 open 以 taker 成交。
- M0：多单挂最近 10 根最低价、空单挂最近 10 根最高价；信号 K 闭合后提交，最多
  检查后续 16 根 K，过期撤单，pending 时忽略新信号。
- Maker 主成交模型要求价格至少越过限价一个 Binance `tickSize=0.001`；另以“触价即
  全成”的乐观模型复核。两者在本窗口得到相同成交集合。
- 均线不是从本轮结果中搜索；只使用本家族在 8 月窗口前已审计过的 `EMA24/672`，并同时
  跑同一均线下的下一根开盘 B1 与 maker M1，以拆分均线和入场效应。
- 主成本沿用 V35 明示口径：每次成交 fee `4.5 bps × allocation`，taker 入场与所有
  退出另计 `4 bps × allocation` adverse slippage；另报仓库 Binance 保守费率
  `10 bps/fill`。
- `+300%` 解释为权益从 `1.0` 增至至少 `4.0`，不是成交名义金额或杠杆仓位累计。

完整预声明见
[审计契约](../specs/hype-cc-v35-maker-entry-audit-contract-2026-09-07.md)。

## 主窗口结果

下表均含官方已观察到的 funding 事件，收益为复利净收益；MDD 为权益最大回撤。

| 变体 | 入场 | 均线规则 | 收益 | MDD | 交易数 | 多 / 空 | Maker 成交率 |
|---|---|---|---:|---:|---:|---:|---:|
| B0 | 下一根 open | 无 | +30.64% | -19.01% | 29 | 19 / 10 | — |
| M0 | 10 根极值 | 无 | -19.45% | -29.40% | 25 | 14 / 11 | 75.76% |
| B1-dual | 下一根 open | 多空均顺 EMA24/672 | +68.31% | -20.00% | 22 | 20 / 2 | — |
| M1-dual | 10 根极值 | 多空均顺 EMA24/672 | +77.59% | -18.36% | 19 | 17 / 2 | 82.61% |
| B1-short-only | 下一根 open | 只过滤逆势空单 | +80.51% | -20.00% | 24 | 22 / 2 | — |
| M1-short-only | 10 根极值 | 只过滤逆势空单 | +75.99% | -18.36% | 20 | 18 / 2 | 76.92% |

仓库保守费率下，B0 / M0 / M1-dual / M1-short-only 分别为 `+22.06% / -24.04% /
+68.41% / +66.34%`。完全不计费用、滑点和资金费时，B0 / M0 / M1-dual /
M1-short-only 分别为 `+45.19% / -13.84% / +89.66% / +88.68%`。放宽摩擦不能把
结果推到 `+300%`。

## 归因：改善主要来自过滤空单

同一 EMA 规则内只切换入场方式：

- dual 规则下，maker 相对下一根 open 仅增加 `9.28` 个百分点（`77.59 - 68.31`）。
- short-only 规则下，maker 反而减少 `4.52` 个百分点（`75.99 - 80.51`）。

所以没有稳定的 maker 收益优势。截图中“做空被过滤了不少”在方向数量上成立：无均线
M0 有 11 笔空单，EMA 后仅剩 2 笔。但这 11 笔 M0 空单仅 1 笔盈利、9 笔止损，按逐笔
复利合计约 `-47.46%`；M0 的 14 笔多单则约 `+53.29%`。均线组合变好的主要原因是
当前样本压掉了亏损空单，而不是 maker 本身产生了 `300%+`。

这也不能外推为一个已验证的新策略：EMA24/672 是预声明敏感性，不一定是同事实际使用
的规则，而且本家族此前对该均线的滚动 OOS 结论是候选失败。本轮窗口只有约 37 天，
又是看见结果后的复核窗口。

## 数据质量与可执行边界

- 价格底座经 canonical V3 strict-content loader 读取：本地 `44,469` 根，inventory
  fingerprint 与 manifest 一致；官方尾部 trade / mark 各 `5,215` 根，合并后
  `44,629` 根，无缺口、重复或 OHLC 违规。
- 本地与 Binance 官方 REST 的 `5,055` 根 trade overlap 在 OHLCV 上零差异；mark
  overlap 的 high / low 也零差异。尾部来自 Binance 官方 kline 与 mark-price kline
  接口，只读取、不回写 data lake。
- Funding rate 在本地与官方重叠的 `2,778` 个事件上数值零差异，但当前 funding 数据集
  明确标记为 `PARTIAL_COVERAGE`；主窗口资金费只能称 observed，不称完整 verified net。
- `touch` 与越过一 tick 的结果相同，只说明本窗口没有仅等于限价的边界成交；15m OHLC
  仍看不到撮合队列、挂单撤改单、部分成交和 post-only 被拒，因此 maker 成交率是模型值，
  不是实盘成交证明。

官方接口口径参见 Binance 的
[Kline/Candlestick Data](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Kline-Candlestick-Data)、
[Mark Price Kline Data](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Mark-Price-Kline-Candlestick-Data)
与 [New Order](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/New-Order)。

## 复核与产物

- 新增的订单时序测试覆盖：信号 K 不成交、延迟成交、16 根到期、越过一 tick、
  short-only 均线过滤及同 bar 成交后保守止损顺序。
- 相关目标测试共 `62 passed`，脚本与测试通过 Ruff。
- 旧 `run_next_open` 实现对同一输入快照得到 B0 `+30.97%`、MDD `-19.01%`、
  29 次入场；本脚本为末端仍持有的一笔空单追加 `terminal_mark` 和退出成本后为
  `+30.64%`。约 `0.33` 个百分点差异可解释，不影响本轮判断。
- 输入快照 SHA256：
  `1d4353c22b03b23c76357007c72fc35bfa45a715853e4a0088fb75f80bbcf072`；快照保留
  HYPE 上市以来至冻结尾端的 `44,629` 根输入及预计算特征，避免截断 EMA warm-up。

产物：

- [汇总 JSON](../artifacts/hype_cc_v35_maker_entry_summary_2026-09-07.json)
- [全窗口与切片对照](../artifacts/hype_cc_v35_maker_entry_comparison_2026-09-07.csv)
- [逐笔交易](../artifacts/hype_cc_v35_maker_entry_trades_2026-09-07.csv)
- [冻结输入快照](../artifacts/hype_cc_v35_maker_entry_input_2026-09-07.parquet)
- [可复现脚本](../scripts/research_hype_cc_v35_maker_entry_audit.py)
- [目标测试](../../../../tests/test_hype_cc_v35_maker_entry_audit.py)

若要对同事代码做 exact parity，至少还需要：均线种类与周期、过滤多空的布尔条件、限价
取值是否含信号 K、4 小时计时边界、未成交后是否追价 / 转 IOC、真实 maker/taker 费率、
收益是否含杠杆与资金费，以及原始逐笔成交或回测代码。缺少这些信息时，`300%+` 不能被
当成已证实结果。
