# 全仓覆盖与未入榜原因

133个策略家族/主题，另100个公开策略原始条目；未入榜不等于亏损。主账摘录及文件指纹保存在机器清单。

| 状态 | 数量 |
|---|---:|
|模型已归档且不再回放|1|
|目录容器或基础设施|10|
|后续全市场输入检查未通过|1|
|缺少1分钟或5分钟输入|5|
|缺少必要辅助数据|1|
|缺少原模型或配置|2|
|不是完整账户策略|12|
|尚缺合格后续输入|10|
|现有行情早于定稿|12|
|未选出最终规则|28|
|已完成后续回放|54|
|原实现或选样有问题|7|

## 全部家族与主题

| 家族或主题 | 本轮状态 | 说明 | 主账/入口 |
|---|---|---|---|
|asset-portfolios/15m-asset-specific-six-strategy-selector|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/asset-portfolios/15m-asset-specific-six-strategy-selector/binance-15m-as6s-core-ledger.md)|
|asset-portfolios/15m-ema-cross-lightgbm-event-selector|未选出最终规则|主账没有可按当前正式版本登记表直接选取的最终可运行策略。搜索/模型/失败候选的历史成绩不自动等于最终版定稿后收益；本次没有替它另选搜索赢家。|[入口](../../../../research/asset-portfolios/15m-ema-cross-lightgbm-event-selector/binance-15m-emax-lgbm-core-ledger.md)|
|asset-portfolios/15m-multi-asset-trend-state-machine|未选出最终规则|主账没有可按当前正式版本登记表直接选取的最终可运行策略。搜索/模型/失败候选的历史成绩不自动等于最终版定稿后收益；本次没有替它另选搜索赢家。|[入口](../../../../research/asset-portfolios/15m-multi-asset-trend-state-machine/binance-15m-tsm-core-ledger.md)|
|asset-portfolios/15m-multi-indicator-intraday|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/asset-portfolios/15m-multi-indicator-intraday/binance-15m-mii-xfer-core-ledger.md)|
|asset-portfolios/1d-btceth-crisis-override-shadow-trend|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/asset-portfolios/1d-btceth-crisis-override-shadow-trend/binance-1d-be-cost-core-ledger.md)|
|asset-portfolios/1d-btceth-crisis-partial-profit-runner|未选出最终规则|原主账明确没有登记版本，开发搜索未选出可继续验证的唯一候选，研究线关闭；不替它在历史前沿中另挑一个赢家。|[入口](../../../../research/asset-portfolios/1d-btceth-crisis-partial-profit-runner/binance-1d-be-cppr-core-ledger.md)|
|asset-portfolios/1d-btceth-crisis-profit-exit-handoff-continuity|未选出最终规则|仅冻结了P0研究计划，原研究尚未运行，也没有选定最终配置；不是已有最终策略的后续回放。|[入口](../../../../research/asset-portfolios/1d-btceth-crisis-profit-exit-handoff-continuity/binance-1d-be-cpehc-core-ledger.md)|
|asset-portfolios/1d-btceth-cross-breadth-channel-trend|未选出最终规则|原主账明确没有登记版本，开发搜索未选出可继续验证的唯一候选，研究线关闭；不替它在历史前沿中另挑一个赢家。|[入口](../../../../research/asset-portfolios/1d-btceth-cross-breadth-channel-trend/binance-1d-be-cbct-core-ledger.md)|
|asset-portfolios/1d-btceth-dual-alpha-sleeve-ensemble|未选出最终规则|原主账明确没有登记版本，开发搜索未选出可继续验证的唯一候选，研究线关闭；不替它在历史前沿中另挑一个赢家。|[入口](../../../../research/asset-portfolios/1d-btceth-dual-alpha-sleeve-ensemble/binance-1d-be-dase-core-ledger.md)|
|asset-portfolios/1d-btceth-dual-horizon-campaign-trend|未选出最终规则|原主账明确没有登记版本，开发搜索未选出可继续验证的唯一候选，研究线关闭；不替它在历史前沿中另挑一个赢家。|[入口](../../../../research/asset-portfolios/1d-btceth-dual-horizon-campaign-trend/binance-1d-be-dhct-core-ledger.md)|
|asset-portfolios/1d-btceth-log-ratio-mean-reversion|未选出最终规则|原主账明确没有登记版本，开发搜索未选出可继续验证的唯一候选，研究线关闭；不替它在历史前沿中另挑一个赢家。|[入口](../../../../research/asset-portfolios/1d-btceth-log-ratio-mean-reversion/binance-1d-be-lrmr-core-ledger.md)|
|asset-portfolios/1d-btceth-relative-cycle-rotation|未选出最终规则|原主账明确没有登记版本，开发搜索未选出可继续验证的唯一候选，研究线关闭；不替它在历史前沿中另挑一个赢家。|[入口](../../../../research/asset-portfolios/1d-btceth-relative-cycle-rotation/binance-1d-be-rcr-core-ledger.md)|
|asset-portfolios/1d-bull-top10-30d-rotation|现有行情早于定稿|本地保存的是2026年9月研究时重跑的历史行情；本轮可用行情截至9月5日，不能把这类定稿前历史成绩当作定稿后的收益。|[入口](../../../../research/asset-portfolios/1d-bull-top10-30d-rotation/binance-1d-bt10r30-core-ledger.md)|
|asset-portfolios/1d-classic-ewmac-replication|尚缺合格后续输入|保留的外部市场/指数/代理历史没有可直接采用的定稿后完整账户结果；需补后续行情及其质量/交易模型检查，不能用旧历史收益顶替。|[入口](../../../../research/asset-portfolios/1d-classic-ewmac-replication/README.md)|
|asset-portfolios/1d-cross-asset-trend-lifecycle|不是完整账户策略|主账当前对象是数据、信号/事件、预测或机制研究；未确认一份当前最终交易规则及对应的定稿后完整账户结果。事件收益和预测分数不能作为账户收益入榜。|[入口](../../../../research/asset-portfolios/1d-cross-asset-trend-lifecycle/binance-1d-catl-core-ledger.md)|
|asset-portfolios/1d-derivatives-structure-trend-opportunity|原实现或选样有问题|主账记有实现、样本选择或复现未对齐问题；尚无排除该问题后的定稿后完整账户结果。具体问题见主账摘录，不能继续引用漂亮的旧成绩代替。|[入口](../../../../research/asset-portfolios/1d-derivatives-structure-trend-opportunity/binance-1d-dsto-core-ledger.md)|
|asset-portfolios/1d-ema-cross-lightgbm-event-selector|未选出最终规则|主账没有可按当前正式版本登记表直接选取的最终可运行策略。搜索/模型/失败候选的历史成绩不自动等于最终版定稿后收益；本次没有替它另选搜索赢家。|[入口](../../../../research/asset-portfolios/1d-ema-cross-lightgbm-event-selector/binance-1d-emax-lgbm-core-ledger.md)|
|asset-portfolios/1d-ewmac-universal-trend|尚缺合格后续输入|保留的外部市场/指数/代理历史没有可直接采用的定稿后完整账户结果；需补后续行情及其质量/交易模型检查，不能用旧历史收益顶替。|[入口](../../../../research/asset-portfolios/1d-ewmac-universal-trend/binance-1d-ewmac-ut-core-ledger.md)|
|asset-portfolios/1d-generic-ma7-trend|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/asset-portfolios/1d-generic-ma7-trend/binance-1d-gma7t-core-ledger.md)|
|asset-portfolios/1d-ma7-asset-local-temporal-audit|未选出最终规则|主账没有可按当前正式版本登记表直接选取的最终可运行策略。搜索/模型/失败候选的历史成绩不自动等于最终版定稿后收益；本次没有替它另选搜索赢家。|[入口](../../../../research/asset-portfolios/1d-ma7-asset-local-temporal-audit/binance-1d-ma7-alta-core-ledger.md)|
|asset-portfolios/1d-ma7-asset-specific-search|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/asset-portfolios/1d-ma7-asset-specific-search/binance-1d-ma7-as-search-core-ledger.md)|
|asset-portfolios/1d-ma7-atr14-long-short-audit|现有行情早于定稿|本地保存的是2026年9月研究时重跑的历史行情；本轮可用行情截至9月5日，不能把这类定稿前历史成绩当作定稿后的收益。|[入口](../../../../research/asset-portfolios/1d-ma7-atr14-long-short-audit/README.md)|
|asset-portfolios/1d-ma7-atr14-long-transfer|现有行情早于定稿|本地保存的是2026年9月研究时重跑的历史行情；本轮可用行情截至9月5日，不能把这类定稿前历史成绩当作定稿后的收益。|[入口](../../../../research/asset-portfolios/1d-ma7-atr14-long-transfer/README.md)|
|asset-portfolios/1d-ma7-basis-premium-meta-label|未选出最终规则|主账没有可按当前正式版本登记表直接选取的最终可运行策略。搜索/模型/失败候选的历史成绩不自动等于最终版定稿后收益；本次没有替它另选搜索赢家。|[入口](../../../../research/asset-portfolios/1d-ma7-basis-premium-meta-label/binance-1d-ma7-bpml-core-ledger.md)|
|asset-portfolios/1d-ma7-bidirectional-trend-generalization|现有行情早于定稿|本地保存的是2026年9月研究时重跑的历史行情；本轮可用行情截至9月5日，不能把这类定稿前历史成绩当作定稿后的收益。|[入口](../../../../research/asset-portfolios/1d-ma7-bidirectional-trend-generalization/ma7-btg-core-ledger.md)|
|asset-portfolios/1d-ma7-cross-atr-generalization|现有行情早于定稿|本地保存的是2026年9月研究时重跑的历史行情；本轮可用行情截至9月5日，不能把这类定稿前历史成绩当作定稿后的收益。|[入口](../../../../research/asset-portfolios/1d-ma7-cross-atr-generalization/bin-1d-ma7-car-gen-core-ledger.md)|
|asset-portfolios/1d-ma7-cross-expansion-regime|不是完整账户策略|主账当前对象是数据、信号/事件、预测或机制研究；未确认一份当前最终交易规则及对应的定稿后完整账户结果。事件收益和预测分数不能作为账户收益入榜。|[入口](../../../../research/asset-portfolios/1d-ma7-cross-expansion-regime/binance-1d-ma7-cer-core-ledger.md)|
|asset-portfolios/1d-ma7-cross-trend-probability|不是完整账户策略|主账当前对象是数据、信号/事件、预测或机制研究；未确认一份当前最终交易规则及对应的定稿后完整账户结果。事件收益和预测分数不能作为账户收益入榜。|[入口](../../../../research/asset-portfolios/1d-ma7-cross-trend-probability/binance-1d-ma7-ctp-core-ledger.md)|
|asset-portfolios/1d-ma7-derivatives-structure-meta-label|不是完整账户策略|主账当前对象是数据、信号/事件、预测或机制研究；未确认一份当前最终交易规则及对应的定稿后完整账户结果。事件收益和预测分数不能作为账户收益入榜。|[入口](../../../../research/asset-portfolios/1d-ma7-derivatives-structure-meta-label/binance-1d-ma7-dsml-core-ledger.md)|
|asset-portfolios/1d-ma7-deviation-continuation|不是完整账户策略|主账当前对象是数据、信号/事件、预测或机制研究；未确认一份当前最终交易规则及对应的定稿后完整账户结果。事件收益和预测分数不能作为账户收益入榜。|[入口](../../../../research/asset-portfolios/1d-ma7-deviation-continuation/binance-1d-ma7dc-core-ledger.md)|
|asset-portfolios/1d-ma7-later-maturity-meta-label|未选出最终规则|主账没有可按当前正式版本登记表直接选取的最终可运行策略。搜索/模型/失败候选的历史成绩不自动等于最终版定稿后收益；本次没有替它另选搜索赢家。|[入口](../../../../research/asset-portfolios/1d-ma7-later-maturity-meta-label/binance-1d-ma7-lmml-core-ledger.md)|
|asset-portfolios/1d-ma7-ma30-pyramiding-transfer|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/asset-portfolios/1d-ma7-ma30-pyramiding-transfer/binance-1d-ma-pt-xfer-core-ledger.md)|
|asset-portfolios/1d-ma7-quantile-utility-meta-label|原实现或选样有问题|主账记有实现、样本选择或复现未对齐问题；尚无排除该问题后的定稿后完整账户结果。具体问题见主账摘录，不能继续引用漂亮的旧成绩代替。|[入口](../../../../research/asset-portfolios/1d-ma7-quantile-utility-meta-label/binance-1d-ma7-quml-core-ledger.md)|
|asset-portfolios/1d-ma7-regime-continuation|不是完整账户策略|主账当前对象是数据、信号/事件、预测或机制研究；未确认一份当前最终交易规则及对应的定稿后完整账户结果。事件收益和预测分数不能作为账户收益入榜。|[入口](../../../../research/asset-portfolios/1d-ma7-regime-continuation/binance-1d-ma7-rc-core-ledger.md)|
|asset-portfolios/1d-ma7-rsi6-direction-aligned-pooled-ml|未选出最终规则|主账没有可按当前正式版本登记表直接选取的最终可运行策略。搜索/模型/失败候选的历史成绩不自动等于最终版定稿后收益；本次没有替它另选搜索赢家。|[入口](../../../../research/asset-portfolios/1d-ma7-rsi6-direction-aligned-pooled-ml/binance-1d-ma7-rsi6-dapml-core-ledger.md)|
|asset-portfolios/1d-ma7-separated-trend-transfer|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/asset-portfolios/1d-ma7-separated-trend-transfer/binance-1d-ma7-st-xfer-core-ledger.md)|
|asset-portfolios/1d-ma7-taker-flow-meta-label|原实现或选样有问题|主账记有实现、样本选择或复现未对齐问题；尚无排除该问题后的定稿后完整账户结果。具体问题见主账摘录，不能继续引用漂亮的旧成绩代替。|[入口](../../../../research/asset-portfolios/1d-ma7-taker-flow-meta-label/binance-1d-ma7-tfml-core-ledger.md)|
|asset-portfolios/1d-medium-term-continuation-state|现有行情早于定稿|本地保存的是2026年9月研究时重跑的历史行情；本轮可用行情截至9月5日，不能把这类定稿前历史成绩当作定稿后的收益。|[入口](../../../../research/asset-portfolios/1d-medium-term-continuation-state/binance-1d-mtcs-core-ledger.md)|
|asset-portfolios/1d-medium-term-trend-capture|现有行情早于定稿|本地保存的是2026年9月研究时重跑的历史行情；本轮可用行情截至9月5日，不能把这类定稿前历史成绩当作定稿后的收益。|[入口](../../../../research/asset-portfolios/1d-medium-term-trend-capture/binance-1d-mttc-core-ledger.md)|
|asset-portfolios/1d-monthly-cs-momentum-long10|现有行情早于定稿|本地保存的是2026年9月研究时重跑的历史行情；本轮可用行情截至9月5日，不能把这类定稿前历史成绩当作定稿后的收益。|[入口](../../../../research/asset-portfolios/1d-monthly-cs-momentum-long10/binance-1d-mcsm-l10-core-ledger.md)|
|asset-portfolios/1d-monthly-cs-momentum-ls3|后续全市场输入检查未通过|后续全市场输入已尝试检查：874代码请求在1000BTTC无有效窗口时失败，尚未完成可核验的整池重建，未补出账户回放。这个技术缺口不是策略亏损；不能只删掉失败代码就声称完整复现。详见 input_probes/ls3.json。|[入口](../../../../research/asset-portfolios/1d-monthly-cs-momentum-ls3/binance-1d-mcsm-ls3-core-ledger.md)|
|asset-portfolios/1d-multi-asset-tsmom-vol-target|未选出最终规则|主账没有可按当前正式版本登记表直接选取的最终可运行策略。搜索/模型/失败候选的历史成绩不自动等于最终版定稿后收益；本次没有替它另选搜索赢家。|[入口](../../../../research/asset-portfolios/1d-multi-asset-tsmom-vol-target/binance-1d-tsmom-vt-core-ledger.md)|
|asset-portfolios/1d-tradfi-futures-tsmom|尚缺合格后续输入|保留的外部市场/指数/代理历史没有可直接采用的定稿后完整账户结果；需补后续行情及其质量/交易模型检查，不能用旧历史收益顶替。|[入口](../../../../research/asset-portfolios/1d-tradfi-futures-tsmom/tf-1d-fut-tsmom-core-ledger.md)|
|asset-portfolios/1d-trend-prebreakout-state-atlas|现有行情早于定稿|本地保存的是2026年9月研究时重跑的历史行情；本轮可用行情截至9月5日，不能把这类定稿前历史成绩当作定稿后的收益。|[入口](../../../../research/asset-portfolios/1d-trend-prebreakout-state-atlas/binance-1d-tpsa-core-ledger.md)|
|asset-portfolios/1d-trend-strength-pullback-restart|现有行情早于定稿|本地保存的是2026年9月研究时重跑的历史行情；本轮可用行情截至9月5日，不能把这类定稿前历史成绩当作定稿后的收益。|[入口](../../../../research/asset-portfolios/1d-trend-strength-pullback-restart/binance-1d-tspr-core-ledger.md)|
|asset-portfolios/1d-turtle-breakout|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/asset-portfolios/1d-turtle-breakout/binance-1d-turtle-core-ledger.md)|
|asset-portfolios/1h-adaptive-regime-multi-asset-ensemble|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/asset-portfolios/1h-adaptive-regime-multi-asset-ensemble/binance-1h-ar-mae-core-ledger.md)|
|asset-portfolios/1h-btceth-cross-impulse-lead-lag|未选出最终规则|原主账明确没有登记版本，开发搜索未选出可继续验证的唯一候选，研究线关闭；不替它在历史前沿中另挑一个赢家。|[入口](../../../../research/asset-portfolios/1h-btceth-cross-impulse-lead-lag/binance-1h-be-cill-core-ledger.md)|
|asset-portfolios/1h-cross-sectional-lightgbm-selector|原实现或选样有问题|主账记有实现、样本选择或复现未对齐问题；尚无排除该问题后的定稿后完整账户结果。具体问题见主账摘录，不能继续引用漂亮的旧成绩代替。|[入口](../../../../research/asset-portfolios/1h-cross-sectional-lightgbm-selector/binance-1h-cslgbm-core-ledger.md)|
|asset-portfolios/1h-ema-cross-lightgbm-event-selector|未选出最终规则|主账没有可按当前正式版本登记表直接选取的最终可运行策略。搜索/模型/失败候选的历史成绩不自动等于最终版定稿后收益；本次没有替它另选搜索赢家。|[入口](../../../../research/asset-portfolios/1h-ema-cross-lightgbm-event-selector/binance-1h-emax-lgbm-core-ledger.md)|
|asset-portfolios/1h-four-asset-trend-habitat-audit|不是完整账户策略|主账当前对象是数据、信号/事件、预测或机制研究；未确认一份当前最终交易规则及对应的定稿后完整账户结果。事件收益和预测分数不能作为账户收益入榜。|[入口](../../../../research/asset-portfolios/1h-four-asset-trend-habitat-audit/binance-1h-fatha-core-ledger.md)|
|asset-portfolios/1h-ma7-root-hazard-timing|未选出最终规则|主账没有可按当前正式版本登记表直接选取的最终可运行策略。搜索/模型/失败候选的历史成绩不自动等于最终版定稿后收益；本次没有替它另选搜索赢家。|[入口](../../../../research/asset-portfolios/1h-ma7-root-hazard-timing/binance-1h-ma7-rht-core-ledger.md)|
|asset-portfolios/1h-multi-horizon-cross-sectional-ml-allocator|模型已归档且不再回放|V1 freeze R4已归档，主账明确放弃prospective OOS；本次不打开盲态结果，不用历史OOF收益排名，未重建被清理模型。|[入口](../../../../research/asset-portfolios/1h-multi-horizon-cross-sectional-ml-allocator/binance-1h-mhcsml-core-ledger.md)|
|asset-portfolios/1h-multi-leg-six-asset-selector|未选出最终规则|主账没有可按当前正式版本登记表直接选取的最终可运行策略。搜索/模型/失败候选的历史成绩不自动等于最终版定稿后收益；本次没有替它另选搜索赢家。|[入口](../../../../research/asset-portfolios/1h-multi-leg-six-asset-selector/binance-1h-ml6as-core-ledger.md)|
|asset-portfolios/1h-price-impulse-campaign|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/asset-portfolios/1h-price-impulse-campaign/binance-1h-pic-core-ledger.md)|
|asset-portfolios/1h-volatility-impulse-pullback-reclaim|未选出最终规则|主账没有可按当前正式版本登记表直接选取的最终可运行策略。搜索/模型/失败候选的历史成绩不自动等于最终版定稿后收益；本次没有替它另选搜索赢家。|[入口](../../../../research/asset-portfolios/1h-volatility-impulse-pullback-reclaim/binance-1h-vipr-core-ledger.md)|
|asset-portfolios/4h-bull-strong-rsi-atr-pullback|现有行情早于定稿|本地保存的是2026年9月研究时重跑的历史行情；本轮可用行情截至9月5日，不能把这类定稿前历史成绩当作定稿后的收益。|[入口](../../../../research/asset-portfolios/4h-bull-strong-rsi-atr-pullback/binance-4h-bsrap-core-ledger.md)|
|asset-portfolios/4h-ema-cross-lightgbm-event-selector|未选出最终规则|主账没有可按当前正式版本登记表直接选取的最终可运行策略。搜索/模型/失败候选的历史成绩不自动等于最终版定稿后收益；本次没有替它另选搜索赢家。|[入口](../../../../research/asset-portfolios/4h-ema-cross-lightgbm-event-selector/binance-4h-emax-lgbm-core-ledger.md)|
|asset-portfolios/4h-ma7-regime-continuation|不是完整账户策略|主账当前对象是数据、信号/事件、预测或机制研究；未确认一份当前最终交易规则及对应的定稿后完整账户结果。事件收益和预测分数不能作为账户收益入榜。|[入口](../../../../research/asset-portfolios/4h-ma7-regime-continuation/binance-4h-ma7-rc-core-ledger.md)|
|asset-portfolios/hype-cross-strategy-account|缺少1分钟或5分钟输入|需要1分钟或5分钟后续行情；当前登记数据目录13个输入没有1分钟/5分钟版本，本轮已有合格价格最小为15分钟。不能用15分钟插成5分钟；尚缺可核验的后续回放输入。|[入口](../../../../research/asset-portfolios/hype-cross-strategy-account/README.md)|
|asset-portfolios/mk7-multi-strategy-account|原实现或选样有问题|主账记有实现、样本选择或复现未对齐问题；尚无排除该问题后的定稿后完整账户结果。具体问题见主账摘录，不能继续引用漂亮的旧成绩代替。|[入口](../../../../research/asset-portfolios/mk7-multi-strategy-account/mk7-multi-strategy-account-core-ledger.md)|
|asset-portfolios/multi-timeframe-dual-state-trend-campaign|未选出最终规则|主账没有可按当前正式版本登记表直接选取的最终可运行策略。搜索/模型/失败候选的历史成绩不自动等于最终版定稿后收益；本次没有替它另选搜索赢家。|[入口](../../../../research/asset-portfolios/multi-timeframe-dual-state-trend-campaign/binance-mtf-dstc-core-ledger.md)|
|asset-portfolios/multi-timeframe-pullback-trend-campaign|未选出最终规则|主账没有可按当前正式版本登记表直接选取的最终可运行策略。搜索/模型/失败候选的历史成绩不自动等于最终版定稿后收益；本次没有替它另选搜索赢家。|[入口](../../../../research/asset-portfolios/multi-timeframe-pullback-trend-campaign/binance-mtf-ptc-core-ledger.md)|
|bnb/15m-adaptive-regime|未选出最终规则|主账没有可按当前正式版本登记表直接选取的最终可运行策略。搜索/模型/失败候选的历史成绩不自动等于最终版定稿后收益；本次没有替它另选搜索赢家。|[入口](../../../../research/bnb/15m-adaptive-regime/bnb-15m-ar-core-ledger.md)|
|bnb/1h-adaptive-regime|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/bnb/1h-adaptive-regime/bnb-1h-ar-core-ledger.md)|
|btc/15m-ema-trend-breakout|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/btc/15m-ema-trend-breakout/btc-15m-ema-tb-core-ledger.md)|
|btc/15m-keltner-trend-breakout|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/btc/15m-keltner-trend-breakout/btc-15m-keltner-trend-breakout-core-ledger.md)|
|btc/15m-trend-continuation|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/btc/15m-trend-continuation/btc-15m-trend-continuation-core-ledger.md)|
|btc/1d-classic-cta-trend|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/btc/1d-classic-cta-trend/btc-1d-ccta-core-ledger.md)|
|btc/1d-ma7-rsi6-lightgbm-trend|未选出最终规则|主账没有可按当前正式版本登记表直接选取的最终可运行策略。搜索/模型/失败候选的历史成绩不自动等于最终版定稿后收益；本次没有替它另选搜索赢家。|[入口](../../../../research/btc/1d-ma7-rsi6-lightgbm-trend/btc-1d-ma7-rsi6-lgbm-core-ledger.md)|
|btc/1d-qingze-critical-point-trend|缺少必要辅助数据|原规格必需的20日持仓量高位过滤缺少历史数据；不删掉过滤器后冒称复现。|[入口](../../../../research/btc/1d-qingze-critical-point-trend/btc-1d-qz-cpt-core-ledger.md)|
|btc/1h-adaptive-regime|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/btc/1h-adaptive-regime/btc-1h-ar-core-ledger.md)|
|btc/1w-ma7-asymmetric-body-trend|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/btc/1w-ma7-asymmetric-body-trend/btc-1w-ma7-abt-core-ledger.md)|
|btc/30m-trend-continuation|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/btc/30m-trend-continuation/btc-30m-trend-continuation-core-ledger.md)|
|cn-indexes/1d-hype-ma7-v7-1-transfer|尚缺合格后续输入|保留的外部市场/指数/代理历史没有可直接采用的定稿后完整账户结果；需补后续行情及其质量/交易模型检查，不能用旧历史收益顶替。|[入口](../../../../research/cn-indexes/1d-hype-ma7-v7-1-transfer/csi300-1d-hm7-xfer-core-ledger.md)|
|eth/1h-adaptive-regime|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/eth/1h-adaptive-regime/eth-1h-ar-core-ledger.md)|
|gold/1d-multi-speed-tsmom|尚缺合格后续输入|保留的外部市场/指数/代理历史没有可直接采用的定稿后完整账户结果；需补后续行情及其质量/交易模型检查，不能用旧历史收益顶替。|[入口](../../../../research/gold/1d-multi-speed-tsmom/gold-1d-ms-tsmom-core-ledger.md)|
|hype/15m-bollinger-keltner-squeeze-breakout|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/hype/15m-bollinger-keltner-squeeze-breakout/hype-15m-bksb-core-ledger.md)|
|hype/15m-candle-count-reversal|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/hype/15m-candle-count-reversal/hype-cc-core-ledger.md)|
|hype/15m-ema-crossover|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/hype/15m-ema-crossover/hype-ema-x-core-ledger.md)|
|hype/15m-ema-trend-breakout|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/hype/15m-ema-trend-breakout/hype-ema-tb-core-ledger.md)|
|hype/15m-factor-ml|缺少原模型或配置|原41家族核查已确认冻结模型/候选JSON缺失：factor-ML缺最终模型和manifest；15m MHEF缺V2完整候选JSON。不能拿默认参数顶替。|[入口](../../../../research/hype/15m-factor-ml/hype-15m-factor-ml-core-ledger.md)|
|hype/15m-keltner-trend-breakout|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/hype/15m-keltner-trend-breakout/hype-15m-keltner-trend-breakout-core-ledger.md)|
|hype/15m-ma7-ma30-pyramiding|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/hype/15m-ma7-ma30-pyramiding/hype-15m-ma-pt-core-ledger.md)|
|hype/15m-multi-horizon-ema-forecast|缺少原模型或配置|原41家族核查已确认冻结模型/候选JSON缺失：factor-ML缺最终模型和manifest；15m MHEF缺V2完整候选JSON。不能拿默认参数顶替。|[入口](../../../../research/hype/15m-multi-horizon-ema-forecast/hype-15m-mhef-core-ledger.md)|
|hype/15m-multi-indicator-intraday|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/hype/15m-multi-indicator-intraday/hype-15m-mii-core-ledger.md)|
|hype/15m-multi-mechanism-trend-following|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/hype/15m-multi-mechanism-trend-following/hype-15m-mmtf-core-ledger.md)|
|hype/15m-multi-timeframe-probe-pyramiding|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/hype/15m-multi-timeframe-probe-pyramiding/hype-15m-mtpp-core-ledger.md)|
|hype/15m-multidimensional-trend-pyramiding|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/hype/15m-multidimensional-trend-pyramiding/hype-15m-mdtp-core-ledger.md)|
|hype/15m-price-kinematics-continuation|不是完整账户策略|主账当前对象是数据、信号/事件、预测或机制研究；未确认一份当前最终交易规则及对应的定稿后完整账户结果。事件收益和预测分数不能作为账户收益入榜。|[入口](../../../../research/hype/15m-price-kinematics-continuation/hype-15m-pkc-core-ledger.md)|
|hype/15m-pullback-trail|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/hype/15m-pullback-trail/hype-15m-pbtr-core-ledger.md)|
|hype/15m-riptide|原实现或选样有问题|主账记有实现、样本选择或复现未对齐问题；尚无排除该问题后的定稿后完整账户结果。具体问题见主账摘录，不能继续引用漂亮的旧成绩代替。|[入口](../../../../research/hype/15m-riptide/hype-15m-riptide-core-ledger.md)|
|hype/15m-sequential-drift-state|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/hype/15m-sequential-drift-state/hype-15m-sds-core-ledger.md)|
|hype/15m-sma-crossover-slope|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/hype/15m-sma-crossover-slope/hype-15m-sma-xs-core-ledger.md)|
|hype/15m-trend-breakout-multi-indicator-ensemble|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/hype/15m-trend-breakout-multi-indicator-ensemble/hype-15m-tb-mii-ens-core-ledger.md)|
|hype/1d-15m-hierarchical-trend-opportunity|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/hype/1d-15m-hierarchical-trend-opportunity/hype-d15-hto-core-ledger.md)|
|hype/1d-bollinger-keltner-squeeze-breakout|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/hype/1d-bollinger-keltner-squeeze-breakout/hype-1d-bksb-core-ledger.md)|
|hype/1d-ma7-asymmetric-body-trend|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/hype/1d-ma7-asymmetric-body-trend/hype-1d-ma7-abt-core-ledger.md)|
|hype/1d-ma7-cross-atr-ratchet|现有行情早于定稿|本地保存的是2026年9月研究时重跑的历史行情；本轮可用行情截至9月5日，不能把这类定稿前历史成绩当作定稿后的收益。|[入口](../../../../research/hype/1d-ma7-cross-atr-ratchet/hype-1d-ma7-car-core-ledger.md)|
|hype/1d-ma7-machine-learning-trend|不是完整账户策略|主账当前对象是数据、信号/事件、预测或机制研究；未确认一份当前最终交易规则及对应的定稿后完整账户结果。事件收益和预测分数不能作为账户收益入榜。|[入口](../../../../research/hype/1d-ma7-machine-learning-trend/hype-1d-ma7-mlt-core-ledger.md)|
|hype/1d-multi-horizon-ema-forecast|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/hype/1d-multi-horizon-ema-forecast/hype-1d-mhef-core-ledger.md)|
|hype/1d-price-kinematics-continuation|不是完整账户策略|主账当前对象是数据、信号/事件、预测或机制研究；未确认一份当前最终交易规则及对应的定稿后完整账户结果。事件收益和预测分数不能作为账户收益入榜。|[入口](../../../../research/hype/1d-price-kinematics-continuation/hype-1d-pkc-core-ledger.md)|
|hype/1d-pyramiding-trend|未选出最终规则|主账没有可按当前正式版本登记表直接选取的最终可运行策略。搜索/模型/失败候选的历史成绩不自动等于最终版定稿后收益；本次没有替它另选搜索赢家。|[入口](../../../../research/hype/1d-pyramiding-trend/hype-1d-pt-core-ledger.md)|
|hype/1h-adaptive-regime|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/hype/1h-adaptive-regime/hype-1h-ar-core-ledger.md)|
|hype/1h-bollinger-keltner-squeeze-breakout|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/hype/1h-bollinger-keltner-squeeze-breakout/hype-1h-bksb-core-ledger.md)|
|hype/1h-multi-horizon-ema-forecast|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/hype/1h-multi-horizon-ema-forecast/hype-1h-mhef-core-ledger.md)|
|hype/1h-multi-mechanism-trend-following|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/hype/1h-multi-mechanism-trend-following/hype-1h-mmtf-core-ledger.md)|
|hype/1h-price-kinematic-trend-survival-control|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/hype/1h-price-kinematic-trend-survival-control/hype-1h-pktsc-core-ledger.md)|
|hype/1h-price-kinematics-continuation|不是完整账户策略|主账当前对象是数据、信号/事件、预测或机制研究；未确认一份当前最终交易规则及对应的定稿后完整账户结果。事件收益和预测分数不能作为账户收益入榜。|[入口](../../../../research/hype/1h-price-kinematics-continuation/hype-1h-pkc-core-ledger.md)|
|hype/1m-ema-crossover|缺少1分钟或5分钟输入|需要1分钟或5分钟后续行情；当前登记数据目录13个输入没有1分钟/5分钟版本，本轮已有合格价格最小为15分钟。不能用15分钟插成5分钟；尚缺可核验的后续回放输入。|[入口](../../../../research/hype/1m-ema-crossover/hype-1m-ema-x-core-ledger.md)|
|hype/1m-ma-pullback-scalp|未选出最终规则|主账没有可按当前正式版本登记表直接选取的最终可运行策略。搜索/模型/失败候选的历史成绩不自动等于最终版定稿后收益；本次没有替它另选搜索赢家。|[入口](../../../../research/hype/1m-ma-pullback-scalp/hype-1m-ma-pbs-core-ledger.md)|
|hype/30m-keltner-breakout-retest|未选出最终规则|主账没有可按当前正式版本登记表直接选取的最终可运行策略。搜索/模型/失败候选的历史成绩不自动等于最终版定稿后收益；本次没有替它另选搜索赢家。|[入口](../../../../research/hype/30m-keltner-breakout-retest/hype-30m-keltner-breakout-retest-core-ledger.md)|
|hype/30m-keltner-trend-breakout|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/hype/30m-keltner-trend-breakout/hype-30m-keltner-trend-breakout-core-ledger.md)|
|hype/4h-bollinger-keltner-squeeze-breakout|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/hype/4h-bollinger-keltner-squeeze-breakout/hype-4h-bksb-core-ledger.md)|
|hype/4h-ma7-asymmetric-body-trend|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/hype/4h-ma7-asymmetric-body-trend/hype-4h-ma7-abt-core-ledger.md)|
|hype/4h-ma7-close-reversal|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/hype/4h-ma7-close-reversal/hype-4h-ma7-cr-core-ledger.md)|
|hype/4h-ma7-rsi6-asymmetric-reversal|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/hype/4h-ma7-rsi6-asymmetric-reversal/hype-4h-ma7-rsi6-ar-core-ledger.md)|
|hype/5m-event-quality-scoring|原实现或选样有问题|主账记有实现、样本选择或复现未对齐问题；尚无排除该问题后的定稿后完整账户结果。具体问题见主账摘录，不能继续引用漂亮的旧成绩代替。|[入口](../../../../research/hype/5m-event-quality-scoring/hype-5m-event-quality-scoring-core-ledger.md)|
|hype/5m-ma-pullback-scalp|缺少1分钟或5分钟输入|需要1分钟或5分钟后续行情；当前登记数据目录13个输入没有1分钟/5分钟版本，本轮已有合格价格最小为15分钟。不能用15分钟插成5分钟；尚缺可核验的后续回放输入。|[入口](../../../../research/hype/5m-ma-pullback-scalp/hype-5m-ma-pbs-core-ledger.md)|
|hype/5m-micro-scalp|缺少1分钟或5分钟输入|需要1分钟或5分钟后续行情；当前登记数据目录13个输入没有1分钟/5分钟版本，本轮已有合格价格最小为15分钟。不能用15分钟插成5分钟；尚缺可核验的后续回放输入。|[入口](../../../../research/hype/5m-micro-scalp/hype-5m-micro-scalp-core-ledger.md)|
|hype/5m-pullback-trail|缺少1分钟或5分钟输入|需要1分钟或5分钟后续行情；当前登记数据目录13个输入没有1分钟/5分钟版本，本轮已有合格价格最小为15分钟。不能用15分钟插成5分钟；尚缺可核验的后续回放输入。|[入口](../../../../research/hype/5m-pullback-trail/hype-5m-pullback-trail-core-ledger.md)|
|hype/6h-rs4-regime-switch|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/hype/6h-rs4-regime-switch/hype-6h-rs4-regime-switch-core-ledger.md)|
|mu/15m-donchian-trend-breakout|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/mu/15m-donchian-trend-breakout/mu-15m-dtb-core-ledger.md)|
|mu/1d-ma7-separated-trend-transfer|尚缺合格后续输入|保留的外部市场/指数/代理历史没有可直接采用的定稿后完整账户结果；需补后续行情及其质量/交易模型检查，不能用旧历史收益顶替。|[入口](../../../../research/mu/1d-ma7-separated-trend-transfer/mu-1d-ma7-st-xfer-core-ledger.md)|
|sol/1h-adaptive-regime|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/sol/1h-adaptive-regime/sol-1h-ar-core-ledger.md)|
|sol/1h-pullback-bracket|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/sol/1h-pullback-bracket/sol-1h-pb-core-ledger.md)|
|sol/1h-volatility-compression-breakout|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/sol/1h-volatility-compression-breakout/sol-1h-vcb-core-ledger.md)|
|sol/4h-rs4-regime-switch|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/sol/4h-rs4-regime-switch/sol-4h-rs4-core-ledger.md)|
|sox/1d-ma7-asset-specific-search|尚缺合格后续输入|保留的外部市场/指数/代理历史没有可直接采用的定稿后完整账户结果；需补后续行情及其质量/交易模型检查，不能用旧历史收益顶替。|[入口](../../../../research/sox/1d-ma7-asset-specific-search/sox-1d-ma7-as-search-core-ledger.md)|
|sox/1d-ma7-separated-trend-transfer|尚缺合格后续输入|保留的外部市场/指数/代理历史没有可直接采用的定稿后完整账户结果；需补后续行情及其质量/交易模型检查，不能用旧历史收益顶替。|[入口](../../../../research/sox/1d-ma7-separated-trend-transfer/sox-1d-ma7-st-xfer-core-ledger.md)|
|trx/1h-adaptive-regime|已完成后续回放|已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。|[入口](../../../../research/trx/1h-adaptive-regime/trx-1h-ar-core-ledger.md)|
|us-indexes/1d-ma7-shared-parameter-transfer|尚缺合格后续输入|保留的外部市场/指数/代理历史没有可直接采用的定稿后完整账户结果；需补后续行情及其质量/交易模型检查，不能用旧历史收益顶替。|[入口](../../../../research/us-indexes/1d-ma7-shared-parameter-transfer/us-indexes-1d-ma7-sp-xfer-core-ledger.md)|
|us-indexes/1d-nasdaq100-ma7-regime-continuation|尚缺合格后续输入|保留的外部市场/指数/代理历史没有可直接采用的定稿后完整账户结果；需补后续行情及其质量/交易模型检查，不能用旧历史收益顶替。|[入口](../../../../research/us-indexes/1d-nasdaq100-ma7-regime-continuation/ndx100-1d-ma7-rc-core-ledger.md)|

## 公开100条

| ID | 名称 | 状态 |
|---|---|---|
|A1|道指 30 CAPM 阿尔法排序|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A2|双推力突破|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A3|晨星基本面选股|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A4|短期价格反转|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A5|基本面多空|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A6|大类资产趋势|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A7|大类资产动量|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A8|残差动量|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A9|行业动量|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A10|隔夜异象|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A11|低波动|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A12|配对交易（平方偏差）|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A13|一个月反转|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A14|12 个月动量|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A15|国家指数动量|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A16|国家指数均值回归|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A17|流动性 / 换手率|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A18|波动率风险溢价|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A19|小盘溢价|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A20|配对切换|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A21|账面市值比|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A22|月末效应|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A23|动量里的短期反转|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A24|国家 ETF 配对|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A25|情绪风格轮动|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A26|资产增长异象|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A27|看市场状态的动量|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A28|应计异象|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A29|风格 ETF 动量|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A30|REIT 动量|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A31|期权到期周|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A32|盈利质量因子|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A33|一月效应|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A34|高波动里的动量反转|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A35|市值组内 ROA|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A36|一月晴雨表|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A37|月相与新兴市场|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A38|VIX 分位择时|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A39|动量加成交量|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A40|节前效应|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A41|低贝塔|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A42|同日历月循环|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A43|集中 12 个月动量|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A44|国家 CAPE 价值|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A45|国家 ETF 贝塔|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A46|低市盈率|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A47|Fama-French 五因子|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A48|股票统计套利|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A49|预期特异偏度|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A50|同日历月季节性|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A51|标准化超预期盈利|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A52|价格动量加盈利动量|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A53|杠杆 ETF 均线|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A54|能源股一目均衡|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A55|ETF 日内动量|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A56|指数 ETF 日内套利|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A57|科技股 G-Score|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A58|药企新闻情绪|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A59|科技股朴素贝叶斯|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|A60|梯度提升日内预测|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|B1|基础配对阿尔法|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|B2|相关配对阿尔法|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|B3|开盘区间突破（活跃股）|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|B4|开盘区间突破论文版|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|B5|防御性自适应配置 KDA 移植版|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|C1|全球股票动量 GEM|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|C2|流动的股票动量|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|C3|周末趋势交易|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|C4|KDA 原文|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|C5|突破波段|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|C6|事件跳空|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|C7|抛物线做空|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|C8|同一作者的仓位规则|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|C9|相对强度动量组合|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|C10|两资产趋势仓|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|D1|资金费率 Z 分数|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|D2|资金费率动量|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|D3|截面 Z 分数动量|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|D4|相对 BTC 的残差回归|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|D5|资金费率事件反向|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|D6|Boros 资金费率均值回归|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|D7|逢跌买入|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|D8|RSI 加布林|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|D9|EMA 趋势加 ADX|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|D10|MACD 动量突破|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|E1|@Team2Trading|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|E2|@EllyDtrades|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|E3|@ChiefPowrTrendz|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|E4|@SRxTrades|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|E5|@FelipeGuirao|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|E6|@karthimaths|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|E7|@PBInvesting|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|E8|@scorpiomanojFRM|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|E9|同一作者第二套|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|E10|@Mc5calpAfee|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|E11|@ripster47|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|E12|@Tradewrite|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|E13|@ameyanifty|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|E14|Ramsay Rippers|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
|E15|@ripster47 趋势日过滤|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|
