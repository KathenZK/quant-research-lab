"""Build the 2026-09-24 documentary audit; no market data or backtest execution."""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/classification-audit-20260924'
DATE = '2026-09-24'

def ids(s):
    return s.split()

BLOCKERS = [
    ('pit', '历史股票池、财报、新闻等当时可见资料未重建', ids('A3 A4 A5 A8 A11 A13 A14 A17 A19 A21 A23 A25 A26 A27 A28 A30 A32 A33 A34 A35 A39 A41 A42 A43 A46 A47 A48 A49 A50 A51 A52 A54 A57 A58 A59 C2 C9'), '资料和整理工程未完成；不能直接使用今天的股票名单或后来修订的财报。'),
    ('old_assets', '老股票、终止ETF、国家估值与身份未补齐', ids('A1 A12 A16 A24 A44'), '价格、分红、合并、退市或清算须连接同一证券身份；不能删掉无报价资产后继续。'),
    ('intraday', '分钟/小时/逐合约数据与账户复现未完成', ids('A56 A60 B3 E8 E9'), '可继续补数据、复现执行；原有短期ETF行情不能替代整个原市场。'),
    ('code', '源码错误、未来信息或市场契约冲突', ids('A15 A45 D3 D4'), '先保留原版，再冻结修正版；修正后的业绩不能称原版准确复现。'),
    ('rules', '交易规则、市场范围或版本仍不唯一', ids('C3 C5 C6 C7 E4 E5 E6 E7 E10 E11 E12 E14'), '先把信号、仓位、成交、退出写成唯一规则；自行补规则必须另标研究版本。'),
    ('options', '期权合约规则和历史逐合约报价不完整', ids('A18 E1 E2 E3 E13'), '补到期日、行权价、买卖报价、盘中持仓量等；标的涨跌不是期权账户收益。'),
    ('partial', '有部分仓位估算，但完整账户未闭合', ids('D6'), '继续补抵押物风险、费用、结算、深度及清算；已有报价不能等同完整账户。'),
    ('component', '信号/仓位/过滤组件，不是独立策略', ids('B1 B2 C8 E15'), '可以做组件开关对照；必须先指定完整基础账户，不能单独算一份策略收益。'),
    ('duplicate', '同源论文与复现，版本差异尚未核对', ids('B4'), '与B3共用数据和机制谱系；5/15/30/60分钟变体若不同须分别冻结。'),
]

# Links below were inspected through web search/open on DATE. Historical milestones
# are not asserted to be inventions of the exact tutorial or code variant.
SOURCES = [
 ('trend_history', 'AQR：A Century of Evidence on Trend-Following Investing', 'https://www.aqr.com/insights/research/journal-article/a-century-of-evidence-on-trend-following-investing', '2017-10-31', '趋势交易早于现代教程；长历史重建不等于策略在1880年发明。'),
 ('tsmom', 'Moskowitz、Ooi、Pedersen：Time series momentum', 'https://www.sciencedirect.com/science/article/pii/S0304405X11002613', '2012-05', '时间序列动量的代表性现代实证论文；不同于横向动量。'),
 ('momentum', 'Jegadeesh、Titman：Returns to Buying Winners and Selling Losers', 'https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.1993.tb04702.x', '1993', '3至12个月相对强弱动量的经典论文年份。'),
 ('value', 'Graham、Dodd：Security Analysis，1934版', 'https://www.mheducation.com/highered/mhp/product/security-analysis-classic-1934-edition.html', '1934（原版）', '价值投资经典出版锚点；网页是后来重印版。'),
 ('ff1992', 'Fama、French：The Cross-Section of Expected Stock Returns', 'https://febs.onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.1992.tb04398.x', '1992-06', '规模与账面市值比的系统实证。'),
 ('ff2015', 'Fama、French：A five-factor asset pricing model', 'https://www.sciencedirect.com/science/article/pii/S0304405X14002323/pdf', '2015-04', '加入盈利与投资的五因子模型；模型不是现成下单策略。'),
 ('size', 'Banz：The relationship between return and market value of common stocks', 'https://www.sciencedirect.com/science/article/pii/0304405X81900180', '1981-03', '小盘效应经典论文。'),
 ('lowrisk', 'Haugen、Heins：Risk and the Rate of Return on Financial Assets', 'https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/abs/risk-and-the-rate-of-return-on-financial-assets-some-old-wine-in-new-bottles/1A92FCFDC6F5898F2D7DA4B583138C0C', '1975-12', '低风险讨论的早期论文；不能误用2009网页上线日期。'),
 ('reversal', 'De Bondt、Thaler：Does the Stock Market Overreact?', 'https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.1985.tb05004.x', '1985-07', '长期反转经典证据；不代表所有短期RSI规则。'),
 ('short_reversal', 'Lehmann：Fads, Martingales, and Market Efficiency', 'https://www.nber.org/papers/w2533', '1988工作论文；1990期刊', '短期赢家/输家随后反转的研究锚点。'),
 ('pairs', 'Gatev、Goetzmann、Rouwenhorst：Pairs Trading', 'https://www.nber.org/papers/w7032', '1999工作论文；2006期刊', '距离配对法代表文献，非唯一发明日期。'),
 ('calendar', 'Lakonishok、Smidt：Are Seasonal Anomalies Real?', 'https://academic.oup.com/rfs/article-abstract/1/4/403/1566965', '1988期刊卷期', '月末、年末、假期等研究锚点；网页另有2015上线日期。'),
 ('calendar_mining', 'Sullivan、Timmermann、White：Dangers of data mining', 'https://www.sciencedirect.com/science/article/pii/S030440760100077X', '2001', '日历效应应考虑同时试验很多规则的数据挖掘问题。'),
 ('pead', 'Bernard、Thomas：Post-Earnings-Announcement Drift', 'https://www.jstor.org/stable/2491062', '1989', '财报公布后价格漂移的经典研究。'),
 ('options1973', 'Black、Scholes：The Pricing of Options and Corporate Liabilities', 'https://www.journals.uchicago.edu/doi/10.1086/260062', '1973-05', '现代期权定价锚点，绝不等于A18卖跨式于1973年发明。'),
 ('option_premium', 'Coval、Shumway：Expected Option Returns', 'https://onlinelibrary.wiley.com/doi/pdf/10.1111/0022-1082.00352', '2001-06期刊卷期', '期权预期收益及波动风险定价研究；网页2002上传日期不是期刊年份。'),
 ('options2025', 'Cboe：The State of the Options Industry: 2025', 'https://www.cboe.com/insights/posts/the-state-of-the-options-industry-2025', '2026-01-22', '2025年SPX当日期权占其成交量59%；产品活跃不证明E组规则盈利。'),
 ('bitmex', 'BitMEX：Five Years Ago, the Perpetual Swap Was Born', 'https://www.bitmex.com/blog/five-years-ago-the-perpetual-swap-was-born-everything-changed', '2021-05-13，回顾2016-05-13', '该交易所XBTUSD永续于2016-05-13发布；非D1/D2/D5算法发布日期。'),
 ('boros', 'Pendle：Boros Funding Futures', 'https://www.pendle.finance/boros/', None, '官方说明直接做多/做空资金利率的产品机制。'),
 ('boros_launch', 'Pendle联合创始人TN访谈：Pendle and Boros', 'https://podcasts.apple.com/us/podcast/pendle-and-boros-shaping-the-future-of-yield/id1651683074?i=1000722466333', '2025-08-18', '创始人访谈讨论刚推出的Boros；这里只据此定位2025年，不声称精确上线日。'),
 ('lightgbm', 'Microsoft Research：LightGBM论文', 'https://www.microsoft.com/en-us/research/publication/lightgbm-a-highly-efficient-gradient-boosting-decision-tree/', '2017-12', '算法论文日期，不是A60教程发明日期。'),
 ('mlfinance', 'Gu、Kelly、Xiu：Empirical Asset Pricing via Machine Learning', 'https://www.nber.org/papers/w25398', '2018工作论文；2020期刊', '现代金融机器学习研究锚点；非股票预测的起点。'),
 ('msci', 'MSCI Factor Indexes', 'https://www.msci.com/indexes/factor-indexes/msci-factor-indexes', None, '当前维护价值、规模、低波动、质量、动量等因子指数。'),
 ('msci2025', 'MSCI：动量及最小波动指数方法修订', 'https://app2.msci.com/webapp/index_ann/DocGet?format=html&lang=en&pub_key=vXBeNkI7Sxg%3D', '2025-02-14；2025-08实施', '动量调仓改季度，并采用分步权重调整控制换手。'),
 ('aqr2026', 'AQR：Systematic Equity', 'https://www.aqr.com/learning-center/systematic-equities', '页面数据截至2026-06-30', '机构产品仍覆盖单/多因子、主动扩展等，使用ML、NLP、替代数据。'),
 ('aqr2025', 'AQR：A New Paradigm in Active Equity', 'https://www.aqr.com/insights/research/white-papers/a-new-paradigm-in-active-equity', '2025-02-05', '机构讨论LLM、机器学习、替代数据与集中市场。'),
 ('man2026', 'Man Group：2026年第一季度交易声明', 'https://www.man.com/document?display-name=Trading+statement+for+the+quarter+ended+31+March+2026&doc-type=pre&locale=en', '2026年第一季度', '报告仍列传统趋势、另类趋势、量化多策略及另类风险溢价业务。'),
 ('man_mix', 'Man Group：The Optimal Market Mix for a Trend Follower', 'https://www.man.com/insights/trend-following-optimal-market-mix', '研究数据至2025-10', '趋势向更多市场扩展，流动性、长期表现与危机表现存在取舍。'),
 ('dl_stat_arb', 'Guijarro-Ordonez、Pelger、Zanotti：Deep Learning Statistical Arbitrage', 'https://arxiv.org/abs/2106.04028', '2021初稿', '研究演化示例：因子残差、时序模型、交易约束；不作普及率或实盘业绩证明。'),
 ('cme_basis', 'CME：Cryptocurrency Basis Watch and Implied Rate Tool', 'https://www.cmegroup.com/markets/cryptocurrencies/cryptocurrency-basis-watch-and-implied-rate-tool', None, '当前专业市场提供加密基差和隐含利率工具；不背书资金费率方向信号。'),
 ('costs', 'AQR：Trading Costs', 'https://www.aqr.com/insights/research/working-paper/trading-costs', '2018-08-23', '真实成交成本与价格冲击的研究；不能将某固定成本外推给所有市场。'),
 ('sec', 'SEC：EDGAR APIs', 'https://www.sec.gov/search-filings/edgar-application-programming-interfaces', '2025-04-08更新', '公开财报和申报历史接口；并不直接补齐价格、借券和历史成分。'),
 ('crsp', 'CRSP US Stock Databases', 'https://www.crsp.org/research__trashed/crsp-us-stock-databases/', '2026-06-30迁移提示', '机构历史股票产品包括活跃/非活跃证券、公司行动、退市；本次未采购或验收。'),
 ('option_data', 'Cboe DataShop：Option Quotes', 'https://datashop.cboe.com/option-quote-intervals', None, '存在历史分钟期权报价产品；不等于仓库已有，也不能补齐所有印度期权OI。'),
 ('framework', 'QuantConnect：Supported Alpha Models', 'https://www.quantconnect.com/docs/v2/writing-algorithms/algorithm-framework/alpha/supported-models', None, 'B1/B2属于Alpha信号组件；完整账户还需其他模块。'),
 ('clenow', 'Andreas Clenow：Stocks on the Move is Out!', 'https://www.followingthetrend.com/2015/06/stocks-on-the-move-is-out/', '2015-06-10', 'C2原书公开发行时间；2019 Python博客是后续实现。'),
 ('radge', 'Nick Radge：Strategies that will continue to profit', 'https://www.thechartist.com.au/strategies-that-will-continue-to-profit/', '2021-04-27，作者回顾2012发布', 'C3 Weekend Trend Trader原书发布时间为作者回顾的2012。'),
 ('kda', 'Ilya Kipnis：Right Now It’s KDA…Asset Allocation', 'https://quantstrattrader.wordpress.com/2019/01/24/right-now-its-kda-asset-allocation/', '2019-01-24', 'C4具体KDA文章日期；B5是移植，非第二个独立机制。'),
 ('orb', 'QuantConnect：Opening Range Breakout for Stocks in Play', 'https://www.quantconnect.com/research/18444/opening-range-breakout-for-stocks-in-play/p1', '2024-12；引用2024论文', 'B3页面说明复现Zarattini、Barbon、Aziz 2024研究；SSRN本轮直取403。'),
 ('gem', 'TrendXplorer：Prospecting Dual Momentum With GEM', 'https://indexswingtrader.blogspot.com/2016/10/prospecting-dual-momentum-with-gem.html', '2016-10-04', 'C1所用具体来源文章年份，非动量原理发明年份。'),
 ('qullamaggie', 'Qullamaggie：3 Timeless Setups', 'https://qullamaggie.com/my-3-timeless-setups-that-have-made-me-tens-of-millions/', '最迟2021-01已有作者回复', 'C5/C6/C7规则来源及公开存在时间界限；不是独占发明权证据。'),
 ('faber', 'Meb Faber：战术资产配置论文发表说明', 'https://mebfaber.com/2007/02/10/published-errrsort-of/', '2007-02-10', '2007春季论文的作者说明；是长期均线配置的代表节点，不是均线发明时间。'),
]

GROUP_INFO = {
 'trend_breakout': ('价格趋势、突破与回踩', '20世纪早期已有趋势实践；2012年时间序列动量论文是现代学术锚点。具体均线/开盘突破配方年代各异。', '趋势跟踪仍是机构主要策略家族之一；E组特定盘中形态的机构采用程度未证实。', '多市场、多速度、按波动控制仓位，联合考虑退出与成本；日内突破加入活跃度及成交约束。', ['trend_history','tsmom','man2026','man_mix','orb']),
 'relative_momentum_rotation': ('横向动量与资产轮动', '1993年相对强弱动量经典论文；ETF配置、GEM与KDA是后来组合实现。', '动量因子仍属主流；每个公开轮动配方不是公认标准答案。', '多因子联合、行业约束、控制换手、动态风险预算；保留简单动量作比较基线。', ['momentum','msci','msci2025','kda']),
 'fundamental_selection': ('基本面、估值与盈利质量', '1934年价值投资经典；1992年规模/价值实证；2015年五因子模型是后续节点。', '价值、质量、盈利、投资仍是机构股票量化的重要输入；单条旧异象不能一概称有效。', '多维质量与估值、行业可比、时点财报、非线性交互、把成本和组合约束一起建模。', ['value','ff1992','ff2015','msci','aqr2026']),
 'style_risk_factors': ('规模、低风险及风险特征', '低风险早期实证1975年，小盘效应1981年；具体CAPM排序、偏度规则分别核对。', '规模、低波动仍有指数及机构应用；偏度等细分异象的普及度不能由此推出。', '与质量/价值搭配、控制行业集中和流动性，区分风险暴露与真正的超额收益。', ['size','lowrisk','msci','aqr2026']),
 'reversal_mean_reversion': ('反转与均值回归', '长期反转经典1985年；短期反转1988工作论文/1990期刊。RSI配方不等于论文策略。', '仍是研究与交易机制；独立零售抄底规则是否主流及有效均无充分证据。', '先扣除共同市场和行业影响，再考虑流动性冲击、市场状态、做空与成交成本。', ['reversal','short_reversal','costs','dl_stat_arb']),
 'relative_value_pairs': ('配对与相对价值统计套利', '距离配对代表研究1999工作论文/2006期刊；实务早于论文，不能当唯一发明日。', '相对价值和股票多空仍有机构应用；固定两只股票的简单价差是基础教学形式。', '从固定配对到动态篮子、因子残差、协方差及非线性信号，并约束真实可交易仓位。', ['pairs','aqr2026','dl_stat_arb']),
 'calendar_time': ('日历、季节性与隔夜时段', '相关实践较早；1988年系统研究是可靠锚点，各种日历异象不是同一时间发明。', '可作辅助信号；本次未找到足以把月相/一月晴雨表称为机构核心主流策略的证据。', '由日期巧合转向可解释的资金流、再平衡和拍卖机制，并控制多重试验和成本。', ['calendar','calendar_mining','costs']),
 'news_sentiment_earnings': ('新闻、情绪与财报事件', '财报后漂移经典论文1989年；词典新闻、VIX分位和事件跳空是不同后续实现。', '信息处理是当前系统投资重要方向；旧词典或简单VIX分位规则的效果需要单独验证。', '由固定词典到金融文本模型/LLM、事件去重和首次发布时间；仍须测试价格反应及交易成本。', ['pead','aqr2025','aqr2026']),
 'volatility_premium': ('期权波动率风险溢价', '1973年现代期权定价、2001年期权风险收益研究是锚点；A18卖跨式加保护的具体首发未核实。', '期权与波动率是成熟市场；A18具体卖跨式规则未得到验证。', '组合管理隐含/实现波动差、期限、偏斜和尾部风险；保证金、价差与对冲路径进入账户。', ['options1973','option_premium','options2025','option_data']),
 'funding_direction': ('资金费率驱动的方向交易', '加密永续产品锚点为BitMEX 2016年；D1/D2/D5具体代码首次发布日期未核实。', '永续市场主流，但由极端费率预测币价的特定规则仍属待验证假设。', '将费率与价格、持仓量、拥挤程度、期限和风险预算结合；方向交易必须与中性收息分开。', ['bitmex','cme_basis']),
 'funding_rates': ('资金利率合约交易', 'Boros产品在2025年已上线；D6代码首发未核实，不能倒推策略在产品上线时发明。', '新兴细分市场；不足以称与传统股票因子一样成熟、普及。', '由预测币价转向直接对冲/交易利率，研究期限价差及完整抵押物、结算和流动性风险。', ['boros','boros_launch']),
 'trained_return_prediction': ('训练模型预测方向', '本组引用2010年代文献；LightGBM论文2017年，金融ML代表实证2018/2020；均非机器学习发明日。', 'ML是机构常用工具之一；A59/A60两份教学实现不能代表行业最先进模型。', '金融特征交互、文本信息、滚动训练、模型漂移监控，并优化扣费后组合而非只追分类准确率。', ['lightgbm','mlfinance','aqr2026']),
 'supporting_rules': ('仓位管理与市场过滤组件', '风险管理思想早于这些帖子；这两条具体规则首发未核实。', '仓位和风险管理是完整策略必需环节；两条帖子不是两种独立超额收益。', '按风险预算、相关性、流动性和账户权益控制仓位，用组件开关实验验证贡献。', ['framework','costs']),
}

HISTORY_OVERRIDES = {
 'A6': ('长期均线资产配置的代表文献Faber 2007；本条文字月线版与每日210日源码版另作区分。', ['faber']),
 'A2': ('源引用Gang Wei的Dual Thrust Intraday Strategy，2012-05；不是Dual Thrust唯一发明日。', []),
 'A3': ('源引用2015年土耳其股票因子选股文献；不代表美国教程规则首次发表于2015年。', []),
 'A4': ('源引用de Groot等2011-07版本；与1988/1990短期反转研究相区别。', ['short_reversal']),
 'A8': ('源引用Residual Momentum，2009工作论文及2017后续研究；具体教程发布日期未知。', []),
 'A14': ('机制锚点1993年相对动量论文；这份大盘股筛选代码首发未核实。', ['momentum']),
 'A19': ('机制锚点Banz 1981；具体市值选股教程首发未核实。', ['size']),
 'A21': ('机制锚点Fama–French 1992；具体五档持仓代码首发未核实。', ['ff1992']),
 'A47': ('五因子模型2015；模型论文不等于这份选股账户实现。', ['ff2015']),
 'A49': ('源引Expected idiosyncratic skewness，2009在线发表/2010卷期；具体代码日期未知。', []),
 'A51': ('源引用Foster等1984；财报漂移经典Bernard–Thomas 1989。', ['pead']),
 'A53': ('源引用Gayed、Bilello，2016-03-03；文字200日与代码200小时为不同变体。', []),
 'A54': ('源引用Gurrib能源股一目研究，2020-01-16；不是一目指标发明日。', []),
 'A55': ('源引用Market Intraday Momentum的2017-06-19版本；不是所有日内动量的起点。', []),
 'A56': ('源引用ETF Arbitrage: Intraday Evidence，2010-11-16；并引用2018策略书。', []),
 'A57': ('源引用Mohanram G-Score文献的2004-04版本；不等于最早基本面选股。', []),
 'A58': ('源引用Shah等2018新闻情绪研究；保存实现为词典，非训练式模型。', []),
 'A59': ('源引用2014/2016机器学习应用文献；本条教程首次发布时间未核实。', ['mlfinance']),
 'A60': ('源参考2013年GBM文献，但代码使用LightGBM；该算法论文2017，不能把现存代码写成2013年发明。', ['lightgbm']),
 'B3': ('QuantConnect复现页面2024-12，所复现论文为2024年；开盘突破原理早于此。', ['orb']),
 'B4': ('Zarattini、Barbon、Aziz论文2024；本轮SSRN直取403，年份由复现作者引用核对。', ['orb']),
 'B5': ('移植C4的2019年KDA；移植版首次日期本次未逐提交核实。', ['kda']),
 'C1': ('本清单来源文章2016-10-04；GEM及动量原理早于文章。', ['gem','momentum']),
 'C2': ('Clenow原书2015-06发行；清单Python实现文章2019-05。', ['clenow']),
 'C3': ('作者2021年文章回顾：Weekend Trend Trader于2012年发布；论坛转写另有参数差异。', ['radge']),
 'C4': ('Ilya Kipnis于2019-01-24发布KDA文章；组合已有动量与自适应配置思想。', ['kda']),
 'C5': ('原作者网站最迟2021-01已公开该方法并回复读者；更早使用及独占发明未核实。', ['qullamaggie']),
 'C6': ('与C5同一作者文章，最迟2021-01已公开；财报事件机制更早。', ['qullamaggie','pead']),
 'C7': ('与C5同一作者文章，最迟2021-01已公开；暴涨做空不是当年才出现。', ['qullamaggie','reversal']),
 'D6': ('Boros产品2025年；meridian具体策略首次发表时间未核实。', ['boros','boros_launch']),
}

def load(path):
    return json.loads((ROOT / path).read_text())

def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def cell(s):
    return str(s).replace('|', '／').replace('\n', ' ')

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    inventory = load('specs/inventory.json')
    old = load('artifacts/continuation-r2/status-100.json')
    guide = load('artifacts/learning-guide-20260910/classification-and-rules.json')
    by_status = {x['id']: x for x in old['rows']}
    by_guide = {x['id']: x for x in guide['rows']}
    expected = {x['id'] for x in inventory}
    group_lookup = {i: (key, name, why) for key, name, members, why in BLOCKERS for i in members}
    assert len(group_lookup) == sum(len(x[2]) for x in BLOCKERS) == 74
    assert set(group_lookup) == {x['id'] for x in old['rows'] if not x['account_backtest']}
    refs = {key: {'id': key, 'title': title, 'url': url, 'publication_or_data_date': date, 'checked_as_of': DATE, 'supports': claim} for key, title, url, date, claim in SOURCES}

    records = []
    a_etfs = set(ids('A2 A6 A7 A9 A10 A15 A16 A20 A22 A24 A29 A31 A36 A37 A38 A40 A44 A45 A53 A55 A56 A60'))
    components = set(ids('B1 B2 C8 E15'))
    fundamental = set(ids('A3 A5 A17 A19 A21 A26 A28 A32 A35 A44 A46 A47 A51 A52 A57'))
    fixed = set(ids('A2 A10 A22 A31 A37 A38 A40 A60'))
    minute = set(ids('A2 A55 A56 A58 A60 B3 B4 E1 E2 E3 E6 E7 E8 E9 E10 E11 E12 E13 E14'))
    monthly = set(ids('A7 A9 A18 A22 A27 A29 A31 A33 A51 B5 C1 C4'))
    annual = set(ids('A19 A21 A28 A36'))
    daily = set(ids('A38 A53 C9 C10'))
    weekly = set(ids('A4 C2 C3'))
    swing = set(ids('C5 C6 C7 E4 E5'))
    stat_model = set(ids('A1 A8 A12 A24 A41 A45 A48 A49 B1 B2 C2 D4'))
    for inv in inventory:
        i = inv['id']; s = by_status[i]; g = by_guide[i]
        category = g['category_id']
        if category == 'funding_volatility':
            category = 'volatility_premium' if i == 'A18' else ('funding_rates' if i == 'D6' else 'funding_direction')
        # Primary information input is exclusive for counting. Secondary data
        # needs (universe, costs, corporate actions) are retained in the blocker.
        if i == 'A18': information = '期权波动率与逐合约数据'
        elif i in fundamental: information = '财报/估值/规模/股本（含量价组合）'
        elif i in ids('A25 A38 E13'): information = '情绪/波动指数/持仓量（含量价）'
        elif i in ids('A58 C6'): information = '新闻/事件（含量价）'
        elif i in ids('D1 D2 D5 D6'): information = '资金费率/利率及合约数据'
        elif category == 'calendar_time': information = '日历/时段（另需行情）'
        elif i in ids('C8 E15'): information = '仓位/市场状态组件'
        else: information = '价格、成交量及其统计特征'
        if i in components: instrument = '组件：交易工具依基础策略'
        elif i == 'A18' or i in ids('E1 E2 E3 E13'): instrument = '期权'
        elif i == 'C10': instrument = '股票ETF＋加密现货'
        elif i in ids('D1 D2 D5'): instrument = '加密永续'
        elif i == 'D6': instrument = '加密资金利率合约'
        elif i.startswith('D'): instrument = '加密现货（D3/D4做空契约待核）' if i in ids('D3 D4') else '加密现货'
        elif i in ids('E8 E9 E10'): instrument = '股指期货'
        elif i in ids('E7 E11 E14'): instrument = '股票/期权版本未分清'
        elif i in a_etfs or i in ids('B5 C1 C4'): instrument = '股票/跨资产ETF'
        else: instrument = '股票（含REIT及市场待定版本）'
        if i in components: structure = '组件，不单列账户'
        elif i in fixed: structure = '固定单一交易标的'
        elif i == 'A18': structure = '单一标的的多腿期权'
        elif i in ids('D1 D2 D5'): structure = '逐币方向规则，可多币复制'
        elif i == 'D6': structure = '逐利率合约，可多市场复制'
        elif i in ids('D7 D8 D9 D10'): structure = '固定七币扫描、最多一仓'
        elif i in ids('D3 D4'): structure = '跨币候选池、多空构建'
        elif instrument == '股票/跨资产ETF' or i == 'C10': structure = '固定多资产池/配置/配对'
        elif i.startswith('E'): structure = '逐标的信号，完整交易池未锁定'
        else: structure = '股票池选股/扫描/配对'
        if i in components: freq = '组件/依基础策略'
        elif i in minute: freq = '分钟/小时观察（不等于持有期）'
        elif i in ids('D7 D8 D9 D10'): freq = '加密15分钟至4小时观察'
        elif i in monthly: freq = '月度/近月调仓或月历事件'
        elif i in annual: freq = '年度/年内固定事件'
        elif i in weekly: freq = '周度检查/调仓'
        elif i in daily: freq = '日度检查，持有期可变'
        elif i in swing: freq = '日线选形态＋盘中执行'
        elif i in ids('D1 D2 D5 D6'): freq = '费率事件/小时执行，持有期各异'
        elif i == 'A10': freq = '隔夜'
        elif i == 'A20': freq = '季度'
        elif i == 'A40': freq = '节假日事件'
        elif i == 'A37': freq = '月相事件'
        elif i == 'A6': freq = '日度/月底两个版本'
        else: freq = '未在本次逐条确认，不补猜'
        method = ('监督学习' if i in ids('A59 A60') else '统计/计量模型' if i in stat_model else '词典文本规则' if i == 'A58' else '仓位/过滤组件' if i in ids('C8 E15') else '显式规则/排名/形态（部分待机械化）')
        detail = g['current_result_or_missing']
        action = s.get('next_needed', '')
        correction = ''
        if i == 'A4':
            detail = '保存的方法页已有22日ROC、成交额前100、每周选强弱各10只及多空各50%的片段；完整嵌入账户代码未恢复。主要仍缺当期股票池、退市历史、借券与准确执行重放。'
            action = '恢复完整框架与时钟语义，补原股票池和证券历史，先按已找到的参数复现；不再称排名窗口或持股数完全未知。'
            correction = '本轮重读源方法页，缩小“代码/参数未知”的范围。'
        elif i == 'A60':
            detail = '固定SPY；缺完整分钟训练数据、旧库兼容、逐轮训练与信号到期后账户退出重放。动态股票池不是该策略的缺口。'
            action = '按原SPY分钟规则恢复训练与标签时间、月末训练、连续信号和仓位到期；固定样本后再跑。'
            correction = '采用2026-09-10源码核对，纠正R2状态表动态股票池旧原因。'
        elif i == 'D6':
            action = '补历史合约参数、FIndex精确结算、抵押物美元净值、入场/退出费、gas、深度与清算规则；扩大有效样本后再评价。'
        elif i == 'C3':
            action = '按已确认的周五收盘判断、周一执行保留时钟；分开文字20周/30%和代码10周/10%两版，补原市场和历史股票池。'
        elif i in ids('E7 E11'):
            correction = '本轮将首要障碍归为规则和交易对象未锁定；分钟/盘前数据仍是次要障碍。'
        elif i in ids('B1 B2 E15'):
            correction = '按实际内容列为组件；这不改变旧回测完成数。'
        historical_text, historical_refs = HISTORY_OVERRIDES.get(i, ('本条具体教程/代码/帖子的首次发表时间未核实；原理年代见所属主题，不代填发明年份。', []))
        if i not in HISTORY_OVERRIDES:
            historical_refs = GROUP_INFO[category][4][:1]
        record = {
            'id': i, 'name': inv['name'], 'source_url': inv['source_url'],
            'previous_theme_11': g['category_id'], 'primary_theme_13': category,
            'instrument': instrument, 'structure': structure, 'primary_information': information,
            'model_method': method, 'decision_clock_group': freq,
            'entry': g['entry'], 'holding': g['holding'], 'exit': g['exit'],
            'specific_version_chronology': historical_text, 'chronology_source_ids': historical_refs,
            'account_backtest': s['account_backtest'], 'partial_position_only': s['numeric_partial_only'],
            'formal_verified': False, 'current_status': g['current_status'],
            'current_detail': detail, 'next_needed': action,
            'primary_blocker': group_lookup[i][0] if i in group_lookup else None,
            'audit_correction': correction,
            'component_only': i in components,
            'scope_notes': g.get('notes',''),
            'local_source_files': [e['path'] for e in inv.get('evidence_files', [])],
        }
        if i in ids('D3 D4'):
            record['scope_notes'] += ' 原市场为Binance.US现货；本仓Binance USDT永续不能作为同一原版。'
        records.append(record)

    assert len(records) == len({x['id'] for x in records}) == 100
    assert {x['id'] for x in records} == expected
    assert sum(x['account_backtest'] for x in records) == 26
    assert sum(x['partial_position_only'] for x in records) == 1
    assert sum(x['component_only'] for x in records) == 4
    assert sum(x['model_method'] == '监督学习' for x in records) == 2
    counts = {axis: dict(Counter(x[axis] for x in records)) for axis in ['primary_theme_13','instrument','structure','primary_information','model_method','decision_clock_group']}
    for c in counts.values(): assert sum(c.values()) == 100
    groups = []
    for key, (name, history, mainstream, evolution, source_ids) in GROUP_INFO.items():
        members = [x for x in records if x['primary_theme_13'] == key]
        groups.append({'id': key, 'name': name, 'ids': [x['id'] for x in members], 'count': len(members), 'account_count': sum(x['account_backtest'] for x in members), 'history_anchor': history, 'current_usage_assessment': mainstream, 'evolution_assessment': evolution, 'source_ids': source_ids, 'judgment_note': '主流程度与演化方向是基于来源的审慎分析，不是行业普及率调查，也不表示本条盈利。'})
    dump(OUT/'sources.json', list(refs.values()))
    dump(OUT/'classification-100.json', {'as_of':DATE,'scope':'文献与归档审计；未新增回测、下载市场数据或提升任何验收等级','counts':counts,'groups':groups,'rows':records,'account_counts':old['counts'],'blocker_groups':[{'id':k,'name':n,'count':len(m),'ids':m,'interpretation':w} for k,n,m,w in BLOCKERS]})

    def link_sources(keys):
        return '、'.join(f"[{refs[k]['title']}]({refs[k]['url']})" for k in keys)

    audit = [
      '# PUBLIC100：74项未完成账户回测的原因复核', '',
      f'日期：{DATE}。这是逐项资料与实现缺口审计，没有新增账户回测。26项有账户诊断（25项实际交易，D2零交易），D6仅部分仓位估算，73项无数值，正式验证仍为0。', '',
      '“未完成”不等于理论上不能测，也不等于策略亏损。下面每项只按一个首要障碍计数，复合缺口写在说明里。数据源存在不代表已取得、已入湖或已满足原始市场与时点要求。', '',
      '| 首要原因 | 数量 | 原编号 | 含义 |','|---|---:|---|---|',
    ]
    for key,name,members,why in BLOCKERS: audit.append(f'| {name} | {len(members)} | {"、".join(members)} | {why} |')
    audit += ['', '本次关键修正：A60固定SPY；A4已有核心参数片段；E7/E11先解决交易对象和规则；B1/B2/C8/E15按组件处理。C3仍沿用已核明的周末时钟，D6已有报价。旧归档不覆盖。', '',
      '公开财报可从SEC继续建设；历史股票产品、分钟期权报价也有供应。这里只确认补齐路径，未采购、未验收完整覆盖。SEC财报仍需按首次公开/申报时间对齐，不能用后来版本倒填；美国期权数据产品不能替代E13原市场的盘中持仓量。来源：' + link_sources(['sec','crsp','option_data']) + '。','',
      '| 数据之外的共同门槛 | 为什么需要 |', '|---|---|',
      '| 时点与执行 | 信号形成以后才能成交；盘中止损、同根K线先后次序、交易时区和换月需要定义。 |',
      '| 完整账户 | 多空、借券、保证金、费用、闲置现金、抵押物与终止结算不能漏算。 |',
      '| 源版本一致 | 文字版、源码版、修正版分开；不根据收益择优认定原策略。 |',
      '| 正式验证 | 即使补跑出数字，还要数据验收、原规则准确复现及独立样本检验；当前26项也未通过这些要求。 |','',
    ]
    by_id = {x['id']:x for x in records}
    for key,name,members,why in BLOCKERS:
        audit += [f'## {name}（{len(members)}项）','',why,'','| 编号及策略 | 现在缺什么 | 怎样才能继续 |','|---|---|---|']
        for i in members:
            x=by_id[i]; audit.append(f"| [{i} {cell(x['name'])}]({x['source_url']}) | {cell(x['current_detail'])} | {cell(x['next_needed'])} |")
        audit.append('')
    audit += ['## 工作顺序判断','',
      '这是一份按补齐路径排列的工程判断，不是收益排名。先做A60的固定SPY完整复现、A4完整源码恢复，以及A15/A45的语法/身份修正；这些项目边界较容易圈定，但本次没有把它们宣称为“数据已齐、马上能正式通过”。', '',
      '历史股票主表、公司行动/退市、逐期成分及财报首次发布时间是共享底座，直接关系37项首要时点资料缺口，也会帮助B3/C3等复合缺口。规则模糊的C/E组应先定规格，再准备昂贵或大规模数据。B1/B2/C8/E15进入组件实验；B4与B3共用谱系，避免重复计算发现。', '',
      'D3/D4需要明确原市场做空是否可执行；改为另一交易所永续是新变体。D6应先补完整账户，而不是把已有两笔费率仓位的低回撤解释为安全。', '',
      '证据：[旧R2状态](../artifacts/continuation-r2/status-100.json)、[2026-09-10源码与类型核对](../artifacts/learning-guide-20260910/classification-and-rules.json)、[本次100项结构化审计](../artifacts/classification-audit-20260924/classification-100.json)。',
    ]
    (ROOT/'diagnostics/public100-unfinished-audit-20260924.md').write_text('\n'.join(audit)+'\n')

    table = ['# PUBLIC100：100项多维分类与来源年代', '',
      f'日期：{DATE}。保留原100个编号；13个主要研究主题每项只计一次。此前11主题中的“资金费率与波动率”拆成卖期权风险溢价、费率方向信号、利率合约三组，其他归属沿用。', '',
      '主题分类用来组织清单；机器学习描述建模方法，仓位组件描述系统角色，不是两种独立经济机制。真实研究还须交叉看交易工具、信息、资产池、频率与证据。A29按文字动量归类，源码逆方向另留证；A34按实际买强卖弱归动量，不能被名称“反转”误导。', '',
      '年代的证据口径：原理/经典论文、具体来源文章、代码/帖文首次发布是三件事。未知就写未核实，不把回测起点、下载日、网页迁移日或引用论文日期当代码发明日。主流程度和演化为本次基于来源的分析判断，不是盈利认证。', '',
      '| 主要主题 | 总数 | 有账户诊断 | 年代锚点 | 当前地位（分析判断） | 演化方向（分析判断） |', '|---|---:|---:|---|---|---|',
    ]
    for g in groups:
        table.append(f"| {g['name']} | {g['count']} | {g['account_count']} | {g['history_anchor']} | {g['current_usage_assessment']} | {g['evolution_assessment']} |")
    table += ['', '## 六个交叉维度的计数','', '下列每个维度各自合计100；它们相互交叉，不能跨表相加。频率写的是观察/决策时钟，不等于固定持仓时间。未知项保留未知。','']
    for axis,label in [('instrument','交易工具'),('structure','资产池与账户结构'),('primary_information','主要信息输入'),('model_method','信号加工方法'),('decision_clock_group','决策时钟')]:
        table += [f'### {label}','','| 分类 | 数量 |','|---|---:|']
        for k,v in counts[axis].items(): table.append(f'| {k} | {v} |')
        table.append('')
    for group in groups:
        table += [f"## {group['name']}（{group['count']}项）", '',
          group['history_anchor'], '', group['current_usage_assessment']+' '+group['evolution_assessment'], '',
          '依据：'+link_sources(group['source_ids'])+'。', '',
          '| 编号及名称 | 交易工具 / 结构 | 信息 / 方法 | 决策时钟 | 具体来源年代及边界 | 回测状态 |',
          '|---|---|---|---|---|---|',
        ]
        for i in group['ids']:
            x=by_id[i];status='账户诊断，未正式验证' if x['account_backtest'] else '部分仓位，非账户' if x['partial_position_only'] else '未数值回测'
            if i=='D2':status='账户已跑，零交易'
            table.append(f"| [{i} {cell(x['name'])}]({x['source_url']}) | {x['instrument']}；{x['structure']} | {x['primary_information']}；{x['model_method']} | {x['decision_clock_group']} | {cell(x['specific_version_chronology'])} | {status} |")
        table.append('')
    table += ['## 来源与口径','',
       '个别条目的“源引用年份”来自已保存的QuantConnect原教程References页，不能当首发证明。完整本地证据路径见JSON的local_source_files。原始买入、持有、退出字段仍保存，缺口见[74项原因审计](../diagnostics/public100-unfinished-audit-20260924.md)。', '',
       '[本次结构化100项表](../artifacts/classification-audit-20260924/classification-100.json) · [外部来源目录](../artifacts/classification-audit-20260924/sources.json)', '',
       '本清单的代表性有限：以美股/ETF和价格信号为主，未系统覆盖宏观利差、商品期限结构、外汇carry、做市、订单簿高频、可转债、并购套利等。未列入不等于不重要；100项的比例不能当全球量化行业占比。',
    ]
    (ROOT/'notes/public100-taxonomy-100-20260924.md').write_text('\n'.join(table)+'\n')
    input_paths = [ROOT/'specs/inventory.json', ROOT/'artifacts/continuation-r2/status-100.json',ROOT/'artifacts/learning-guide-20260910/classification-and-rules.json']
    input_paths += [ROOT/p for x in records for p in x['local_source_files']]
    manifest = {'as_of':DATE,'input_sha256':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p)} for p in sorted(set(input_paths))], 'checks': {'all_100_ids_once': True,'all_74_unfinished_ids_once':True,'account_count_unchanged_26':True,'formal_verified_unchanged_0':True,'all_axes_sum_100':True,'components_4':True,'supervised_ml_2':True,'no_market_data_read_or_backtest_run':True},'counts':counts,'blocker_counts':{k:len(m) for k,n,m,w in BLOCKERS}}
    dump(OUT/'validation.json',manifest)
    print(json.dumps({'rows':100,'unfinished':74,'blockers':manifest['blocker_counts'],'axes':counts},ensure_ascii=False,indent=2))

if __name__ == '__main__':
    main()
