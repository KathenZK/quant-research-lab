# 并行批次005：dot执行交接

基线为 Lab main `8661e31456a44887903327c82cf0f97604fd3b03`。dot仅写分支 `dot/public-strategies-20261003-b002` 的逐ID目录；Codex是唯一全局索引、allowlist、计数和集成写者。Site仍由dot独立Site worker操作，回测执行者不操作Site。2026-10-03 09:57:40 UTC用户已解除Graph验收对回测扩量的前置限制。

## 立即可认领的首批

- **M0275 Heracles / 4h**：按固定源码 `buy_params` 的Donchian pband(10)前移15根，除以Keltner wband(20)前移9根，比值0.16–0.75入场；无指标退出。源码ROI分钟阶梯、-25.6%止损、AgeFilter100天和`ta`依赖必须核实保留；不要把IntParameter default16误当buy_params15。先独立冻结参数加载、NaN、成交和停市处理。
- **M0274 GodStra / 12h**：源码固定买入`trend_ichimoku_base < 0.06295`，卖出`trend_kst_diff == 0.8779`；原ROI分钟阶梯、-34.549%止损和追踪参数需完整保留。`add_all_ta_features(fillna=True)`必须做截断因果检查，若有未来依赖则阻塞原实现或另列改编，不静默修复。零交易也是有效研究结果；不得调阈值追求交易。

精确URL、字节数、SHA256与占用见[claims](claims-20261003-parallel005.json)。源码注释旧优化收益不算本次结果。源码文件全量虽已只读验收，本交接不把第三方全文重复入库。

## 输入和QA

BTCUSDT现货研究实例，输入2022-12-01至2025-01-01不含末端，评价2023-01-01至2025-01-01不含末端。不是作者完整选池复现，默认HYPOTHESIS。输入窗口和执行协议须在读取策略结果前冻结；不根据结果换窗。

4h沿用已合并M0256的受审重建脚本与官方25月清单：`research/public-strategies/M0256/scripts/rebuild_official_bars.py --timeframe 4h --target <新的独立目录> --expected-manifest research/public-strategies/M0256/artifacts/20261003-first-replay/4h-input-manifest-light.json --terms-reviewed`。先核命令参数与清单；目标canonical input SHA256为`9f5cb39c1426ec91098bb8a1b1f0c926b80760e66fe452d6b0c0aa55429d126c`。已有本机dot冻结输入可先验hash再只读复用；父或Codex路径不代表dot本地可读。

12h须从相同官方Binance Vision原生12h月档重新获取，按既有捕获/QA规范适配：ZIP/CHECKSUM/CRC、native12、网格、开闭时间、OHLCV、缺口/乱序、重复、微秒格式和历史停市审查。当前脚本仅列明的周期可直接使用，**不能直接把`--timeframe 12h`当已支持，也不能以4h重采样冒充原生12h**。保留2023-03-24停市事实；实际下单时钟/部分停市桶的代理须预先声明，不能隐式使用无交易时刻价格。数据QA/来源失败则具体阻塞，严格复现仍0。

已同意Binance条款只用于本次个人非生产研究；沿用M0256许可/归因，不能推断商业、实盘或一般数据外传授权。原始行情和大曲线不进公开Git。每个任务开始前确保至少5GiB余量。

## 后续预留，不算已启动

M0257 AwesomeMacd和M0273 Freqtrade_backtest_validation_freqtrade1仅预留给dot，首批保存后逐项认领。两者为1h；已知原生2023-03-24缺13:00桶及12:00零量/非整点闭合，M0259原完整网格契约失败。必须独立来源/数据门控，不能复制M0259结果、填补缺口或改窗冒充通过。若需不同明确停市执行假设，先冻结并单独标HYPOTHESIS，不算严格原策略。

## 每ID输出和保存

在`research/public-strategies/<ID>/`保存README、独立中文策略报告/主账/决策日志、原ID与原规则引用、白话规则、理论与缺失证据、标的选池信号入出仓位风险成本时间、固定源版本hash、冻结规格/曝光账、代码/依赖版本、数据来源/QA/覆盖/hash、基准和成本/延迟敏感性、指标/净值/交易或无法生成的原因、失败场景/后续方向、Graph兼容record、重建说明与独立验证。配置和控制不计新ID，代理/假设/严格/阻塞分开。

检查点：C0源/输入QA；C1冻结协议（尚未看结果）；C2已校验结果；C3远端读回及恢复核验。每到可复核检查点立即通知协调者。逐ID可以提交代码/Markdown/已审轻量证据到分配的dot分支；不得修改全局文件，不得强推、覆盖冻结文件、删除旧证据或自行合并main。由Codex汇总治理登记、required CI和集成。每次远端保存返回commit及逐文件hash读回回执；按当前授权保留私有Library轻量恢复包/独立清单（可用时），完整行情/大曲线使用来源+hash+已验证重建配方。Library失败准确报告，不能宣称工作盘为备份。原始数据许可不允许外传时只保留来源与配方。

Codex两路独占M0286/M0288，不可重叠认领。dot尚无实际启动回执时状态保持ASSIGNED_NOT_STARTED。
