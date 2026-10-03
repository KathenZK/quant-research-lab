# M0299 SimpleBollinger 独立源码规则审计 v1

## 身份与范围

固定来源：[模块](https://github.com/jesse-ai/example-strategies/blob/7c91e0a37bf62165790120d730442e4f6eb00364/SimpleBollinger/__init__.py)；commit `7c91e0a37bf62165790120d730442e4f6eb00364`；原字节SHA256 `746cc0f8644a7fae12089f597448b573d4d482a3855c870d18b4a7bfeb0a5255`，1683字节。MIT核验通过。固定Lab读取commit `b891d5dbd734fe3bc71866d2e0a2e3d46956bc25`，输出契约只允许此批四ID；两条.cursor规则与前次handoff逐字节一致；AGENTS仅前次本地副本多一个尾换行，无实质规则差异。原11字段保存在相邻artifacts，未经改写。

阶段 SOURCE_RULE_DEDUP_AUDIT_ONLY。行情请求0，历史回测0，原生Jesse/Rust运行0，源码文件仅文本/AST解析，没有import/exec第三方代码。已有主表只读比较不扩展新策略执行。

## 可执行规则与默认参数

- docstring明写1h；本模块未强制路由，不可改写为4h。仅多；close严格高于BB上轨，同时filters要求close严格高于span_a和span_b。代码是状态门，不要求刚刚上穿
- 源码BB只显式传source_type="hl2"。固定Jesse参考defaults为20、devup=devdn=2、matype=0、devtype=0，hl2由(high+low)/2取得。Rust标准分支用总体方差sum_sq/n−mean²，无max(var,0)钳制；浮点相消时可能NaN，审计没有静默数值修正。其他库sample std、typical price或hl2误作(open+close)/2均不等价
- 出场是close严格低于BB中轨，不是docstring提及的可替换下轨。原文“best results”没有运行证据，本次不将其当结论
- size_to_qty按全部balance、当前price与fee_rate；参考默认precision3，扣3倍费率buffer。should_cancel_entry=True只对已有未成交entry/flat时取消，不等于持仓每根平仓；参考go_long先准备buy再filters，未通过不会提交。close-price订单在所核参考near-price分支被当市场订单，实盘/其他版本成交未知

## 一目云对齐与因果

- 单独pin参考Jesse 417f876…与jesse-rust 65e1007…（Cargo1.3.0，Python依赖同为1.3.0），不冒认原作者环境或发布wheel
- Python wrapper默认9/26/52/displacement26；不足80根返回全NaN，超过80根只看末80
- 已读Rust src/trend.rs 12–63：先删除末(displacement−1)=25根，然后用9/26/52高低中点形成spanA/B；当前转换/基准线另用末9/26。对于决策t，span窗口截止t−25，不是泛称shift26。80根例子spanB输入索引3..54，spanA用46..54与29..54
- 因为span只依赖过去至t−25，当前云过滤在该参考公式下无未来读取。自写索引与Decimal oracle在80/81/100/200长度、79不足、未来suffix与最后25根扰动上核验；没有执行原Rust，不能说跨库/原runtime逐值一致。原runtime未知，因此严格因果与复现总状态仍未建立

## 固定参考边界

Jesse [固定commit](https://github.com/jesse-ai/jesse/tree/417f8765225e3bfc12043d4b712f19fe15a3c078)；Rust [固定commit](https://github.com/jesse-ai/jesse-rust/tree/65e1007faf1804ca66651bc76cccd3feb80a0d6d)。它们晚于策略最初开发且未被认定原runtime。Python/Rust精确文件hash在来源清单；同源版本字符串不能证明wheel二进制等同。费用数值、路由与实际委托契约没有替作者决定。

## 重复、相关与不同

在经hash核验的6973行做exact source_url/name/rule文本扫描；本source_url仅匹配本ID。候选regex及所有候选ID可复核，逐项人工比较范围见dedup JSON；不声称6973语义穷举去重。下面置信度指所述关系，非收益相关性。

- M2339：RELATED_RULE_FAMILY_NOT_VERIFIED_DUPLICATE，置信high。虽一目9/26/52及BB20/2相近，catalog写close源、下轨cross、TK/迟行条件与多空；此处hl2上轨state、仅多、中轨退
- M1394：RELATED_RULE_FAMILY_NOT_VERIFIED_DUPLICATE，置信high。另一catalog为一目18/52/104/52双向云突破，未见BB上轨门；非同一参数/退出核
- M0316：DISTINCT_VERIFIED_DEFINITION，置信high。已核Lab规格是RSI10+EMA5/10同步cross+ADX25；其命名hl2实际(open+close)/2，不是本源Jesse hl2

本批四源不同SHA/AST；SMA状态、BB+云、RSI跨阈与Turtle通道/callback核心不同。相同关键词/参数不能抹平时间对齐、方向、仓位或撮合区别。结论：保留原ID；没有确认可自动合并的exact duplicate。

## 实际证据计数

本ID自写合成case 16，合批65；合批AST/参考静态检查30；另独立静态/Decimal复审25（部分重复验证，不能相加成新策略运行）。所有合成/静态项PASS不等于原生策略运行PASS，不等于原runtime复现或盈利。公开结构中tested_variants=0、strict_reproductions=0、implementation为空。

## 缺失依赖与后续门槛

- 原作者Jesse版本、其依赖/平台/配置/路由未提供
- 实际交易所、具体标的、市场类型、合约乘数、费用/滑点/资金费及借币成本未冻结
- 挂单/部分成交/精度/最小下单量、时钟与撮合版本未冻结
- 没有真实行情、历史收益或净值/交易记录；不得以合成PASS宣称策略有效或严格复现
- 同版本Rust源码参考不证明发布wheel二进制一致；未执行原指示器
- 不能将其他库shift26的span直接套用；若换库须逐值/边界验证
- 原文best results无冻结样本/成本/运行证据，未采信收益主张

若今后获历史执行授权，须先固定原runtime或明确标注参考实现假设，解决上述具体差异，冻结市场/周期/成本/撮合/数据证据，再进行独立恢复与历史核验。本审计没有提前修规则、迁移指标库、补新周期或开始市场请求。
