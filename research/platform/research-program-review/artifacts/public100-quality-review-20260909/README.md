# PUBLIC100质地审查证据

日期：2026-09-09。归属研究计划整体审计的诊断主题；没有登记或晋升策略，没有改动PUBLIC100原材料、数据湖及并发补测任务。

入口：[综合评价与资源取舍](../../diagnostics/public100-strategy-quality-review-2026-09-09.md)。

## 结论与证据对应

| 范围 | 报告 | 可核对证据 |
| --- | --- | --- |
| 全100条思想、源码素材与研究价值 | [逐ID明细](inventory/all100-quality.md) | [完整JSON](inventory/all100-quality.json)、[完整CSV](inventory/all100-quality.csv)、[来源指纹](inventory/sourcehash.json)、[A8/A11最小反例](inventory/static-counterexamples.json) |
| 重点ETF账户、规则、固定对照 | [独立复核](etf/independent-review.md) | [结果JSON](etf/audit-results.json)、[217份输入清单](etf/snapshot-manifest.json)、[54份实际计算输入定位](etf/reproduction-inputs.json) |
| A36已定位时点差异 | ETF报告第3节 | [单点敏感度净值](etf/A36_only_2021_feb_dec_BIL_sensitivity-equity.csv) |
| 三个固定静态对照 | ETF报告第2节 | [60/40](etf/STATIC_SPY60_BIL40_MONTHLY-equity.csv)、[行业池等权](etf/STATIC_SECTOR10_EQ_MONTHLY-equity.csv)、[跨资产池等权](etf/STATIC_GROUP5_EQ_MONTHLY-equity.csv) |
| D7–D10及D1–D6源代码 | [加密独立复核](crypto/independent-review.md) | [12次运行复算](crypto/recomputed.json)、[逐交易归因](crypto/trade_attribution.json)、[执行记录](crypto/execution.log) |
| 已发布结果覆盖与年度相对贡献 | 综合报告第1、4节 | [汇总JSON](root/root-result-summary.json)、[41份读取快照清单](root/source-snapshot-manifest.json)、[原交付核对](root/delivery-check.json) |
| 并发补测变化 | 综合报告第1、5、9节 | [收尾来源观察](root/final-source-observation.json)、[资金费率补测观察](crypto/continuation-observation/observation.json)、[其待验收数值快照](crypto/continuation-observation/funding-results-pending-release.json) |

逐条表的6项“优先”、56项“条件保留”、33项“低优先”和5项“组件”是机制/素材判断；未测条目不会因为缺数据被判为无效。综合报告再结合本轮账户证据安排实际投入顺序。A6/C1机制评级与当前版本处置、A9机制评级与文字版优先复核，不是相同层次的结论。

## 范围与再生

- 六条ETF账户独立回放最大误差4.36e−14；12份加密回测ZIP共3,784笔交易复算，最大逐笔误差约5e−9 USDT。这些证明限定账户算术对应，不能代替原引擎完整复现、无偏选池或实盘成交验收。
- 三个静态对照、年度归因、报价单位检查、A36单点敏感度均为结果揭示后的有限诊断。没有优化候选或搜索好年份，不属于新的独立样本验证。
- 19个原编号/81个初始未测仅描述已发布批次。B5与D1/D2/D5补测已有变化，单独保留观察，不与旧批次混成一个验收状态。
- 原始市场数据保留在既有数据湖；原已发布目标权重、订单和净值保留在PUBLIC100家族。这里保存定位与精确指纹，不再次复制行情湖。若输入指纹不符，必须找回原输入，不能拿当前默认数据替代。
- 本目录保留一个审查快照、必要结果及源码证据，不按轮次扩展大矩阵。JSON/CSV为本地长期证据，未提交Git或更改产物白名单。

保留的审计脚本：[ETF复算](../../scripts/public100-quality-review-20260909/etf_audit.py)、[加密账本复算](../../scripts/public100-quality-review-20260909/recompute_crypto.py)、[已发布汇总](../../scripts/public100-quality-review-20260909/summarize_published.py)、[100条评价生成](../../scripts/public100-quality-review-20260909/build_inventory.py)。它们是本次实际执行文件的原样副本；历史临时输出路径保留在源码与日志中，不代表长期证据仍只放在临时目录。

ETF复算使用NumPy和pandas。将ETF脚本复制为系统临时目录下的`audit.py`，同时复制本目录的`snapshot-manifest.json`，然后按照`reproduction-inputs.json`将每个`original_path`校验SHA256后复制到该临时目录的`staging_relative_path`；共54份文件，包含34份已入湖响应和20份已发布账户输入。运行该脚本会在临时目录生成复算、归因及四条对照/敏感度净值，不能把输出位置设在已发布源家族。

加密复算脚本接受`--repo`与`--out`，输出必须在仓库外；原12份ZIP、源代码和数据位置均记录在`recomputed.json`。该次使用的Freqtrade环境位于`/tmp/public100-freqtrade-env`，版本约束见读取快照中的`specs/freqtrade-requirements.lock.txt`。若重建环境，须核对原版本，不能把新版成交规则当原版复算。

已发布汇总脚本读取`/tmp/public100-quality-root-20260909/source-snapshot`；该目录的41份原样副本已保存在`root/source-snapshot`。恢复到独立临时位置后执行，不会运行原策略引擎。100条构建脚本包含逐ID人工审阅判断，不是自动测得的盈利评分。

[归档来源映射](archive-provenance.json)记录原临时产物与长期路径及复制前指纹；独立报告只调整链接和归档范围提示，数值JSON和审计脚本原样保留。[交付指纹](delivery-manifest.json)及[指纹文件](delivery-manifest.json.sha256)用于核查本次长期结果，未将可变导航页当成策略冻结输入。
