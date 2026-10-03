# M1396 Core Ledger

## Family Identity

独立公开catalog ID M1396，BTCUSDT spot/UTC1d；周二UTC日线收盘时hl2高于当前含本根SMA4则排队买入；周六收盘排队卖出。lag1为周三/周日开盘，lag2为周四/周一开盘。原2012–2018过滤明确改为2023–2024，不能声称原期间复现。

## Current State

PREHISTORY_C0 / not promoted / not live-ready。计划四策略配置，零新control；实际历史0，strict0。

## Shared Assumptions

[规格](specs/protocol-v1.json)固定Decimal50、100000USDT、全现金含费、base8bps+2bps单边、fee0/fee20/delay2；无杠杆、利息、资金费、止损或期末强平。不得以旧95%control代替尚待验收的M1258全现金control。

## Evidence Map

[输入QA](artifacts/20261003-catalog-v1/input-QA.json) · [合成边界](artifacts/20261003-catalog-v1/synthetic-prehistory.json) · [带成交合成因果性](artifacts/20261003-catalog-v1/synthetic-causality.json)。C0独审及root control远端pin仍是历史门禁。
