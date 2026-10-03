# M1463 Core Ledger

## Family Identity

独立公开catalog ID M1463，BTCUSDT spot/UTC1d；当前含本根20日收盘均值与人口方差ddof0，2倍标准差。上轨入场严格current close>current upper、previous close<=previous upper；中轨退出严格current close<current middle、previous close>=previous middle。会员正文与原作者runtime未核实。

## Current State

PREHISTORY_C0 / not promoted / not live-ready。计划四策略配置，零新control；实际历史0，strict0。

## Shared Assumptions

[规格](specs/protocol-v1.json)固定Decimal50、100000USDT、全现金含费、base8bps+2bps单边、fee0/fee20/delay2；无杠杆、利息、资金费、止损或期末强平。不得以旧95%control代替尚待验收的M1258全现金control。

## Evidence Map

[输入QA](artifacts/20261003-catalog-v1/input-QA.json) · [合成边界](artifacts/20261003-catalog-v1/synthetic-prehistory.json) · [带成交合成因果性](artifacts/20261003-catalog-v1/synthetic-causality.json)。C0独审及root control远端pin仍是历史门禁。
