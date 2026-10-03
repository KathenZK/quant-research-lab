# 公开采集策略研究

本区与个人深入研究的市场家族分开，按稳定catalog ID组织；市场、标的、周期是规格字段。后续公开采集策略统一进入此处，不再新建到 research/btc 等个人研究区。既有 PUBLIC100 是另一份固定100条历史项目，不批量迁移或改其编号。

| 稳定 ID | 条目 | 当前分类 |
| --- | --- | --- |
| M0004 | [大类资产动量轮动](M0004/README.md) | 数据阻塞，回测0 |
| M0200 | [Connors RSI2](M0200/README.md) | 假设性回测，严格0 |
| M0215 | [RSI2反弹](M0215/README.md) | BTC单腿假设性回测，严格0 |
| M0216 | [SMA11/20](M0216/README.md) | 来源风险门假设性回测，严格0 |
| M0217 | [日线振幅突破](M0217/README.md) | 日级成交假设性回测，严格0 |
| M0212 | [成交量收缩规则](M0212/README.md) | 执行日锚假设；首版额外延迟保留，严格0 |
| M0214 | [SMA10/20加平均K](M0214/README.md) | 现货只多改编，严格0 |
| M0233 | [单资产z分数回撤](M0233/README.md) | 锁源码的只多投影改编，严格0 |
| M0211 | [布林复合评分预审](M0211/README.md) | 原规则执行阻塞，回测0 |
| M0220 | [周线EMA动量](M0220/README.md) | 617日历史假设回放，严格0 |
| M0232 | [海龟突破预审](M0232/README.md) | 完整代码访问与输入阻塞，回测0 |
| M0221 | [Hash Ribbons预审](M0221/README.md) | 算力QA通过，退出规则阻塞，回测0 |
| M0226 | [日频定投预审](M0226/README.md) | 金额与资金流规则阻塞，回测0 |
| M0256 | [AverageStrategy EMA8/21](M0256/README.md) | 4h假设回测4配置及1买持对照，严格0 |
| M0259 | [BbandRsi数据预审](M0259/README.md) | 1h缺口与停市异常阻塞，回测0 |
| M0274 | [GodStra](M0274/README.md) | 原生12h输入与完整管线因果阻塞，回测0 |
| M0275 | [Heracles](M0275/README.md) | 4h假设回测4配置及1买持，严格0 |
| M0286 | [MultiMa](M0286/README.md) | TEMA信号核验及4配置假设回测、1买持，严格0 |
| M0288 | [PatternRecognition](M0288/README.md) | 原生参考引擎假设回测4配置及1买持，严格0 |
| M0293 | [ReinforcedAverageStrategy](M0293/README.md) | EMA8/21与已收盘48h SMA50假设回测4配置及1买持，严格0 |
| M0316 | [hlhb](M0316/README.md) | 4h假设回测4配置及1买持，严格0 |
| M0317 | [mabStra](M0317/README.md) | 原卖出区间矛盾保留的4h假设回测4配置及1买持，严格0 |

| M0315 | [UniversalMACD](M0315/README.md) | 原生5m字面参数假设回测4配置及1买持，严格0 |

| M0311 | [TechnicalExampleStrategy CMF21](M0311/README.md) | 4配置执行改编失败诊断及1买持，严格0 |

| M0296 | [SMACrossover](M0296/README.md) | 源码/规则/去重审计，历史运行0，严格0 |
| M0299 | [SimpleBollinger](M0299/README.md) | 源码/规则/去重审计，历史运行0，严格0 |
| M0312 | [TradingView_RSI](M0312/README.md) | 源码/规则/去重审计，历史运行0，严格0 |
| M0314 | [TurtleRules](M0314/README.md) | 源码/规则/去重审计，历史运行0，严格0 |

| M0300 | [SmoothOperator](M0300/README.md) | 4配置原生5m执行代理诊断；买持复用，严格0 |
| M0302 | [Strategy001](M0302/README.md) | 4配置原生5m执行代理诊断；买持复用，严格0 |
| M0305 | [Strategy003](M0305/README.md) | 4配置原生5m执行代理诊断；买持复用，严格0 |
| M0306 | [Strategy004](M0306/README.md) | 4配置原生5m执行代理诊断；买持复用，严格0 |
| M0307 | [Strategy005](M0307/README.md) | 4配置原生5m执行代理诊断；买持复用，严格0 |

本次目录迁移发生在三个执行者完成之后，由单一协调者串行执行。各ID的 path-migration-20261003.json 记录旧根、新根及原始文件哈希；冻结JSON内历史路径与哈希链不改写，按映射解释。修改过的操作文档原字节保存在各ID的 artifacts/path-migration-20261003/original-documents/。这保留证据与历史commit身份，不表示再次回测或升级可信度。

完整行情和大量曲线不进入公开Git；仅代码、独立说明、来源哈希和获准轻量证据。备份按批次记录：M0256/M0259 私有 Library 检查点 （见私有恢复登记） v0 已由接收端取回，93 个清单成员核验通过，18 个确定性输出重建一致；这不代表此前其他批次的 Library 状态已解决。官方重建验证与异地快照备份分开统计。Graph保持现有详情/比较UI，未有导入或部署回执时不得称网站更新。

[M0316/M0317收益前来源预检](dot-next-preflight-20261003/README.md)：诊断主题，独立于各ID运行计数。

[dot batch006来源预检](dot-batch006-preflight-20261003/README.md)：M0253/M0272/M0264/M0266为唯一dot后续批次，当前仅源审，历史运行0。

[root batch011来源预检](root-batch011-preflight-20261003/README.md)：M0260/M0265/M0282/M0283已分配，逐ID C0与独立验收后才计完成。

- [M0298 Simple](M0298/README.md)：四配置原生5m成交代理诊断；严格0，独立验收另记。
- [M0304 Strategy002](M0304/README.md)：四配置原生5m成交代理诊断；严格0，独立验收另记。

[batch009六ID离线恢复入口](batch009-offline-recovery-20261003/README.md)：固定既有代码、输入及88个结果指纹，复用原执行入口；完整私有包远端备份状态单列。

- [M0260 BinHV27](M0260/README.md)：原生5m四配置执行代理诊断；冻结共享v1，复用既有买持对照，严格0。
- [M0265 CofiBitStrategy](M0265/README.md)：原生5m四配置执行代理诊断；冻结共享v1，复用既有买持对照，严格0。
- [M0282 MACDStrategy](M0282/README.md)：原生5m四配置执行代理诊断；冻结共享v1，复用既有买持对照，严格0。
- [M0283 MACDStrategy_crossed](M0283/README.md)：原生5m四配置执行代理诊断；冻结共享v1，复用既有买持对照，严格0。

[dot007两ID来源预检](dot-batch007-preflight-20261003/README.md)：M0287/M0289独占分配dot，8配置/0新对照待C0；其余26条仅不兼容本批，不计全局失败。

- [M0253 ASDTSRockwellTrading](M0253/README.md)：原生5m四配置执行代理诊断；既有买持复用，严格0；root独立验收另记。

- [M0272 EMASkipPump](M0272/README.md)：原生5m四配置执行代理诊断；既有买持复用，严格0；root独立验收另记。

- [M0264 ClucMay72018](M0264/README.md)：原生5m四配置执行代理诊断；既有买持复用，严格0；root独立验收另记。

- [M0266 CombinedBinHAndCluc](M0266/README.md)：原生5m四配置执行代理诊断；既有买持复用，严格0；root独立验收另记。

[M1358冷启动来源预检](root-batch013-m1358-preflight-20261003/README.md)：单ID日线4配置执行改编已分配，待独立C0；严格0。

- [M0287 MultiRSI](M0287/README.md)：10m/40m闭合重采样的原生5m四配置执行代理；基础配置亏损48.56%，零费仍保留滑点；严格0。
- [M0289 PowerTower](M0289/README.md)：原始绝对价格幂参数3.849/3.798保留；四配置零交易，无参数搜索；严格0。

- [M1358 EMA13/48冷启动状态策略](M1358/README.md)：日线四配置执行改编；保留收益前数值失败与修复，原作者环境未复现，严格0。

- [Catalog假设批次015冻结准备](catalog-hypothesis-batch015-preflight-20261003/README.md)：M1180/M1258，原始字段、执行选择与数据依赖明确；尚无新历史运行。

- [Catalog日线假设批次016冻结准备](catalog-hypothesis-batch016-preflight-20261003/README.md)：M1396/M1463，8个计划策略配置；待代码/C0/独审及同口径控制验收，当前无新历史运行。

- [M1258 五期RSI跨50目录假设](M1258/README-results-v1.md)：[研究报告](M1258/M1258.md)，原C0文档保持收益前快照；4策略与1个100%含费控制的独立终验/远端恢复逐项记录。
