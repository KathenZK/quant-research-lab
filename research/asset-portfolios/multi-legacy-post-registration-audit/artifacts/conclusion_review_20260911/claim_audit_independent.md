# 两轮策略结论独立文字审计（2026-09-11）

确有评价错误，不能只把Keltner的一行改成“优先研究”就结束。最明确的问题是：没有先说明评价目标，就把较小回撤当作总体优先级；被纠正后，又从收益第一直接推导优先级。另有几处把单段、整套版本的比较说成某项修改的作用或稳定效果，结论强于证据。

本次只检查父代理提供的逐字会话摘录、两轮已保存报告、14组配对和已有验收资料。没有新回测，也没有重新穷尽审计所有策略代码。下文说“成立”均只限于明示时间和模型；本次不能给“之前所有结论都正确”的保证。

## 可以保留的事实及其限制

- 共同窗口是2026-07-23 00:00至2026-09-05 15:00 UTC，44天15小时。开仓名义为当时权益的1倍，实际数量持有期间固定；不是单笔止损风险相同。每次成交手续费0.1%、基础滑点0.04%。收益加入已有资金费估计，回撤按K线收盘权益计算。
- 14组固定对照中，最终版收益7组提高、6组下降、1组相同；最终版盈利5组，早期对照盈利3组。排除资金费后，14组收益变化的方向均不变。这个计数既不能证明过拟合是主因，也不能排除它。
- Keltner在旧16个登记最终版主情景、新14个最终版统一1倍情景、新14个最终版保留原仓位情景中，终值收益均第一，分别为22.34%、1.71%、4.86%。这句在“最终版本”范围内正确；各起点、账户设定不同，且行情重叠，不是三次独立证实。
- EMA-X恢复基线本段18.47%及CC中期V21本段9.77%不属于上述最终版本排名。不能把“最终版本第一”省略成全仓库所有版本第一。
- 第一轮HYPE 15m MMTF确有RVOL使用48根而非96根的错误，旧−14.22%已经单独更正为−14.15%。不改变亏损方向，并不等于之前数字没错。

## 14组可复核的本段事实

|家族|早期→最终|早期收益|最终收益|早期收盘回撤|最终收盘回撤|交易数|
|---|---|---:|---:|---:|---:|---:|
|HYPE 15m EMA-X|V1→V18|+18.47%|-5.39%|18.88%|9.20%|11→3|
|HYPE 15m EMA-TB|V35→V41|-3.05%|-3.42%|8.63%|9.38%|19→21|
|HYPE 15m MII|V1→V1.4A|-5.63%|+0.78%|6.78%|4.33%|13→9|
|HYPE 15m TB+MII组合|V35+MII1.3→V2|-3.22%|-1.15%|8.63%|8.63%|23→24|
|BNB 1h AR|V1→V3|-4.24%|-4.53%|7.00%|7.28%|4→4|
|BTC 1h AR|V1→V4|-0.82%|+1.08%|2.99%|0.00%|5→1|
|ETH 1h AR|V1→V4|-3.04%|-1.08%|3.62%|4.32%|4→4|
|HYPE 15m MMTF|V1→V3|-3.60%|-4.71%|4.44%|5.54%|10→10|
|HYPE 1h AR|V1→V4|-6.05%|-1.19%|10.50%|4.70%|7→7|
|HYPE 1h MMTF|V1→V3|-1.30%|+1.07%|9.31%|4.40%|9→11|
|HYPE 30m Keltner|V2.1→V3|+1.71%|+1.71%|11.32%|10.39%|15→15|
|SOL 1h AR|V1→V3|+10.86%|+0.00%|0.85%|0.00%|4→0|
|TRX 1h AR|V1→V3|-1.64%|-3.05%|2.63%|3.54%|7→5|
|HYPE 15m 10/8反转|V10→V35|-6.60%|+0.52%|14.88%|12.06%|33→37|

“早期”不是14个家族都具有完整原始简单版身份。EMA-X完整V1退出规格缺失；EMA-TB主对照从V35起；ENS早期为明确冻结的诊断组合；CC最早完整规格为V10。CC V10本身已有过滤、冷却和ATR退出，不是裸10/8信号。

## 逐条审计

会话原句由父代理逐字提供，来源编号保存在同名JSON。这里没有把只见概述而无逐字文本的旧回复伪装成引语。

### C01 · REQUIRES_SEPARATION

> 我对这批策略的整体评价偏低：多数还停留在研究原型阶段，少数值得继续验证，目前没有一条已经证明值得投入实盘资金。

**判断类型：** subjective_preference、validation_scope。

整体评价偏低是意见，不是14组数值的统计结论；多数研究原型还带有全体策略成熟度判断，本次没有逐条审计生产或全部历史验收状态。

**应改为：** 本次完成的历史对照中，14个最终版本有5个在统一1倍情景盈利，证据不足以确认任何一个能在未见行情持续盈利。整体研究价值和投入顺序尚未按明确目标评定。

**仍不知道：** 各策略全部历史验证和实际生产状态；用户的收益、风险、研究投入目标。

依据：[diagnostics/iteration-comparison-20260911.md 第3行](../../diagnostics/iteration-comparison-20260911.md)。

### C02 · UNSUPPORTED_PRIORITY

> 表现一般，研究优先级不高｜赚1.71%，最大回撤10.39%；新增筛选没有提高这段最终收益

**判断类型：** subjective_preference。

把Keltner列为研究优先级不高，未说明评价目标；同表更低收益但更低回撤的MII/MMTF却获保留。低回撤偏好没有来自这轮用户的约束，不应当伪装成总体优劣。该意见的缺陷不是1.71或10.39写错。

**应改为：** Keltner V3在这14个最终版本的本段1倍情景中，终值收益最高，收盘回撤也较大。是否优先研究，要说明是在追求收益、较小回撤，还是查清某项改动的作用。

**仍不知道：** 相对收益与回撤的取舍规则。

依据：[diagnostics/iteration-comparison-20260911.md 第23行](../../diagnostics/iteration-comparison-20260911.md)；[diagnostics/iteration-comparison-20260911.md 第15行](../../diagnostics/iteration-comparison-20260911.md)。

### C03 · SUPPORTED_WITH_SCOPE

> 赚1.71%，最大回撤10.39%

**判断类型：** numeric_fact。

数值与保存的配对结果一致。必须保留共同时间、成本、1倍名义仓位和收盘回撤定义，不能解释为当前实盘收益或盘中最大损失。

**应改为：** 2026-07-23 00:00至09-05 15:00 UTC，每次开仓名义为权益1倍、单次手续费0.1%及滑点0.04%，加入现有资金费估计后，Keltner V3收益1.71%，按K线收盘权益计算的最大回撤10.39%。

依据：[diagnostics/iteration-comparison-20260911.md 第7行](../../diagnostics/iteration-comparison-20260911.md)；[diagnostics/iteration-comparison-20260911.md 第30行](../../diagnostics/iteration-comparison-20260911.md)。

### C04 · NARROW_FACT_SUPPORTED_BROAD_DISMISSAL_UNSUPPORTED

> 新增筛选没有提高这段最终收益

**判断类型：** numeric_fact、unsupported_inference。

统一1倍主情景下V2.1与V3终值收益相等，这句单独看成立；但它不能推出筛选没有价值、没有研究价值或两版完全一样。收盘回撤由11.32%降为10.39%，原仓位情景收益约4.88%对4.86%。

**应改为：** V3新增筛选在本段没有增加统一1倍终值收益；收盘回撤有所下降。这是收益与路径的局部结果，不能据此否定研究价值，也不能证明风险改善会延续。

**仍不知道：** 哪项筛选改变了哪些入场和风险路径；风险改善是否在独立样本保留。

依据：[diagnostics/iteration-comparison-20260911.md 第23行](../../diagnostics/iteration-comparison-20260911.md)；[diagnostics/iteration-comparison-20260911.md 第46行](../../diagnostics/iteration-comparison-20260911.md)。

### C05 · CRITERIA_NOT_DISCLOSED

> 可以保留，有限度继续验证

**判断类型：** subjective_preference。

有限度继续验证可以是研究建议；但与Keltner的低优先级并列时，没有统一、公开的选择依据，不能从较低回撤直接推导较高整体研究价值。

**应改为：** MII与HYPE 1h MMTF本段最终版都改善并盈利，分别约0.78%及1.07%；它们可作为待验证候选。候选名单和优先顺序属于根据已见结果作出的研究选择。

依据：[diagnostics/iteration-comparison-20260911.md 第15行](../../diagnostics/iteration-comparison-20260911.md)；[diagnostics/iteration-comparison-20260911.md 第22行](../../diagnostics/iteration-comparison-20260911.md)。

### C06 · UNSTATED_RISK_PREFERENCE

> 最值得继续核对的是 HYPE 15m MII V1.4A，以及未登记但规格明确的 HYPE 1h 多速度EMA预测。它们这段有利润且回撤比30m Keltner小，但目前样本时间仍短，不能因此认定长期有效。

**判断类型：** subjective_preference。

第一轮保存报告已经把更小回撤用作最值得研究的理由，且各策略开始日和部分账户模型不同。提醒样本短是正确的，但不能消除未说明目标的排序。

**应改为：** 这些策略在各自落档后窗口盈利，且记录的回撤比Keltner低；这提供不同的收益风险取舍。第一轮不同起点和模型下的结果不足以给统一优劣排序。

依据：[diagnostics/report-20260910.md 第32行](../../diagnostics/report-20260910.md)；[diagnostics/report-20260910.md 第5行](../../diagnostics/report-20260910.md)。

### C07 · RANK_CORRECTION_VALID_PRIORITY_STILL_CONDITIONAL

> 我之前过于看重回撤较小，把收益排名和风险偏好混在了一起。更准确的评价是：Keltner V3应当列为这批策略中优先继续验证的对象；它目前赚得最多，但承担的回撤也明显偏大。

**判断类型：** conditional_rank、subjective_preference。

纠正Keltner最高终值收益是必要的；但从收益第一直接改成应优先验证，仍未说明研究目标。评价意见可以给，但应标成按某个目标作出的判断。

**应改为：** 纠偏应撤回无明确依据的优先级。事实是Keltner在指定最终版本集合及指定情景中终值收益最高；是否优先验证不能只靠收益或只靠回撤决定。

**仍不知道：** 研究优先级的明确目标。

依据：[diagnostics/iteration-comparison-20260911.md 第23行](../../diagnostics/iteration-comparison-20260911.md)。

### C08 · SUPPORTED_WITH_STRICT_SCOPE

> 它在三种比较里都排第一

**判断类型：** conditional_rank。

三种数据表的第一名均属实：旧16个登记主情景，新14个最终版本统一1倍，新14个最终版本保留原仓位。若去掉最终版本限定就不成立，EMA-X早期和CC中期有更高收益；这三张表也不是三次独立验证。

**应改为：** 在这三个已指定的最终版本结果集合里，Keltner的终值收益均最高。旧窗口起点各不相同，新两情景共享行情，不能把三次排名当成三次独立证实或全仓库排名。

**仍不知道：** 跨家族统一、完整资金费和一致执行模型下的精确排名。

依据：[artifacts/all_results.json](../../artifacts/all_results.json)；[artifacts/iteration_comparison_20260911/all_results.json](../../artifacts/iteration_comparison_20260911/all_results.json)。

### C09 · SUPPORTED_WITH_SCOPE

> 7组最终版收益提高，6组下降，1组持平。但提高不一定代表赚钱，有些只是少亏。

**判断类型：** numeric_fact。

7/6/1及提高不一定赚钱均成立。计数来自预先指定的14组两端，统一1倍、本次共同窗口；14组共享市场，不是独立样本，也未按版本数量建立因果或统计模型。

**应改为：** 在这14个固定对照中，本段最终版收益7组提高、6组下降、1组相同，盈利数由3组变为5组。这个描述既不能证明版本多导致过拟合，也不能证明频繁迭代无害。

**仍不知道：** 版本搜索次数与后续退化的关系；市场状态变化、成本和规则修改各自的影响。

依据：[diagnostics/iteration-comparison-20260911.md 第3行](../../diagnostics/iteration-comparison-20260911.md)；[diagnostics/iteration-comparison-20260911.md 第5行](../../diagnostics/iteration-comparison-20260911.md)。

### C10 · RISK_HYPOTHESIS_NOT_CAUSAL_FINDING

> 对“是不是过拟合”，我的判断是：值得高度怀疑，但还不能把所有问题都归到它身上。

**判断类型：** unconfirmed_inference。

可以基于反复搜索历史行情提醒过拟合风险，但高度怀疑是定性判断，不是7/6/1测出的概率；后半句还不能把所有问题归到它身上，仍容易让读者误以为已确认过拟合解释了部分亏损。本次没有识别其实际贡献。

**应改为：** 大量历史试错会增加过拟合风险；本次整版对照不能判断哪些亏损由过拟合造成，也不能测出它是不是主要原因。

**仍不知道：** 搜索流程是否反复看验证样本；真正未见数据中的表现；过拟合对收益下降的实际贡献。

依据：[diagnostics/iteration-comparison-20260911.md 第5行](../../diagnostics/iteration-comparison-20260911.md)；[diagnostics/iteration-comparison-20260911.md 第83行](../../diagnostics/iteration-comparison-20260911.md)。

### C11 · SUPPORTED

> 这次没有证实“版本多就是主要病因”。

**判断类型：** evidence_limit。

没有证实版本多是主要病因，与本次研究设计及结果一致。它是没有得到证明，不等于已经证明不是主要原因。

**应改为：** 这次没有证实，也没有排除过拟合是主要原因。

依据：[diagnostics/iteration-comparison-20260911.md 第83行](../../diagnostics/iteration-comparison-20260911.md)。

### C12 · RULE_CAUSALITY_OVERSTATED

> 这次结果回答哪些修改在后续行情有帮助

**判断类型：** unsupported_inference。

实际比较的是整套版本，在统一仓位及修正后的执行模型中回放同段历史。未经逐项消融，不能给单个修改归功；有帮助也必须限定本段收益或其他具体指标。

**应改为：** 这次比较了预定版本组合在这段历史中的收益、回撤及交易差异，没有识别每项修改单独的作用。

依据：[diagnostics/iteration-comparison-20260911.md 第5行](../../diagnostics/iteration-comparison-20260911.md)；[diagnostics/iteration-comparison-20260911.md 第83行](../../diagnostics/iteration-comparison-20260911.md)。

### C13 · STABILITY_LANGUAGE_TOO_STRONG

> 当前结果支持“有些增强没有带来稳定好处”

**判断类型：** unsupported_inference。

部分最终版本段落后成立，但一个共同窗口没有测出增强效果的稳定性；稳定好处的措辞大于本次能够确认的范围。

**应改为：** 部分最终版本在这段共同历史中的终值收益低于预定早期对照；效果是否跨时期稳定仍不知道。

依据：[diagnostics/iteration-comparison-20260911.md 第83行](../../diagnostics/iteration-comparison-20260911.md)。

### C14 · NUMBERS_SUPPORTED_IDENTITY_NEEDS_INLINE_QUALIFIER

> EMA-X早期简单版｜值得作为基础对照｜赚18.47%，说明这段复杂版没兑现优势；但最大回撤18.88%，只有11笔，也还没证明优于简单持有

**判断类型：** numeric_fact、baseline_identity、subjective_preference。

18.47%、18.88%和11笔成立；复杂版本段收益落后成立。早期简单版容易被理解成当年完整唯一V1策略，但完整独立退出规格缺失，实际为按早期代码恢复的裸交叉基线。未证明优于持有是合理限制，不能写成已经输给持有。

**应改为：** 恢复的EMA-X裸交叉基线本段收益18.47%，收盘回撤18.88%，11笔；最终V18为−5.39%。这可用于比较，但不是已确认完整历史V1的逐笔复现；本轮也没有完成买入持有基准的优劣检验。

**仍不知道：** 历史唯一V1完整退出规则；相同成本与资金费下买入持有对照。

依据：[diagnostics/iteration-comparison-20260911.md 第28行](../../diagnostics/iteration-comparison-20260911.md)；[diagnostics/iteration-comparison-20260911.md 第13行](../../diagnostics/iteration-comparison-20260911.md)。

### C15 · REPORT_DISCLOSED_SHORT_LABELS_CAN_MISLEAD

> 早期版本与最终版本：同一段后续行情的比较

**判断类型：** baseline_identity、scope。

第二轮报告对早期身份披露充分，但主表短标签和后续评价不能让人以为14组都是最初未经调参的简单版：EMA-TB为V35起，CC为V10，ENS是诊断组合，EMA-X完整V1退出规格缺失。

**应改为：** 这是14组预定早期可复现对照与最终版的比较；其中有4组不能称为完整原始简单版对最终版。

**仍不知道：** 缺失的真正早期规格能否恢复。

依据：[diagnostics/iteration-comparison-20260911.md 第28行](../../diagnostics/iteration-comparison-20260911.md)。

### C16 · DISCLOSED_BUT_MUST_NOT_IMPLY_ORIGINAL_REPLAY

> 保留原仓位后的区别

**判断类型：** implementation_scope。

保留原仓位场景仍采用共同成本、实际成交固定数量和执行修正；统一1倍是名义头寸统一，不是单笔损失风险统一。旧22.34%、新4.86%不可全部解释为缩短样本的效果。

**应改为：** 旧22.34%与新4.86%同时存在起点、账户和实现差异；新4.86%是保留原仓位公式的共同账户诊断，不是旧引擎原样复现。

**仍不知道：** 逐项模型差异的收益影响。

依据：[diagnostics/iteration-comparison-20260911.md 第51行](../../diagnostics/iteration-comparison-20260911.md)；[diagnostics/iteration-comparison-20260911.md 第28行](../../diagnostics/iteration-comparison-20260911.md)；[diagnostics/iteration-comparison-20260911.md 第74行](../../diagnostics/iteration-comparison-20260911.md)。

### C17 · SUPPORTED_ONLY_FOR_FIVE_FROZEN_CC_CASES

> 较长窗口所有版本都亏

**判断类型：** numeric_fact、scope。

CC五个预定版本在6月8日至9月5日的统一1倍较长窗口都亏损成立，主窗口V21优于V35也成立。这不能单独证明10/8反转没有经济逻辑、所有可能版本无效，或亏损主要来自过拟合。

**应改为：** 在本次五个版本及统一因果执行、仓位和成本设定下，CC较长窗口全部亏损；本段结果不足以支持跟随历史赢家，也没有识别10/8信号自身的收益贡献。

**仍不知道：** 裸10/8信号在控制幅度、趋势和成本后的增量作用；经济假说是否有独立支持。

依据：[diagnostics/iteration-comparison-20260911.md 第59行](../../diagnostics/iteration-comparison-20260911.md)；[diagnostics/iteration-comparison-20260911.md 第62行](../../diagnostics/iteration-comparison-20260911.md)；[diagnostics/iteration-comparison-20260911.md 第65行](../../diagnostics/iteration-comparison-20260911.md)；[diagnostics/iteration-comparison-20260911.md 第69行](../../diagnostics/iteration-comparison-20260911.md)。

### C18 · REAL_PREVIOUS_IMPLEMENTATION_ERROR

> 上一轮HYPE15m MMTF的RVOL错误用了48根，原规格和引擎要求96根。

**判断类型：** known_numeric_correction。

这是此前存在的真实实现错误，不能因为幅度小或不改变正负就说之前所有数字完全正确。保存的第一轮汇总仍是历史旧值−14.22%。

**应改为：** 第一轮HYPE 15m MMTF有已确认窗口参数错误，后续单独复算把−14.22%改为−14.15%，仍亏损。这一项已纠正；它也说明验证通过不能无限扩大成全部历史结论保证。

依据：[diagnostics/iteration-comparison-20260911.md 第73行](../../diagnostics/iteration-comparison-20260911.md)；[artifacts/iteration_comparison_20260911/ar_mmtf/legacy_rvol_correction/comparison.json](../../artifacts/iteration_comparison_20260911/ar_mmtf/legacy_rvol_correction/comparison.json)。

### C19 · SUPPORTED_AS_THIS_STUDY_LIMIT

> 本轮没有任何一条被证明能稳定盈利

**判断类型：** evidence_limit。

本轮没有独立未来验证、完整资金费/执行证明，所以这句限于本轮成立；不能改写成所有策略永远不能盈利、没有价值或从未通过任何其他研究。未重放的家族也不能算失败。

**应改为：** 本轮证据不足以确认持续盈利。缺完整配置、没有交易规则或缺更早版本的对象，分别保留为未完成或不可比较，不纳入亏损分母。

**仍不知道：** 未重放或未比较对象的真实表现；其他独立历史和前瞻证据。

依据：[diagnostics/iteration-comparison-20260911.md 第85行](../../diagnostics/iteration-comparison-20260911.md)；[diagnostics/iteration-comparison-20260911.md 第76行](../../diagnostics/iteration-comparison-20260911.md)；[diagnostics/report-20260910.md 第100行](../../diagnostics/report-20260910.md)。

### C20 · MUST_NOT_EXPAND_PASS_TO_ALL_CONCLUSIONS

> 独立复核通过（对验收结果的使用范围）

**判断类型：** verification_scope。

保存的独立验收主要核对源规则/实现条件、账户算术、输入和文件汇总；它们不能替主观排名、因果解释或投资可用性背书。本次文字审计也没有重跑全部策略、重新穷尽所有源代码。

**应改为：** 可以说指定检查未发现阻断性问题，并列出已知修正和实现限制；不能据此断言之前所有结论都可靠。

**仍不知道：** 未覆盖检查是否仍有缺陷。

依据：[artifacts/iteration_comparison_20260911/acceptance_aggregate.json](../../artifacts/iteration_comparison_20260911/acceptance_aggregate.json)；[artifacts/iteration_comparison_20260911/acceptance_ema_independent.json](../../artifacts/iteration_comparison_20260911/acceptance_ema_independent.json)；[artifacts/iteration_comparison_20260911/acceptance_cc_independent.json](../../artifacts/iteration_comparison_20260911/acceptance_cc_independent.json)；[artifacts/iteration_comparison_20260911/acceptance_ar_mmtf_independent.json](../../artifacts/iteration_comparison_20260911/acceptance_ar_mmtf_independent.json)。

### C21 · EX_POST_SELECTION_NEEDS_LABEL

> 若继续验证，先固定EMA-X简单基线、MII最终版及CC V21/V35这几条对照

**判断类型：** subjective_research_choice。

预定两端比较没有按成绩重选，不代表后续推荐名单也是预先确定的。研究名单取自看过本次结果后的判断，可以用于提出问题，不能视为已验证的未来赢家。

**应改为：** 这些仅是根据本次发现提出的后续问题候选；要先明确是比较信号、检验退出还是寻找收益，再决定研究顺序，并在之后未见的数据上检验。

依据：[diagnostics/iteration-comparison-20260911.md 第85行](../../diagnostics/iteration-comparison-20260911.md)。

## 仍不能确认的关键问题

1. 用户更在意最高收益、较小回撤、资金占用，还是先查清机制。没有这一目标，不能把任一单项指标冒充统一优劣。
2. 过拟合究竟贡献了多少退化。7/6/1和大量试错只能构成描述或风险提醒，不能拆开过拟合、市场状态、成本和实现差异。
3. Keltner V3新增筛选、CC提前退出各自有没有可重复的价值。本次整版比较没有做逐项消融，也没有未见时期的验证。
4. 10/8反转是否具有独立收益来源。它有均值回归直觉，但同色K的数量不直接等于涨跌幅过度、流动性压力或可交易反转；本次未把信号、过滤、退出和仓位贡献分开。
5. 盈利版是否值得跟随。本段盈利是回看记录；交易少、资金费估计及执行/原规格差异仍存在，本轮未提供持续盈利或实盘可用的证明。
6. 缺配置或没有完整原始规则的对象真实表现怎样。第一轮7个未有效回测家族、第二轮3个不能配对对象，不能记作经济失败。

## 本次审计对可信度的处理

应撤回没有公开标准的主观优先级，把可复核数值、限定范围内的排序、尚未证实的原因和个人取舍分开。已有数值验收可支持指定计算检查通过，不能替因果解释和投入建议背书；本次文字审计也不替未检查的结论背书。没有给出新的冠军名单。

[机器可读审计及资料哈希](claim_audit_independent.json) · [第一轮报告](../../diagnostics/report-20260910.md) · [同段比较报告](../../diagnostics/iteration-comparison-20260911.md) · [14组原始配对](../iteration_comparison_20260911/paired_results.json)
