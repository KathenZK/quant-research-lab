# BTCETH-8H-Small-Account-Cash-And-Carry

- Family ID：`BTCETH-8H-SACC`。独立家族，首次有限可行性对象 `C0 / C0-E1`。
- 主状态：`explore / not promoted / not live-ready`；研究结果：`NO_EXECUTABLE_NET_PROFIT_VERIFIED`。
- 原始 C0：OKX BTC/ETH 现货多头 + USDT 线性永续/到期空头。USDT 到期产品已停发并于 2026-06-26 最后到期。
- C0-E1：在读取价格结果前追加币本位反向到期交易面。没有覆盖原合同或沿用旧家族证据。
- 首轮经济裁决：按冻结资金分配、公开基础费用和现金机会成本假设，暂不投入资金；不外推为所有场所、费率和资金规模的 carry 永久无效。

[中文结论](diagnostics/carry-feasibility-2026-09-08.md) · [主账](btceth-8h-sacc-core-ledger.md) · [决策/曝光日志](decision-log.md) · [C0 合同](specs/contract.json) · [反向追加合同](specs/expiry-inverse-amendment.json) · [机器汇总](artifacts/results/summary.json) · [输入哈希](artifacts/input_manifest.json)

离线一键重算（仅 Python 标准库）：

```bash
python3 research/asset-portfolios/8h-btceth-small-account-carry/scripts/reproduce.py --verify
python3 research/asset-portfolios/8h-btceth-small-account-carry/scripts/verify_accounts.py
```

前者核对输入及代码哈希，再重算所有 CSV/JSON/SVG；后者只从 CSV 独立对资金费、现金、币本位收益和关闭状态，不导入研究引擎。额外 PNG 为展示图，核心离线重算不依赖绘图库。

[抓取入口](scripts/fetch_public.py) 只调用公开 OKX GET 接口；重新抓取必须使用不存在的新目录，不得覆盖本轮原始快照。当前原始请求、响应、UTC 和校验值在 [capture_curl_20260908](artifacts/raw/capture_curl_20260908/selection.json)，首次 TLS 失败和部分成功请求另行保留。共享数据湖和原工作树未改写。

本家族没有训练模型、真实下单、账户授权、生产运行或持续监控实例。30–60 天运行观察不能证明长期收益；本轮没有合格候选，因此不启动新前瞻。
