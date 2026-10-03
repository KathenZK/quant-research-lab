# M0274 GodStra：来源忠实核验与阻塞研究报告

## 1. 结论与范围

本轮未运行真实策略回测，严格复现数为0。状态为 **BLOCKED / HYPOTHESIS / DIAGNOSTIC_ONLY**。下载失败与原完整指标管线因果失败分别构成阻塞，不能相互掩盖。没有收益率、Sharpe、回撤、胜率、交易数、资金曲线、成本或延迟敏感性的数值结果；这些字段为null/NOT_RUN，不是0。也没有把参数阈值在BTCUSDT上可能极少触发的直觉冒充零交易结果。

预先指定实例为Binance现货BTCUSDT、原生12h。输入窗口 `[2022-12-01T00:00:00Z, 2025-01-01T00:00:00Z)`，评价窗口 `[2023-01-01T00:00:00Z, 2025-01-01T00:00:00Z)`，预热62根，完整预期1524根、评价1462根。没有因下载失败改为14个月研究，也没有以4h重采样冒充12h。

## 2. 原ID、来源与作者规则

作者标记为Mablue / Masoud Azizi，仓库freqtrade/freqtrade-strategies。固定提交 `f3340ce11f5bdf62f598522e64d1f5638eaa13f5` 下的[GodStra.py](https://github.com/freqtrade/freqtrade-strategies/blob/f3340ce11f5bdf62f598522e64d1f5638eaa13f5/user_data/strategies/GodStra.py)，6802字节，SHA256 `48e405f6d073944da9b993dfbce03aa980d0eea8a5da3c4a6b60f2f1b7264b86`。与交接claims及原主表M0274行核对一致。源码内旧优化收益不是本轮结果。

精确机器规格见[原规则](specs/source-rules-v1.json)，核心为：

- 周期12h，只设置做多入场。买入 `trend_ichimoku_base < 0.06295`
- 卖出编码 `sell-oper-0='=R'` 调用 `numpy.isclose(trend_kst_diff, 0.8779)`，默认rtol=1e-5、atol=1e-8、equal_nan=False。主表“等于”必须读作源码的容差比较，不能擅改为浮点严格==
- ROI分钟阶梯：持仓0分钟起35.56%；4818分钟起21.275%；6395分钟起9.024%；22372分钟起0
- 初始止损 -0.34549，即-34.549%
- trailing_stop=True；trailing_stop_positive=0.22673；trailing_stop_positive_offset=0.2684；trailing_only_offset_is_reached=True
- 源码注释要求StaticPairList之后加AgeFilter，min_days_listed=30；并建议尽量小的max_open_trades。这里没有作者原配置和动态选池历史，不能声称复现
- 先执行 `ta.utils.dropna(dataframe)`，再 `add_all_ta_features(..., fillna=True)`。有效参数取源码buy_params/sell_params，不进行优化或参数加载覆盖
- buy-cross `volatility_kcc`、buy-int 42、sell-cross `volume_mfi`、sell-int 98被读取，但在当前 `<R`/`=R`分支不参与判据，完整保留而不误用

白话理解：当一目均衡基准线低于很小的绝对数值时买入，KST与其信号线的差接近指定值时卖出，同时辅以ROI、止损和追踪。ta的Ichimoku base是以价格计价的26根最高/最低中点，未进行归一化；阈值0.06295不是6.295%收益率。这个量纲可能与BTCUSDT尺度不匹配，但本次未调阈值追求交易。

## 3. 机制、理论与证据缺口

一目基准线描述近期区间中点，KST加权不同长度价格动量，再与平滑信号线作差。源码是“基因模板”的一组固化条件，没有足够证据解释绝对阈值对BTCUSDT的经济机制。旧源码注释显示经过搜索，但搜索空间、总试验次数、训练/验证拆分、历史标的池、原依赖和原Freqtrade版本都未固定，不能计算可信的DSR/PBO，也不能声称独立OOS。

同一BTCUSDT 2023–2024窗口已用于此前catalog诊断，本目录不重置样本曝光。新增参数搜索0次。未进行收益筛选、窗口择优或“无交易则换阈值”。

## 4. 新增研究假设与源规则的边界

[收益前计划](specs/pre-performance-plan-v1.json)预先记录了只有门控通过才可能使用的假设，但实际均未运行：固定单币、初始10000 USDT、最多一笔多仓、1倍无杠杆、含入场费的全额仓位、允许分数数量，不声称满足交易所最小量/容量。

基线每边8bps手续费+2bps滑点，费用敏感性每边0/20bps仍加2bps滑点；信号闭合后下一根开盘成交，额外1根延迟敏感性。买持计划使用同窗首次可执行开盘入场和末根收盘清算，并使用一致费用。只定义计划，没有算买持收益。

12h数据无法精确还原ROI分钟阈值跨越、止损与追踪同根先后。计划显式采用风险优先、低价先于高价的保守路径代理，盘内更新只在下一根生效；ROI分钟新阶梯在下一可执行开盘生效。追踪采用收盘确认偏移后下一根更新的代理。这些并非作者原Freqtrade引擎的严格复刻，因此即使输入/因果通过也最多是HYPOTHESIS。原参数数值保持不变。完整假设与优先级以JSON为准。

NaN处理保留源码。传给dropna的只应是date/open/high/low/close/volume；若把原生归档ignore=0列传入，会把所有行删掉。脚本对此区分并禁止静默删有效行。AgeFilter30天需要独立日K有效性/动态池语义，31天预热不能替代。

## 5. 原生数据捕获与质量门禁

来源为官方Binance Vision月档 `/data/spot/monthly/klines/BTCUSDT/12h/`，保留ZIP、CHECKSUM、原始CSV、HTTP时间和摘要。新脚本只接受12h，没有修改旧受审脚本。源文档明确支持12h；native12指12个原生字段，不应与12h周期混淆。

14个完整月档覆盖2022-12至2024-01，共854根。独立离线校验43个现存对象，其中14×3个ZIP/CHECKSUM/CSV及2024-02单独CHECKSUM：ZIP SHA256与官方CHECKSUM一致、CRC正常、单CSV成员、原生12列、UTC每12小时递增、close_time=open_time+12h−1ms、价格/成交量/成交笔数/主动成交量范围和报价界限均通过。没有排序、去重、插值、填零或聚合。所有已取得时间戳为毫秒。官方2025-01-01开始微秒变更在计划末端之外，但剩余未下载部分未被实际测试，不能写全窗口通过。

2026-10-03T10:21:48.078981Z，2024-02 ZIP的GET返回 `Tunnel connection failed: 403 Forbidden`。session读回随后返回 `automatic approval review was cancelled`。立刻停止网络重试，未换host/代理；保留.partial失败证据。首后台launch没有留下持久捕获进程，10:18:10改前台执行，启动历史分开保存，均不是回测启动。

尚缺670根，完整25月canonical输入未创建，完整窗口QA失败。第二次网络抓取及完整网络重建NOT_RUN。已有854根离线复核通过不意味着完整市场数据可信。九项门禁见[输入门禁](artifacts/input-gates-v1.json)：registered_status=UNACCEPTED，scope=EXPLICIT_DIAGNOSTIC，quality_status=DIAGNOSTIC_ONLY。没有写normalized/trusted数据湖，也未借用旧4h或perp输入。

原归档没有权威is_closed标志；既有api.binance.com/time请求HTTP451，本轮未重试或绕过。月档完整网格、HTTP时钟和校验一致不等于当前桶/稳定双次抓取协议完成，更不等于历史发布时点不可修订。因此strict current finality、PIT universe及可交易容量均未建立。

## 6. 停市事实及订单时钟

官方材料表明2023-03-24 11:27 UTC暂停现货、14:00恢复。12h的00:00桶末段和12:00桶前段都受停市影响。12:00桶虽有合法12h网格和正成交量，其首笔实际交易不能被假设发生在12:00。

本轮只读既有官方1h证据及公告：12:00 1h是零量、非标准闭合，13:00缺桶；14:00的1h开盘值与12:00原生12h桶开盘值相同。没有读/下载1m。事先声明的假设是把本应12:00执行的订单推迟至14:00，并把12h开盘仅作为恢复后第一价格代理；若比对失败就阻塞。没有实际下单或回测成交，不能把这个代理写成确认的订单簿可成交价格。见[停市证据摘要](artifacts/outage-and-source-provenance-v1.json)。

## 7. 因果审计：已证明什么、没有证明什么

作者未固定ta版本；本次固定ta0.11.0、NumPy2.3.5、pandas2.2.3，模块SHA均有记录。未安装/运行完整Freqtrade。静态审查发现KST在shift前端使用整段close.mean填充；visual Ichimoku也以整段span均值填充。这使历史初始化可能依赖未来数据。

在240根确定性合成OHLCV中，分别只给前62/80/124/239根，与全240根对应前缀比较。11列在容差rtol1e-12、atol1e-10下发生历史变化；KST_diff变化位于索引1–51，Ichimoku base不变。KAMA的变化可延续到62根预热之后，但它不是当前入出判据所选列。完整checks与独立审核脚本逐字段一致，换目录离线重跑也一致。

这是原完整 `add_all_ta_features(fillna=True)` 管线的可重复反例，足以触发冻结的“存在未来依赖就阻塞原实现”规则。它**不是**真实完整行情的因果测试，更不是证明本次BTCUSDT评价期间实际买卖信号改变。合成输入的当前选用两列在索引62后没有观察到变化。未以此缩减列集、改fillna、忽略原管线或套用“预热吸收”来放行。

完整真实窗口因果审计NOT_RUN，真实特征及信号计数也NOT_RUN。指标合成反例运行不计策略回测。当前NumPy实际仍能导入numpy.lib.math（弃用警告），没有把版本猜测误报成导入失败。

## 8. 结果、失败场景与后续方向

结果字段见[results-status](artifacts/results-status-v1.json)。费用/延迟/买持/风险分解/年度绩效/交易清单均未执行，原因同上。不能宣称盈利、无效策略或已完成零交易回测。

潜在失败场景包括价格量纲与绝对阈值不匹配、浮点容差误实现、全局填充值前视、作者库版本差异、动态AgeFilter缺证、停市时钟错配、12h盘内路径及分钟ROI无法还原、缺少历史池/PIT与容量证据。没有足够证据晋升或实盘使用。

将来若需要继续，须先在授权访问恢复后单独保留新的完整原生输入并逐hash重建；原管线因果失败不会因数据补齐自动消失。任何仅保留因果列、改初始化或修改阈值的方案必须作为另行批准的改编规格，不覆盖本冻结证据。本轮没有启动后续改编、扩大币种或新窗口。

## 9. 检查点与可恢复性

- C0：源码身份PASS；已留存14月行质量PASS；完整25月输入INCOMPLETE_BLOCKED
- C1：收益前规则/成本/执行/曝光计划已冻结；随后阻塞诊断协议冻结，未绑定不存在的全量输入hash
- C2：阻塞证据经独立复核及本地换目录恢复通过；真实回测C2为NOT_RUN
- C3：本worker未Git提交、远端发布、Library保存或Site操作；由协调者后续记录，不能以工作盘当备份

公开包保留中文文档、精确规格、源及依赖hash、重建代码、对象摘要和轻量阻塞结果。完整第三方源码、原始行情、大曲线及私有Graph detail被排除。Graph兼容记录results为空数组，状态BLOCKED。
