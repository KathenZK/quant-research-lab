# M0298 Simple：2024 原生5m诊断结果

## 结论

固定4个策略配置和1个同窗买入持有对照已完成，独立全事件/逐bar账本、费用与指标审计通过，并在新目录使用独立重建输入完成冻结重放。基础配置全年总收益 **+31.51%**、全5m收盘净值最大回撤 **−39.68%**；同窗95%资金买入持有为 **+115.03% / −32.02%**。本假设实例落后对照，且对费用和执行延迟敏感，没有晋升结论。

保真等级 **HYPOTHESIS**，数据与结果 **DIAGNOSTIC_ONLY / untrusted**；严格复现0、OOS声明false、参数搜索0。真实原作者资产池、成本和runtime未知，不能把本结果称为作者原策略业绩、可交易性证明或实盘建议。

## 身份、来源与输入

- 稳定ID M0298；Simple；Gert Wohlgemuth / freqtrade-strategies
- 运行ID M0298-calendar2024-execution-v1-20261003；变体 M0298-BTCUSDT-NATIVE5M-SIMPLE-20261003-v1
- Lab交接提交48851ef54b5fba6fef1da6825983864e1665fe1e
- [固定源码](https://github.com/freqtrade/freqtrade-strategies/blob/f3340ce11f5bdf62f598522e64d1f5638eaa13f5/user_data/strategies/berlinguyinca/Simple.py)：2695B、SHA256 812a8d63b0e0ddff6b9bae582c4d573ab9a4ffec6dd0d1c5b8f8180f11db6d0b；仅AST读取，从未执行第三方策略原码
- [源码指纹/全部显式属性](../specs/source-fingerprint.json)：INTERFACE_VERSION3、5m、ROI从0分钟起1%、stoploss−25%
- Binance BTCUSDT spot原生5m，输入[2023-12-01,2025-01-01)，114336行/31428289B；规范CSV SHA256 91e5bb0ba80ba2b70c5d6a5924c590459b0ffbe3e5955ba177abc981fb2a0af2
- 2023-12共8928根预热；2024年评估105408根。2024窗口按可用性选择，先于本候选收益，不是OOS，不与先前两年总收益直接比较

## 精确原规则

MACD12/26/9；RSI7；以close计算BB(window12,std2,min_periods1,ddof1)。入场为 macd>0、macd>signal、BB上轨比前bar上行、RSI>70 四项同时成立；出场为RSI>80。全部不等式保持严格，RSI=80不满足出场。

两列原始信号分别保留。入/出碰撞禁止新入仓，也抑制信号出场；不把入场改成70<RSI<=80，ROI/止损继续独立生效。基础配置可用信号窗口内观察到2999个碰撞bar。qtpylib默认链和框架参考只用于明确假设，不证明作者当年的运行环境。

## 先冻结，再执行

[执行协议](../specs/execution-plan-v1.json)和[C0](../specs/C0-20261003-v1.json)于2026-10-03 **12:48:26.079295UTC**冻结；C0 SHA256 55b0a3221bd296aa1465cf476d9ced3f50b77cd43ee052570ff3c9e8f2e1cf4e。独立审核 **12:50:14.681680UTC**放行；[原字节release](../artifacts/execution-v1/M0298-C0-release-v1.json) SHA256 a064286eefa0884ac36aa32f0a5c27da063d145239b98bb7592eaa525c92cf13。首跑 **12:50:59.442338429UTC**启动、exit0。冻结前仅源规则、合成或输入/特征QA，没有计算历史账户收益。

代码是单仓现货多头的独立诊断移植，不是Freqtrade原生引擎。100000 USDT初始现金，95%预算，无杠杆/借币/加仓。信号必须来自闭合bar；lag1在下一根激活，lag2在第二根激活。起始账户零仓，但首评估bar允许消费最后预热闭合信号（lag1为12/31 23:55，lag2为23:50）。

入场/信号出场限价为原信号bar close，有利开盘价成交，否则区间触价；GTC在一根可执行5m末明确取消。采用全额分数成交，不建模盘口排队、部分成交、tick/lot/min-notional。每边费用8bps，另有2bps独立现金摩擦；摩擦不把限价成交价推到价格约束以外。ROI目标覆盖双边费用和现金摩擦后净1%，因此变更费用也会改变退出时点和交易路径。

止损触发为入场成交价×0.75，采用明确的market替代，区别于参考默认stoploss limit。开盘事件按stop gap→可成交signal→ROI gap；区间按stop→signal→ROI。intrabar新入不认同bar ROI但仍可止损；不允许同bar退出后再入。价格触达/止损/ROI使用包含等号的边界，这是已冻结的执行假设。末尾持仓按最后close估值，**不强平**。

## 4配置与同窗对照

| 配置 | 每边费用 | 每边现金摩擦 | 信号延迟 | 总收益 | 全5m MDD | 日Sharpe | 已平交易 |
|---|---:|---:|---:|---:|---:|---:|---:|
| base | 8bps | 2bps | 1bar | +31.51% | −39.68% | 0.8251 | 242 |
| fee0 | 0bps | 2bps | 1bar | +96.18% | −32.02% | 1.6663 | 278 |
| fee20 | 20bps | 2bps | 1bar | −13.16% | −51.72% | −0.0943 | 210 |
| delay2 | 8bps | 2bps | 2bar | +18.37% | −43.32% | 0.5933 | 182 |
| buyhold | 8bps | 2bps | 首评估open | +115.03% | −32.02% | 1.7447 | 0，末尾仍持有 |

以上全为同一2024窗口、初始100000和95%预算，不增加参数搜索。fee0仍有2bps摩擦，并不等于零成本。买入持有从首评估open买入后只估值，不应用策略信号、ROI或止损。

base末值131511.53 USDT，末尾仍有一笔持仓；估计扣除末尾退出成本后的净清算值131386.73 USDT，单列而未当作实际强平。242笔已平交易中196笔ROI、46笔signal；总手续费41996.10 USDT、现金摩擦10499.03 USDT，二者均已在账户内扣除。base只有1个超时订单，delay2为129个，说明延迟配置同时检验旧限价在更晚bar的成交可达性。delay2出现1笔止损；这不是根据结果新增或修订规则。

完整数值见[summary](../artifacts/execution-v1/summary.json)。MDD按**全部105408根5m收盘净值加初始现金**计算，非日采样回撤；Sharpe使用366个UTC日收盘收益、ddof1、rf0、sqrt365；年化收益按365/366计算。日曲线366点仅供展示；2025-01-01T00:00:00Z表示2024最后一根bar的估值边界。

## 数据、因果、账本和恢复证据

1. 首次恢复的首个请求遇Tunnel403，原始[阻塞回执](../history/preparation-v0/artifacts/data-recovery-blocker-safe.json)与完整旧21文件包保留，不回填为成功。用户随后授权等待后同源有限重试
2. 第二次实际26GET、13个月、39源对象全部验hash/ZIP CRC；全114336行网格/OHLCV/原生数量通过，缺口/重复/零量/非标准close_time为0。独立逐字节规范重建通过，见[成功恢复](../artifacts/execution-v1/data-recovery-safe-v2.json)与[独立原始QA](../artifacts/execution-v1/independent-canonical-qa-v1.json)
3. 原始6000合成bar独立标量公式、碰撞语义与边界检查通过；完整引擎18个合成执行fixture通过。共享独立Decimal审计重建1965 fills/11879 marks，30组完整执行prefix/未来扰动通过；[审计](../artifacts/execution-v1/shared-Decimal-ledger-audit-v2.json)不声称原框架等价
4. 真实固定输入的9000/40000/100000行特征prefix及未来扰动前缀均逐列完全一致，见[因果检查](../artifacts/execution-v1/real-input-feature-causality-v1.json)。有限经验检查不是普遍无前视证明
5. 真实4+1合计**1828 fills / 527040个bar账户标记**已独立Decimal逐笔复算，订单/闭合信号时序、每bar持仓/现金/净值、全bar MDD、日采样和Sharpe/年化均相符；[实际账本审计](../artifacts/execution-v1/M0298-historical-ledger-audit-v1.json)。各case最大绝对Decimal差异均低于4e−9
6. 新目录复制冻结代码/门禁，使用独立重建规范输入，实际重跑同4+1。33结果文件中31个逐字节相同；另外两项仅summary中峰值RSS及相应manifest变化，去RSS后summary完全一致。见[恢复回执](../artifacts/execution-v1/recovery-receipt.json)
7. 每Python以RLIMIT_AS1GiB硬限制，BLAS1；主跑峰171409408B、独立恢复172130304B。无新增依赖或升级。原始数据和全长账户/信号输出仅本地保留，公共包只发布代码、规格、哈希、摘要和日度权益投影

## 保留限制

作者runtime/资产池未知；既往搜索次数UNKNOWN，不能推断可靠DSR/PBO。PIT、历史最终性、真实可交易性均未建立。native5m OHLC不能证明真实限价队列成交或bar内路径；本次path-ambiguous计数为0也不使这些假设变成事实。输入原档未来可能修订或不可访问，必须匹配冻结hash，不得自动换源、窗口或修bar。当前结果是已审计的假设实例，不晋升、不部署、不绑定生产定义。

[可运行恢复命令](../RECOVERY-execution-v1.md) · [当前主账](../m0298-core-ledger.md) · [当前决策记录](../decision-log.md) · [原阻塞准备包](../history/preparation-v0/README.md)
