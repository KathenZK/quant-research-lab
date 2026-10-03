# M0304 Strategy002：源码复核、合成证据和输入阻塞

## 1. 当前结论

本条目没有历史收益、交易账本、净值曲线或策略绩效结论。首个官方数据请求在 2026-10-03 12:17:23.507340Z 遇到 `Tunnel connection failed: 403 Forbidden`，不是已证实的 Binance origin HTTP 状态。实际恢复完整源对象 0、规范输入未发布，本地完整 raw QA 未通过、独立 raw rebuild 未完成。过程退出码 UNKNOWN，不能冒充已正常结束。失败证据原字节保留；截至本报告，新增同源有限重试授权由整合方负责，尚未改变本条目的数据门禁。

## 2. 来源和身份

- 稳定 ID：M0304，Strategy002；主表 quant-master-draft.csv 的含表头物理第 305 行，主表 SHA256 15cc0ecbcb23261e3cd7f2fb0851815daed59951090d9ce3e759ef224ea6f415
- 作者标注 Gerald Lonlas；原仓库 [freqtrade/freqtrade-strategies 固定源码](https://github.com/freqtrade/freqtrade-strategies/blob/f3340ce11f5bdf62f598522e64d1f5638eaa13f5/user_data/strategies/Strategy002.py)
- 原文件 4363 bytes；SHA256 d1ca86a4ceb68ef828b35490ce1112330dad209cc3bb1e1b6c303c21ab3d8a90；经 GitHub 连接器取回并仅用文本/AST 审查，未执行第三方原代码
- Lab 工作基线 48851ef54b5fba6fef1da6825983864e1665fe1e；继承输出合同创建时旧 base 单独保留，未改写
- 原作者交易品种池、成本、账户配置和当年实际运行时 UNKNOWN。同目录没有 Strategy002.json 仅证明固定仓库目录的缺席，不证明作者机器不存在覆盖

## 3. 精确规则

所有条件为严格不等式；NaN 不触发。

入场：RSI(close,14)<30，STOCH 的 slowK<20，典型价 BB(20,2) 下轨>close，CDLHAMMER==100，四项同时满足。

退出信号：SAR>close 且 Fisher RSI>0.3。Fisher 输入为 0.1×(RSI−50)，输出为 (exp(2x)−1)/(exp(2x)+1)。不额外添加成交量信号条件；未来 raw QA 必须另行拒绝非正成交量。

- STOCH 为 TA-Lib 默认 fastK=5、slowK=3/SMA、slowD=3/SMA，仅取 slowK。RSI 为 Wilder 14；SAR acceleration=.02、maximum=.2；CDLHAMMER 使用已固定 TA-Lib C 库默认蜡烛设置
- BB 的典型价=(high+low+close)/3，窗口20、min_periods=1，样本标准差 ddof=1；第一根标准差为 NaN，第二根已经可算。不是 close 输入，不是 ddof=0，也不是强制满20根
- 全部原类属性另存 AST 明细。INTERFACE_VERSION=3，process_only_new_candles=true，use_exit_signal=true，ignore_roi_if_entry_signal=false；informative_pairs 返回空
- ROI 阶梯：持仓分钟 [0,20) 为5%，[20,30) 为4%，[30,60) 为3%，60以后1%；固定 stoploss=-10%
- trailing_stop=false。trailing_stop_positive=.01 和 offset=.02 为闲置属性，不启用 trailing
- 原类型 entry/exit=limit，stoploss=market，stoploss_on_exchange=false

参考框架固定为 freqtrade@1f394eaebc2f46a83d26971388628707802f8602；其 qtpylib 指标转导向 technical 1.7.0，本次解析到 commit c3fc191961cb20e3c6cb9d8de8866a983dc340d7。只借此核默认与覆盖次序，不声称复现原作者运行时。优先级为外部 runtime 配置、sidecar 特殊参数、原类属性、框架默认；本研究方案明确不加载 sidecar、不覆盖原策略参数。缺省 exit_profit_offset=0、GTC、startup_candle_count=0 是参考语义，并单独明示。

## 4. 最重要的执行假设

当前仅写成事前方案，没有完整执行/账本引擎，不能以合成公式通过代替执行 C0。

计划本金100000 USDT，单一无杠杆多仓，含手续费预算95%；每边基础手续费8bp，滑点2bp。entry/exit 限价为已闭合信号 bar 的 close，GTC 单个5m bar 超时。限价允许触及全额成交、忽略队列/部分成交/交易所精度，这是未证明的可交易性假设。

必须保留 exit_profit_only=true：在执行 bar 开盘、挂出退出限价之前，以观测 open 报价 q 检查 q×(1−退出费率)/(入场成交价×(1+入场费率))−1 > 0。严格大于0，分母含入场费用。只检查指标退出，不阻止 stop/ROI。通过后不按最终成交重新筛选；报价与成交间滑点仍可能造成净亏成交，不能偷偷改成事后保本条件。

计划以诊断 O-L-H-C 路径处理 bar 内顺序；开盘 stop gap 优先于 signal limit，再 ROI；升段按首次触及，等价位信号优先。该顺序与参考框架原序列有差异，因此 HYPOTHESIS。新入场仅暴露于余下路径，同 bar 出场后不重入。intrabar 时间仅给 bar 内区间，不伪造 tick 时间。

入场 open 成交从 open 计龄；intrabar 成交保守从 bar close+1ms 起计龄。每个 bar open 冻结 ROI 阶梯，避免提前使用未来分钟边界。止损为入场价×0.9；退出盈利门控不得对其生效。期末按最后 close mark，不强平、不扣不存在的平仓费。

## 5. 预注册配置、窗口和指标

四个计划配置：base(8bp,delay1)、fee0(0bp,delay1)、fee20(20bp,delay1)、delay2(8bp,delay2)。另计划同窗 buyhold：首个评估 open 市价买入，95%含费预算、2bp滑点、8bp费用，期末 mark。实际上述配置/对照均未运行，不能计作4+1完成。

输入期望2023-12-01至2025-01-01 exclusive，114336根原生5m；前8928根仅预热，评估2024年105408根。窗口因更早2023 raw QA失败而按可用性事前选择，不是 OOS，不能直接和旧两年总收益比较。历史窗口既有曝光次数 UNKNOWN，不能算可信DSR/PBO。

未来 MDD 必须从全部5m close净值和初始本金计算 running peak，不能从日采样曲线重算；该值仍不是 intrabar MDD。年化以366天窗口与365日年基准计算。日Sharpe以UTC日末收益、样本标准差ddof1、sqrt365、rf0；5m Sharpe另行区分。

## 6. 已完成和未完成证据

已完成：固定源码 bytes/hash、全部原类属性核对、参考优先级与默认核对、19项合成公式检查。2400根合成 bar 上3个精确前缀和3个未来扰动测试通过；严格入/出边界、BB初始化、费用后盈利门槛、ROI分钟边界通过。有限样本测试不是一般性无前视证明。原第三方代码未执行。

独立复核：另外6000根自造bar经手写标量oracle对照全部指标/信号一致，36个合成入场、432个合成退出。标量实现与库实现的最大BB误差约6.11e-11，布尔信号完全一致；另有独立Decimal费用门槛边界核验。这是公式/helper审核，不是完整交易账本核验。详见[独立公式回执](../artifacts/independent-formula-audit.json)。

未完成：市场输入恢复/逐行QA、真实信号、完整订单状态机、交易/费用/净值账本、独立Decimal交易账本核验、历史收益、市场数据独立恢复、最终执行C0。不得写成失败策略或成功策略，更不进入 runner。

## 7. 后续门禁

仅在授权访问恢复后，完成固定39对象校验、全114336行QA、同环境独立字节一致重建，再完成明确执行引擎、合成成交/边界审计、独立C0审核与负责人明确运行授权。计划变更和新证据追加版本，当前403与所有已冻结证据保留。公开包不包含原始行情、长净值、第三方全文代码、Library身份或私人Graph内容。
