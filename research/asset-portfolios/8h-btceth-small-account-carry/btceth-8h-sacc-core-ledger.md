# BTCETH-8H-Small-Account-Cash-And-Carry 主账

| 对象 | 身份与状态 | 经济问题 | 首轮结论 | 证据 |
| --- | --- | --- | --- | --- |
| C0：现货 + USDT 线性到期空头 | explore / not promoted / not live-ready | 同场所到期基差在 10,000 USD 全资本上的剩余收益 | 原交易面已于 2026-06-26 最后到期；明确产品缺口 | [原合同](specs/contract.json)、[官方说明原文](artifacts/raw/sources/expiry_discontinued.html) |
| C0-E1：现货 + 币本位反向到期空头 | explore / not promoted / not live-ready | 以 q=N/F 配对，币抵押不重复计资本 | 当前条件结算净额 BTC +$7.75、ETH +$2.82；成本翻倍转负，未达到现金机会成本假设；本轮经济不采用 | [追加合同](specs/expiry-inverse-amendment.json)、[盘口经济表](artifacts/results/quotes_and_economics.csv) |
| C0：现货 + USDT 线性永续空头 | explore / not promoted / not live-ready | 真实历史资金费是否覆盖全部资金成本 | 近 90 天账户代理净额 BTC +$38.99、ETH +$31.20；总本金简单年化 1.58% / 1.27%，不足以支持前瞻候选 | [比较](artifacts/results/perpetual_comparison.csv)、[账户/资金费证据说明](diagnostics/carry-feasibility-2026-09-08.md) |

本轮结果标签为 `NO_EXECUTABLE_NET_PROFIT_VERIFIED`（解释性经济裁决，不作为生产主状态）。尚无实盘/runner 证据，不登记生产 NO-GO 状态。新对象不继承 MA7 basis/meta-label 等旧家族身份。

[总报告](diagnostics/carry-feasibility-2026-09-08.md) · [机器汇总](artifacts/results/summary.json) · [决策日志](decision-log.md) · [README](README.md)

若未来出现新的、可核验的产品权限或全资本净基差，按报告的重开条件另冻采样对象。旧原始响应、合同与失败结果必须保留；不通过降低现金假设、回看资金费最高窗口或减少保证金来回填候选。
