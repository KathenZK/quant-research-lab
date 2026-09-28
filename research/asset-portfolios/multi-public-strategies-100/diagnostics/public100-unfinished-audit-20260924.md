# PUBLIC100：74项未完成账户回测的原因复核

日期：2026-09-24。这是逐项资料与实现缺口审计，没有新增账户回测。26项有账户诊断（25项实际交易，D2零交易），D6仅部分仓位估算，73项无数值，正式验证仍为0。

“未完成”不等于理论上不能测，也不等于策略亏损。下面每项只按一个首要障碍计数，复合缺口写在说明里。数据源存在不代表已取得、已入湖或已满足原始市场与时点要求。

| 首要原因 | 数量 | 原编号 | 含义 |
|---|---:|---|---|
| 历史股票池、财报、新闻等当时可见资料未重建 | 37 | A3、A4、A5、A8、A11、A13、A14、A17、A19、A21、A23、A25、A26、A27、A28、A30、A32、A33、A34、A35、A39、A41、A42、A43、A46、A47、A48、A49、A50、A51、A52、A54、A57、A58、A59、C2、C9 | 资料和整理工程未完成；不能直接使用今天的股票名单或后来修订的财报。 |
| 老股票、终止ETF、国家估值与身份未补齐 | 5 | A1、A12、A16、A24、A44 | 价格、分红、合并、退市或清算须连接同一证券身份；不能删掉无报价资产后继续。 |
| 分钟/小时/逐合约数据与账户复现未完成 | 5 | A56、A60、B3、E8、E9 | 可继续补数据、复现执行；原有短期ETF行情不能替代整个原市场。 |
| 源码错误、未来信息或市场契约冲突 | 4 | A15、A45、D3、D4 | 先保留原版，再冻结修正版；修正后的业绩不能称原版准确复现。 |
| 交易规则、市场范围或版本仍不唯一 | 12 | C3、C5、C6、C7、E4、E5、E6、E7、E10、E11、E12、E14 | 先把信号、仓位、成交、退出写成唯一规则；自行补规则必须另标研究版本。 |
| 期权合约规则和历史逐合约报价不完整 | 5 | A18、E1、E2、E3、E13 | 补到期日、行权价、买卖报价、盘中持仓量等；标的涨跌不是期权账户收益。 |
| 有部分仓位估算，但完整账户未闭合 | 1 | D6 | 继续补抵押物风险、费用、结算、深度及清算；已有报价不能等同完整账户。 |
| 信号/仓位/过滤组件，不是独立策略 | 4 | B1、B2、C8、E15 | 可以做组件开关对照；必须先指定完整基础账户，不能单独算一份策略收益。 |
| 同源论文与复现，版本差异尚未核对 | 1 | B4 | 与B3共用数据和机制谱系；5/15/30/60分钟变体若不同须分别冻结。 |

本次关键修正：A60固定SPY；A4已有核心参数片段；E7/E11先解决交易对象和规则；B1/B2/C8/E15按组件处理。C3仍沿用已核明的周末时钟，D6已有报价。旧归档不覆盖。

公开财报可从SEC继续建设；历史股票产品、分钟期权报价也有供应。这里只确认补齐路径，未采购、未验收完整覆盖。SEC财报仍需按首次公开/申报时间对齐，不能用后来版本倒填；美国期权数据产品不能替代E13原市场的盘中持仓量。来源：[SEC：EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)、[CRSP US Stock Databases](https://www.crsp.org/research__trashed/crsp-us-stock-databases/)、[Cboe DataShop：Option Quotes](https://datashop.cboe.com/option-quote-intervals)。

| 数据之外的共同门槛 | 为什么需要 |
|---|---|
| 时点与执行 | 信号形成以后才能成交；盘中止损、同根K线先后次序、交易时区和换月需要定义。 |
| 完整账户 | 多空、借券、保证金、费用、闲置现金、抵押物与终止结算不能漏算。 |
| 源版本一致 | 文字版、源码版、修正版分开；不根据收益择优认定原策略。 |
| 正式验证 | 即使补跑出数字，还要数据验收、原规则准确复现及独立样本检验；当前26项也未通过这些要求。 |

## 历史股票池、财报、新闻等当时可见资料未重建（37项）

资料和整理工程未完成；不能直接使用今天的股票名单或后来修订的财报。

| 编号及策略 | 现在缺什么 | 怎样才能继续 |
|---|---|---|
| [A3 晨星基本面选股](https://github.com/QuantConnect/Tutorials/tree/master/04%20Strategy%20Library/09%20Stock%20Selection%20Strategy%20Based%20on%20Fundamental%20Factors) | 还没补齐每个历史时点能看到的晨星分类、财报和股票名单。 | 从公开财报补公告日期和原字段；替代不了的字段单独列出。 |
| [A4 短期价格反转](https://github.com/QuantConnect/Tutorials/tree/master/04%20Strategy%20Library/10%20Short-Term%20Reversal%20Strategy%20in%20Stocks) | 保存的方法页已有22日ROC、成交额前100、每周选强弱各10只及多空各50%的片段；完整嵌入账户代码未恢复。主要仍缺当期股票池、退市历史、借券与准确执行重放。 | 恢复完整框架与时钟语义，补原股票池和证券历史，先按已找到的参数复现；不再称排名窗口或持股数完全未知。 |
| [A5 基本面多空](https://github.com/QuantConnect/Tutorials/tree/master/04%20Strategy%20Library/11%20Fundamental%20Factor%20Long%20Short%20Strategy) | 选股要用当时成交额和财报，现有数据没有覆盖这套动态股票池。 | 补全当年的成交额、财报公告日期、退市股票和做空成本。 |
| [A8 残差动量](https://github.com/QuantConnect/Tutorials/tree/master/04%20Strategy%20Library/136%20Residual%20Momentum) | 残差动量需要当年的股票名单、回归因子和训练时间，尚未对齐。 | 补齐历史名单与因子发布时间，再固定回归窗口后运行。 |
| [A11 低波动](https://github.com/QuantConnect/Tutorials/tree/master/04%20Strategy%20Library/18%20Volatility%20Effect%20in%20Stocks) | 低波动排名要在当年的候选股票里做，不能只用今天还在上市的股票。 | 补齐历史名单、退市股票和含分红的价格，再做252日波动排名。 |
| [A13 一个月反转](https://github.com/QuantConnect/Tutorials/tree/master/04%20Strategy%20Library/15%20Short%20Term%20Reversal) | 20日反转的候选名单依赖当时市值，相关历史资料还没补齐。 | 补历史市值和股票名单，按原多空各10只的规则测。 |
| [A14 12 个月动量](https://github.com/QuantConnect/Tutorials/tree/master/04%20Strategy%20Library/21%20Momentum%20Effect%20in%20Stocks) | 252日动量之前还有成交额、市值两层筛选，不能用今天名单代替。 | 补历史成交额、市值和上市退市记录，再还原每次选出的五只股票。 |
| [A17 流动性 / 换手率](https://github.com/QuantConnect/Tutorials/tree/master/04%20Strategy%20Library/24%20Liquidity%20Effect%20in%20Stocks) | 换手率要除以当时的股数，历史股本、市值和退市记录还没补齐。 | 补历史股本和公告日期，不能拿今天股数倒算过去的换手率。 |
| [A19 小盘溢价](https://github.com/QuantConnect/Tutorials/tree/master/04%20Strategy%20Library/28%20Small%20Capitalization%20Stocks%20Premium%20Anomaly) | 小盘选股缺当年全市场市值，已退市小公司也尚未完整纳入。 | 补每年的公司名单、股数、价格和终止收益，再按市值选股。 |
| [A21 账面市值比](https://github.com/QuantConnect/Tutorials/tree/master/04%20Strategy%20Library/31%20Book-to-Market%20Value%20Anomaly) | 缺带公告日期的账面值；财年结束时市场还看不到后来发布的财报。 | 按财报实际公布日期对齐账面值、市值和可买股票名单。 |
| [A23 动量里的短期反转](https://github.com/QuantConnect/Tutorials/tree/master/04%20Strategy%20Library/34%20Momentum-Short%20Term%20Reversal%20Strategy) | 先选动量赢家输家、再选短期反转，所需历史股票名单还没补齐。 | 补齐每期候选名单，按两层排名顺序重建多空组合。 |
| [A25 情绪风格轮动](https://github.com/QuantConnect/Tutorials/tree/master/04%20Strategy%20Library/36%20Sentiment%20and%20Style%20Rotation%20Effect%20in%20Stocks) | 缺历史看跌看涨比，以及当时的成长股、价值股分类。 | 补情绪指标的原统计口径，并按财报公布时间还原风格名单。 |
| [A26 资产增长异象](https://github.com/QuantConnect/Tutorials/tree/master/04%20Strategy%20Library/39%20Asset%20Growth%20Effect) | 资产增长比较需要最初发布的财报及日期，不能用后来重述的数据直接倒填。 | 补原始总资产、公告日期和历史股票名单，再计算增长率。 |
| [A27 看市场状态的动量](https://github.com/QuantConnect/Tutorials/tree/master/04%20Strategy%20Library/37%20Momentum%20and%20State%20of%20Market%20Filters) | 源码使用Wilshire5000判断市场状态，现有资料没补齐该指数和历史股票池。 | 补原指数与股票名单，或把替代指数版另起名字后再测。 |
| [A28 应计异象](https://github.com/QuantConnect/Tutorials/tree/master/04%20Strategy%20Library/38%20Accrual%20Anomaly) | 应计指标涉及多张财务报表，原字段和实际公布时间还没补齐。 | 按公告日期补资产负债表、现金流等字段，再还原十分组多空组合。 |
| [A30 REIT 动量](https://github.com/QuantConnect/Tutorials/tree/master/04%20Strategy%20Library/152%20Momentum%20Effect%20in%20REITs) | 原策略轮动的是REIT股票，不是直接买一只REIT基金，历史分类还没补齐。 | 补历年的REIT公司名单、价格、分红和退市处理。 |
| [A32 盈利质量因子](https://github.com/QuantConnect/Tutorials/tree/master/04%20Strategy%20Library/229%20Earnings%20Quality%20Factor) | 盈利质量指标需要当年的财务分项，现有资料还没覆盖。 | 补原指标所用字段和公布日期，再还原当期分组。 |
| [A33 一月效应](https://github.com/QuantConnect/Tutorials/tree/master/04%20Strategy%20Library/114%20January%20Effect%20in%20Stocks) | 原代码选当时最大、最小的股票，并不是两个大小盘ETF之间切换。 | 补历史市值和公司名单，按原每组10只运行。 |
| [A34 高波动里的动量反转](https://github.com/QuantConnect/Tutorials/tree/master/04%20Strategy%20Library/155%20Momentum%20and%20Reversal%20Combined%20with%20Volatility%20Effect%20in%20Stocks) | 要先分出当年的高波动股票，再在里面比较动量，完整历史样本还没补齐。 | 补股票名单、价格、市值和退市记录，再按原分层顺序测。 |
| [A35 市值组内 ROA](https://github.com/QuantConnect/Tutorials/tree/master/04%20Strategy%20Library/199%20ROA%20Effect%20within%20Stocks) | 按市值分组再按ROA选股，缺当时可见的ROA和市值。 | 补财报公布日期与同期市值，逐期重建分组。 |
| [A39 动量加成交量](https://github.com/QuantConnect/Tutorials/tree/master/04%20Strategy%20Library/66%20Combining%20Momentum%20Effect%20with%20Volume) | 动量和成交量交叉选股还需要完整历史股票及股本资料。 | 补量价、股本和退市记录，再运行原交叉分组。 |
| [A41 低贝塔](https://github.com/QuantConnect/Tutorials/tree/master/04%20Strategy%20Library/77%20Beta%20Factors%20in%20Stocks) | 低贝塔用Wilshire5000作市场基准，还依赖当年的股票名单。 | 补原指数与历史名单，并核对贝塔权重和做空成本。 |
| [A42 同日历月循环](https://github.com/QuantConnect/Tutorials/tree/master/04%20Strategy%20Library/125%2012%20Month%20Cycle%20in%20Cross-Section%20of%20Stocks%20Returns) | 同日历月规律要在完整历史股票样本上比较，现在只有部分行情。 | 补长期股票名单和退市价格，保留每个当时实际存在的成员。 |
| [A43 集中 12 个月动量](https://github.com/QuantConnect/Tutorials/tree/master/04%20Strategy%20Library/162%20Momentum%20Effect%20in%20Stocks%20in%20Small%20Portfolios) | 集中动量的多空各10只来自动态候选池，历史市值和成交额尚未补齐。 | 补每次筛选用的原名单与字段，再核对做空及退市处理。 |
| [A46 低市盈率](https://github.com/QuantConnect/Tutorials/tree/master/04%20Strategy%20Library/92%20Price%20Earnings%20Anomaly) | 缺按公告时间可见的市盈率；代码的成交额升序筛选也要按原样还原。 | 补原候选池、历史市盈率和退市收益，先测源码的实际规则。 |
| [A47 Fama-French 五因子](https://github.com/QuantConnect/Tutorials/tree/master/04%20Strategy%20Library/353%20Fama%20French%20Five%20Factors) | 原策略要自己选股票，公开五因子收益序列不能代替这套账户回测。 | 补历史股票、财务字段和同期因子，再对齐选股与交易时间。 |
| [A48 股票统计套利](https://github.com/QuantConnect/Tutorials/tree/master/04%20Strategy%20Library/211%20Mean-Reversion%20Statistical%20Arbitrage%20Strategy%20in%20Stocks) | 需要当时成交额前20的股票及小时成交路径，现有资料还没覆盖。 | 补动态候选池和小时价格，按原60日窗口、每30日更新执行。 |
| [A49 预期特异偏度](https://github.com/QuantConnect/Tutorials/tree/master/04%20Strategy%20Library/354%20Expected%20Idiosyncratic%20Skewness) | 偏度预测需要当年的股票样本、因子和严格分开的训练预测时间。 | 补历史样本和三因子，再固定训练窗口，避免用未来标签训练过去。 |
| [A50 同日历月季节性](https://github.com/QuantConnect/Tutorials/tree/master/04%20Strategy%20Library/269%20Seasonality%20Effect%20based%20on%20Same-Calendar%20Month%20Returns) | 同月季节性需要长期全市场样本，不能只回看今天的前100只股票。 | 补历史股票名单、退市收益和借券成本后运行。 |
| [A51 标准化超预期盈利](https://github.com/QuantConnect/Tutorials/tree/master/04%20Strategy%20Library/355%20Standardized%20Unexpected%20Earnings) | 超预期盈利需要至少36个月历史季度盈利，以及每期财报首次公布日期。 | 补原季度EPS、公布时间和历史股票名单，再做预热与信号计算。 |
| [A52 价格动量加盈利动量](https://github.com/QuantConnect/Tutorials/tree/master/04%20Strategy%20Library/271%20Price%20and%20Earning%20Momentum) | 价格与盈利动量联合选股，缺当时已公布的季度盈利快照。 | 按季度公告日期补盈利与原候选池，再对齐下次交易。 |
| [A54 能源股一目均衡](https://github.com/QuantConnect/Tutorials/tree/master/04%20Strategy%20Library/1028%20Ichimoku%20Clouds%20in%20the%20Energy%20Sector) | 原策略每月选当时最大的10只能源股，现有名单无法重建过去的行业和市值。 | 补历史能源分类、市值和公司行动，并检查一目指标的时间位移。 |
| [A57 科技股 G-Score](https://github.com/QuantConnect/Tutorials/tree/master/04%20Strategy%20Library/1030%20G-Score%20Investing) | 科技股G-Score用研发等财务分项及同行排名，历史字段和行业名单还没补齐。 | 补原财务字段、公告日期和科技公司名单，再逐期比较。 |
| [A58 药企新闻情绪](https://github.com/QuantConnect/Tutorials/tree/master/04%20Strategy%20Library/1027%20Using%20News%20Sentiment%20to%20Predict%20Price%20Direction%20of%20Drug%20Manufacturers) | 缺带首次发布时间的历史药企新闻全文，也缺当年的药企名单。 | 补原新闻流、公司映射和发布后行情，再做情绪打分。 |
| [A59 科技股朴素贝叶斯](https://github.com/QuantConnect/Tutorials/tree/master/04%20Strategy%20Library/1036%20Gaussian%20Naive%20Bayes%20Model) | 模型每月换成当时最大的10只科技股，历史行业、市值和训练时点还没重建。 | 先补股票名单，再按原4日特征、100样本窗口逐次训练和交易。 |
| [C2 流动的股票动量](https://teddykoker.com/2019/05/momentum-strategy-from-stocks-on-the-move-in-python/) | 周频股票动量需要当年的标普500成分，现有名单不能排除存活股票偏差。 | 补成分变更、退市价格，再按原回归动量和ATR仓位测。 |
| [C9 相对强度动量组合](https://github.com/Donvink/quant-trade) | 代码已经找到，但默认用今天的股票名单，拿来回测过去会漏掉退市公司。 | 换成逐期历史成分，保留原追踪止损和持有期限后再运行。 |

## 老股票、终止ETF、国家估值与身份未补齐（5项）

价格、分红、合并、退市或清算须连接同一证券身份；不能删掉无报价资产后继续。

| 编号及策略 | 现在缺什么 | 怎样才能继续 |
|---|---|---|
| [A1 道指 30 CAPM 阿尔法排序](https://github.com/QuantConnect/Tutorials/tree/master/04%20Strategy%20Library/01%20CAPM%20Alpha%20Ranking%20Strategy%20on%20Dow%2030%20Companies) | 原代码实际列了29只股票，包含已改名、合并的老代码；这些价格还没补齐，代码还把两只股票各买满仓。 | 先找回老股票对应的完整价格，再把“两只各100%仓位”和普通等权版分开测。 |
| [A12 配对交易（平方偏差）](https://github.com/QuantConnect/Tutorials/tree/master/04%20Strategy%20Library/19%20Pairs%20Trading%20with%20Stocks) | 原银行股名单包含已经合并或退市的股票，完整价格还没补齐。 | 找回这些股票的原始身份和最后结算，再按源码的四组配对测。 |
| [A16 国家指数均值回归](https://github.com/QuantConnect/Tutorials/tree/master/04%20Strategy%20Library/23%20Mean%20Reversion%20Effect%20in%20Country%20Equity%20Indexes) | 原19只国家ETF里有已终止产品；这次取得的ERUS报价全空。 | 继续查原19只ETF的历史价格和终止价值，齐全后按原多空规则测。 |
| [A24 国家 ETF 配对](https://github.com/QuantConnect/Tutorials/tree/master/04%20Strategy%20Library/40%20Pairs%20Trading%20with%20Country%20ETFs) | 原国家ETF名单有历史终止产品，本次GAF没有有效报价，身份也没对上。 | 找回原名单和终止价格，再按源码121日距离法配对。 |
| [A44 国家 CAPE 价值](https://github.com/QuantConnect/Tutorials/tree/master/04%20Strategy%20Library/207%20Value%20Effect%20within%20Countries) | 本轮重新查询原Dropbox CAPE链接仍返回错误HTML；Barclays链接返回应用外壳，未取得带发布日期的原序列。源码另含加拿大XIC身份/币种及ERUS等历史终止ETF，不能按现存美股池替代。 | 补原国家估值历史、公布日期、币种和ETF终止记录。 |

## 分钟/小时/逐合约数据与账户复现未完成（5项）

可继续补数据、复现执行；原有短期ETF行情不能替代整个原市场。

| 编号及策略 | 现在缺什么 | 怎样才能继续 |
|---|---|---|
| [A56 指数 ETF 日内套利](https://github.com/QuantConnect/Tutorials/tree/master/04%20Strategy%20Library/1023%20Intraday%20Arbitrage%20Between%20Index%20ETFs) | 两只指数ETF的日内套利需要同步细行情，日线无法判断价差出现时能否成交。 | 补同步分钟或更细的买卖报价，再计算价差与执行成本。 |
| [A60 梯度提升日内预测](https://github.com/QuantConnect/Tutorials/tree/master/04%20Strategy%20Library/1033%20Gradient%20Boosting%20Model) | 固定SPY；缺完整分钟训练数据、旧库兼容、逐轮训练与信号到期后账户退出重放。动态股票池不是该策略的缺口。 | 按原SPY分钟规则恢复训练与标签时间、月末训练、连续信号和仓位到期；固定样本后再跑。 |
| [B3 开盘区间突破（活跃股）](https://www.quantconnect.com/research/18444/opening-range-breakout-for-stocks-in-play/) | 需要每天全市场筛股和开盘分钟成交量，尚未取得覆盖历史名单的完整数据；一次未认证接口请求失败不代表免费数据都不可用。 | 继续找免费分钟数据和历史候选池，先明确能覆盖的范围，再测原5分钟版本。 |
| [E8 @scorpiomanojFRM](https://threadreaderapp.com/thread/1123275657386057728.html) | 需要股指期货5分钟行情及真实换月记录，枢轴均线的原定义也未核对。 | 明确合约和指标定义，补每张到期合约的价格、换月和交易成本。 |
| [E9 同一作者第二套](https://threadreaderapp.com/thread/1123610532488122368.html) | 同样缺股指期货5分钟逐合约行情和换月记录，不能把连续图当实际成交。 | 补原合约、交易时段和枢轴定义，再按真实换月核算。 |

## 源码错误、未来信息或市场契约冲突（4项）

先保留原版，再冻结修正版；修正后的业绩不能称原版准确复现。

| 编号及策略 | 现在缺什么 | 怎样才能继续 |
|---|---|---|
| [A15 国家指数动量](https://github.com/QuantConnect/Tutorials/tree/master/04%20Strategy%20Library/22%20Momentum%20Effect%20in%20Country%20Equity%20Indexes) | 源码有两个漏逗号错误，动量窗口也和文字不同；原名单还有已终止的ETF。 | 把代码修正版和文字版写清楚，并补终止ETF的完整价格和结算。 |
| [A45 国家 ETF 贝塔](https://github.com/QuantConnect/Tutorials/tree/master/04%20Strategy%20Library/78%20Beta%20Factor%20in%20Country%20Equity%20Indexes) | 源码国家名单同样有漏逗号错误及失效ETF，还没形成可运行的修正版。 | 记录具体修复内容，补齐原ETF身份和价格后再算贝塔及权重。 |
| [D3 截面 Z 分数动量](https://github.com/briplot/systematic-crypto-strategy) | 源码默认当期Binance.US现货池与做空借贷、随机成本/成交时序尚未补齐；数据湖Binance USDT永续不能自动替代该市场和历史池。 | 先固定权重、随机成本和成交时间，重建历史币种名单与做空方式后测。 |
| [D4 相对 BTC 的残差回归](https://github.com/briplot/systematic-crypto-strategy) | 贝塔分母错误、全样本最大仓位缩放及残差收益不可直接交易的问题仍须修正版；同样缺原Binance.US现货池和做空契约，不能用永续结果冒充原版。 | 另存修正版，去掉未来信息，按真正可交易的组合重新算收益。 |

## 交易规则、市场范围或版本仍不唯一（12项）

先把信号、仓位、成交、退出写成唯一规则；自行补规则必须另标研究版本。

| 编号及策略 | 现在缺什么 | 怎样才能继续 |
|---|---|---|
| [C3 周末趋势交易](https://usethinkscript.com/threads/weekend-trend-trader-by-nick-radge-strategy-for-thinkorswim.669/) | 已核原论坛：止损按周五收盘判断、周一执行，并非还缺周内止损。剩余缺口是原历史股票池、市场范围，以及文字20周/30%与代码10周/10%的版本冲突。 | 按已确认的周五收盘判断、周一执行保留时钟；分开文字20周/30%和代码10周/10%两版，补原市场和历史股票池。 |
| [C5 突破波段](https://qullamaggie.com/my-3-timeless-setups-that-have-made-me-tens-of-millions/) | 收缩、领涨、突破平台和分批仓位还带主观判断，尚未变成唯一可运行规则。 | 把形态阈值与每次买卖比例写清楚，再按一个固定版本测。 |
| [C6 事件跳空](https://qullamaggie.com/my-3-timeless-setups-that-have-made-me-tens-of-millions/) | 事件催化剂和盈利超预期还没有机械判定方式，也没补真实首次发布的事件资料。 | 先定义哪些事件算信号，再补发布时间、预期盈利和分钟行情。 |
| [C7 抛物线做空](https://qullamaggie.com/my-3-timeless-setups-that-have-made-me-tens-of-millions/) | 抛物线走势、VWAP失败和回补位置还没量化，历史能否借到股票也没核对。 | 固定形态、止损和回补规则，再补分钟行情与做空成本。 |
| [E4 @SRxTrades](https://threadreaderapp.com/thread/1929326825689223595.html) | 缩量、窄幅、反复测试等说法没有明确阈值，满仓和减仓比例也没固定。 | 先把形态和仓位写成明确数值，再补历史扫描字段与行情。 |
| [E5 @FelipeGuirao](https://threadreaderapp.com/thread/1997388912982110569.html) | 贴均线、阻力、上影小还没定义；看完收盘信号却按同一收盘成交也需要修正。 | 固定形态定义和下单时点，再补盘中止损路径及仓位规则。 |
| [E6 @karthimaths](https://threadreaderapp.com/thread/1615692407768764417.html) | 大跳空、多个位置挤在一起没有明确尺度，具体市场和时区也没锁定。 | 先确定市场、时区和阈值，再取对应交易时段的15分钟数据。 |
| [E7 @PBInvesting](https://threadreaderapp.com/thread/1689062941205708800.html) | 现在已有SPY/IWM/IYR短期日内行情；仍缺原交易股票池、明确的完整退出规则及原VWAP口径。不能擅自把SPY典型价乘量指标当所有原股票/期权版本。 | 先选股票版或期权版，确定交易时段，再补分钟数据；期权版另外补合约报价。 |
| [E10 @Mc5calpAfee](https://threadreaderapp.com/thread/2041989250787299383.html) | 图上6点等信号时间没有说明时区和交易所，区间外交易方向也需查原图。 | 找回原图说明，明确交易时间与方向，再补3或5分钟合约数据。 |
| [E11 @ripster47](https://www.tradingview.com/script/7LPOiiMN-Ripster-EMA-Clouds/) | 现有分钟数据为常规时段；原文要求盘前，且5/12或5/13、多层云确认及止损仍未固定。取得普通分钟数据不能补齐未给出的交易规则。 | 补含盘前的原标的分钟行情，明确入场退出；若交易期权，另补期权报价。 |
| [E12 @Tradewrite](https://threadreaderapp.com/thread/1911644891374899603.html) | 均线云只给方向，具体哪根K线入场、何时退出、买多少还没规定。 | 固定多周期对齐、入场、退出和仓位，再下载对应分钟行情。 |
| [E14 Ramsay Rippers](https://en.rattibha.com/thread/1516250396624408579) | 关键位、过度延伸和退出办法还不够明确，股票与期权版本混在一起。 | 先分开交易对象，定义关键位、追价限制和退出，再补5分钟或期权数据。 |

## 期权合约规则和历史逐合约报价不完整（5项）

补到期日、行权价、买卖报价、盘中持仓量等；标的涨跌不是期权账户收益。

| 编号及策略 | 现在缺什么 | 怎样才能继续 |
|---|---|---|
| [A18 波动率风险溢价](https://github.com/QuantConnect/Tutorials/tree/master/04%20Strategy%20Library/25%20Volatility%20Risk%20Premium%20Effect) | 还没有每个到期日、行权价的历史期权买卖报价，不能从SPY涨跌反推出跨式收益。 | 补期权链、买卖价差、行权和保证金规则，再核算每条期权腿。 |
| [E1 @Team2Trading](https://threadreaderapp.com/thread/1954180176314786139.html) | 关键位回踩还没写成明确条件，期权到期日、行权价和权利金退出规则也缺。 | 先固定这些规则，再补盘前、2分钟标的行情和对应期权买卖报价。 |
| [E2 @EllyDtrades](https://threadreaderapp.com/thread/1978250242886656501.html) | 标的方向过滤已有，但当天到期期权选哪个合约、付多少价差仍不明确。 | 固定到期日和行权价选择，再补10分钟触发时点的期权报价。 |
| [E3 @ChiefPowrTrendz](https://threadreaderapp.com/thread/1530004887471329280.html) | 均线只能给方向，期权买哪一档、剩多久到期、如何控制权利金风险还没写清。 | 明确均线周期与合约选择，补对应历史期权报价后测。 |
| [E13 @ameyanifty](https://threadreaderapp.com/thread/1122087538578030592.html) | 需要到期日期权各行权价的盘中持仓量和权利金变化，只有收盘快照不够。 | 确定市场与本地时间，补逐合约盘中持仓量及买卖报价。 |

## 有部分仓位估算，但完整账户未闭合（1项）

继续补抵押物风险、费用、结算、深度及清算；已有报价不能等同完整账户。

| 编号及策略 | 现在缺什么 | 怎样才能继续 |
|---|---|---|
| [D6 Boros 资金费率均值回归](https://github.com/0xSmartCrypto/meridian) | 已取得真实Boros历史买卖价与链上结算，另做三张2025-12-26到期合约的25日币本位费率仓位估算，每张只有2笔。未含抵押物美元风险、gas、入场费、盘口深度、历史参数和FIndex精确结算，不能计完整账户。 | 补历史合约参数、FIndex精确结算、抵押物美元净值、入场/退出费、gas、深度与清算规则；扩大有效样本后再评价。 |

## 信号/仓位/过滤组件，不是独立策略（4项）

可以做组件开关对照；必须先指定完整基础账户，不能单独算一份策略收益。

| 编号及策略 | 现在缺什么 | 怎样才能继续 |
|---|---|---|
| [B1 基础配对阿尔法](https://www.quantconnect.com/docs/v2/writing-algorithms/algorithm-framework/alpha/supported-models) | 它只给配对信号，没有给完整股票池、仓位分配和退出规则，不能单独报账户收益。 | 补齐一套完整交易方案，再把该信号放进去测试。 |
| [B2 相关配对阿尔法](https://www.quantconnect.com/docs/v2/writing-algorithms/algorithm-framework/alpha/supported-models) | 它只说选相关性最高的一对，没给完整候选池、重选频率和账户规则。 | 补候选池、相关窗口、重选与退出规则，再和B1做对照。 |
| [C8 同一作者的仓位规则](https://threadreaderapp.com/thread/1331865723203948549.html) | 它只是C5、C6、C7配套的仓位管理方法，没有自己的买卖信号。 | 在选定的基础策略上分别开关这套仓位规则，比较收益和回撤。 |
| [E15 @ripster47 趋势日过滤](https://en.rattibha.com/thread/1744525905257791908) | 这是决定加减仓的趋势日过滤条件，没有独立买卖规则，不能给它单独算一条策略收益。 | 放到指定基础策略上，比较有无这个过滤条件时的收益和回撤。 |

## 同源论文与复现，版本差异尚未核对（1项）

与B3共用数据和机制谱系；5/15/30/60分钟变体若不同须分别冻结。

| 编号及策略 | 现在缺什么 | 怎样才能继续 |
|---|---|---|
| [B4 开盘区间突破论文版](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4729284) | 这是B3同一思路的论文版，目前还没核对论文与代码的参数差异，不能重复记一份收益。 | 逐项比对论文的5、15、30、60分钟版本，再分别决定哪些确实需要单独测。 |

## 工作顺序判断

这是一份按补齐路径排列的工程判断，不是收益排名。先做A60的固定SPY完整复现、A4完整源码恢复，以及A15/A45的语法/身份修正；这些项目边界较容易圈定，但本次没有把它们宣称为“数据已齐、马上能正式通过”。

历史股票主表、公司行动/退市、逐期成分及财报首次发布时间是共享底座，直接关系37项首要时点资料缺口，也会帮助B3/C3等复合缺口。规则模糊的C/E组应先定规格，再准备昂贵或大规模数据。B1/B2/C8/E15进入组件实验；B4与B3共用谱系，避免重复计算发现。

D3/D4需要明确原市场做空是否可执行；改为另一交易所永续是新变体。D6应先补完整账户，而不是把已有两笔费率仓位的低回撤解释为安全。

证据：[旧R2状态](../artifacts/continuation-r2/status-100.json)、[2026-09-10源码与类型核对](../artifacts/learning-guide-20260910/classification-and-rules.json)、[本次100项结构化审计](../artifacts/classification-audit-20260924/classification-100.json)。
