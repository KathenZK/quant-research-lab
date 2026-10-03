# M1510 原源码只读预审

原固定源码已核实，尚未达到执行冻结条件。核验的是规则与依赖边界，不是历史表现；本次历史指标、信号、账户、控制均为 0，未创建 C0。

来源为 [固定源码](https://github.com/davidzr/freqtrade-strategies/blob/9623c1f3d8c7f60c8b411010fa26377e6ca99ab9/strategies/Babico_SMA5xBBmid/Babico_SMA5xBBmid.py)。短引用解析为完整 commit `9623c1f3d8c7f60c8b411010fa26377e6ca99ab9`，仓库提交时间 2023-11-05T15:22:08Z；该时间不代表策略首次提出日期。源码 1,813B，SHA256 `64846c265b53f34dfdd117cc31b195466f09e1dc154a9f3c3835cf1eab4600fd`，Git blob `aace9bb4b79271b62a8b5350a85fe535cf1eeb81`。实际 raw HTTP200 原件与固定目录 API 的 blob/长度吻合；目录只含该源码文件，未见同目录参数或依赖锁。

固定仓库 [LICENSE](https://github.com/davidzr/freqtrade-strategies/blob/9623c1f3d8c7f60c8b411010fa26377e6ca99ab9/LICENSE) 是 GPL 第3版全文，35,141B/SHA256 `589ed823e9a84c56feb95ac58e7cf384626b9cbf4fda2a907bc36e103de1bad2`。此为仓库许可证据，不替代每个社区贡献的权属审查，也不覆盖市场数据。源码本身未给作者/版本锁/单独许可证头；本次只交自撰安全摘要，不把源码全文加入公开仓库。README 仅要求安装 Freqtrade，不能据此锁定运行版本。

## 已证实规则与目录缺项

- 名称含 SMA，但实际快线调用 TA-Lib EMA，周期5；慢线是典型价的布林20中轨。布林参数2仅决定外轨，本源码信号不读取外轨。
- 原生时间框架为1d；快线上穿中轨产生 buy 标志，中轨上穿快线产生 sell 标志。这是交叉事件调用，不是持续大小状态；严格/等号/NaN 的实际边界由尚未锁定的 vendored qtpylib 决定。
- **目录未包含关键执行开关：`sell_profit_only=True`、`use_sell_signal=True`。** 因而不能把反向交叉直接解释为无条件亏损平仓。被盈利门阻止的交叉，不能自行改为“以后盈利立即补卖”的常驻条件。
- 原 buy/sell/stoploss 均声明 limit，且 stoploss_on_exchange 为 false。另有 trailing_stop_loss 映射；其是否被目标框架识别，须实际加载验证。源码 trailing_stop 为 false，其他 trailing 数值虽存在但不能据此启用追踪止损。
- stoploss 是有限 −0.99，ROI 原值是 `{"0":99999999}`，不是 Python 无穷大或省略风险分支；不得为复用旧引擎将两者删掉。process_only_new_candles 为 true 不等于已声明预热。

## 冻结前必须解决

1. **运行版本/配置。** 锁 Freqtrade、其 vendored qtpylib、TA-Lib Python与底层库、pandas/numpy，并实际加载旧 buy/sell API。源码没有 INTERFACE_VERSION、startup_candle_count、配置覆盖、stake/pairlist/max_open_trades、余额预算、杠杆、时间有效期或超时约定。不能把选定新版本的默认值说成原作者原运行默认。
2. **指标初始化。** EMA 的 seed、浮点/Decimal及兼容模式、lookback；典型价(H+L+C)/3的顺序；BB中轨的 rolling/min_periods/NaN；cross 当前严格与前值等号；数据边界和首次可交易 bar 都要锁定。不能把“window20”未经依赖核验直接当“前19根必 NaN”，或改用收盘价慢均线。采用 Decimal 独立实现必须说明与原 TA-Lib 数值不等价，不能加 epsilon 掩盖交叉。
3. **盈利门与成本。** 明确利润计算价格、双边费率/费用币、profit offset默认/覆盖、严格门槛、滑点落点及 gate 在决策还是成交时判断；确认它只限制何种退出，不能无证把止损/ROI也挡住。费用和滑点并未在本源码中声明。
4. **执行与风险优先级。** 明确 next-open或限价触达/队列/超时/部分成交、挂单消失/取消、同 bar BUY/SELL碰撞、止损/ROI/sell signal竞争次序、同 bar高低路径、跳空和期末未成交处理。仅日线 OHLC 无法证明实际限价成交或99%止损保证。若父端选 market next-open，应明确 ADAPTED_EXECUTION_PROXY，并保留声明的原风险条件及盈利门，不迁就既有引擎删除它们。
5. **研究身份与输入。** 原文件没有指定 BTCUSDT/Binance、评价区间或仓位比例。选这些属于研究适配。先决定输入/暖启动长度和已曝光窗口，再看收益；冻结前源验证完成不代表严格复现、PIT或实盘可交易性通过。

## 已有行情兼容性（只读元数据及不解析价格的 SHA 校验）

| 已验输入 | bytes / SHA256 | 可用覆盖与边界 |
|---|---|---|
| native1d 831行 | 139983 / `a21612759ddd7e849f4a5e5b3ac62f74b003c84bf9e0e77d45ab8670b59eb550` | 2022-09-23至2024-12-31；若评价为2023–2024则100预热+731评价 |
| native1d 1466行 | 247171 / `db05acd35ad9f09d08a3a2126fc0aba62c40ba12a90eef2faa00af0d3cd7ae26` | 2020-12-27至2024-12-31；同一评价窗则735预热+731评价 |

两者都是 BTCUSDT spot UTC原生1d，已有独立QA覆盖12原生列、OHLCV/grid/校验与离线重建；HLC满足典型价原料需要。本次只重新流式校验上述输入字节 SHA，未解析价格或重跑原数据QA。两者皆 DIAGNOSTIC_ONLY，PIT/finality/tradability 未证，2023-03-24已知盘中停牌不因日线网格完整而消失。100/735是各自已有研究的选择，不是 M1510 的原预热参数；735也不是本策略信号精度保证。若父端预先选择2023–2024评价，831已有足够原料做明确暖启动适配，是否采用100根仍须合同确定；不得从两套输入试出较优信号再择一。1466并非当前信号需求强制要求，不需要新行情请求。

## 最小合成扩展建议

这些是后续门禁建议，本审没有执行指标或账户合成运行。

- 用选定真实依赖类与另一独立实现对照：恒价、递增/递减、H/L改变而close不变、首4/5/19/20根、NaN及恢复、等号前值/当前值、极小差异、prefix/future；证明 EMA5非SMA5、典型价中轨非close均线，先全输入算特征后取评价视图而不重播种。
- 在持仓利润低于/等于/高于门槛时触发相同反向交叉；分别无费和双边费、原限价与声明代理。亏损交叉被拒绝后下一根无新交叉，核实不会无证补卖。止损和ROI分别独立触发，证明不会被错误的盈利门吞掉。
- 合成有限 −99%止损边界及跳空、巨大但有限ROI的等号/越界，覆盖同 bar signal/stop/ROI冲突；避免“ROI太大所以未实现”或“止损太宽所以删除”。
- 合成限价未触及、开盘改善、费用后现金不足、订单过期/取消/同侧重复、末端持仓/挂单，核查实际加载 flags，旧API/未知 order_types key应显式通过或阻塞。已有账户内核只有确实支持这些被冻结行为才可复用；其不同规则不能反向定义本策略。
- 四配置/控制数量由父端后续合同决定，本次不授权控制复用或删除。复用 benchmark 需资产、区间、账户预算、执行、费用/滑点、统计口径全部精确一致。

## 经济假设和失败场景

可检验假设是较快收盘EMA突破较慢典型价均值捕捉上行延续；这不是布林下轨抄底，也未得到因果收益证据。窄幅震荡容易反复交叉和付费；反向交叉若因亏损被盈利门拦截，会延长下跌中的持仓，−99%止损提供的资本保护很有限。日线限价、跳空、停牌和流动性也会使保证成交代理偏乐观。上述为待检验失败机制，不是已观测历史结果。

当前结论：`SOURCE_VERIFIED_EXECUTION_UNRESOLVED`；源码/版本/仓库许可证据可供父端准备冻结，执行语义缺项须显式解决，strict0/history0。本地抓取原件及私有 manifest 不是远端备份；本次未向 Library/Git/Site 写入。
