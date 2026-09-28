# Quant Platform V4 研究报告（公开元数据）

状态：`explore / untrusted / not promoted / not live-ready`。本轮 **ELIGIBLE=0，Formal Backtest=0，正式 ResearchEvidence=0**。三个最接近准入的模板已完成来源、许可、规则、假设版本和数据需求核验；实际数据仍为 PARTIAL/raw_unaccepted。

- 数据源：Bit2Me public REST，BTC/EUR spot，日线两个模板与 4h 一个模板。日线请求 1549 根、返回 719 根；4h 请求 9294 根、返回 714 根。冻结窗口 2022-07-01 至 2026-09-27（右开）没有缩短。
- 原生 trade_count、quote_volume、vwap、is_closed 与来源身份核验仍缺。信号字段推导不覆盖或降低全仓库行情质量标准。
- 三个家族 / 13 参数配置作为私有真实行情诊断运行，正式入口三次 fail closed。基线参数不变；IS/OOS、成本、滑点、换手、参数面、暴露和统计适用性完整保存，但都不计入正式研究。
- DSR 明确每 bar 单位、年化、偏度、Pearson 峰度、网格与既往试验数；PBO 缺样本或方差为 NOT_APPLICABLE。未实现 purge/embargo，跨块持仓保留 LIMITATION。
- v2 市场内核修正开盘退出暴露代理，逐笔 PnL/fills/fees 与 v1 一致；盘中真实暴露时长未知，给上下界。
- 新合同与旧 V3 合同各自保留。新链路以 exact contract bytes、dataset manifest、raw/data、reviewed rights、code/config 的 SHA 固定；旧下载器退役。
- 公开仓库不包含行情或派生收益。完整本机报告在 `platform-v4-work/Quant Platform V4 Research Report.md`；家族产物在各自 `artifacts/20260928-v4-chain-acceptance/`。

## 复现入口

在 Lab 安装锁定依赖后，使用 `research/platform/quantgraph-integration/scripts/fetch_market_v4.py --contract <冻结合同> --rights <已审核许可 JSON> --output <新 raw 目录>`。它只采集许可覆盖的数据，不自行授权；任何 403/429 均停止。

随后 `research_v4.py --contract <同一合同> --manifest <manifest.json> --output <新家族 artifacts 目录>` 默认正式模式：必须先通过覆盖、原生 schema、来源/闭合、raw-normalized 审核、V4 ELIGIBLE 和所有哈希绑定。此次数据会拒绝；只有显式 `--private-diagnostic` 可运行受限诊断。

通过时生成 schema 3.0 envelope；`strategy_lab.knowledge.results.submit_market_evidence` 使用稳定 SDK 写回并逐一读回。当前没有可写回的正式结果。研究状态与执行授权完全独立。

## 路由

[SMA](../../../btc/1d-quantgraph-source-sma/README.md) · [ZScore](../../../btc/1d-quantgraph-source-zscore/README.md) · [EMA](../../../btc/4h-quantgraph-source-ema/README.md)。Graph 完整审计位于其 `docs/audits/quant-platform-v4-audit.md`，开发前 main 基线单列。

本机完整测试 900 passed / 98 skipped，governance preflight 和 lint PASS；typecheck 未配置。Graph 完整测试 143 passed / 1 skipped，发布重建及 public 检查 PASS。CI 以 PR 的最终提交检查为准。
