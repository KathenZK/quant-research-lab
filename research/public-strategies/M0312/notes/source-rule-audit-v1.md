# M0312 TradingView_RSI 独立源码规则审计 v1

## 身份与范围

固定来源：[模块](https://github.com/jesse-ai/example-strategies/blob/7c91e0a37bf62165790120d730442e4f6eb00364/TradingView_RSI/__init__.py)；commit `7c91e0a37bf62165790120d730442e4f6eb00364`；原字节SHA256 `86a0532e427cfe3b4f3ff9fa94c7d007ffb544c96db7fa20613b7ebf724d2769`，1764字节。MIT核验通过。固定Lab读取commit `b891d5dbd734fe3bc71866d2e0a2e3d46956bc25`，输出契约只允许此批四ID；两条.cursor规则与前次handoff逐字节一致；AGENTS仅前次本地副本多一个尾换行，无实质规则差异。原11字段保存在相邻artifacts，未经改写。

阶段 SOURCE_RULE_DEDUP_AUDIT_ONLY。行情请求0，历史回测0，原生Jesse/Rust运行0，源码文件仅文本/AST解析，没有import/exec第三方代码。已有主表只读比较不扩展新策略执行。

## 参数异常必须原样保留

源hyperparameters：rsi min10/max30/default5；stop_loss min0.5/max0.99/default0.95；take_profit1.1..1.2/default1.1；xparam60..90/default75。RSI默认5越界是源码事实，本审计保留5，不剪裁成10。

固定参考 _prepare_routes给外部HP/DNA优先，然后_init_objects在空HP时逐项直接注入default；所核普通路径没有range检查/剪裁，所以不能直接断言“默认5必然被引擎拒绝”。参考Optimize整数抽样在min..max，可能令优化域与默认运行域不一致。本次未运行这些代码，其他UI/API/历史版本验证行为未证明。

## 信号、仓位与执行

- RSI调用sequential=True。入场为前值≤35且现值>35；出场为前值≥75且现值<75，或前值≥10且现值<10。已经持续低于10不会单因低值再次触发cross；NaN比较不触发。未满足条件时should_long隐式返回None，参考if判定视为假
- 两处size_to_qty(balance,price,3,fee_rate=…)中的3在参考签名是precision，不是3倍杠杆。参考数量=floor(balance×(1−3×fee)/price,3小数)
- 额外要求qty>0且available_margin严格大于qty×price。fee0、恰好整除余额时严格等额会拒绝；fee buffer或向下舍入余数可能让同余额通过；已有占用保证金仍可能拒绝。已做Decimal两种边界交叉核验，不能用>=替换
- go_long按提交时self.price设stop=0.95×price、TP=1.1×price。不是按实际平均成交价重新计算；费用后净亏损也不恰好5%。在所核现代Jesse，spot模式禁止go_long直接设置SL/TP，故主表现货标签不能证明可直接运行；未搬到on_open_position修代码
- should_cancel_entry=False；long-only。参考_short-candle多单排序：红bar（open>close）先上后下，其他先下后上，故已同时激活的SL/TP双触顺序依赖短bar颜色；跳空/订单激活/撤单会另影响结果，不能简单宣称永远先止损。具体路由基础周期、真实tick路径、同棒新订单激活时刻仍未知

## 因果限制

crossed读取末两点，参考RSI Rust用截至当时的涨跌与Wilder递推；无未来索引。warmup、保留历史长度、NaN/平价序列及原RSI版本仍须固定。当前参考Rust平序列avg_loss=0会给100，不等于所有指标库。合成只对阈值/数量/排序公式，未执行原RSI或原引擎，不产生历史交易。

## 固定参考边界

Jesse [固定commit](https://github.com/jesse-ai/jesse/tree/417f8765225e3bfc12043d4b712f19fe15a3c078)；Rust [固定commit](https://github.com/jesse-ai/jesse-rust/tree/65e1007faf1804ca66651bc76cccd3feb80a0d6d)。它们晚于策略最初开发且未被认定原runtime。Python/Rust精确文件hash在来源清单；同源版本字符串不能证明wheel二进制等同。费用数值、路由与实际委托契约没有替作者决定。

## 重复、相关与不同

在经hash核验的6973行做exact source_url/name/rule文本扫描；本source_url仅匹配本ID。候选regex及所有候选ID可复核，逐项人工比较范围见dedup JSON；不声称6973语义穷举去重。下面置信度指所述关系，非收益相关性。

- M0322：RELATED_RULE_FAMILY_NOT_VERIFIED_DUPLICATE，置信high。另一catalog RSI14上穿35叠加SuperTrend、65空、1.5%/1%风控；此处RSI5/75/10/5%/10%
- M0588：RELATED_RULE_FAMILY_NOT_VERIFIED_DUPLICATE，置信high。另一catalog XOM RSI14上穿35，50退出并做空65；此处仅多、RSI5、75/10退出
- M2739：RELATED_RULE_FAMILY_NOT_VERIFIED_DUPLICATE，置信high。另一catalog 15m RSI14+BB下轨或TEMA支路，ROI/追踪完全不同；共享35不足去重
- M0316：DISTINCT_VERIFIED_DEFINITION，置信high。已核Lab规格RSI10与EMA同根交叉、50门槛和ADX；不同核心合取与风险规则

本批四源不同SHA/AST；SMA状态、BB+云、RSI跨阈与Turtle通道/callback核心不同。相同关键词/参数不能抹平时间对齐、方向、仓位或撮合区别。结论：保留原ID；没有确认可自动合并的exact duplicate。

## 实际证据计数

本ID自写合成case 21，合批65；合批AST/参考静态检查30；另独立静态/Decimal复审25（部分重复验证，不能相加成新策略运行）。所有合成/静态项PASS不等于原生策略运行PASS，不等于原runtime复现或盈利。公开结构中tested_variants=0、strict_reproductions=0、implementation为空。

## 缺失依赖与后续门槛

- 原作者Jesse版本、其依赖/平台/配置/路由未提供
- 实际交易所、具体标的、市场类型、合约乘数、费用/滑点/资金费及借币成本未冻结
- 挂单/部分成交/精度/最小下单量、时钟与撮合版本未冻结
- 没有真实行情、历史收益或净值/交易记录；不得以合成PASS宣称策略有效或严格复现
- 默认RSI5越界是原源码事实；保留5，不改10，不声称所有历史版本都会拒绝或放行
- 参考引擎spot禁止go_long中预设SL/TP；不能直接认作现货可运行
- 同根双触以参考短周期阴阳路径排序为模型；原运行与真实盘中路径未知

若今后获历史执行授权，须先固定原runtime或明确标注参考实现假设，解决上述具体差异，冻结市场/周期/成本/撮合/数据证据，再进行独立恢复与历史核验。本审计没有提前修规则、迁移指标库、补新周期或开始市场请求。
