# Binance 15m 全历史缺口治理 V3 契约

用户明确要求完成上一轮未完成的全历史质量治理。本轮只处理 Binance USD-M USDT 永续 15m 数据，截止沿用 V2 的 `2026-09-05T15:45:00Z`；不扩展到 1m/5m、资金费率、高周期或策略研究。

1. 输入为经 catalog 严格内容哈希与全量 SQL 验证的 `binance.perp.ohlcv.15m.refreshed.v2`。旧 normalized、已发布 V1/V2、原始响应与缓存均不覆盖。修复发布为 `binance.perp.ohlcv.15m.history.v3`。
2. 重扫整个输入的内部时间网格，不只依赖旧缺口表。对每段缺口连同两端 bar 查询官方 API，并取得该缺口覆盖月份的官方 Vision 15m ZIP 与 CHECKSUM。月度/API 未覆盖的具体日期继续核对日度归档。原生零成交 bar 可以保留，但不得由程序补零或插值。
3. 原始响应与 ZIP/CHECKSUM 保留原文、URL、抓取时间、SHA256。ZIP 必须通过 SHA256、CRC、单 CSV、列数、时间单位/网格、顺序/重复、OHLCV/笔数与明确 close_time 检查。月度/日度返回必须在请求月份/日期内。
4. API 与 Vision 来源分别保留；同来源重复值必须一致，跨来源不一致先报告并停止发布。V2 已有键不得默默更换；重叠按 V2 的价格/笔数精确、volume 绝对 1e-9 相对 1e-12、quote_volume 绝对 1e-6 相对 1e-10 容差检查。
5. 全部缺口逐段按实际时间戳对账。`RECOVERED` 仅用于缺失网格全部被官方 bar 覆盖；`SOURCE_UNAVAILABLE` 表示指定区间经 API、月度和逐日日度仍无法获得，不证明该区间没有交易，保留历史覆盖 blocker。网络错误、未完成请求和校验失败不得归为不可恢复。
6. 全历史行质量、重复、来源、闭合、UTC 网格、VWAP/成交量一致性、原生零成交分布、原始数据到规范快照对齐、旧输入指纹、526 个活跃 COIN/INDEX 的冻结尾部均要复核。历史起止为观测边界，不伪造上市/退市或历史 PIT 成分。
7. 发布前后独立验收。任何残余缺口都保留到研究缺口门禁，验证 `reject` 拒绝、`contiguous_segments` 不跨缺口。不通过删历史行/删币使缺口消失，不把治理有完整处置台账写成无缺口。
8. 下载可续跑并验缓存哈希，少于 30 GiB 停止；不复制全量高周期数据。引用的 V2 helper 代码冻结并记录 SHA256，V3 的修复逻辑独立保存。

官方字段与归档口径：[Binance Public Data](https://github.com/binance/binance-public-data)、[USD-M Kline](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/market-data/rest-api/Kline-Candlestick-Data)。
