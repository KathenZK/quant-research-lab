# BIN-1D-MA7-CAR-GEN 主账

## 身份

Binance观测COIN USDT永续 / 日线信号 / 小时执行 / 单币独立10,000 USDT账户。来源是HYPE-1D-MA7-CAR R4的H4，不是MA7-BTG、ABT或其它类似MA7研究。

## P1，2026-09-09：计算与独立账户核验完成

计算前固定F0、H4_D0、H4_D2、H4_D3和同币买持，主窗口2025-06-29至2026-09-04，手续费0.05%及滑点0.03%/次；全部四组另做滑点0.10%、每日额外0.05%持仓成本。652待检币→346完整433日＋193其它≥180日＋72短历史＋41无窗口；611币执行失败0。

共6,756策略区间、4,888压力账户、1,689买持账户。611币各自选中全段四方案41,262笔交易，其中346币完整433日四方案28,915笔。独立审计核验全部11,644策略/压力账户、163,996笔交易、1,882,544条止损更新，另含1,689买持账户，全部通过，无抽样或跳过。

| 方案 | 完整346币赚钱数 | 中位收益 | 最大回撤中位数 | 较稳定候选 |
| --- | ---: | ---: | ---: | ---: |
| F0固定止损 | 80 | −32.73% | 62.26% | 2 |
| H4_D0高低价收紧 | 93 | −27.76% | 59.21% | 3 |
| H4_D2再等2日 | 84 | −41.64% | 64.66% | 2 |
| H4_D3再等3日 | 72 | −45.34% | 67.59% | 0 |

结论：高低价停滞收紧有局部改善，但多数币亏损、回撤大，**不支持全市场统一推广**。延后达标能补入场机会，却进一步恶化整体账户；不替换原入场。H4_D0较稳定历史候选为HYPE、DEEP、TRX（TRX收益低于买持）；D2局部候选VET、ARKM，补充ELSA只有196日，不据此按币选最优参数。

状态：`explore / diagnostic-complete / universal-generalization-not-supported / not promoted / not live-ready`。全部价格和账务核验通过不代表真实资金费率、PIT身份、维持保证金强平或未来有效已被验证。

证据：[完整报告](diagnostics/results-p1-20260909.md) · [交互总览](artifacts/html_20260909_v2/index.html) · [全币排名](artifacts/analysis_20260909/ranking.csv) · [账户审计](artifacts/audit_results_20260909.json) · [输入审计](artifacts/input_audit_20260909.json)。

固定来源：[规则](specs/contract-p1-20260909.md) · [最终输入计划](specs/input-plan-v4-20260909.json) · [运行固定来源](artifacts/results_20260909/run_manifest.json) · [共享内核](../../_shared-kernels/ma7-cross-atr-ratchet/README.md)。

输入清单SHA：`a2390b002883506a8f39522a31e708e76346e21be6a0a598e753b4a5b5e4891c`；结果清单SHA：`880d7201b4c23695265d80d2704e0ec03245dfdb8a274b50873f82fbfb50a13d`；全量审计SHA：`08e12de5e6bd68ac93a24fd94e6a0bc072ff20f450146c0a10f3631175c1c580`。
