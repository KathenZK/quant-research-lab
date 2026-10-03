---
research_classification: strategy_family
---

# M0264 · ClucMay72018 研究回测

结论：HYPOTHESIS_NOT_STRICT / ADAPTED_EXECUTION_PROXY，仅诊断；严格复现数为0。原始策略的限价单、原作者配置和市场范围没有得到复现证明。

2024年BTCUSDT现货原生5分钟，初始100,000 USDT。基准费率每边8bps、每边滑点2bps、信号延迟1根：收益0.52%，最大回撤4.99%，日频Sharpe 0.1379，完整往返7次。

## 固定规则

- 入场：close<EMA50(close) AND close<0.985*BB20(typical,2).lower AND volume<mean(volume,30).shift(1)*20
- 信号退出：close>BB20(typical,2).mid
- 固定止损：-5.00%；ROI分钟表：{"0": 0.01}。
- 来源补充：ema100 column is EMA50; volume threshold uses previous rolling mean; RSI5/EMA5(RSI)/MACD/ADX computed but unused in signals.
- 当根收盘形成信号，下一根开盘执行；延迟2配置再等一根。不使用预热期信号下单。
- 同时出现入/出信号时不据此入场或退出；止损/ROI仍生效。信号退出先于风险判断，盘内两阈值可达时止损优先。
- 信号退出盈利门：False；按原始开盘价和买卖手续费判定盈利，之后再计卖出滑点。门控不作用于止损/ROI。
- 每次使用95%可用现金，预算包含入场费；仅多头、1倍、最多一仓、不加仓、允许小数数量。期末不强平，未实现卖出费不计入。

## 四个预先冻结配置

| 配置 | 每边手续费 | 信号延迟 | 收益 | 最大回撤 | 日频Sharpe | 往返 | 期末权益USDT |
|---|---:|---:|---:|---:|---:|---:|---:|
| base | 8bps | 1根 | 0.52% | 4.99% | 0.1379 | 7 | 100523.330326 |
| fee0 | 0bps | 1根 | 0.68% | 4.92% | 0.1749 | 7 | 100675.832341 |
| fee20 | 20bps | 1根 | 0.30% | 5.13% | 0.0862 | 7 | 100295.033897 |
| delay2 | 8bps | 2根 | -0.91% | 6.54% | -0.1281 | 7 | 99088.701847 |

同窗口基准只引用既有M0311买入持有：收益115.03%、最大回撤32.02%、日频Sharpe 1.7447。本批未新增控制回测；精确摘要哈希已核验，基准曲线原文件未取得，因此结构化记录不填补曲线。

## 数据、因果与独立核验

- 114,336根连续原生K线，其中2023年12月8,928根仅预热；2024年105,408根用于评估，366日。缺口/重复/异常OHLCV直接拒绝，没有插值、删行、替代市场或重新下载行情。
- 已持有的39个原始对象哈希核验通过；该输入仍为DIAGNOSTIC_ONLY，trusted=false，PIT与严格终态未证实。原始来源与本地获取清单的哈希不同，按单独冻结的兼容性补充保留两者，不能混称。
- 原类实际加载、全部标志与参数、完整qtpylib重导出链核对；原信号与独立Boolean表达式逐行相同。完整样本10个前缀/未来扰动切点通过；高级TA指标仍依赖同一固定TA-Lib，未声称全部独立重实现。
- 冻结Decimal独立账户复算及补充事件阶段、时间、可用性、notional、所有指标核验通过；绝对容差0、相对1e-9，预期零严格为零。
- MDD来自完整5分钟路径；日频Sharpe采用UTC日末收益、样本标准差、sqrt365、无风险利率0；年化365/366。日采样曲线的回撤分母仍来自完整5分钟峰值。

## 边界与使用限制

- 原始GTC限价、排队、部分成交、撤单、超时、最小金额/手数、订单簿和历史可交易性未模拟。开盘/阈值完整成交是研究代理假设；盘内路径未知。
- 单市场单年度且是可取得来源的筛选样本，不是OOS，不是稳健性或可实盘证明。未做参数搜索；四配置不得计为四个策略。
- 只在父协调者完成公开集成/检查后登记全局；此包不意味着网站、Git或Graph已发布。

## 恢复与证据

- [固定协议](specs/protocol.json)、[C0](specs/C0.json)、[源规则卡](specs/source-rule-card.json)、[完整指标摘要](artifacts/results/summary.json)、[核验摘要](artifacts/results/validation-summary.json)。
- 每ID4配置，1个策略；每配置105,408根。附完整私有账户日志和源码/依赖锁；公开仅日曲线与非统计抽样。完整原始OHLCV不打包；私有账户日志保留估值收盘价。恢复必须提供同SHA的已授权本地输入。
- 本ID首轮执行耗时11.735秒、CPU11.732秒；进程累计峰值RSS 696193024字节。实际Library读回与再次运行的独立收据在批包交付后提供，不与新配置数混计。

固定来源：https://raw.githubusercontent.com/freqtrade/freqtrade-strategies/f3340ce11f5bdf62f598522e64d1f5638eaa13f5/user_data/strategies/berlinguyinca/ClucMay72018.py
来源commit：f3340ce11f5bdf62f598522e64d1f5638eaa13f5；SHA256：d146f7bc8285b5f1e48514d5d6acc53b37b0ca00299780210e3bdf84564978aa。
