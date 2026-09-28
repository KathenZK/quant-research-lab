# 2026-09-25 全项目策略盘点证据

阅读入口：[策略创建时间线、参数与研究演进](../../diagnostics/strategy-project-chronology-and-research-review-2026-09-25.md)。用户要求将全项目策略整理成一份可细读的Markdown，本目录保存该文档的结构化清单与来源证据，不新增策略版本或回测结果。

报告已按用户要求改为**独立转发版**：只发送报告Markdown即可阅读。引用的研究文字、规格和决策记录收入文内附录，大型数据及非文本附件使用内容摘要或用途说明。附录中的来源标识不要求接收者具备原目录；原本地链接全部改为文内跳转。

## 范围

- 主仓库136个家族/主题，独立工作区`5f41`内主仓库缺少的3个家族，共139张卡片。`0498`内重复家族不重复计数。
- 12个早期代码原型、29份归档研究，以及PUBLIC100原编号100项。各层互有重叠，不能相加成独立策略数。
- 470份规格文件；来源指纹包括本轮实际读取的文档、结构化结果和恢复源码。当前工作副本中已有的未提交材料也在范围内。
- 创建时间指最早可核实的机制代码、决策日志或日期化研究文件；不把行情开始、归档迁入时间自动当成研究创建时间。

## 文件

|文件|用途|
|---|---|
|[inventory.json](inventory.json)|139个家族路径、标识、日期候选、主账、规格和文档索引|
|[source-manifest.json](source-manifest.json)|实际读取来源的绝对路径、字节数和SHA256，以及原材料中27处缺失引用|
|[validation.json](validation.json)|文档覆盖、日期排序、本地链接、锚点、折叠块、表格、代码围栏和来源一致性验证|
|[self-contained-manifest.json](self-contained-manifest.json)|独立版内嵌来源、全文/摘要方式、来源指纹、排版修复和最终报告指纹|
|[linked-source-edition.md](linked-source-edition.md)|编译前的内部草稿；其相对链接基准为最终报告目录，不是传阅入口|
|[historical-prototypes.json](historical-prototypes.json)|退役源码原型的日期、提交、参数默认值与历史路径|
|[historical-source/](historical-source)|从Git恢复的只读来源快照，没有重新运行这些策略|
|[editorial.md](editorial.md)、[historical-editorial.md](historical-editorial.md)、[closing.md](closing.md)|用于生成报告的分析文本；其中相对链接以最终报告所在目录为基准|

生成工具：[build_strategy_chronology_20260925.py](../../scripts/build_strategy_chronology_20260925.py)，会自动调用[独立文档打包工具](../../scripts/make_strategy_chronology_self_contained_20260925.py)。文档验证：[validate_strategy_chronology_20260925.py](../../scripts/validate_strategy_chronology_20260925.py)，要求独立版没有本地文件链接、文内跳转有效且470份规格全文覆盖。工具从项目根目录运行；生成过程依赖原项目文件、Git历史和上述独立工作区，阅读最终Markdown无需这些文件。更新后必须重新验证。文档中的关键绩效采用已有归档结果，本次没有重新回测、训练模型、校验全市场数据或读取生产服务。

验证通过只表示**本轮盘点所声称的覆盖和资料引用一致**。外部网页没有重新抓取，原报告的市场数据、规则实现、资金费完整性和实盘授权不能由文档验证替代。原材料中无法打开的引用已显示为缺失说明，不生成失效的可点击链接；原始文件没有因此改动。
