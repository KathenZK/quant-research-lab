# 研究家族只读审计证据（2026-09-08）

范围：HYPE 5m/15m/1h/1d、BTC/ETH/SOL/BNB/TRX adaptive、经典 CTA/EWMAC/TSMOM、迁移与实盘观察。未训练、未回测、未访问生产账户、未修改仓库文件。下述行号针对本次读取的仓库快照。研究指标均为各自报告的冻结口径，不跨家族拼接。

结论：证据不支持“技术指标中低频整体无效”。主要问题是旧目标下的高维广搜、少量独立交易和反复使用已揭示历史、执行假设错误、成本与风险预算混淆，以及观察/实施闭环不完整。另有一些正收益或分散价值迹象，但远未构成真实可执行和长期实盘有效的证明。用户现已明确初始资金 10,000 美元、接受 20%–30% 最大回撤、接受非加密市场；新方向不应继续沿用旧 20x 年化目标。

## 12 条具体证据

### 1. 旧目标与现在的投资需求错位

HYPE 15m MMTF 要求净年化权益 >=20x、胜率 >=80%、MDD<20%、杠杆<=3x；1h MMTF 要求 full/OOS 同时达到且至少 60/15 笔。今天的 10,000 美元及 20%–30%DD 接受度不应继续继承 20x 作为新研究筛选目标。原失败仍保留，不事后改变其裁决。

- [research/hype/15m-multi-mechanism-trend-following/hype-15m-mmtf-core-ledger.md:14](../../../hype/15m-multi-mechanism-trend-following/hype-15m-mmtf-core-ledger.md)
- [research/hype/1h-multi-mechanism-trend-following/hype-1h-mmtf-core-ledger.md:36](../../../hype/1h-multi-mechanism-trend-following/hype-1h-mmtf-core-ledger.md)

### 2. 广搜规模远大于有效独立交易样本

BNB 首轮 1,000,000 随机 + 500,000 邻域，再跑 500,000 + 250,000；ETH 首轮 600,768 组。BNB rerun OOS 仅 4 笔；ETH 各版 OOS 仅 4–12 笔。百万 K 线或候选不是百万独立经济样本。这种搜索与验证规模失衡使幸运赢家和样本不稳定成为首要问题。

- [research/bnb/1h-adaptive-regime/bnb-1h-ar-core-ledger.md:29-34](../../../bnb/1h-adaptive-regime/bnb-1h-ar-core-ledger.md)
- [research/eth/1h-adaptive-regime/eth-1h-ar-core-ledger.md:19](../../../eth/1h-adaptive-regime/eth-1h-ar-core-ledger.md)
- [research/eth/1h-adaptive-regime/eth-1h-ar-core-ledger.md:30-34](../../../eth/1h-adaptive-regime/eth-1h-ar-core-ledger.md)

### 3. 历史指标改善没有带来同等新增验证信息

ETH V1 prefit 2.81x/OOS 0.52x；V3 prefit 4.06x、100% 胜率/OOS 0.87x、4 笔；V4 prefit 5.49x/OOS 1.06x、12 笔。后续明确是 reused holdout。BTC、BNB 也出现同类演进。这与选择偏差和样本不稳定一致，但仅靠数值不能唯一识别原因。版本登记和参数清理不是新增经济证据。

- [research/eth/1h-adaptive-regime/eth-1h-ar-core-ledger.md:30-40](../../../eth/1h-adaptive-regime/eth-1h-ar-core-ledger.md)
- [research/btc/1h-adaptive-regime/btc-1h-ar-core-ledger.md:14-31](../../../btc/1h-adaptive-regime/btc-1h-ar-core-ledger.md)
- [research/bnb/1h-adaptive-regime/bnb-1h-ar-core-ledger.md:32-34](../../../bnb/1h-adaptive-regime/bnb-1h-ar-core-ledger.md)

### 4. 高胜率伴随低盈亏比和负尾部

HYPE 15m prefit 胜率 92%、平均盈亏比 0.333；OOS 胜率仍 76.19% 却收益 -14.78%、PF 0.547；full 最大单笔亏损 -17.55%。这是没有通过样本外经济性，不是只差 20x 目标。

- [research/hype/15m-multi-mechanism-trend-following/diagnostics/hype-15m-mmtf-v3-final-audit-2026-07-22.md:11-17](../../../hype/15m-multi-mechanism-trend-following/diagnostics/hype-15m-mmtf-v3-final-audit-2026-07-22.md)
- 同文件 `:32-35`
- 本次读取对应 `artifacts/hype_15m_mmtf_v3_locked_oos_reveal_2026-07-22.json`，核对了 prefit 和 OOS 主要指标。

### 5. 一部分信号不能承受 K 线边界和成交时序扰动

HYPE 15m 延迟一根 K 后 full -48.19%/DD 71.76%；真实 1m 重聚合偏移 5m/10m，prefit 变 -51.26%/-22.16%。HYPE 1h K+2 full DD 64.80%，30m 相位收益仅原生约 26%。这指向边界依赖与执行稳健性，不支持以继续增加指标来解释或修复。

- [research/hype/15m-multi-mechanism-trend-following/diagnostics/hype-15m-mmtf-v3-final-audit-2026-07-22.md:39-44](../../../hype/15m-multi-mechanism-trend-following/diagnostics/hype-15m-mmtf-v3-final-audit-2026-07-22.md)
- [research/hype/1h-multi-mechanism-trend-following/diagnostics/hype-1h-mmtf-v3-final-audit-2026-07-22.md:43-48](../../../hype/1h-multi-mechanism-trend-following/diagnostics/hype-1h-mmtf-v3-final-audit-2026-07-22.md)

### 6. 硬门槛失败不等于没赚钱

HYPE 1h MMTF locked OOS 实际 +15.59%、PF 1.732、13 笔；失败项是 DD 33.07%、样本少、20x 年化不达以及稳健性不足。原版仍不合格，但全仓库 NO-GO/HARD-GATE-FAILED 标签不能直接推导所有价格信号为零。

- [research/hype/1h-multi-mechanism-trend-following/diagnostics/hype-1h-mmtf-v3-final-audit-2026-07-22.md:11-17](../../../hype/1h-multi-mechanism-trend-following/diagnostics/hype-1h-mmtf-v3-final-audit-2026-07-22.md)
- 本次读取对应 `artifacts/hype_1h_mmtf_v3_locked_oos_reveal_2026-07-22.json` 核对。

### 7. 存在足以翻转结果的不可成交假设

HYPE 5m PBTR V1 legacy 收益 +1713.55%、PF 2.806、DD 7.77%；严格可成交 fill 重放变 -87.29%、PF 0.637、DD 88.27%。原因是 min-hold 解除后仍允许按已经穿越的 stop/target 价格成交。市场数据行连续完整也不会发现这种执行语义错误。

- [research/hype/5m-pullback-trail/diagnostics/hype-5m-pbtr-v1-strict-live-audit-2026-06-27.md:23-46](../../../hype/5m-pullback-trail/diagnostics/hype-5m-pbtr-v1-strict-live-audit-2026-06-27.md)
- 限制：该报告引用的 `artifacts/hype_5m_pbtr_v1_strict_live_audit_2026-06-27.json` 在当前标准路径缺失；本轮引用报告证据，没有独立重放。

### 8. HYPE 专用规则在短历史少量事件上优秀，跨资产迁移差

V7.1 在 432 天 20 笔上 +711.04%/DD 18.40%，但 U 本位 Top15 仅 2/15 正收益，中位 -27.49%；USDT Top30 仅 9/30 正收益，中位 -20.81%。V4 改善来自过滤两笔已知亏损，V3 仅改变两笔退出。不能据此证明全为过拟合，但专用性与样本不足证据很强。

- [research/hype/1d-ma7-asymmetric-body-trend/hype-1d-ma7-abt-core-ledger.md:34-47](../../../hype/1d-ma7-asymmetric-body-trend/hype-1d-ma7-abt-core-ledger.md)

### 9. 经典 CTA 的信号、成本、风险预算与多空方向必须分开

BTC 文献 EWMAC 未对 BTC 调参，约六年净收益 +71.45%、Sharpe 0.530、DD 37.04%；实际平均仓位 0.323x，却以 1x 买入持有 +238.62% 直接比较绝对收益。多头-only Sharpe 0.739、DD 26.74%；空头-only -16.10%，资金费明显拖累。未跑赢买入持有混合了风险预算与信号质量，不能单独证明无价值。多头-only 是事后归因，不能作为已验证新策略。

- [research/btc/1d-classic-cta-trend/diagnostics/btc-1d-ccta-classic-cta-backtest-2026-08-17.md:13-20](../../../btc/1d-classic-cta-trend/diagnostics/btc-1d-ccta-classic-cta-backtest-2026-08-17.md)
- 同文件 `:35-44`
- 同文件 `:71-75`：数据行与 funding 审计通过，但未模拟最小名义、数量步长和拒单。

### 10. 跨资产文献基线有弱分散迹象，不是暴利独立系统

EWMAC P4 主窗 23.8 年，净 CAGR 5.2%、Sharpe 0.48、DD 24%、换手 21.8x；与 SPY 相关 0.01；50/50 组合 Sharpe 0.67→0.82、DD 55.2%→25.2%。原 G1/G4 失败仍有效，但可描述为有历史分散迹象、真实实现未证。MOP 作者/AQR 论文后 2010–2026-05 Sharpe 0.402，也提示当代文献基线不能自然期望高夏普暴利。

- [research/asset-portfolios/1d-ewmac-universal-trend/diagnostics/xa-1d-ewmac-ut-p4-gate-recalibration-2026-08-06.md:21-34](../../../asset-portfolios/1d-ewmac-universal-trend/diagnostics/xa-1d-ewmac-ut-p4-gate-recalibration-2026-08-06.md)
- 同文件 `:49-57`
- [research/asset-portfolios/1d-tradfi-futures-tsmom/diagnostics/tf-1d-fut-tsmom-paper-exact-p1-2026-08-19.md:15-20](../../../asset-portfolios/1d-tradfi-futures-tsmom/diagnostics/tf-1d-fut-tsmom-paper-exact-p1-2026-08-19.md)
- 对应两条 summary JSON 存在，本次已读取；没有重建所有绩效。

### 11. P4/传统市场研究仍是代理，不能直接交给 10,000 美元账户

P4 平均 gross 1.57、最高 3x；继承收盘价成交近似、无借券/融资成本、联合 UTC 日历、ffill 五天。固定当前标的按上市/ready 激活只解决尚未上市问题，不等于历史全市场 PIT 选池，也不能消除事后选择标的的可能。没有 clean OOS。ETF 商品 roll 结构、FX 代理缺 forward carry 不等于期货复刻；黄金线明确 raw_unaccepted、缺官方 roll mapping。

- [research/asset-portfolios/1d-ewmac-universal-trend/diagnostics/xa-1d-ewmac-ut-p3-breadth-scale-2026-08-06.md:13-15](../../../asset-portfolios/1d-ewmac-universal-trend/diagnostics/xa-1d-ewmac-ut-p3-breadth-scale-2026-08-06.md)
- [research/asset-portfolios/1d-ewmac-universal-trend/specs/xa-1d-ewmac-ut-p4-gate-recalibration-contract-2026-08-06.md:15](../../../asset-portfolios/1d-ewmac-universal-trend/specs/xa-1d-ewmac-ut-p4-gate-recalibration-contract-2026-08-06.md)
- [research/asset-portfolios/1d-ewmac-universal-trend/specs/xa-1d-ewmac-ut-portfolio-contract-2026-08-06.md:15-22](../../../asset-portfolios/1d-ewmac-universal-trend/specs/xa-1d-ewmac-ut-portfolio-contract-2026-08-06.md)
- [research/asset-portfolios/1d-ewmac-universal-trend/diagnostics/xa-1d-ewmac-ut-portfolio-2026-08-06.md:7](../../../asset-portfolios/1d-ewmac-universal-trend/diagnostics/xa-1d-ewmac-ut-portfolio-2026-08-06.md)
- [research/asset-portfolios/1d-classic-ewmac-replication/diagnostics/xa-1d-classic-ewmac-replication-2026-08-10.md:60-63](../../../asset-portfolios/1d-classic-ewmac-replication/diagnostics/xa-1d-classic-ewmac-replication-2026-08-10.md)
- [research/gold/1d-multi-speed-tsmom/gold-1d-ms-tsmom-core-ledger.md:14-17](../../../gold/1d-multi-speed-tsmom/gold-1d-ms-tsmom-core-ledger.md)

### 12. 实盘尝试存在，运行和人工干预也阻断验证

EMA-TB V35 冻结后截至 2026-07-22 研究 +5.73%/12 笔、实盘时间加权 +0.525%/11 笔；9 笔自动退出路径没有显示实盘普遍跑差，主要差异来自两次人工平仓，同时 trade ledger 漏记费用亏损。PBTR V6.2.1 为授权 tiny-live-pilot，但 2026-09-03 报告记录 8 月 19 日 8.95 USDT 订单低于 50 最低名义，pending 恢复失败后 halted。日线 V7.1 截至 9 月 6 日才一笔自然闭合且存在缺 K 延迟。问题包含验证链尚未持续跑起来，不能当作充分实盘否证。

- [research/hype/15m-ema-trend-breakout/runner-tracking/hype-ema-tb-v35-post-freeze-live-parity-2026-07-22.md:9-18](../../../hype/15m-ema-trend-breakout/runner-tracking/hype-ema-tb-v35-post-freeze-live-parity-2026-07-22.md)
- 同文件 `:99-120`
- [research/hype/5m-pullback-trail/hype-5m-pullback-trail-core-ledger.md:13-18](../../../hype/5m-pullback-trail/hype-5m-pullback-trail-core-ledger.md)
- [research/hype/5m-pullback-trail/runner-tracking/hype-5m-pbtr-live-halted-incident-2026-09-03.md:24-41](../../../hype/5m-pullback-trail/runner-tracking/hype-5m-pbtr-live-halted-incident-2026-09-03.md)
- [research/hype/1d-ma7-asymmetric-body-trend/hype-1d-ma7-abt-core-ledger.md:14-16](../../../hype/1d-ma7-asymmetric-body-trend/hype-1d-ma7-abt-core-ledger.md)
- 限制：均为仓库记录快照，本轮未访问生产账户；不据此宣称当前服务状态，也不改变授权。

## 针对新投资条件的研究方向

优先新建“少量广泛资产 ETF、多头/现金、无杠杆、周或月频”独立家族，是符合小账户约束的合理待检验方向，不是投资收益承诺，也不是把 P4 的失败翻案。

1. 先冻结实际账户执行面：账户可交易范围、整股或碎股、最低佣金和订单大小、买卖价差、分红与调整价、现金收益、换汇、交易日历、结算与次日真实成交时序。
2. 使用少数文献固定规则，不逐资产调参；优先检验它相对等风险静态配置/现金基准是否改善回撤和尾部。单独展示总收益，不预设必须同时跑赢满仓 SPY 和拥有更小回撤。
3. 不复制 P4 参数，不继承其相关 0.01 或 50/50 Sharpe 0.82：删掉空头会失去部分危机保护来源，投资组合构造已改变。
4. 旧 P4 保持失败，新线已有历史仍是开发/诊断；固定一个可持续观察的版本，以新增时间和执行证据获得新信息。
5. 20%–30% 最大回撤是风险设计约束，不是任何策略能保证不穿越的硬地板。应先评估坏情形，决定研究目标风险预算，再锁定停止/降风险规则；不能回测后缩放到刚好通过。

## 对旧报告解释强度的审查

P4 报告中的“死结唯一就是成本”“信号本身没问题”“信号被证实”等表述比实际证据更强。借券/融资成本缺失、收盘成交近似、固定代理宇宙与 OOS 边界，已经阻止唯一归因。较严谨的结论是：在现有代理与约定成本下，存在毛收益或低相关迹象，日频调仓成本明显拖累；真实可执行净收益、独立验证及长期可靠性尚未证明。

## 辅助观察

- SOL V3 reused holdout 仅三笔，后续约十天 fresh forward 为零笔：[research/sol/1h-adaptive-regime/sol-1h-ar-core-ledger.md:15,33-37](../../../sol/1h-adaptive-regime/sol-1h-ar-core-ledger.md)。十天零交易不能验证或否定日线/低频策略。
- TRX V3 clean tune 12,531 唯一候选，收益/胜率/DD 同时改善零命中：[research/trx/1h-adaptive-regime/trx-1h-ar-core-ledger.md:113-115](../../../trx/1h-adaptive-regime/trx-1h-ar-core-ledger.md)。继续在同面追求三指标同时改善已进入明显边际收益递减。
- 加密 TSMOM 演示显示每年 34x 单边换手、五年价格 PnL +64.4%、成本 -23.9%、资金费 -11.7%：[research/asset-portfolios/1d-multi-asset-tsmom-vol-target/diagnostics/bin-1d-tsmom-vt-p0-demo-2026-07-27.md:24-32](../../../asset-portfolios/1d-multi-asset-tsmom-vol-target/diagnostics/bin-1d-tsmom-vt-p0-demo-2026-07-27.md)。这里的分解是报告口径，不与复利总收益直接相加；毛收益逐年正不足以证明真实可交易因子。

## 审计限制

本文件是一手仓库文件与部分 JSON 的只读证据整理，不是所有策略脚本和全部原始数据的独立复现。未确认当前实盘账户和服务状态。未更新任何策略身份、参数、运行授权或仓库文档。旧报告中的数据快照和指标不作为当前市场事实。
