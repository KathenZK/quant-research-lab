# Binance-1D-TPSA-Long-Account Core Ledger

## Family Identity

- Full name：`Binance-1D-TPSA-Long-Account`；Alias：`BIN-1D-TPSA-LA`。
- Binance 历史USDT-M多头事件 / UTC 1d；把 TPSA P1 long 概率映射为资金受限的账户。
- 与原状态地图独立。原 P1 不含完整最终模型对象；R0保存新对象，不继承旧预测作为新OOS，不恢复CTP或MHCSML身份。

## Current State

- R0：`registered / not promoted / not live-ready`。
- 经济决策：本轮账户候选NO-GO；`HARD-GATE-FAILED / diagnostic-only`。主条件账户最大回撤79.45%，并弱于无筛选/哈希基线。
- 净输入/执行阻塞：历史身份、funding日历、结算mark价、历史最小单与步进、日收盘处理后可成交价、全池同源特征尚未闭合。
- 未向runner交接或启用。保存对象用于复现诊断，不能作为完整前瞻部署对象。

## Version Table

| 版本 | 主状态 | 固定机制 | 核心证据 | 决策 |
| --- | --- | --- | --- | --- |
| BIN-1D-TPSA-LA-R0 | registered / not promoted / not live-ready | 单个原容量MA7-long模型，p≥0.40，最多4×20%，close barrier→次open代理 | [契约](specs/r0-contract.md) · [报告](diagnostics/r0-results-2026-09-08.md) · [224笔路径](artifacts/trade_paths.html) | 不启动本轮候选前瞻；不搜阈值/杠杆救曲线 |

改标签、阈值、退出、容量、数据源或模型规模须独立新对象并先冻结；不得覆盖R0。

## Evidence Map

[机器配置](specs/frozen-config.json) · [源码/数据源pin](artifacts/source_manifest.json) · [对象/旧折对拍](artifacts/model_audit.json) · [源bar特征与标签](artifacts/original_feature_label_audit.json) · [混合数据审计](artifacts/hybrid_price_event_audit.json) · [净启动阻塞](artifacts/net_startup_blocker.json) · [资金日历缺口](artifacts/funding_calendar_audit.json) · [账户与压力](artifacts/variant_metrics.json) · [手算fixture](artifacts/manual_account_check.json) · [主账独立核验](../../platform/small-account-three-line-validation/artifacts/independent-b-ledger-audit.json) · [决策日志](decision-log.md)。
