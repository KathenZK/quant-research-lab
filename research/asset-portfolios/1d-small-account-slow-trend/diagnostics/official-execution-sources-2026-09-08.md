# 执行面及官方来源核查

查询日期为 2026-09-08。下表只核对产品/公开交易条件，不表示用户已持有对应账户权限，也不把当日费率外推为历史真实券商账单。七只 ETF 均以美元交易，使用整股、不融资、不借券；基金内部持仓或期货管理机制不等于本账户使用杠杆。

| 工具 | 经济角色与官方核查 | 本研究处理 |
| --- | --- | --- |
| SPY | 美国大盘股，NYSE Arca，季度分配；[State Street 产品页](https://www.ssga.com/us/en/individual/etfs/state-street-spdr-sp-500-etf-trust-spy) | 市价与显式分配建账。原生价格不能直接替换为含分红复权价格来算整股 |
| EFA | 美国/加拿大以外发达市场大中盘股，NYSE Arca，半年分配；当前费用率 0.32%；[iShares 产品页](https://www.ishares.com/us/products/239623/ishares-msci-eafe-etf?periodCd=m) | 美元报价仍含底层汇率风险；本账户不再另加一次外汇收益 |
| VNQ | 美国上市房地产证券；[Vanguard 产品页](https://advisors.vanguard.com/investments/products/vnq/vanguard-real-estate-etf?compositionTabBox=1) | 房地产股票与其他股票并非独立风险资产。不同类别税务分配尚未按个人税籍还原 |
| IEF | 7–10 年美国国债，NASDAQ，月配，费用率 0.15%；2026-09-04 收盘 92.25，30 日中位买卖价差 0.01%；[iShares 产品页](https://www.ishares.com/us/products/239456/ishares-710-year-treasury-bond-etf) | 中久期债券会有资本损失，不用到期收益率充当账户现金利息 |
| TLT | 20 年以上美国国债，NASDAQ，月配，费用率 0.15%；2026-09-04 收盘 82.21，30 日中位价差 0.01%；[iShares 产品页](https://www.ishares.com/us/products/239454/ishares-20-year-treasury-bond-etf) | 与 IEF 的期限风险相关；2022 为必要压力块 |
| GLD | 黄金信托，跟踪黄金减费用，费用率 0.40%；[State Street 产品页](https://www.ssga.com/us/en/individual/etfs/spdr-gold-shares-gld) | 不假定有票息或现金分红，费用已在实际交易价变化中体现 |
| PDBC | 大类商品期货管理基金、No K-1，2014-11-07 成立，NASDAQ；[Invesco 官方事实表](https://www.invesco.com/us-rest/contentdetail?contentId=03b8588c0971b410VgnVCM100000c2f1bf0aRCRD) | 使用基金本身市场价、分配与费后路径，不冒充逐合约期货 roll 验证。成立日期限制账户共同历史，不拼接 DBC |

券商成本采用公开条件形成可复算假设：`max($1, $0.005×股数)`，另收成交额 0.5 bps 的监管/清算保守余量、基础单边 5 bps 不利滑点。最低费用的微小订单上限优惠未使用，偏保守。官方固定计划费率、佣金上限、交易所及监管费用可能依券商实体不同；真实开户实体和路由须在前瞻前核实。[IBKR 固定计划](https://www.interactivebrokers.com/en/accounts/fees/stknorthambundcoms.php?ib_entity=es&path=3)

IBKR 的首 10,000 美元闲置现金不付息，本研究全部现金按 0% 计息，即便后期 NAV 增长可能使部分现金具备计息资格，也不把未知账户权益算进利润。[IBKR 利息规则](https://investors.interactivebrokers.com/en/accounts/fees/pricing-interest-rates.php?menu=A)

账户采用现金已结算资金，销售所得延迟用于新买入：2017-09-05 前 T+3，其后 T+2；2024-05-28 起 T+1。这些结算天数按交易日历推进，不把周末当结算日。节假日与提前闭市使用 `exchange_calendars` 的 XNYS 日历；NASDAQ 股票常规交易日通过同一日历核验，但不声称已证明各上市交易所开盘竞价微观规则。[SEC 2017 实施说明](https://www.sec.gov/newsroom/press-releases/2017-163)、[SEC 2024 实施说明](https://www.sec.gov/newsroom/press-releases/2024-62)

分配应收在除息日计入权益；现金统一等 60 自然日后的下一交易日才释放。SPY 历史存在较长的除息到支付间隔，不能用股票收盘价的分红调整因子直接假装现金已收到。[SPY 招募说明书](https://www.ssga.com/library-content/products/fund-docs/etfs/apac/prospectus-sg-en-spy.pdf) 说明其季度支付安排。60 日是保守诊断规则而非已验证的逐次实际支付日；另跑 90 日和所有分配预扣 30% 敏感性。30% 是压力情景，不能替代个人税籍及每类分配的税法判断。

实际尚缺：历史全量发行人分配精确金额/支付日、券商可用产品与账户权限、开盘报价或历史竞价成交证据、用户实际手续费和税费。当前日线没有 quote volume/VWAP/trade count 因而不提升为通用可信 normalized 层；这些字段缺失本身不否定已经闭合的月频账户算术。真正限制可投资结论的是公司行动与执行假设仍是代理，且未来运行未发生。

结算额外排除美国银行假日：Columbus Day 与 Veterans Day 虽然股票市场可开市，却不是结算日。[FINRA 结算说明](https://www.finra.org/sites/default/files/2022-11/Information-Notice-111822.pdf) 支持这一点。本实现采用交易所会话与美国联邦银行营业日交集，遇股票市场关闭但DTC仍有某些服务的日期偏保守；不是逐年逐份DTC服务通知的完整还原。独立比较12个变体历史实际销售日期后，没有一笔结算日改变，账户结果不受此次日历补充影响。
