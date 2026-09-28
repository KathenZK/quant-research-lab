# C0 / C0-E1 证据

- [原始抓取选择](raw/capture_curl_20260908/selection.json)：官方服务器UTC、90天请求界限、按期限选出的两个到期合约。
- `raw/`：首次原生产品快照、首次部分失败请求、完整curl抓取、官方说明HTML；每个HTTP响应对应来源URL、本机UTC和SHA256。
- [机器汇总](results/summary.json)、[输入清单](input_manifest.json)、[输出清单](output_manifest.json)。
- [订单](results/orders.csv)、`results/btc_account_hourly.csv`、`results/eth_account_hourly.csv`、`results/btc_expiry_account.csv`、`results/eth_expiry_account.csv`：现金/币/合约/保证金账户。
- `results/*_funding_events.csv`：真实rate、mark小时代理、上下界与累计资金费；不得改称精确账单。
- [当前报价](results/quotes_and_economics.csv)、[时钟闸](results/quote_validation.csv)、[数据质量](results/data_quality.json)。
- [成本/延迟](results/perpetual_comparison.csv)、[基差历史](results/historical_basis.csv)、[压力](results/stress_scenarios.csv)、[现金敏感性](results/cash_sensitivity.csv)。
- [独立算术](results/independent_arithmetic.json)、[手算与真实例子](results/manual_checks.json)。

SVG由标准库复算；PNG只是可读展示。全部账户是相互独立的10000美元研究对象，不可相加。
