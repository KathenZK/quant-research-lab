# 量化研究方法只读审计（2026-09-08）

范围：近期 CTP、CATL、TPSA、BTC MA7-RSI6、DAPML、DSML、MHCSML。已核对当前仓库文档，部分核对脚本；未重新训练或重算收益。本文路径均相对于 `/Users/ZK/OpenCode/quant-strategy-lab`。

结论：近期研究并非完全没有统计信号，而是长期停留在事件解释和概率排序，未持续完成冻结模型、可执行组合和完整前瞻验证的链条。现有结果也不支持继续叠加同源技术指标及 ML 复杂度。

## 12 条证据

1. **当前事实：MHCSML R4 已归档，原前瞻正式放弃。** [research/asset-portfolios/1h-multi-horizon-cross-sectional-ml-allocator/binance-1h-mhcsml-core-ledger.md:13-19](../../../asset-portfolios/1h-multi-horizon-cross-sectional-ml-allocator/binance-1h-mhcsml-core-ledger.md) 明确，2026-08-04 磁盘清理删除模型、freeze 合同、盲链快照与 prospective 数据，08-05 决定不重建。[research/asset-portfolios/1h-multi-horizon-cross-sectional-ml-allocator/artifacts/README.md:3-8](../../../asset-portfolios/1h-multi-horizon-cross-sectional-ml-allocator/artifacts/README.md) 明确历史指标不具备本地独立复现证据。这是研究资产连续性损失，不是市场证伪。旧 memory/watchdog 状态已过时。历史 OOF 年化 59.30%、Sharpe 4.49、7/7 折盈利只能作为旧开发结论，不能据此恢复原候选身份。

2. **当前事实及推断：2025+ 已被多轮研究消费，不再是独立验证资源。** [research/asset-portfolios/1d-ma7-cross-trend-probability/binance-1d-ma7-ctp-core-ledger.md:50-58](../../../asset-portfolios/1d-ma7-cross-trend-probability/binance-1d-ma7-ctp-core-ledger.md) 记录 P5 reused validation、P6 受已观察结果启发、P7 reused diagnostic。跨研究改名或物理分家不能让同一共同市场历史重新变成盲测。推断：短缺的是独立时间证据，而不是资产行数、特征数或迭代编号。

3. **当前事实：P7A 安慰剂削弱了把约三成成功率当作 MA7 预测能力的直觉。** [research/asset-portfolios/1d-ma7-cross-trend-probability/diagnostics/binance-1d-ma7-ctp-p7a-placebo-base-rate-audit-2026-09-04.md:3-18](../../../asset-portfolios/1d-ma7-cross-trend-probability/diagnostics/binance-1d-ma7-ctp-p7a-placebo-base-rate-audit-2026-09-04.md)：实际 MA7 成功率 31.9700%，同穿越 asset-date 随机方向 31.0272%，同日 non-cross 随机方向 29.9074%。`:43-47`：方向增量 +0.9428pp，28 日块 CI [-0.0874pp,+1.9926pp]；movement 增量 +1.1198pp。约三成主要是屏障/路径基础概率。边界：本轮检验裸 MA7，不逻辑否定 B0 条件筛选的所有可能价值；`:18` 明确它是与 P7 并行、不读 P7 的独立 sidecar diagnostic。

4. **当前事实：P7B 牛熊六格未证明 MA7 额外方向优势。** [research/asset-portfolios/1d-ma7-cross-trend-probability/diagnostics/binance-1d-ma7-ctp-p7b-regime-conditional-direction-placebo-audit-2026-09-04.md:3-35](../../../asset-portfolios/1d-ma7-cross-trend-probability/diagnostics/binance-1d-ma7-ctp-p7b-regime-conditional-direction-placebo-audit-2026-09-04.md)：牛市向上 incremental MA7 +1.2635pp，CI 穿 0；熊市向下 -0.0048pp；顺市场状态效果 -0.3228pp，CI 穿 0；裁决 REGIME_DRIFT_EXPLAINS_APPARENT_EDGE。`:50-66` 记录年度翻转及 2025+ 牛市向上增量 -0.8988pp。这是看过 P7A/P6 后的 targeted diagnostic，不能叫新盲测。`:108` 及 [research/asset-portfolios/1d-ma7-cross-trend-probability/diagnostics/binance-1d-ma7-ctp-p7b-deferred-registration-2026-09-04.md:3-15](../../../asset-portfolios/1d-ma7-cross-trend-probability/diagnostics/binance-1d-ma7-ctp-p7b-deferred-registration-2026-09-04.md) 说明因并行工作尚未更新共享主账，仅读主账会漏掉最新结果。

5. **已修复事实：P5 统计实现缺陷与测试语义不足曾影响科学结论的可信度。** [research/asset-portfolios/1d-ma7-cross-trend-probability/diagnostics/binance-1d-ma7-ctp-p5-independent-acceptance-audit-2026-09-02.md:121-134](../../../asset-portfolios/1d-ma7-cross-trend-probability/diagnostics/binance-1d-ma7-ctp-p5-independent-acceptance-audit-2026-09-02.md)：原 bootstrap 对块内非线性指标先算再平均，CI/p/q 无效；校准使用当时未完成标签；阈值混用不同 Platt 概率空间。修复后无增量结论不变，不能说负结果都是代码造成；但测试通过和脚本一致不足以取代统计语义验收。

6. **当前事实：B0 有弱总事件排序，但诊断分组与可执行账户之间仍有断层。** 上述 P5 独立审计 `:65-78`：B0 year-relative Top10 成功率 35.11%，裸基线 31.72%，事件净均值 0.23%、中位数 -5.70%。`:95-109`：Top10 净均值 8/17 月及 9/18 块为负；全年预测后再取年度最高十分位是诊断分组，不能直接当作当日已知入场门槛。重要边界见 [research/asset-portfolios/1d-ma7-cross-trend-probability/specs/binance-1d-ma7-ctp-p0-p6-external-review-reproduction-spec-2026-09-04.md:20-24](../../../asset-portfolios/1d-ma7-cross-trend-probability/specs/binance-1d-ma7-ctp-p0-p6-external-review-reproduction-spec-2026-09-04.md)：同日同方向选币失败不能逻辑上推翻跨日期总事件弱排序，不应强加同日选币为原始问题的必要成功条件。

7. **当前阻断：CTP B0 不能直接接前瞻，冻结分数无法精确重构。** [research/asset-portfolios/1d-ma7-cross-trend-probability/diagnostics/binance-1d-ma7-ctp-p7-temporal-drift-calibration-decomposition-2026-09-04.md:3-10](../../../asset-portfolios/1d-ma7-cross-trend-probability/diagnostics/binance-1d-ma7-ctp-p7-temporal-drift-calibration-decomposition-2026-09-04.md) 与 `:20-30`：当前 P5 脚本 hash 与 manifest 一致，development raw probability 最大误差仍为 0.00928714，final 2025+ 误差 0.000207733，均超过原 1e-8。裁决 DATA_OR_REPRODUCTION_FAILURE，停止 drift/calibration 机制归因。它不证明旧 P5 每个数值虚假，但阻止把当前实现称为同一冻结可执行模型。

8. **当前事实：CATL 的失败词过度概括，不能用词表代替具体证据。** [research/asset-portfolios/1d-cross-asset-trend-lifecycle/diagnostics/binance-1d-catl-p1-entry-model-2026-08-31.md:23-30](../../../asset-portfolios/1d-cross-asset-trend-lifecycle/diagnostics/binance-1d-catl-p1-entry-model-2026-08-31.md)：Entry terminal AUC 0.5698。`:50-60`：相对 MA_PROBE_LOGIT AUC +0.0506、95% CI [0.0145,0.0906]；失败的是 cross-market 块相对 FULL_NO_CROSS_MARKET 开发增量只有 +0.0004。[research/asset-portfolios/1d-cross-asset-trend-lifecycle/scripts/run_binance_1d_catl_p1_donor_walk_forward_modeling.py:2212-2227](../../../asset-portfolios/1d-cross-asset-trend-lifecycle/scripts/run_binance_1d_catl_p1_donor_walk_forward_modeling.py) 将任一增量门失败统一映射为 LEARNABLE_BUT_NOT_INCREMENTAL_BEYOND_MA，不能据此概括为价格模型完全没增量。报告 `:25,60,99-101` 同时表明 428,990 个 terminal landmark 去除 20 日重叠仅剩 21,972、AUC 降至 0.5285，且无仓位、资本占用、撮合和账户；行数不是独立机会数。

9. **当前失败：BTC 正收益表象没有通过稀疏样本与阈值稳定性门。** [research/btc/1d-ma7-rsi6-lightgbm-trend/diagnostics/btc-1d-ma7-rsi6-logistic-ev-p3-robustness-2026-08-10.md:5-18](../../../btc/1d-ma7-rsi6-lightgbm-trend/diagnostics/btc-1d-ma7-rsi6-logistic-ev-p3-robustness-2026-08-10.md)：combined 仅 47 笔、4 折只有 2 折正收益、bootstrap 净正概率 60.94%。`:44-69`：predicted EV 门槛从 1.0% 提到 1.5% 后收益反而 -18.28%；short-only 虽好看但仅 14 笔。这支持样本和排序稳定性不足，不应靠降低门槛或只展示赚钱分腿解决。

10. **当前失败：五资产、方向对齐及 LightGBM 没有解决同源状态的迁移性。** [research/asset-portfolios/1d-ma7-rsi6-direction-aligned-pooled-ml/diagnostics/binance-1d-ma7-rsi6-dapml-p1-pooled-development-2026-08-10.md:5-18](../../../asset-portfolios/1d-ma7-rsi6-direction-aligned-pooled-ml/diagnostics/binance-1d-ma7-rsi6-dapml-p1-pooled-development-2026-08-10.md)：事件数从 449 扩到 2,091。`:20-42`：temporal combined 每笔 -0.158%、Spearman -0.044；LOAO combined 每笔 -0.095%、Spearman -0.030；long-only 每笔 +0.032% 低于 all-cross long +0.441%。`:59-69`：LightGBM 正收益分支仍缺时间稳定性、排序为负。支持停止同一 MA7/K 线/RSI6/当前退出标签上的微调，不支持否定全部中低频策略。

11. **容量失败，独立信息假说未被证伪：DSML 根本未进入建模。** [research/asset-portfolios/1d-ma7-derivatives-structure-meta-label/diagnostics/binance-1d-ma7-dsml-p0-capacity-2026-08-10.md:5-23](../../../asset-portfolios/1d-ma7-derivatives-structure-meta-label/diagnostics/binance-1d-ma7-dsml-p0-capacity-2026-08-10.md)：四个 altcoin 官方 metrics 2021-12 才开始，加入上下文后稀疏 maturity events 最多只剩 967/1,448，四项容量门不可达。失败的是把独立衍生品信息附加到既有稀疏标签的采样设计。可另立覆盖期内每日全锚点及独立经济机制研究；不是在旧事件上再加 OI 或降低门槛。

12. **可低预算保留假设，但没有当前可运行候选：TPSA P1 long。** [research/asset-portfolios/1d-trend-prebreakout-state-atlas/diagnostics/binance-1d-trend-prebreakout-state-atlas-p1-barrier-ml-2026-08-25.md:11-17,28-45](../../../asset-portfolios/1d-trend-prebreakout-state-atlas/diagnostics/binance-1d-trend-prebreakout-state-atlas-p1-barrier-ml-2026-08-25.md)：低波、回撤后稳定再向上突破；MA7 LightGBM 5/5 年 AUC>0.5、均值 0.582，MA30 4/4 年、均值 0.548。两条均线方向一致值得保留，但只是探索性 first-hit 排序，无账户盈利证明。[research/asset-portfolios/1d-trend-prebreakout-state-atlas/scripts/run_binance_1d_trend_prebreakout_state_atlas_p1_barrier_ml.py:112-116](../../../asset-portfolios/1d-trend-prebreakout-state-atlas/scripts/run_binance_1d_trend_prebreakout_state_atlas_p1_barrier_ml.py) 按完整测试期分数 qcut 分组；`:453-519` 保存预测、画像和树规则，没有导出最终冻结模型与 imputer。只能保留一条假设，先补可执行冻结对象及账户可行性审核，再决定启动新前瞻，不能叫已有 dry-run 候选。

## 建议与新用户约束

用户当前资金约 10,000 美元，可承受回撤 20%–30%，允许非加密市场。近期 ML 家族没有一个同时满足冻结产物完整、账户规则可执行、独立前瞻已成立的当前候选。

建议把主研究预算转到一个独立的跨市场慢速低换手 ETF 多头/现金家族：先写收益来源、可交易资产、时点、交易成本、资金占用和风险限制，再冻结少量简单趋势与持有基准，评估净收益和风险价值。该主方向是研究建议，不是当前已证明盈利的策略；资金规模与回撤约束需要体现在账户合同中，不能通过事后加杠杆制造通过。

ML 仅保留 TPSA long 一条低预算假设，暂停新增价格特征、模型容量和已看历史优化。先做数据/模型复现和从概率到订单的账户可行性检查，通过后才以唯一冻结对象进入新前瞻。CTP B0 先解决重构阻断；R4 不恢复旧身份；BTC/DAPML 不继续同机制微调；DSML 可留作未来独立信息源研究储备。

归因排序为研究目标到实盘目标的转化断层、同源价格信息反复优化、独立时间证据不足、冻结与保存失败、局部数据和统计实现缺陷。现有证据不足以裁决所有技术指标中低频策略都不行。

记忆仅用于定位：`/Users/ZK/.codex/memories/MEMORY.md:65-110`；当前仓库状态优先，特别是 R4 已归档及 CTP 新 sidecar 诊断。
