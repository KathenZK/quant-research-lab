from pathlib import Path
import json,csv,hashlib,re,collections
import numpy as np

ROOT=Path('/Users/ZK/OpenCode/quant-strategy-lab')
F=ROOT/'research/asset-portfolios/multi-public-strategies-100'
OUT=Path('/tmp')
inventory=json.loads((F/'specs/inventory.json').read_text())
review=json.loads((F/'artifacts/strategy-review-100.json').read_text())
untested=json.loads((F/'artifacts/untested-81-20260909.json').read_text())
review_map={r['id']:r for r in review['rows']}
un_map={r['id']:r for r in untested['rows']}

# One judgment per original ID. Potential and practical priority are deliberately separate.
# ID | mechanism | economic hypothesis | research priority | small-account burden | reason / boundary | overlap
raw='''A1|残差/因子选股|CAPM异常收益延续可检验，但估计误差和行业暴露可能冒充alpha|条件保留|中高：集中持仓及原码约200%总敞口|先固定残差口径与持仓；不把历史回归alpha视作未来alpha|A8/A47
A2|日内突破|开盘后订单流或信息扩散可能延续|低优先|高：小时内执行、反手与成本|泛化突破模板，先证明微观结构增量再投入|B3/B4/A55/E组
A3|基本面组合|盈利、估值及行业约束可能代理风险溢价|条件保留|中：历史财报与多股组合|有真实公司信息，但必须拆清实际因子而非仅凭Morningstar标签|A5/A21/A32/A47
A4|短期反转|流动性补偿与短期过度反应|条件保留|高：短端换手及借券|思想可留，低成本大样本账户成立是前提|A13/A23
A5|基本面组合|估值与公司经营差异可能形成横截面收益差|条件保留|高：双边股票和PIT财报|多空暴露与交易成本需分开；不是独立于价值质量的新机制|A3/A21/A32
A6|慢速资产趋势|趋势持续与空仓降低长期下跌暴露|优先|低：少数流动ETF、月度调仓|适合作为简单基线；优先研究不代表当前版本已可实盘|A7/C1/C4/B5/C10/A53
A7|跨资产动量|缓慢信息扩散与资产风险收益持续性|优先|低：少数ETF、月度轮换|与A6/C1同一研究槽比较，勿把多个参数版本算独立alpha|A6/C1/A9/A15/A20
A8|残差动量|剔除共同因子后的公司收益延续|条件保留|高：因子时点、动态股票、多空|经济机制值得保留；原源码残差形状和月收益口径须重建|A1/A14/A47
A9|行业动量|行业景气与资金流的中期持续|条件保留|低中：少数行业ETF但较集中|63日绝对价差与12月百分比动量要分开，不继承混合结果|A7/A14/A15
A10|隔夜持有|隔夜信息及承担跳空风险可能获得补偿|条件保留|中高：每日双边成交、开收盘质量|经济问题成立，净收益高度依赖执行；不能仅凭收开盘差|A22/A31/A40
A11|低风险股票|杠杆约束或追逐高波动可能压低稳健股票价格|条件保留|中：长持股票、PIT与分散|思想可留；原码使用股价标准差，需另立收益率波动版本|A41/A45
A12|配对均值回归|相关企业共同因素下的暂时相对错价|条件保留|高：双边借券、失效和企业行动|相似路径不保证价差回归；旧银行代码不能直接续接|A24/A48/B1/B2/D4
A13|短期反转|短期流动性冲击与价格过度反应|条件保留|高：月度股票多空及借券|可做反转代表，不与A4重复投入|A4/A23
A14|股票价格动量|中期信息扩散与投资者追涨产生持续性|条件保留|中：长仓股票、PIT与集中度|机制可留；原码Momentum指标须明确绝对价差语义|A43/C2/C9/A8
A15|国家动量|国家风险偏好与景气的中期持续|条件保留|中：国家ETF身份和外部交易时段|原代码有拼接ticker错误及信号口径冲突，修复版另立身份|A7/A9/A20
A16|长期价值/反转|长期相对低迷市场可能经历估值均值回归|条件保留|高：国家ETF借券、长回撤与持有|思想区别于短反转；36月输家不自动等于便宜|A44/A13
A17|流动性/小盘|不受关注及难交易资产可能提供流动性补偿|低优先|高：微盘、价差、容量与借券|机制非无效；收益来源本身可能被小账户成交成本抵消|A19/A49
A18|期权波动率溢价|卖保险获得尾部风险补偿|条件保留|高：合约粒度、保证金、尾部和行情|有经济基础但不适合直接当10k低回撤方案；不是无风险收益|E组期权不等价
A19|规模效应|小公司风险、融资约束与关注不足|低优先|中高：微盘及退市、分散成本|单独按最小市值买入逻辑较粗，先与质量和流动性分辨|A17/A33/A47
A20|跨资产动量|股债之间相对强弱持续|条件保留|低：两ETF季度调整|简单对照值得保留，但属于动量家族的受限资产池|A7/C1
A21|价值|便宜资产的风险补偿或市场过度悲观|优先|中：PIT财报、年度长仓和分散|未测中值得保留的独立信息来源；先验收PIT可得性再建账户|A46/A44/A47/A3
A22|日历资金流|月底工资、基金调仓等可能造成可预测流量|条件保留|低中：ETF但集中开收盘成交|简单且可证伪；日期冲突应分别冻结，不按最好日期解释|A10/A31/A40
A23|动量与反转交互|中期趋势上叠加短期流动性冲击|条件保留|高：多层排序、双边成本|先验证相对纯动量/纯反转的增量，不能复用同一证据|A4/A13/A14
A24|配对均值回归|相关国家资产相对价格暂时偏离|条件保留|高：双边ETF、结构改变及借券|非风险免费套利；历史身份和距离定义必须还原|A12/A48/B1/B2
A25|情绪与风格|情绪可能改变成长/价值的相对定价|条件保留|高：情绪及PIT风格分类、多空|含独立情绪信息但交互自由度大；需简单风格基线|A38/A21/A47
A26|投资/资产增长|过度扩张或投资风险差异可能影响未来收益|条件保留|高：历史报表、多空和年度持仓|未测不等于弱；与价值质量有重合，先选一个代表|A28/A32/A47
A27|状态条件动量|市场趋势可能改变动量策略的风险|条件保留|高：股票多空和市场状态|相对无条件动量检验增量，保留Wilshire和原120日定义|A14/A43/C2
A28|应计/盈利质量|投资者可能高估不可持续的应计盈利|条件保留|高：多期PIT报表和多空|有公司信息基础；不是再加一个技术指标|A32/A35/A57
A29|风格动量|风格收益可能持续，但反转是另一假设|条件保留|中：ETF多空与借券|文字动量和源码反向不能汇为同一成绩|A7/A25/A47
A30|REIT动量|地产行业信息与价格趋势缓慢传递|条件保留|中：个股REIT池和行业集中|是动量资产池变体；不能用VNQ代替个股排序|A14/A9
A31|到期周资金流|衍生品到期相关对冲或结算流可能影响指数|低优先|低中：ETF但特定日内成交|是ETF日历策略，非期权策略；机制窄且容易事后选历法|A22/A40
A32|盈利质量|现金兑现、盈利持续性和经营质量可能被低估|条件保留|高：多个PIT字段及原多空组合|思想值得保留；综合分数需要明确单位、权重与信息增量|A28/A35/A57/A47
A33|日历与规模|税损卖出和资金流可能影响小盘年初表现|低优先|中：动态大/小盘股票池|月份条件较脆弱；不是简单IWM/SPY代替即可还原|A19/A42/A50
A34|动量与波动交互|高波动股票可能存在不同动量/反转行为|低优先|高：多重筛选、双边交易|条件越多越易选择偏差，先过纯动量和纯波动基线|A14/A11/A23
A35|盈利能力|高资产盈利能力可能反映持续经营优势|条件保留|高：PIT报表、分组股票多空|经济信息可信但与质量家族共用研究预算|A32/A28/A57/A47
A36|日历状态|一月收益可能反映当年风险偏好，但唯一月份依据较弱|低优先|低：SPY/短债年内切换|容易把持续股市暴露当一月预测力；已有数字不提高思想评级|A6/A22
A37|月相|月相影响风险偏好的传导缺少清晰可交易基础|低优先|中：多空、历法和成本|低优先源于弱经济先验和大量日历搜索空间，非数据缺口|A42/A50
A38|情绪反转|恐慌与自满可能形成短期风险溢价变化|条件保留|中：ETF多空、状态保持和借券|VIX信号可能只是权益风险暴露；需同风险基线|A25/A4
A39|动量与成交量|成交量可能帮助识别信息驱动和拥挤交易|条件保留|高：股票PIT与多空|保留为动量的预先声明增量，非独立价格alpha|A14/A23/A34
A40|日历资金流|节前风险偏好与交易流量可能改变收益|低优先|低中：ETF但稀疏交易和开收盘|能清楚证伪，经济先验及独立样本弱，排在通用机制之后|A22/A31
A41|低贝塔|融资与杠杆约束可能使高beta被高估|条件保留|高：beta估计、杠杆和借券|经济机制值得保留；原多空beta策略不适合直接简化成10k无杠杆结论|A11/A45/A47
A42|股票季节性|机构重复交易或信息周期可能产生同月持续|低优先|高：PIT股票多空及稀疏独立年份|与A50同家族，月份检验空间大，需跨年验证|A50/A33
A43|股票价格动量|中期赢家输家的收益持续|条件保留|高：集中多空和动量崩溃|代表性动量机制可留；集中与做空是实施差异不是新alpha|A14/C2/C9
A44|国家价值|长期估值偏离或国家风险补偿|条件保留|中：历史CAPE公布时点、长回撤|低换手且经济逻辑明确；数据缺口不降低思想价值|A21/A16
A45|低贝塔|国家风险偏好与杠杆偏好可能影响低beta收益|条件保留|高：国家ETF多空及身份|先修复ticker与beta规则；同低风险家族|A11/A41
A46|价值|低估值可能包含风险补偿或预期修复|条件保留|中：PIT估值和小成交额股票|原码按低成交额选池，不能称作大盘低PE原版|A21/A19
A47|因子框架|市场、规模、价值、盈利、投资解释共同风险|条件保留|高：多因子PIT股票组合|适合作为暴露归因及因子候选；解释模型不自动提供选股alpha|A19/A21/A26/A35
A48|统计套利|共同因子之外的短期偏离可能均值回归|条件保留|高：PCA估计、双边股票、小时交易|残差回归假设值得检验，但非无风险套利，10k执行负担重|A12/A24/D4
A49|偏度偏好|投资者可能为彩票式正偏度支付溢价|条件保留|中高：残差偏度估计、尾部和PIT|具有行为基础但估计不稳定，需与规模/流动性分离|A17/A19/A41
A50|股票季节性|重复资金流和信息周期可能形成同月效应|低优先|高：长历史、多空和多重月份检验|与A42共用假设家族，不当第二个独立证据|A42/A33
A51|盈利信息漂移|市场可能逐步吸收相对历史的盈利意外|优先|中：首次披露PIT EPS、月度长仓|未测中的优先信息机制；先做明确SUE事件/持仓契约，不需臆造分析师预期|A52/C6
A52|价格与盈利动量|价格和公司盈利信息可能互相补充|条件保留|中：EPS时点、股票PIT和季度调仓|先与纯价格和纯SUE/盈利动量做有限增量检验|A51/A14
A53|杠杆趋势|趋势过滤降低杠杆资产的持续下跌暴露|低优先|中高：日复位杠杆、跳空与尾部|杠杆改变风险不创造信息；200日/200小时不可混合|A6/C10
A54|技术趋势/行业|趋势可能持续，但一目均衡未提供额外经济信息|低优先|中：能源集中、多指标参数|是通用趋势的行业实现，优先证明相对简单趋势的增量|A6/A14/D9/E组
A55|日内动量|开收盘订单流和机构再平衡可能造成日内持续|条件保留|高：日内高质量行情、执行和时段|机制较明确，仍应排在小账户慢速基线之后|A2/B3/B4
A56|日内相对价格|相关指数ETF偏离可能暂时修复|条件保留|高：同步分钟价格、双边和价差|只有相对价值交易假设，不能以套利二字推断无风险|A12/A24/A48
A57|成长股质量|经营质量可能区分高估成长与可持续成长|条件保留|高：R&D等PIT字段及行业比较|含真实财务信息，和质量/盈利家族重叠|A32/A35/A28
A58|新闻信息|药物与监管等新闻可能逐步反映在价格中|条件保留|高：首次新闻时间、文本/事件与行业尾部|有独立信息价值，但狭窄行业和延迟成本不适合先做大NLP工程|C6/A51
A59|统计预测/技术|过去短期收益是否预测未来是待证统计关系|低优先|高：动态股票池、短训练与换手|朴素贝叶斯本身不是经济优势；先有基线和目标收益定义|A60/技术ML
A60|统计预测/技术|技术特征与日内收益的关系需要独立证据|低优先|高：分钟行情、滚动训练和执行|模型复杂度不增加信息来源，四周训练对稳定性要求高|A59/技术ML
B1|配对组件|价格比偏离均值可作为相对价值信号|组件非策略|未定义：缺资产池与组合/退出契约|是AlphaModel组件，不能脱离选池风控独立称完整策略|B2/A12/A24
B2|配对组件|高相关资产可能共享共同因素|组件非策略|未定义：缺再选对和账户规则|最高相关不等于稳定价差；组件非完整策略|B1/A12/A24
B3|活跃股开盘突破|异常开盘量可能识别有新信息、趋势更强的股票|条件保留|高：PIT分钟股票、多空及开盘执行|论文机制和可编码规则值得保留；10k成本与监管账户约束待核|B4/A2/A55
B4|活跃股开盘突破|与B3同一信息/订单流延续机制|条件保留|高：同B3|论文与复现保留各自ID，但只算一个机制家族；多个窗口非独立alpha|B3
B5|防御资产配置|动量和金丝雀共同决定风险预算|条件保留|低中：ETF但组合优化与规则较多|与C4近亲非同一实现；已见补测源码，初始未测状态不代表最新阻塞|C4/A6/A7/C1
C1|慢速双动量|相对动量与绝对趋势控制权益风险暴露|优先|低：三ETF月度切换|适合作为简单代表；当前代理实现的胜负不能代替GEM原版结论|A6/A7/A20
C2|股票趋势组合|中期价格持续配合风险分配|优先|中：PIT股票、周度检查与多股分散|比零散指标更接近完整组合；这是二手实现，须冻结书本/代码身份|A14/A43/C9
C3|周频突破趋势|长期趋势持续且较低换手|条件保留|中：股票分散及较宽止损|方向可留，但论坛转写参数和状态止损不能冒充原书精确规则|C2/C5/A14
C4|防御资产配置|动量、资产分散和条件防守|条件保留|低中：月度ETF及协方差估计|先证明相对A6/C1的增量；B5移植不能共享回测结论|B5/A6/A7/C1
C5|价格突破形态|强势股整理后可能继续反映信息|条件保留|高：形态离散化、日内入场和集中|交易经验可作为假设；形态和分批退出未机械化则非可直接复现alpha|C3/C6/A14
C6|事件驱动趋势|重大盈利/催化剂可能引发分阶段重估|条件保留|高：事件PIT、跳空和开盘执行|包含价格之外的信息，保留价值高于泛均线叠加；须定义催化剂与入场|A51/A52/A58/C5
C7|极端反转做空|狂热和短期过度反应可能修正|低优先|极高：难借券、挤空、跳空和无限空头尾部|即便信号成立也与10k/DD20-30%目标冲突较大|A4/极端反转
C8|仓位组件|风险预算限制单笔亏损与集中度|组件非策略|低但依赖宿主策略|可复用风控原则，没有独立收益来源|C5/C6/C7
C9|股票价格动量|相对强者可能延续|条件保留|中：五股集中、日级调整和多个退出|动量机制可留；20/60/120、85、10%/30%等需与简单基线分开|A14/A43/C2
C10|两资产趋势|股票与BTC各自趋势持续及防守现金|条件保留|中：跨券商/交易所、不同交易日及BTC风险|规则简单可研究；固定30%BTC不是经过验证的DD20-30%账户预算|A6/C1/A53
D1|资金费率拥挤|极端费率可能反映杠杆拥挤和之后价格反转|条件保留|中高：永续保证金、价格PnL和funding|想法可检验；原回测只计signal×funding忽略标的PnL，当前代码不可用|D2/D5
D2|资金费率状态|持续杠杆需求可能伴随趋势或反转|条件保留|中高：交易所单位和永续账户|方向需先固定；源码跨币滚动污染使当前数字失去解释|D1/D5
D3|加密横截面动量|币种信息与资金流可能持续分化|条件保留|高：PIT币池、合约身份和多空|机制可留，tanh连续权重与文字排名不是同一策略；优化窗口不能后选|A14/A43/加密动量
D4|加密残差反转|共同BTC因素外的币种偏离可能回归|条件保留|高：真实对冲腿、beta和资金费率|原beta/归一化/残差PnL错误，必须重建；不能称已实现市场中性套利|A48/A12
D5|资金费率事件拥挤|费率极端加OI变化可能识别拥挤去杠杆|条件保留|中高：小时价格/OI/funding与事件执行|独立持仓信息有研究价值；同刻入场、止损区间、资金占用须修正另立版本|D1/D2
D6|资金利率相对价值|远期隐含固定利率与未来浮动利率差异可交易|条件保留|高：Boros期限合约、抵押品和流动性|需要实际可成交固定利率；浮动funding不是可锁定报价，更非现货永续carry|D1/D5但不同交易对象
D7|技术均值回归|短期下跌可能反弹|低优先|中高：加仓、尾部和手续费|基础回归假设可留；特定ROI/追踪/补仓参数堆叠缺独立信息|D8/A4
D8|技术均值回归|超跌状态可能反转|低优先|高：15分钟交易、止损和成本|RSI与布林多为同价格信息重表达，不能靠指标数量证明优势|D7/A4
D9|技术趋势|价格趋势可能持续|低优先|中高：小时换手与成本|趋势思想不被该实现结果否定；EMA/ADX增加的增量未证明|D10/A54/E组
D10|技术趋势突破|趋势突破可能反映订单流持续|低优先|高：30分钟换手与多过滤阈值|MACD/唐奇安/均线/量能叠加主要增加自由度|D9/A54/E组
E1|主观技术/期权方向|关键位可能聚集订单，但反弹拒绝定义主观|低优先|高：2分钟执行和期权合约/价差|股票方向规则不等于期权策略，未指定合约与成交不可评收益|E2/E3/E14
E2|主观技术/期权方向|关键价格及均线可能描述局部趋势|低优先|高：0DTE/期权选择和Gamma尾部|未机械化回踩与合约，不能用标的方向胜率替代期权盈利|E1/E3
E3|主观技术/期权方向|趋势延续假设|低优先|高：期权到期/行权价/波动率与执行|10/50均线本身不构成独立信息，缺完整期权契约|E1/E2/D9
E4|技术形态趋势|强势股票缩量整理后可能继续趋势|低优先|高：扫描PIT、形态主观和日内执行|多条件和蜡烛形态自由度大，先与单一趋势/动量比较|C5/E5/E14
E5|技术突破波段|价格扩张可能反映新买盘|低优先|中高：形态定义及收盘成交|用最终收盘判断又按同一收盘入场有时序问题，须先机械化|C5/E4
E6|枢轴位突破|参考价位或有订单聚集，但特定公式缺独立机制|低优先|高：15分钟、跨市场时区和跳空过滤|Camarilla/均线/多关键位叠加，未定义大跳空和场所|E8/E9
E7|VWAP趋势|成交量加权价格可能代理机构执行参照|低优先|高：5分钟、双边和成交质量|可作为微观结构特征；简单穿越不自动带来净收益|E8/E9/E14
E8|VWAP通道趋势|量价趋势及回踩可能延续|低优先|高：5分钟、ticks和多个退出条件|三倍通道加枢轴均线形成高度具体实现，增量未证|E7/E9/E14
E9|枢轴/VWAP趋势|关键位突破后的订单流可能持续|低优先|高：多级枢轴、5分钟执行和参数|与E8同作者近亲，条件堆叠不能当新独立alpha|E6/E7/E8
E10|时段反转形态|特定交易时段可能具有不同流动性|低优先|高：3/5分钟和市场/时区缺失|小时列表及区间规则未说明经济来源，必须先定时区/会话|日内反转/E组
E11|均线云趋势|趋势延续假设|低优先|高：10分钟、盘前流动性与双边|多条均线云是同价格信息重表达，不增加独立证据|E12/E15/D9
E12|趋势过滤组件|多周期趋势一致可能过滤环境|组件非策略|未定义：缺确定入场和退出|作为过滤假设可留，当前文字不是完整可回测账户策略|E11/E15
E13|期权OI解释|OI和权利金变化可能反映定位，但不能唯一推断卖方边界|低优先|极高：0DTE尾部、合约粒度和全权利金风险|由OI推断边界不唯一，1:4目标不是正期望证据|E1/E2/E3
E14|VWAP/均线形态|趋势和局部订单聚集假设|低优先|高：5分钟、多条件和主观过度延伸|规则与E7/E11高度相关，先定义边界再谈独立性|E7/E11/E4
E15|趋势日过滤组件|趋势日与震荡日可能有不同交易条件|组件非策略|未定义：依赖宿主进出场和满仓定义|是仓位/状态过滤器，非独立策略；过滤须避免看完整天后分类|E11/E12'''

parsed={}
for line in raw.splitlines():
    p=line.split('|')
    assert len(p)==7,(p[0],len(p))
    id,mechanism,hypothesis,priority,burden,reason,overlap=p
    parsed[id]=dict(mechanism_category=mechanism,economic_hypothesis=hypothesis,research_priority=priority,small_account_burden=burden,priority_reason=reason,overlapping_family_ids=overlap)
assert len(parsed)==100

def line_of(path, token):
    return next((n for n,l in enumerate(path.read_text().splitlines(),1) if token in l),None)
def source_type(id):
    if id.startswith('A'):return 'QuantConnect教程；其中部分转述论文机制，教程不是原论文独立复现'
    if id in ['B1','B2']:return 'QuantConnect框架组件'
    if id=='B3':return 'QuantConnect研究文章/论文复现'
    if id=='B4':return 'SSRN论文链接；当前保存页未成功获取正文，机制按清单与B3核对'
    if id=='B5':return '论坛/平台移植；已发现后续原源码恢复目录，未并入初始状态'
    if id in ['C1','C2','C3','C10']:return '博客或论坛转述/实现；不能自动等同原书/原研究'
    if id=='C4':return '作者策略原文及代码'
    if id in ['C5','C6','C7']:return '交易者本人经验文章；主观条件尚非机械契约'
    if id=='C8':return '交易者经验转录；风险管理组件'
    if id=='C9' or id.startswith('D'):return '公开GitHub实现；无独立验证保证'
    return '社交媒体/线程转录经验；出处与完整规则需要单独验收'

semantic_overrides={
'A8':'当前代码须重建：列向量与一维预测广播风险，月收益除以Close；尚未在原QC环境执行。',
'A11':'当前代码不是标准低波动：直接计算原始股价标准差，受计价单位影响。',
'A14':'源码直接构造Momentum(252)，须确认绝对价差语义，不能默认为252日百分比收益。',
'A51':'规则相对清楚，SUE为历史EPS变化标准化；月度重复采样需与实际财报首次公布日期对齐。',
'A32':'有综合质量代码；现金流指标的命名/分母及字段单位须逐项核对，不凭名称承认实现正确。',
'D5':'源码与下一小时规则不一致，side=left可同刻入场；止损含原定开盘退出之后整根bar，PnL固定初资且无funding。',
'D6':'README自行承认原回测把浮动利率当可锁定利率；实际Boros隐含固定报价不可省略。',
'B5':'初始SOURCE_OR_RULE_BLOCKED是时间戳状态；后续recovered-b5-original已存在，不能继续断言原源码不可获得。'
}

direct_ids={'A1','A6','A7','A8','A9','A11','A14','A15','A21','A26','A28','A29','A32','A35','A41','A47','A51','A52','A53','A57','B3','C2','C4','C5','C6','C7','D1','D2','D3','D4','D5','D6'}
rows=[]
for item in inventory:
    id=item['id']; prev=review_map[id]; d=parsed[id]
    evidence=[f"research/asset-portfolios/multi-public-strategies-100/specs/inventory.json:{line_of(F/'specs/inventory.json', chr(34)+'id'+chr(34)+': '+chr(34)+id+chr(34))}",f"research/asset-portfolios/multi-public-strategies-100/artifacts/strategy-review-100.json:{line_of(F/'artifacts/strategy-review-100.json', chr(34)+'id'+chr(34)+': '+chr(34)+id+chr(34))}"]
    if id in semantic_overrides and (F/f'artifacts/sources/extracted/{id}.txt').exists():
        evidence.append(f'research/asset-portfolios/multi-public-strategies-100/artifacts/sources/extracted/{id}.txt:1')
    rule_quality=semantic_overrides.get(id,prev.get('finding',''))
    if d['research_priority']=='组件非策略': potential='有组件价值；无独立收益命题'
    elif id in ['A37','A36','A42','A50','A59','A60'] or id.startswith('E'):potential='经济先验较弱或经验条件主导；并非已经证伪'
    elif id in ['A2','A31','A33','A34','A40','A53','A54','D7','D8','D9','D10','C7']:potential='基础机制可理解；此特定组合的增量依据薄弱'
    else:potential='有可检验的经济或行为机制；当前不代表已有效'
    rows.append(dict(original_id=id,original_name=item['name'],original_backtestability_rating=item.get('original_rating'),original_rating_meaning='可回测程度，非盈利质量',**d,idea_potential=potential,source_type=source_type(id),source_rule_quality=rule_quality,inspection_scope=('清单/初审及部分原始源码或方法正文抽查' if id in direct_ids else '逐条清单/初审交叉检查；未声称独立执行源码'),original_empirical_status=prev['status'],initial_has_numeric_diagnostic=prev['status']=='NUMERIC_DIAGNOSTIC_ONLY',initial_formally_verified=False,empirical_status_as_of=review.get('as_of'),unresolved_requirement=prev.get('required_next',''),source_url=item['source_url'],evidence=evidence))

assert [x['original_id'] for x in rows]==[x['id'] for x in inventory]
assert len({x['original_id'] for x in rows})==100
assert sum(r['initial_has_numeric_diagnostic'] for r in rows)==19
assert len(un_map)==81
meta={'audit_date':'2026-09-09','scope':'只读思想与研究价值分层；非新回测、无收益打分、无实盘荐股','base_empirical_snapshot':review.get('as_of'),'snapshot_warning':'19有数字/81未测只描述给定初始快照；另任务正在补测，不能当最新总进展。思想优先级独立于实证状态。','priority_counts':dict(collections.Counter(x['research_priority'] for x in rows)),'initial_untested_priority_counts':dict(collections.Counter(x['research_priority'] for x in rows if not x['initial_has_numeric_diagnostic'])),'component_reclassification':'B1/B2/E12/E15是本审计对完整策略定义的判断，非把旧状态静默改写；C8原本已为组件。','rows':rows}
(OUT/'public100-quality-all100-20260909.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
with (OUT/'public100-quality-all100-20260909.csv').open('w',newline='',encoding='utf-8-sig') as h:
    writer=csv.DictWriter(h,fieldnames=list(rows[0]));writer.writeheader()
    for r in rows: writer.writerow({**r,'evidence':'; '.join(r['evidence'])})

inputs=['specs/original-list-20260908.md','specs/inventory.json','artifacts/strategy-review-100.json','artifacts/untested-81-20260909.json','artifacts/sources/pages-manifest.json']
keys=inputs+[f'artifacts/sources/extracted/{id}.txt' for id in ['A1','A6','A7','A8','A9','A11','A14','A15','A21','A26','A28','A29','A32','A35','A41','A47','A51','A52','A53','A57']]
keys+=['artifacts/sources/Adeline117__Strategy-project/src/backtest.py','artifacts/sources/Adeline117__Strategy-project/src/signals.py','artifacts/sources/0xSmartCrypto__meridian/README.md','artifacts/sources/0xSmartCrypto__meridian/docs/PAPER-TRADING.md','artifacts/sources/recovered-b5-original/source-manifest.json']
page_manifest=json.loads((F/'artifacts/sources/pages-manifest.json').read_text())
for id in ['B3','C1','C2','C3','C4','C5','C10']:
    u=next(x['source_url'] for x in inventory if x['id']==id)
    keys.extend([x['path'] for x in page_manifest if x['url']==u and x.get('path')])
source_hashes=[]
for path in dict.fromkeys(keys):
    p=F/path
    if p.exists():source_hashes.append({'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
declared=[]
for item in inventory:
    for e in item.get('evidence_files',[]):
        p=F/e['path']; actual=hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
        declared.append({'id':item['id'],'path':e['path'],'matches_declared':actual==e['sha256']})
shape_observed=np.array([[.01],[.03],[-.02]])
shape_pred=np.array([.008,.020,-.015])
source_sub=shape_observed-shape_pred
vector_sub=shape_observed[:,0]-shape_pred
prices=np.array([100.,110.,100.,110.]); scaled=prices/100
static={'scope':'仅静态最小反例，无市场数据、无回测、无调参；未装statsmodels且未执行原QC环境','A8':{'observed_shape':list(shape_observed.shape),'prediction_shape_assumption':list(shape_pred.shape),'source_result_shape':list(source_sub.shape),'intended_result_shape':list(vector_sub.shape),'source_result':source_sub.tolist(),'intended_result':vector_sub.tolist(),'source_score':float(source_sub.sum()/source_sub.std()),'vector_score':float(vector_sub.sum()/vector_sub.std()),'limitation':'一维预测为常见statsmodels单响应输出；本反例证明此形状下源码必广播，不证明旧版本完整运行行为。源码月收益除以Close是另一个直接可见问题。'},'A11':{'prices':prices.tolist(),'same_economics_new_unit':scaled.tolist(),'source_std_before':float(prices.std()),'source_std_after':float(scaled.std()),'return_std_before':float(np.std(prices[1:]/prices[:-1]-1)),'return_std_after':float(np.std(scaled[1:]/scaled[:-1]-1)),'interpretation':'经济收益完全相同而原源码分数改变100倍；即使拆股复权完整，横截面的股价计价尺度仍会影响排序。'}}
(OUT/'public100-quality-static-counterexamples-20260909.json').write_text(json.dumps(static,ensure_ascii=False,indent=2)+'\n')
hashes={'audit_date':'2026-09-09','source_files':source_hashes,'inventory_evidence_files_checked':len(declared),'inventory_evidence_hash_mismatch':[x for x in declared if not x['matches_declared']],'note':'文件哈希仅标识和核对来源快照；不是来源正确性、代码正确性或策略通过证明。'}
(OUT/'public100-quality-sourcehash-20260909.json').write_text(json.dumps(hashes,ensure_ascii=False,indent=2)+'\n')

lines=['# 公开100条策略：思想质地与研究价值独立审计','',
'审计日期：2026-09-09。只读 main 中冻结的清单、初始审查及保留来源；没有新下载、回测或参数搜索。逐原 ID 保留全部 100 条。',
'',
'## 结论边界','',
'这是一份质量不均的公开研究素材集，包含有经济基础的风险溢价/行为机制、完整度较高的组合模板、教材演示、同一家族不同实现、主观交易经验和风险组件。它不是100个相互独立、已经验证的alpha。清单自己已说明“高”只表示规则/代码可回测程度，不是赚钱质量；本审计没有把作者原话改写成盈利承诺（specs/original-list-20260908.md:5–12）。',
'',
f"给定初始快照 {review.get('as_of')} 中19条有数值诊断、81条未产生数值、正式验证0条。81未测绝不等于81无效；后续补测目录已经出现，本表仅保留输入快照状态，不冒充最新研究进展。原实证状态与本次思想判断在CSV/JSON中分列。",
'',
f"81条初始未测中，本次分为：{json.dumps(meta['initial_untested_priority_counts'],ensure_ascii=False)}。其中优先做研究验收的是A21、A51、C2；另有49条条件保留，绝不是把数据缺口批量当无效。",
'',
'思想优先级是研究资源排序，不是预期收益评分或投资建议。“优先”也不等于当前代码可以运行/实盘。“条件保留”中存在经济思想较强、但原源码必须重建的条目；数据暂缺不会被记作思想弱。$10k落地负担只讨论资金分散、合约粒度、杠杆/借券、换手和运维；实际券商、税务、市场权限、保证金和交易规则仍须未来按用户所在市场核实。DD20–30%是账户验收目标，不是这里已证明满足的风险上限。',
'',
'## 值得保留的研究槽','',
'1. 慢速、少资产的趋势/动量组合：A6、A7、C1选有限代表比较，A20是两资产对照。C4/B5、C10属于延伸，不应一开始同时展开几十种变体。它们的价值是规则简单、低换手和账户化清楚；当前任何有利诊断不能代替原版忠实复现或新时间验证。',
'2. 价格之外的信息：A21价值、A51历史SUE值得优先做有限的PIT可得性与原码语义验收；A26/A28/A32/A35/A57为投资/盈利质量近亲，挑一个代表而非全部当独立发现。A52用于检验盈利是否在纯价格动量上提供增量。A51是相对历史EPS的意外，不应擅自变成需要分析师预测的另一个策略。',
'3. 股票动量的完整组合：C2比零散买卖信号更接近账户模板；A14/A43/C9可作同机制的规则对照，不能汇总成四个独立alpha。C2是公开二手实现，需冻结来源身份与PIT成分，不等同原书精确复现。',
'4. 思想保留、当前代码先重建：A8残差动量、A11低波动、D1/D2资金费率、D4加密残差回归。发现源码错误不能证明它们经济机制失败，也不能跳过源码错误拿其历史数字指导参数。A41低beta、A44国家价值具有不同经济信息，但原账户/数据负担较高。',
'5. 高负担的条件池：A18卖保险、A48/56相对价值、B3/B4活跃股ORB、C6事件跳空、D5费率/OI事件、D6利率相对价值。思想有价值不代表适合10k首条实盘主线。D1/D5是方向性拥挤交易；D6交易固定/浮动利率差；都不能被改称已经验证的BTC/ETH现货永续carry。',
'',
'较低优先不等于统计上已证伪：A37月相、若干日历条件、A59/A60纯技术机器学习、D7–D10特定指标堆叠、E组大部分日内主观模板，主要弱点是经济先验/新增信息少、研究自由度高、执行与成本负担不成比例。A36即使已有正数字也不能据此提高思想评级；其一月预测增量必须与普通权益暴露分辨。',
'',
'## 关键原始证据与新增源码检查','',
'- A11：`artifacts/sources/extracted/A11.txt:53–57`把Close放入Price窗口，`:84–98`对价格做`np.std`。同一价格路径换计价单位后分数改变100倍，而收益率波动不变。低风险经济假设可留；现代码不是标准收益率低波动。',
'- A8：`artifacts/sources/extracted/A8.txt:97–98`明确单列DataFrame；`:139–146`把二维`.values`减预测的一维`.values`，存在n×n广播风险；`:166`月收益分母为Close而非Open。静态反例保留数组和结果，但未执行原QC/历史statsmodels；不能声称完成原算法复现。',
'- A14：`artifacts/sources/extracted/A14.txt:65–77`按指标排序，`:90–92`构造Momentum而非ROC；须先固定其绝对价格变动语义，不能自动当标准12月相对收益动量。',
'- A51：`artifacts/sources/extracted/A51.txt:5–15`给出历史EPS变化的SUE逻辑和参考，`:65–84`用月度EPS窗口计算；资料公布时点与季报重复月份必须验收。经济信息来自盈利变化，和堆技术指标有本质信息区别。',
'- A32：`artifacts/sources/extracted/A32.txt:50–51`“cash flow to assets”注释对应的分母为EPS×股数；应逐项核验分母与质量分数意义，不能靠因子名称推断实现准确。',
'- D5：`artifacts/sources/Adeline117__Strategy-project/src/backtest.py:76–98`可按信号同刻开盘成交，`:110–119`把原定开盘退出bar之后的高低也算止损，`:121–155`固定初资相加而非真实资金账户，未加入funding。这些是源代码问题，不是费率/OI信息无效证据。',
'- D6：`artifacts/sources/0xSmartCrypto__meridian/README.md:19–25`自己说明原回测把浮动费率当可锁定利率；`docs/PAPER-TRADING.md:73–74`明确固定/浮动腿。没有实际期限隐含固定报价就不能声称利率套利利润。',
'- A9/A29/A53已有初审文字/代码冲突：分别是63日绝对价差与12月相对动量、反向与顺向、200小时与200日。保留不同版本，不按最好结果选择哪个叫原策略。',
'',
'以上源码相对路径均以 `research/asset-portfolios/multi-public-strategies-100/` 为根。关键源文件与输入SHA256另存JSON；全100表每行附清单与初审确切行号。源码抽查不等于执行测试；未抽查条目明确标注检查范围。',
'',
'## 重复和组件','',
'- B3/B4是论文与复现的同机制；C4/B5是KDA原文与移植的近亲，但再平衡/选仓规则不同，所以不能共享同一回测结论。',
'- A14/A43/C2/C9及行业/国家/REIT动量大量共享价格动量；A6/A7/C1/C4/B5/C10共享趋势与防御配置；A26/A28/A32/A35/A57共享投资/质量信息；A42/A50共享同月季节性。',
'- D7/D8共享技术反转；D9/D10及E组不少均线/VWAP模板共享技术趋势。多加几条均线、换周期/市场或换作者不自动增加独立alpha。上述为机制重合判断，未计算策略收益相关性，不能给精确独立alpha数量。',
'- B1、B2、C8、E12、E15按当前公开内容更适合作为组件。除原C8外，这是本次研究性质判断，不把原审计状态悄悄改写；补全宿主契约后可以形成新策略。',
'',
'## 全100条紧凑表','',
'P=优先研究；C=条件保留；L=低优先；K=组件。N=初始已有数值诊断，U=初始未测。所有行均无正式通过；N不能解读为有效，U不能解读为无效。完整经济逻辑、来源可信度、$10k负担、原实证状态、证据行号见配套CSV/JSON。','',
'| 原ID | 名称 | 机制 | 思想/研究判断 | 初始实证 | 主要原因 |','|---|---|---|---|---|---|']
short={'优先':'P','条件保留':'C','低优先':'L','组件非策略':'K'}
for r in rows:
    lines.append('| '+' | '.join([r['original_id'],r['original_name'],r['mechanism_category'],short[r['research_priority']],'N' if r['initial_has_numeric_diagnostic'] else 'U',r['priority_reason']])+' |')
lines+=['','## 验收与文件','',f"分层数量（人为研究分组，不是概率）：{json.dumps(meta['priority_counts'],ensure_ascii=False)}。100个原ID完整且唯一；初始N=19、U=81；校验了{len(declared)}个清单声明的来源文件哈希，差异{len(hashes['inventory_evidence_hash_mismatch'])}。",'',
'- `/tmp/public100-quality-all100-20260909.csv`：100条完整分列评价。',
'- `/tmp/public100-quality-all100-20260909.json`：同表、原实证时间戳和边界。',
'- `/tmp/public100-quality-sourcehash-20260909.json`：关键源码/输入SHA256与清单源文件一致性。',
'- `/tmp/public100-quality-static-counterexamples-20260909.json`：A8/A11最小静态反例，无新市场回测。',
'- `/tmp/public100-quality-build-20260909.py`：产生本审计表和反例的脚本；只向/tmp写审计产物。','',
'后续完成条件：选少量互不重复的信息机制；先冻结忠实源版与必要纠错版的身份，验收当时可用数据，再用同一真实资金账户、同风险/市场暴露基线、成本压力和未读时间证据判断。补测中的失败只能否定对应输入/规则/账户范围；不能由这100条或其中已测子集推断“中低频技术策略全部无效”，也不能由公开规则或论文引用承诺长期实盘盈利。','']
(OUT/'public100-quality-inventory-20260909.md').write_text('\n'.join(lines))
print(json.dumps({'rows':len(rows),'priority_counts':meta['priority_counts'],'declared_source_hash_checks':len(declared),'mismatches':len(hashes['inventory_evidence_hash_mismatch']),'output_report':str(OUT/'public100-quality-inventory-20260909.md')},ensure_ascii=False))
