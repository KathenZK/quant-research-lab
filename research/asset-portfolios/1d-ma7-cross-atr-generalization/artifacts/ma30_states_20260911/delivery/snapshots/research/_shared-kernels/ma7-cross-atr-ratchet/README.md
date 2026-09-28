# MA7穿越、候选等待与ATR单向止损内核

## v5：MA30区分防守与延伸，2026-09-11

[v5说明](v5/README.md) · [冻结清单](v5/manifest.json)。引擎SHA256：`f98eb0fb30ffe388e6e55d7535619d8dd8f0edb47c4efe864e5d61f8b7ef1a3f`。新增默认关闭的MA30持仓状态，逆向受压才额外防守、同向有浮盈才允许健康延伸及加速观察；原空单RSI提前止盈仅在明确延伸状态暂缓，离开后恢复。双向止损和ATR倍数不能放宽，多个触发同日最多收紧一次；28项针对性测试通过，关闭时保留v4原字段行为。

唯一消费方BIN-1D-MA7-CAR-GEN通过[独立pin](../../asset-portfolios/1d-ma7-cross-atr-generalization/specs/ma30-states-engine-pin-20260911.json)加载。九方案8,586账户及16,226个同入场比较全部核验；[结果与反例](../../asset-portfolios/1d-ma7-cross-atr-generalization/diagnostics/ma30-states-results-20260911.md)。MA30管理有局部改善，仍未达到全市场长期盈利；共享v5不是正式策略V5，V1/V2/V3不变，已固定引擎不得原地修改。

## v4：按闭合日条件准入、整笔退出方式固定，2026-09-11

[v4说明](v4/README.md) · [冻结清单](v4/manifest.json)。引擎SHA256：`956698aeda487c849eabe2eda2109397098e4a1edc4d689e5e69ebaf8bc47aa8`。增加六个严格日程字段控制原合格穿越的准入与退出方式；已开仓路线不随模型日期改变。默认关闭保持v3旧行为；新准入63项、学习30项、旧状态机93项检查通过。

唯一新增消费方为BIN-1D-MA7-CAR-GEN，按[独立pin](../../asset-portfolios/1d-ma7-cross-atr-generalization/specs/adaptation-engine-pin-20260911.json)加载。4,770连续账户及146条学得条件见[本轮报告](../../asset-portfolios/1d-ma7-cross-atr-generalization/diagnostics/adaptation-learning-results-20260911.md)。代码v4不是正式策略V4；正式V1/V2/V3不变，源码固定后不原地修改。

## v3：退出状态机与固定入场回放，2026-09-10

[v3说明](v3/README.md) · [冻结清单](v3/manifest.json)。引擎SHA256：`31549725a5384303415763c05cb4cb91446e0682f88b519c95f815ef239778b2`。增加防守、健康暂停、加速延伸观察和持续保护，以及同入场同数量的退出对照；93项针对性检查通过，旧默认字段保持兼容。历史日历报告另有1项边界检查通过。

消费方通过[独立pin](../../asset-portfolios/1d-ma7-cross-atr-generalization/specs/exit-state-engine-pin-20260910.json)加载，明确传入用户新费用。结果与完整交易路径见[退出状态机报告](../../asset-portfolios/1d-ma7-cross-atr-generalization/diagnostics/exit-state-machine-results-20260910.md)。本轮未得到全市场普遍盈利的新策略，代码v3不代表用户策略V3或正式V4；已固定源码禁止原地修改。


## v2：四项独立验证，2026-09-10

[v2说明](v2/README.md) · [冻结清单](v2/manifest.json)。引擎SHA256：`0d2aace099849a717da9702f129c262302746c6d547e594bedaf90b04a0b99dc`。新增方向限制、MA30入场过滤、含费用的止损风险仓位，以及新高低刷新后重新等待收紧；新字段默认值保留v1计算。86项合成测试通过，没有重跑旧真实市场策略。

消费方仍为BIN-1D-MA7-CAR-GEN的[四项验证runner](../../asset-portfolios/1d-ma7-cross-atr-generalization/scripts/run_four_tests_20260910.py)，通过[独立pin](../../asset-portfolios/1d-ma7-cross-atr-generalization/specs/four-tests-engine-pin-20260910.json)加载。这里v2是共享代码版本，不是用户正式命名的策略V2；正式V1/V2/V3策略规则不变。

## v1：原全市场四方案，保持冻结

`v1/engine.py` 来源于冻结的HYPE-1D-MA7-CAR R4引擎，保留原止损/成本/日小时执行，新增失败斜率穿越的有限等待，并将重复的日线索引预计算。旧HYPE各轮不迁移、不改写。

- v1 SHA256：`54f559748b557c81ec21ca53e4f30e09264547e5d0e8cb658716e33cf2f8d72b`。
- 原R4 SHA256：`feb82e01e0b63a55a64c549b1f51bc581b86b9d83e08f77a507681184beec50a`。
- 唯一新消费方：[BIN-1D-MA7-CAR-GEN](../../asset-portfolios/1d-ma7-cross-atr-generalization/README.md)，通过common.py固定SHA加载。
- 等待0保留原行为；等待2/3使用仍在同侧、斜率严格过线、收盘越过原穿越收盘三个条件，首次满足次日成交。详见[消费方规格](../../asset-portfolios/1d-ma7-cross-atr-generalization/specs/contract-p1-20260909.md)。
- 54个新合成测试及原R2/R3/R4共169项通过；多组原5份输出旧字段逐值完全一致。合成433天运行时间由约0.46秒降至0.062秒，性能差异不作为策略收益证据。

此版本已被SHA引用，禁止原地修改；修正需新版本。结果、输入及图表均由消费方保管。
