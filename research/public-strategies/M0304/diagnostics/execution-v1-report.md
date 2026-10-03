# M0304 Strategy002：2024年原生5m诊断回放

## 结论

冻结的4个策略配置全部亏损。基准配置净收益 **−2.1551%**、全5m收盘最大回撤 **12.8746%**、日Sharpe **−0.1627**；同窗95%资金buyhold净收益 **+115.0304%**。在这组明确的限价/路径假设和已曝光窗口下，未显示相对于同资产对照的收益优势，不晋升、不接生产。

1个稳定策略ID、4个预注册策略配置、1个同窗对照完成；严格复现0，搜索0。保真度 **HYPOTHESIS**，研究/数据状态 **DIAGNOSTIC_ONLY**，trusted=false、非OOS，不证明作者原runtime、PIT、历史finality或可交易性。

## 时间线与固定证据

- 12:17:23 UTC：首CHECKSUM请求tunnel403，原阻断回执保留；不是已知Binance origin状态
- 用户授权等待后同源有限重试；12:33:27–12:37:11 UTC完成26官方GET、39源对象，12:38:47 UTC独立canonical rebuild通过。原失败未删除、未换host/周期/窗口
- 12:47:57.712661 UTC：执行C0冻结，之前未算真实账户收益。protocol SHA256 **49d74d0aa83d34c24c980264d66eedeb1f2a630645b1e43e0767684d186c2083**；引擎 SHA256 **525be5ffa69a6c4977286e48bf8acaf897ce059fd26d4737728c494b6ca57818**
- 12:50:14.681680 UTC：独立C0审核放行；12:51:16 UTC启动，12:51:44 UTC前观察到exit0；没有单独记录精确进程结束时刻
- 全部输出获独立171 fills / 527040 bar marks审核；另用独立重建CSV与新复制代码完成22个文件一致的clean恢复，summary仅排除环境峰RSS字段

原source：freqtrade/freqtrade-strategies@f3340ce11f5bdf62f598522e64d1f5638eaa13f5，Strategy002.py 4363B/SHA d1ca86a4ceb68ef828b35490ce1112330dad209cc3bb1e1b6c303c21ab3d8a90。Lab基线48851ef54b5fba6fef1da6825983864e1665fe1e。原类所有属性、参考默认/sidecar缺席及作者runtime未知保持不变；见[来源](../specs/source-manifest.json)与[完整协议](../specs/execution-v1/protocol.json)。

## 结果

| 配置 | 每边费率 / 信号延迟 | 净收益 | 年化收益 | 全5m MDD | 日Sharpe | 平仓轮数 | 总手续费USDT |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| base | 8bp / 1bar | −2.1551% | −2.1493% | 12.8746% | −0.1627 | 24 | 3625.98 |
| fee0 | 0bp / 1bar | −1.4181% | −1.4143% | 12.7226% | −0.0900 | 24 | 0 |
| fee20 | 20bp / 1bar | −11.2827% | −11.2537% | 20.6318% | −0.8033 | 22 | 7763.22 |
| delay2 | 8bp / 2bar | −5.5271% | −5.5124% | 13.7268% | −0.5778 | 15 | 2223.44 |
| buyhold | 8bp / 首bar市价 | +115.0304% | +114.5811% | 32.0211% | 1.7447 | 0（末尾持有） | 75.94 |

所有策略配置末尾已平仓；buyhold剩余2.2444901717 BTC，5000 USDT现金，末尾总权益215030.4123 USDT，仅按close mark，没有强平费。各配置105408个5m收盘观察、366个UTC日末点。年化指数365/366；MDD从初始本金及全部5m收盘净值峰值计算，绝非日采样重算，也不表示intrabar MDD。精确原始结果见[summary](../artifacts/execution-v1/summary.json)。

## 机制与风险解释

基准24轮中23轮盈利，胜率95.8333%，仍净亏。18轮信号退出、5轮ROI退出、1轮止损；盈利轮平均仅+0.3662%，最坏一轮净亏−10.1619%。高胜率不能掩盖盈利小、止损尾损大的结构。

exit_profit_only=true确实在执行bar开盘以fee-aware净收益严格>0门控：base检查581次，拒绝563次。该门控只约束信号退出，不限制止损/ROI；不按事后成交筛选保本。fee20有1088次检查、1075次拒绝，2轮止损。手续费敏感性会同时改变退出时点及后续交易机会，不能简单视为同一交易列表减去费用。

delay2只15轮、15个未成交超时订单；base为24轮、1个超时。额外一根5m延迟对固定信号close限价的成交概率和结果有影响，但本研究未为改善收益再搜索报价、延迟或止损。

trailing_stop=false始终执行，所有配置trailing activation=0。positive=.01/offset=.02仅原类闲置参数，未被擅自启用。

## 执行与外推边界

信号使用已闭合bar；基础delay1最早下根open，delay2两根后。限价固定信号close，GTC单bar超时，触及即全量成交；有利open按2bp不利滑点但限制不得比限价差，intrabar限价精确触及成交。stop为market，2bp不利滑点。95%含费预算、100000 USDT初始现金、单多仓、1倍、无资金费/利息。

假设O-L-H-C路径；开盘stop gap优先，再信号limit，再ROI；上升段先触价位优先，等价位信号优先。新entry仅经历剩余路径、同bar不重入。intrabar只给时间区间，持仓计龄保守从bar结束边界开始；每bar open确定ROI20/30/60分钟阶梯。此替代引擎不等价原Freqtrade回放，不是保守上下界；忽略队列/部分成交/lot-tick/min-notional，不能称已证明可成交。

输入2023-12-01到2025-01-01，114336原生5m bar，预热8928；评估2024年105408bar。CSV31428289B、SHA91e5bb0ba80ba2b70c5d6a5924c590459b0ffbe3e5955ba177abc981fb2a0af2。窗口因早先2023输入QA问题按可用性预选，非OOS，不和旧两年总收益直接比较；历史曝光/搜索总次数UNKNOWN，不能可信计算DSR/PBO。

## 审计、恢复与交付边界

- 原码仅AST/文本检查；独立6000自造bar标量指标、19原公式边界、21订单边界、286fills状态prefix通过；共享审计另独立1965合成fills/11879marks及30组执行prefix/future检查通过
- 实际171 fills及527040bar marks由Decimal重建现金、数量、费用、每bar权益；最大账户误差约7.01e−11。全barMDD、全部信号可见性、orders/gates、366日采样与Decimal日Sharpe、年化有限数检查均通过。[独立审计](../artifacts/execution-v1/independent-historical-ledger-audit.json)
- 新复制冻结代码在独立重建CSV上重放4+1，22输出一致（summary只忽略RSS）；这是可恢复性证据，不是另一套独立运行时实现。[clean恢复](../artifacts/execution-v1/clean-recovery.json)
- 主运行峰RSS195468KiB，独立审计约253MB，均低于每Python1GiB；无新增/升级依赖
- [可运行恢复说明](execution-v1-recovery.md)；公开仅轻量指标、代码、来源/输入/输出指纹和审核回执。原始行情、完整逐bar曲线/信号、完整事件账本和Graph detail不入公共Git。私有Graph只是兼容投影，不等于已导入、绑定或部署
