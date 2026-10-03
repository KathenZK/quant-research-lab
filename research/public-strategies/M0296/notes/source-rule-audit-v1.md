# M0296 SMACrossover 独立源码规则审计 v1

## 身份与范围

固定来源：[模块](https://github.com/jesse-ai/example-strategies/blob/7c91e0a37bf62165790120d730442e4f6eb00364/SMACrossover/__init__.py)；commit `7c91e0a37bf62165790120d730442e4f6eb00364`；原字节SHA256 `453440d7b934c494934a1c56b3826d94638594f79ad4e4c7faaff36b96d33fae`，1809字节。MIT核验通过。固定Lab读取commit `b891d5dbd734fe3bc71866d2e0a2e3d46956bc25`，输出契约只允许此批四ID；两条.cursor规则与前次handoff逐字节一致；AGENTS仅前次本地副本多一个尾换行，无实质规则差异。原11字段保存在相邻artifacts，未经改写。

阶段 SOURCE_RULE_DEDUP_AUDIT_ONLY。行情请求0，历史回测0，原生Jesse/Rust运行0，源码文件仅文本/AST解析，没有import/exec第三方代码。已有主表只读比较不扩展新策略执行。

## 可执行规则与原文差异

- 源码 fast_sma/slow_sma 分别传50与200；参考SMA默认close。should_long/should_short只比较当前 >/<，没有前根比较，故叫“Crossover”不等于交叉事件。持续上方且空仓时仍满足多头资格；相等时两边均不成立。退出同样是反向状态，不须发生新cross
- 主表保留“加密现货”原文，但代码有 go_short。所核Jesse参考 _check 在spot且 should_short=True时抛InvalidStrategy；不能静默投影成现货仅多
- go_long/go_short均按完整balance与price调用size_to_qty(fee_rate=当前费率)，不是固定95%预算。参考实现扣3倍fee_rate后向下保留3位数量；fee buffer不是全部实扣交易成本。fee_rate数值、交易所精度、借币/资金费与保证金未知
- should_cancel_entry=False；没有源码stop_loss/take_profit。持仓时update_position请求liquidate。参考_check先更新持仓并模拟已排市场退出，再在flat/无入场单时检测信号，允许同次执行进入另一方向；这不是原作者撮合证据，也没有擅自加一根延迟
- 模块与固定源仓树无路由配置；原作者使用周期、symbol、spot/futures与warmup不明。别名URL提到15分钟不构成该Jesse模块路由证据，更不能补成4h

## 因果与核验边界

自身信号只取当前可见candles的尾窗50/200，无未来索引。充分历史及已收盘bar是假设输入条件；实时未完成bar、信号价与成交价的先后仍由引擎/路由决定。自写合成覆盖严格边界、持续state≠cross、双向退出、NaN与Decimal算术，不执行Jesse/Rust，不验证实际成交或盈利。参考SMA由Rust计算，未核对wheel逐位一致性。

## 固定参考边界

Jesse [固定commit](https://github.com/jesse-ai/jesse/tree/417f8765225e3bfc12043d4b712f19fe15a3c078)；Rust [固定commit](https://github.com/jesse-ai/jesse-rust/tree/65e1007faf1804ca66651bc76cccd3feb80a0d6d)。它们晚于策略最初开发且未被认定原runtime。Python/Rust精确文件hash在来源清单；同源版本字符串不能证明wheel二进制等同。费用数值、路由与实际委托契约没有替作者决定。

## 重复、相关与不同

在经hash核验的6973行做exact source_url/name/rule文本扫描；本source_url仅匹配本ID。候选regex及所有候选ID可复核，逐项人工比较范围见dedup JSON；不声称6973语义穷举去重。下面置信度指所述关系，非收益相关性。

- M0089：RELATED_RULE_FAMILY_NOT_VERIFIED_DUPLICATE，置信high。50/200 SMA相关；M0089日线标普仅多并用cross事件，此处多空state且路由未定
- M0920：RELATED_RULE_FAMILY_NOT_VERIFIED_DUPLICATE，置信medium。50/200多空接近，但M0920定义SPY日线cross即时反转；本源state/路由/余额精度不同，另一完整实现未核
- M0686：RELATED_RULE_FAMILY_NOT_VERIFIED_DUPLICATE，置信high。另有日线/基础1h、EMA过滤与前低1%卖出，本源无这些条件
- M0293：DISTINCT_VERIFIED_DEFINITION，置信high。已核固定Lab规格为EMA8/21事件+高周期SMA50、仅多；不是50/200 SMA多空state

本批四源不同SHA/AST；SMA状态、BB+云、RSI跨阈与Turtle通道/callback核心不同。相同关键词/参数不能抹平时间对齐、方向、仓位或撮合区别。结论：保留原ID；没有确认可自动合并的exact duplicate。

## 实际证据计数

本ID自写合成case 8，合批65；合批AST/参考静态检查30；另独立静态/Decimal复审25（部分重复验证，不能相加成新策略运行）。所有合成/静态项PASS不等于原生策略运行PASS，不等于原runtime复现或盈利。公开结构中tested_variants=0、strict_reproductions=0、implementation为空。

## 缺失依赖与后续门槛

- 原作者Jesse版本、其依赖/平台/配置/路由未提供
- 实际交易所、具体标的、市场类型、合约乘数、费用/滑点/资金费及借币成本未冻结
- 挂单/部分成交/精度/最小下单量、时钟与撮合版本未冻结
- 没有真实行情、历史收益或净值/交易记录；不得以合成PASS宣称策略有效或严格复现
- catalog现货标签与源码做空冲突，禁止静默改仅多
- TradingView别名未另核源码/周期，不能借别名15m替代该模块路由

若今后获历史执行授权，须先固定原runtime或明确标注参考实现假设，解决上述具体差异，冻结市场/周期/成本/撮合/数据证据，再进行独立恢复与历史核验。本审计没有提前修规则、迁移指标库、补新周期或开始市场请求。
