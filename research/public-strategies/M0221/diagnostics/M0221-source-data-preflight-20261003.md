# M0221 Hash Ribbons：退出规则阻塞，算力数据已取得

**BLOCKED_RULE_EXECUTION，策略回测0、严格复现0。** 不能只用已有BTC价格跑本策略，也不能将第三方退出补作Charles Edwards原规则。

## 作者规则与闭合缺口

原catalog的Charles Edwards/@caprioleio [指定帖子](https://x.com/caprioleio/status/1600053321527873536)正常访问403，停止该路径。作者[Capriole文章](https://capriole.com/hash-ribbons-bitcoin-bottoms)正常可读：2019-10-30发表、2023-04-13编辑。两段式思想为30/60日算力均线恢复，再等价格10日均线高于20日均线买入。算力为估计量而非直接测量；来源讨论实际出块与难度。

作者公开文章将到“下一周期峰值”的收益和长期持有用于示例，没有给可事前执行的卖出条件、固定持有期、仓位/加仓或多次信号去重契约。事后峰值不能用作回测退出；永久持有也不自动定义新增信号资金分配。买入状态机的交叉当日价格过滤与延后等待方式仍需固定实现证据。作者TradingView链接本工具返回restricted URL，未尝试其他端点绕过。因此已确认的是入场指标，尚未闭合交易策略。

[Stopsaving第三方文章](https://www.stopsaving.com/bitcoin-hash-ribbons-indicator/)使用买后首次再次投降退出，明确属于其测试假设，不能归因原作者。[FMZ第三方](https://www.fmz.com/strategy/438471)描述算力30/60交叉双向交易、IntoTheBlock数据，不含相同价格确认；正文可读但完整源码要求登录，未读取登录内容。这些都不能补充原规则完成严格复现。

## 实际合法数据与QA

已通过[CoinMetrics官方公开数据仓库](https://github.com/coinmetrics/data)取得BTC CSV，锁定提交 `f1a36afb962731c387bb03982758ab0103063da5`。官方README及LICENSE为CC BY-NC 4.0；仅用于非商业研究，不把完整数据公开发布。CSV共6,351行，2009-01-03—2026-05-24，2,482,497字节；SHA256 `06495ff8e643432e6948b7b4686ce44fc106217287dabdc1b38351d9ddec46c3`。

对候选研究及60日预热范围2022-11-01—2024-12-31实际检查792行：日期连续、重复0、缺日0，HashRate缺失0，均有限正值。没有生成均线信号、交易或策略收益。2022-11月算力已可预热；现有M0216价格起于2022-12-01，若后续独立适配研究评估2023年起，价格20日预热可覆盖。数据量齐备不等于源策略可执行。

官方[HashRate定义](https://gitbook-docs.coinmetrics.io/network-data/network-data-overview/mining/hash-rate.md)为每日估计值，BTC单位TH/s，依据日出块数和平均难度推导；不是原作者数据供应链已证实一致。不同供应方估值不能直接宣称同一历史信号。

CSV含AssetCompletionTime和AssetEODCompletionTime。官方[完成时间说明](https://gitbook-docs.coinmetrics.io/network-data/network-data-overview/availability/asseteodcompletiontime.md)将后者定义为该资产当天所有指标完成计算的epoch时刻。范围内792行均非空；相对于记录日期次日00:00 UTC，最小晚8,164秒，最大晚426,210秒。由此不能在紧邻日结束的同一午夜使用当天算力交易，也不能用固定一天延迟无条件替代实际完成时间。

当前文件是后来的版本快照。完成时间字段不自动证明其中每个HashRate值就是当时首次发布值，也没有提供逐值修订履历；是否为原发布/重算完成时刻仍需核查。未认证PIT。后续若做明确适配历史诊断，应把算力可用时间与价格决策时间连接并禁止前填，披露版本修订风险，而非冒称严格历史信息集。

## 阻塞与下一步

主要阻塞是作者可执行退出与资金分配/状态机未定义，不是“行情完全拿不到”。数据另外存在供应方一致性、完成时点解释及历史修订PIT限制。仅当独立明确授权适配第三方退出时才能另建HYPOTHESIS规格，不能把它标原作者完成；当前停止该ID，0回测。

完整作者HTML、官方说明/许可证及BTC CSV保存在artifacts/20261003-source-preflight/private-source，本地副本不等于远端快照备份。轻量source-manifest记录网址/字节/hash/取得时间；data-qa记录已验范围；preflight-decision记录阻塞。数据重建为固定commit的官方csv/btc.csv并验上述hash，不从图片提取数据、不购买或绕权。模型与effort均UNKNOWN。
