# 资金费率 v2 全市场近期查询补充

## 原因与边界

逐币队列在补回 130 个查询后再次返回 HTTP 403，已停止。官方 `GET /fapi/v1/fundingRate` 的 `symbol` 是可选参数；在冷却后验证不指定标的的有界全市场查询，目标仅为 V3 已冻结范围内的近期尾部 `2026-09-01T00:00:00Z` 至 `2026-09-05T15:45:00Z`。

同一个官方地址、同样至少 2 秒间隔、单线程；不使用代理或替代地址。再次遇 403/418/429 即停止。保存所有返回原文，但只把交易所原生代码精确对应 V3 标的的事件纳入发布；其他代码只保留 raw，不改写计价币。

按 UTC 日分块；每页上限 1000、包含末时间戳重叠分页，以免遗漏同毫秒的其他合约或 Special 事件。如果一个毫秒的返回量达到分页上限而无法继续前进，整块不得声称完整。

全市场近期查询与原 634 个逐币历史查询分开记账；不得把近期尾部查询成功冒充所有原查询完整，亦不得代替历史频率证据。

来源：[官方字段、分页与参数](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data#get-funding-rate-history)。主契约：[资金费率 v2](binance-funding-v3-inputs-v2-2026-09-07.md)。
