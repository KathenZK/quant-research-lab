# Top10 基线：合约终止证据专项复核

日期：2026-09-08。本文件只核查五个已知终止事件，不替代完整历史 PIT 身份或净收益批准。

## 结论

三个旧“缺退出价格”应先区分：**2025-03 的 BNX、2025-04 的 VIDT 是持有中自动结算；2025-05 的 ALPACA 在入场前已经终止，是入场资格错误，不是 6 月缺退出价格。** 同理，FRONT 的 2024-09、LOKA 的 2025-08 不应按零成交占位价格开新仓。

| 原合约 | 官方禁止新仓（UTC） | 官方自动结算（UTC） | 对本基线的影响 |
| --- | --- | --- | --- |
| BNXUSDT | 2025-03-17 08:30 | 2025-03-17 09:00 | 3 月持仓须结算，4 月已不能新开仓 |
| VIDTUSDT | 2025-04-14 08:30 | 2025-04-14 09:00 | 4 月持仓须结算 |
| ALPACAUSDT | 2025-04-30 08:30 | 2025-04-30 09:00 | 5 月月初不得入场 |
| FRONTUSDT | 2024-08-23 08:30 | 2024-08-23 09:00 | 9 月月初不得入场 |
| LOKAUSDT | 2025-07-21 08:30 | 2025-07-21 09:00 | 8 月月初不得入场 |

官方公告：[BNX](https://www.binance.com/en/support/announcement/detail/2f963977c7274e0583f16f2e26987b61)、[VIDT](https://www.binance.com/en/support/announcement/detail/fac9c3e401da4cc8b604566fd261d70c)、[ALPACA](https://www.binance.com/en/support/announcement/detail/0274f9d47da1437990bc13eb17b0ec99)、[FRONT](https://www.binance.com/en/support/announcement/detail/3ab5488a00e04d4fb338c77ea28326a8)、[LOKA](https://www.binance.com/en/support/announcement/detail/551eeaf9861c47b8ad3482f45abf3f38)。这些公告均早于所对应的失格月初。

ALPACA 的英文官方原文明确为 09:00；外部转述中出现的 16:00 不采用。合约终止后的 token 兑换比例不能用于原永续仓位的现金结算。

## 精确结算价尚未关闭，但获得了官方指数价格的有界证据

[2024-11-04 官方规则变更公告](https://www.binance.com/en-AE/support/announcement/detail/4bcabddf0e81423ebca242e185bf157d)明确：2024-11-11 08:00 UTC 起，交割及退市合约使用终止前 30 分钟每秒指数价的均值，合计 1,800 个值；此前为 60 分钟、3,600 个值。[当前退市 FAQ](https://www.binance.com/en/support/faq/detail/dd60dfbf654d4055aa6b217ea6d5ddba)说明自动结算收 taker 费。当前 FAQ 不能单独外推全部历史费率和历史细则。

公开 `indexPriceKlines` 接口返回了每个事件对应完整窗口的 1 分钟指数 OHLC，时间戳按网格逐条核对；`delivery-price` 的五个请求均返回空数组。该接口官方文档属于季度交割合约，因此空返回不代表永续自动结算金额为零，也不证明不存在结算。

| 原合约 | 窗口完整分钟数 | 每分钟 low 的均值 | 每分钟 high 的均值 |
| --- | ---: | ---: | ---: |
| BNXUSDT | 30 | 1.7856616517 | 1.8574754240 |
| VIDTUSDT | 30 | 0.0029009013 | 0.0029651513 |
| ALPACAUSDT | 30 | 1.0783486213 | 1.0933008807 |
| FRONTUSDT | 60 | 0.9024855713 | 0.9056117135 |
| LOKAUSDT | 30 | 0.1126354370 | 0.1132468690 |

**这不是精确结算价表。** 如果这些官方分钟指数 OHLC 完整包含正式结算所用的每秒指数采样，则最终均值应落在两列构成的包络内；这是有条件的代数边界，可做单独标明的敏感性分析。不能取两列中点、最后成交价、最后 mark 或后续占位价，冒充已确认的现金结算。BNX 的 2.0 占位价格明显不在上述指数包络内，尤其不能沿用。

仍缺：交易所针对这些历史终止合约的最终现金结算价/回单，或全部每秒指数样本及该合约适用规则/舍入规则的可复算证明。资金费、交易费、可能的强平或 ADL 另行核验。

## 日线所谓“终止后仍有价格”不是正成交矛盾

使用本家族上一轮已固定启动返回投影（SHA256 `3565255edeafcdc5dd3083191b820d2302f993e4ac89679bd812e43601e7049a`），只截取五个指定资产、终止前一日至下一月初后三日。

五币终止后的完整自然日均为零成交量、零成交笔数；ALPACA 5 月、FRONT 9 月、LOKA 8 月都没有正成交。终止当天聚合日 K 仍有早于终止时刻的成交，所以整日 `observed_valid=true` 不代表当天 24 小时可交易。这不是新增回测数据源，也不能让日线掩码取代精确合约状态。

## 留存证据及复现

- [最终复核 JSON](../artifacts/baseline-verification-20260908/terminal-evidence/final-review.json)，SHA256 `f735e3f11941ff01d7a65cc2db1a1e6dde2265d098ace0599ee47e694f354af6`。
- 每币 `*-announcement-cms.json` 是币安公开 CMS 原始响应，包含原始公告正文、标题、发布时间；对应 `.meta.json` 留存请求 URL、抓取时刻、状态码、长度与 SHA256。五份公告均独立检查到对应终止时刻、禁开仓时刻和自动结算说明。
- `settlement-rule-change-cms.json` 是官方规则更新原始响应，SHA256 `1b056d9bce4856204b3bcb08214b40e3d1273646afe3068a6862d2cc70f46066`。
- 每币 `*-index-1m.json` 与 `*-delivery-price.json` 为公开行情 API 原始响应，元信息单独留存。
- [日线断点摘录](../artifacts/baseline-verification-20260908/terminal-evidence/projection-terminal-days.csv)。
- 本次直接抓网页获得的 202 空正文也保留，以说明失败路径；这些空 HTML 不作为公告正文证据。`summary.json` / `summary-with-cms.json` 是中间取证阶段，不是最终复核入口。
- [独立有界取证脚本](../scripts/audit_baseline_terminals_20260908.py)。不读取密钥、不调用交易接口、不修改数据湖、不改旧研究绩效；Ruff 及 diff whitespace 检查通过。

本文件交付给基线主研究使用。仅修正上述五个已被官方公告证明的合约资格；不得因此宣称全市场所有历史合约身份已验证。精确账户净收益仍需主研究将每项现金流串通并明确未关闭项。
