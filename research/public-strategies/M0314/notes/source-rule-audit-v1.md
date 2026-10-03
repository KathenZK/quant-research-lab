# M0314 TurtleRules 独立源码规则审计 v1

## 身份与范围

固定来源：[模块](https://github.com/jesse-ai/example-strategies/blob/7c91e0a37bf62165790120d730442e4f6eb00364/TurtleRules/__init__.py)；commit `7c91e0a37bf62165790120d730442e4f6eb00364`；原字节SHA256 `35e4c3cd69010ca81402277693cb6f7deaf52a284153f20f25d4cf605701408a`，8142字节。MIT核验通过。固定Lab读取commit `b891d5dbd734fe3bc71866d2e0a2e3d46956bc25`，输出契约只允许此批四ID；两条.cursor规则与前次handoff逐字节一致；AGENTS仅前次本地副本多一个尾换行，无实质规则差异。原11字段保存在相邻artifacts，未经改写。

阶段 SOURCE_RULE_DEDUP_AUDIT_ONLY。行情请求0，历史回测0，原生Jesse/Rust运行0，源码文件仅文本/AST解析，没有import/exec第三方代码。已有主表只读比较不扩展新策略执行。

## 通道与原文所称系统

- before()每根硬设S1、entry20、exit10、ATR20、倍数2、unit_risk_percent1、最大层4、阈0.5。注释出现S2/55不是可用的S2参数化路径；只改vars后下一before会覆写
- 固定参考donchian非sequential模式取candles[-period:]，含当前根。entry_signal先high≥upper给entry_long，elif low≤lower才entry_short。因此“突破”含相等，并且同根两边触及优先多头；不能默默改成前一根通道或严格>
- exit_signal也先high≥upper返回exit_short，再elif low≤lower返回exit_long。同棒两侧触及会抑制多头的exit_long分支；反向entry同样high优先，故不能写成两方向独立OR
- 评论称“20日/10日”，实际长度是路由bar计数，没有固定日线/4h路由。主表现货标签与源码双向及参考spot guard冲突

## 风险、加仓与计数

- quantity=(1%×balance)/(ATR20×dollars_per_point)，默认乘数1；止损距2×ATR。因而单初始单位无滑点无费的名义止损损失是2%余额，不是1%。不是按2ATR距离反推的1%总风险，也无名义仓位/保证金cap、fee buffer、ATR=0/NaN显式保护
- 理想常ATR/余额、以0.5ATR间隔满加到4单位且止损距最后价2ATR时，四单位到共同止损的风险算例是5%原余额；这里只是算术fixture，不是组合风险上限、实际收益或承诺
- go_long/go_short在下单赋值时即增加层数并记录last_opened_price，未等成交。新增仓callback又加层、记self.price并按abs(position.qty)重设整体SL。所以层数不是已证fill单位；参考go_long在filters之前调用，S1拒绝时可先留下自定义计数副作用，框架_reset未清这些自定义属性
- 追加需要价严格超last_price±0.5×当前ATR，等于不加。每次update最多提交一次，跳涨不补所有跳过层。on_increased_position止损没有max/min保护，ATR变大可能把旧止损放宽；并且update先考虑追加后考虑离场，两条件同根成立时的订单抵消依赖引擎

## skip-profit与callback修正链

1. 源模块不直接赋take_profit，last_was_profitable只在on_take_profit置True；S1_filter消耗标记一次后立即False。不能只凭“没设置TP”就判跳过逻辑死代码，因为框架liquidate可能生成TP
2. 所核参考Strategy.liquidate在pnl>0时确实设置take_profit，否则stop_loss。但正PnL→TP并不证明旧on_take_profit被派发
3. 同一固定参考的_on_updated_position只分派open/close/increased/reduced；_on_close_position调用新的on_close_position(order,closed_trade)，在所核路径没有旧on_take_profit/on_stop_loss。因此此参考dispatch下没有证据支持盈利标记和止损层数归零由旧hooks达成。全仓库搜索零只是补充，未当完备证明
4. 原作者运行时代未知，不能据现代参考断言当年一定失败，也不能静默修到新callback。即使旧hook可达，S1_filter跳的是下一次资格检查，不模拟经典海龟“跳过的突破仍虚拟跟踪是否盈利”的完整机制；按订单类型触发也不等于已净扣费用盈利

## 因果限制

通道用已见当前高低，无未来值；但当根极值可能先于close形成。源码按self.price下单不能当成历史在突破价成交。ATR每次重算、callback实时价、单棒双侧触及都依赖路由与撮合；合成只验证局部分支与金额，不算原策略复现。

## 固定参考边界

Jesse [固定commit](https://github.com/jesse-ai/jesse/tree/417f8765225e3bfc12043d4b712f19fe15a3c078)；Rust [固定commit](https://github.com/jesse-ai/jesse-rust/tree/65e1007faf1804ca66651bc76cccd3feb80a0d6d)。它们晚于策略最初开发且未被认定原runtime。Python/Rust精确文件hash在来源清单；同源版本字符串不能证明wheel二进制等同。费用数值、路由与实际委托契约没有替作者决定。

## 重复、相关与不同

在经hash核验的6973行做exact source_url/name/rule文本扫描；本source_url仅匹配本ID。候选regex及所有候选ID可复核，逐项人工比较范围见dedup JSON；不声称6973语义穷举去重。下面置信度指所述关系，非收益相关性。

- M0179：RELATED_RULE_FAMILY_NOT_VERIFIED_DUPLICATE，置信high。catalog为1h入10/出30/ATR15且账户停机规则；不同参数及控制
- M0232：RELATED_RULE_FAMILY_NOT_VERIFIED_DUPLICATE，置信high。固定Lab来源审计明确N1/N2/ATR与完整代码未知，不能默认20/10或确认为同源
- M0354：RELATED_RULE_FAMILY_NOT_VERIFIED_DUPLICATE，置信high。catalog含S1/S2与2%单位风险；本源before固定S1且1%/ATR sizing
- M0691：RELATED_RULE_FAMILY_NOT_VERIFIED_DUPLICATE，置信medium。catalog为OKX现货日线，通道长度未给；不能推定为20/10相同实现
- M1391：RELATED_RULE_FAMILY_NOT_VERIFIED_DUPLICATE，置信high。catalog双通道20/20、offset20、close cross与10exit；不是当前high/low inclusive分支
- M1938：RELATED_RULE_FAMILY_NOT_VERIFIED_DUPLICATE，置信medium。20/10/ATR20×2/1%文字最接近，但挂突破stop入与本源信号后self.price下单、1%/ATR与真实止损风险、pyramid/skip/callback需完整另一源才能确认；本轮未取其完整实现
- M2485：RELATED_RULE_FAMILY_NOT_VERIFIED_DUPLICATE，置信high。catalog含快20/10+慢55/20、前棒通道与pyramiding5；本源S1 current-inclusive且层数4
- M2599：RELATED_RULE_FAMILY_NOT_VERIFIED_DUPLICATE，置信high。catalog五ETF仅多、风险仓位与等权上限取小；本源多空、无名义上限
- M2704：RELATED_RULE_FAMILY_NOT_VERIFIED_DUPLICATE，置信high。catalog默认仅多、close比前棒通道并ATR追踪；本源high/low当前通道与特殊callback
- M0270：RELATED_RULE_FAMILY_NOT_VERIFIED_DUPLICATE，置信high。同Jesse库catalog写前一根Donchian收盘cross+SMA200仅多，非本源high/low优先分支+加仓

本批四源不同SHA/AST；SMA状态、BB+云、RSI跨阈与Turtle通道/callback核心不同。相同关键词/参数不能抹平时间对齐、方向、仓位或撮合区别。结论：保留原ID；没有确认可自动合并的exact duplicate。

## 实际证据计数

本ID自写合成case 20，合批65；合批AST/参考静态检查30；另独立静态/Decimal复审25（部分重复验证，不能相加成新策略运行）。所有合成/静态项PASS不等于原生策略运行PASS，不等于原runtime复现或盈利。公开结构中tested_variants=0、strict_reproductions=0、implementation为空。

## 缺失依赖与后续门槛

- 原作者Jesse版本、其依赖/平台/配置/路由未提供
- 实际交易所、具体标的、市场类型、合约乘数、费用/滑点/资金费及借币成本未冻结
- 挂单/部分成交/精度/最小下单量、时钟与撮合版本未冻结
- 没有真实行情、历史收益或净值/交易记录；不得以合成PASS宣称策略有效或严格复现
- 原作者legacy callback reachability未知；现代所核dispatch不支持上述旧hook
- 盈利后跳过是下一次过滤器调用而非完整虚拟突破交易；不得补成经典海龟规则
- 最初1%是每1ATR金额单位；2ATR初始名义风险2%，非完整组合最大亏损1%
- S2仅注释，无before可持续配置S2/55代码路径；不改周期/模式
- 挂单失败、过滤拒绝、停损回调缺失与partial fill可能使层数偏离成交单位；ATR变化可能放宽止损

若今后获历史执行授权，须先固定原runtime或明确标注参考实现假设，解决上述具体差异，冻结市场/周期/成本/撮合/数据证据，再进行独立恢复与历史核验。本审计没有提前修规则、迁移指标库、补新周期或开始市场请求。
