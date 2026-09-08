# 数据、股票合约与基本面范围审计

本家族通过正式 Lab 的固定 `binance.v3.research_inputs.v2` 组合重新校验全部五组件内容与日线行质量，874个显式代码全部返回可用的价格诊断帧。源码、组合SHA、请求、每帧哈希和资格均已保存；未读旧cache作为行情源。见[输入汇总](../artifacts/p0-inputs-20260908/summary.json)、[全部覆盖](../artifacts/p0-inputs-20260908/coverage.csv)、[连续段](../artifacts/p0-inputs-20260908/segments.csv)。

日线最后开盘为2026-09-04，收盘为2026-09-05 00:00 UTC。当前代码工作区和数据根分离，正式Lab数据实际存在；更新发布日期不延长覆盖。

| 观测分类 | 库存代码 | 至少180根连续有效日K | 主639天+121根预热 |
| --- | ---: | ---: | ---: |
| COIN | 652 | 611 | 205 |
| UNKNOWN | 31 | 24 | 0 |
| EQUITY（含尚待细分ETF） | 155 | 8 | 0 |
| HK_EQUITY | 13 | 0 | 0 |
| KR_EQUITY | 8 | 0 | 0 |
| CN_EQUITY | 2 | 0 | 0 |
| COMMODITY / INDEX / PREMARKET | 13 | 8 | 1（INDEX） |

205是新主分母，原研究244币是窗口内冷启动15根的另一个合同，不能混写。库存包含历史已结束或更名代码，所有记录都保留。观测分类不构成历史PIT、退市清算可执行性或单位身份全历史认证；不以缺失者当作零收益，也不据收益删除异常币。

## 全成本边界

资金快照有2,654,430个事件；585个代码的639个部分历史片段具有原生月档结算频率证明。但是**0个代码的完整主639天窗口获得连续资金结算日历证明**。主末端跨入未证明的9月尾部，股票Special结算也未由该窗口门禁认证。

真实尝试的净研究入口拒绝缺少独立历史身份复核材料，保留原错误，未伪造材料或补零资金费。逐币事件/特殊结算数和末端见[资金范围审计](../artifacts/funding-scope-20260908/report.json)、[逐币状态](../artifacts/funding-scope-20260908/symbol-funding-status.csv)。因此后续收益只能称“扣手续费与滑点的价格诊断”；全成本有效比例是未验证，不能由价格正收益比例替代。

## 真实股票合约：已识别的执行面

Binance官方资料明确这些是追踪股票的永续合约，并给出了MSTR、AMZN、CRCL、COIN和PLTR对应公司。合约可24/7交易，标的证券仍有自身闭市和节假日；闭市期间的指数模式不能等同现货成交。官方资料也说明该机制在2026年5月调整过，当前规则不自动适用于更早历史。来源：[Binance股票合约说明](https://www.binance.com/en/academy/articles/how-to-trade-stock-perpetual-contracts-on-binance)。

INTC/HOOD官方上市时间为2026-02-02，映射Intel与Robinhood；它们是合约，不是直接股票持有。来源：[INTC/HOOD上市公告](https://www.binance.com/en/support/announcement/detail/d592f6ba938746cbadaaf5a8a714abd6)。TSLA的交易所当前元数据、SEC公司名称和本地首根完整日K交叉一致。当前[exchangeInfo快照](../artifacts/official-source-review/exchangeInfo-20260908.json)仅用于当前身份核对，不能作为全历史PIT证明。

能够满足180日基础历史的真实个股合约只有八个：TSLA219天，INTC/HOOD各214天，AMZN/COIN/CRCL/MSTR/PLTR各207天；按冻结121根预热后仅剩86–98天。其余EQUITY分类可能含ETF、杠杆/反向ETF或特殊身份，不能默认为独立个股。它们均不符合主长窗资格，也不增加八股的验证分母。

股息需要特殊资金支付，可能伴随临时reduce-only和结算频率改变；现金股息的支付方向与空头成本密切相关。特殊支付不能当成普通零资金日，价格除息跳空也不能直接认作空头alpha。不同美股、港股、韩股、中国股票的处理时点不同。来源：[官方股息调整规则](https://www.binance.com/en/support/faq/detail/7ced719b5e9a4859a1864c2fe657309f)、[传统资产合约规则](https://www.binance.com/en/support/faq/detail/fe7dcdf24f1943d98b368f5f9f744398)。本研究未得到完整历史特殊支付、订单簿价差、逐时mark-price及临时下单限制记录，因此八股短窗回放也不是可执行全成本验证。

另查OKX，其这批个股永续2026年2月才上市，不能补齐本合同639天跨年样本。[OKX上市公告](https://www.okx.com/en-us/help/okx-to-list-perpetual-futures-for-selected-stocks)。港交所存在真正单股期货和历史数据渠道，但本地没有已接受的逐合约换月、乘数调整与成交/结算链；目前没有完成该市场数据接入，不能说其股票策略失败。[HKEX单股期货官方资料](https://www.hkex.com.hk/eng/prod/drprod/sf/Documents/HKEX_Stock_Futures_EN.pdf)、[历史数据服务](https://www.hkex.com.hk/Global/Exchange/FAQ/Market-Data/Getting-Market-Data?sc_lang=en)。没有购买数据，也没有用现货/ETF长历史冒充合约。

## 基本面：来源可以取得，统计验证仍不足

已实际获取上述八家公司的SEC submissions与companyfacts，16个请求均返回200，并逐家核对CIK、公司名与ticker。SEC提供按公司归集的申报及XBRL数据，可与文件的接收时间对应。[SEC官方API文档](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)。

本家族完成了按信号收盘时可得的年度利润、经营现金流、收入字段审计：只有该accession的接收时间不晚于决策时点才可用，后续修订不回填历史；分子分母要求同accession与会计期间。714个可交易后信号日中628个拥有一致的年度字段，原始accession和接收时间逐行保留。[逐日PIT字段与缺失](../artifacts/stock-fundamentals-availability-20260908/daily-pit-availability.csv)、[发行人核对](../artifacts/stock-fundamentals-availability-20260908/issuer-coverage.csv)。

这说明不能把问题概括为“没有基本面数据”。具体缺口是：股票合约只有8个长于180日的个股，预热后不足100天，没有多个合约市场年份或足够大的独立股票保留组；无法满足冻结的适用范围验证。此次不以几家当前盈利公司拼成选股结论。加密全市场仍缺同等可复核的历史token经济/基本面发布与修订链，本次没有建立其基本面盈利规律。价格/流动性六特征与八个真实筛选分支仍独立完成。

直接网页下载遇到Binance 202空响应、SEC文档403；这些空/拒绝收据保留，正文核查使用浏览工具的官方页面。SEC数据端点与Binance当前元数据端点成功，不能把文档下载拒绝扩写为全部官方数据不可访问。[HTTP收据](../artifacts/official-source-review/official-sources-receipts.json)、[SEC数据收据](../artifacts/official-source-review/sec-eight-stock-receipts.json)。
