# dot 首批互斥交接：M0256 / M0259

协调者Codex仅负责全局清单、进度及Lab/Graph集成；外部执行者dot只认领M0256与M0259。登记文件 `claims-20261003-dot001.json` 状态ASSIGNED_NOT_STARTED，须等dot返回实际启动回执才计运行。M0253未分配。跨机器不假定共享目录，不传凭证或原始大行情。

## 来源与契约

Library原表 `libfile_296b8fa9c4348191a5c6d138830f8494`（quant-master-draft.csv）：M0256第259行，M0259第262行，2026-10-03重新read确认。只将可读行作为规则来源，不等同完整CSV字节恢复。

两源码锁 `freqtrade/freqtrade-strategies@f3340ce11f5bdf62f598522e64d1f5638eaa13f5`，路径前缀 `user_data/strategies/berlinguyinca/`：

| ID | 文件/hash | 原源码规则与额外风控 |
| --- | --- | --- |
| M0256 | AverageStrategy.py；2630B；SHA256 `63606866fdf1cb3d71dc39a951ed0784a31686690b1c4014c12d2481c8dbf094` | 4h；TA-Lib EMA8上穿21做多、反向退出、volume>0；minimal_roi 0分钟50%，stoploss−20% |
| M0259 | BbandRsi.py；1854B；SHA256 `65718e8d0c14094b67be82b66238ea60a4af4bbf6fd9a6e1879dad5c48125547` | 1h；RSI14<30且close<BB20/2下轨做多，RSI>70退出；BB基于typical price；minimal_roi 0分钟10%，stoploss−25% |

使用固定commit原始URL下载，核hash后再读；核源仓库许可与署名，不把代码许可当行情授权。不做hyperopt；EMA默认8/21，不从参数搜索范围选优。框架/TA-Lib/qtpylib版本须锁定；尤其交叉、RSI/EMA种子和BB标准差语义不得按常识替代。

默认标的是预声明的BTCUSDT spot实例，源策略文件未指定资产池，不能声称原作者币种选择复现。默认HYPOTHESIS；若改掉任何信号/风控则ADAPTATION并说明。即便源信号逐行相同，也不自动构成严格复现。

## 数据和执行

- dot自行获取官方Binance Vision月档与CHECKSUM：M0256用4h，M0259用1h。输入2022-12-01—2024-12-31，评估2023-01-01—2024-12-31；不得拿当前Codex的日线顶替。
- 每ZIP/checksum、解压文件、最终规范输入记录sha256/字节/拉取时间。核精确UTC开收盘网格、排序去重、缺口、OHLC关系、量字段、资产/市场类型、完整bar、源许可及PIT限制。保持至少5GiB余量。
- 窗口已被其它策略曝光，原历史搜索次数未知；不宣称纯净OOS或可靠DSR/PBO。
- 先冻结spec/源码版本/执行器代码hash/参数/exposure，再实际计算收益。初始资金、仓位、含费预算、费用/滑点、真实下一open入场、期末持仓规则均明确。建议首批基准单边8bps+2bps不利滑点，0/20bps费用及额外一根bar延迟，另同窗同成本买持；这些是执行假设，不是源码事实。
- 不省略源码ROI和stoploss。优先使用已锁原框架并记录有效配置；若独立移植，必须预声明ROI/stop/exit-signal同时发生顺序、开盘跳空及同bar路径不确定性。需要更细bar时自行取官方匹配数据并QA；日内路径未获证实则不strict。禁止未来数据、合成指标价成交或未声明杠杆。
- 独立信号/账本实现核指标、每笔费用、每日/每bar净值；未来扰动必须涵盖日内/周边界；新目录用冻结代码和明确输入重建一次。QA/恢复重跑不增加策略ID或参数搜索计数。

## 交付与导入

以Lab远端提交 `797a8e7d1dda2a1009ab03baac0bf770dab8a806` 为公开参考，独立分支 `dot/public-strategies-20261003-b001`；仅写 `research/public-strategies/M0256/` 和 `.../M0259/`。不要改AGENTS、全局索引、allowlist、进度、Graph仓库、其他ID或既有证据。协调者负责合并必要注册、CI与Graph绑定。不得擅自merge受保护主分支。

每ID沿用M0214/M0220的README、`<id>-core-ledger.md`、decision-log、specs、scripts、diagnostics结构。逐策略报告包含原规则/出处/白话、标的/选池/入退出/仓位/成本/时点、经济假设、忠实度分类、数据来源版本hash/覆盖缺口/PIT、代码参数、基准及敏感性/样本外范围、指标/净值/成交或缺失原因、具体结论/失败场景/下一步。

关键轻量结果：summary.json、1条基准净值（必要时有明确采样元信息）、基准成交、验证和重建回执、source/input/result hash manifests、exposure、许可署名。完整行情和大曲线可重建，不要求长期打包备份；不自动删除已有证据。保留精确公共来源重建代码，实际验证后才标VERIFIED；来源将来下架/修订或hash不符必须报UNAVAILABLE/MISMATCH，不能承诺永远可重建。

Graph record沿用已有结构：`id,name,status,reason,tested_variants,families,audit,implementations,related_results`；每implementation/result保留origin_run_id、variant_id、fidelity_class和protocol/manifest hash。完整私有detail包含id/run_id/variant_id/name/family/spec/audit/lineage/limitations、metrics.periods.full（start/end/observations/total_return/max_drawdown/sharpe）及curve和curve_meta。Graph输入兼容不等于已绑定定义或已部署。不得虚造既有definition_revision。

返回：分支与完整commit、精确轻量发布文件清单及各hash、实际ID/配置/对照数、阻塞项、最新产物时间、QA/实际重建回执、若成功保存Library则给ID。不要传原始大文件或凭证。无跨机器路径可达假设；协调者从不可变Git版本/授权Library引用重新取字节验收，再登记全局和Graph。

## 当前不冲突范围

Codex已运行M0200/M0212/M0214/M0215/M0216/M0217/M0220/M0233；M0004/M0211/M0221/M0226/M0232具体阻塞。以上均不得分配给dot重跑。当前模型设置由父线程确认后续轮 `gpt-6-astra / xhigh`，当前已运行轮仍UNKNOWN；不要反推或回填历史运行模型。

## 最新端到端门控

M0256/M0259仅为1—2条端到端小样本，非大批量启动授权。分配/QA/Lab远端保存/实际重建/Graph小样本导入/实际页面展示全部验收之前，不启动大批回测或大批Graph导入；不把PR存在当作上站。当前已通过前批远端与恢复，Graph导入/页面验收尚未通过。
