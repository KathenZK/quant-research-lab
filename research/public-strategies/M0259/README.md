# M0259：BbandRsi 数据门控阻塞

当前为 `DATA_BLOCKED / HYPOTHESIS / explore`。实际市场回测 **0**，没有收益、净值、交易或晋升结论。

官方BTCUSDT现货1h全部25月已完成原始归档审核，共18287/18288根；唯一缺口为2023-03-24 13:00 UTC，唯一零量/异常close_time为12:00那根（12:39:41.646 UTC）。无其它缺口、重复、乱序或基本值错误。2023-03月档743/744根、同日官方日档23/24根且逐字段一致。它违反原定完整1h网格和整小时闭合契约。未补值、删零或另择窗口。

- [数据阻塞证据](diagnostics/data-blocked-20261003.md)
- [独立月档审计](artifacts/20261003-data-blocked/independent-monthly-audit.json)
- [主账](m0259-core-ledger.md)
- [未冻结规格](specs/M0259-first-replay.json)
- [来源语义](diagnostics/source-preflight-20261003.md)
- [恢复说明](diagnostics/rebuild-20261003.md)
- [决策记录](decision-log.md)

用户已同意本次个人研究适用的Binance条款。授权并未改变数据质量门槛。只处理M0259 / BTCUSDT spot / 1h / 2023–2024，含2022-12预热；不改窗口以绕过阻塞。代码与合成验证准备完成，但不能据此声称真实回测通过。Graph仅交付无收益/曲线的阻塞记录，实际发布及页面验收另由协调者处理。
