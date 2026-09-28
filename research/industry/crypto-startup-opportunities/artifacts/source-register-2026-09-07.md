# 来源核验记录

检索日：2026-09-07。无明确发布日的网页标为动态文档；抓取日不替代事件发生日。本表为自行整理的使用边界，并非网页全文存档。引用在报告对应段落附近。

| ID | 来源 | 时间/类型 | 用途与限制 |
| --- | --- | --- | --- |
| S01 | [CoinGecko Q2](https://www.coingecko.com/research/publications/2026-q2-crypto-report) | 2026-07 更新；窗口至 06-30 | 季度规模；预测市场摘要/正文数字冲突，该项未使用 |
| S02 | [CoinGecko Global](https://api.coingecko.com/api/v3/global) | 当日 API 快照 | 市值等统计；不判定牛熊周期 |
| S03 | [DefiLlama Chains](https://api.llama.fi/v2/chains) | 当日 API 快照 | DeFi TVL；不代表全链资金或付费客户 |
| S04 | [RH 主网发布](https://robinhood.com/us/en/newsroom/robinhood-accelerates-global-expansion-robinhood-chain-mainnet-stock-tokens-agentic-trading/) | 2026-07-01 | 上线背景；区分现有产品和计划 |
| S05 | [RH 连接](https://docs.robinhood.com/chain/connecting/) | 动态官方文档 | Chain ID 4663、技术栈、gas；未部署合约 |
| S06 | [RH Stock Tokens](https://docs.robinhood.com/chain/stock-tokens/) | 动态官方文档 | RHJ 债务证券、权利、地区及一级市场限制 |
| S07 | [RH 资产与价格 API](https://docs.robinhood.com/chain/stock-token-apis/) | 动态官方文档 | REST 与链上价格调整区别；非再分发许可 |
| S08 | [Building with Stock Tokens](https://docs.robinhood.com/chain/building-with-stock-tokens) | 动态官方文档 | multiplier、交易场所、发行回收限制；经直接 HTTP 正文解析核验 |
| S09 | [RH Bridging](https://docs.robinhood.com/chain/bridging/) | 动态官方文档 | 挑战期与桥路线；不是实测转账 |
| S10 | [RH 生态](https://docs.robinhood.com/chain/) | 动态官方文档 | 已有基础设施；开放主网不等于空白市场 |
| S11 | [RH 资产接口](https://api.robinhood.com/rhj/assets) | 当日 API 快照 | 194 个唯一 ID 及主网部署；不证明深度 |
| S12 | [HL Builder codes](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/builder-codes) | 动态官方文档 | 用户授权和收费条件；上限不是建议定价 |
| S13 | [HIP-3](https://hyperliquid.gitbook.io/hyperliquid-docs/hyperliquid-improvement-proposals-hips/hip-3-builder-deployed-perpetuals) | 动态官方文档 | 页面所列质押和运营责任；参数可能变化 |
| S14 | [HL Funding](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/funding) | 动态官方文档 | 小时结算；不采用网页长期年化宣传值 |
| S15 | [HL Info](https://api.hyperliquid.xyz/info) | 当日 POST 快照 | metaAndAssetCtxs、predictedFundings、perpDexs；请求体保留于 JSON |
| S16 | [HL 官方公告](https://t.me/s/hyperliquid_announcements?before=579) | 多条历史公告 | outcome 与产品变化；最新部署资格未完整核验 |
| S17 | [Hyperdash](https://hyperdash.com/asset/hype-hyperliquid) | 公开产品页 | 竞争功能；未采用页面未加载的费率占位值 |
| S18 | [Loris HIP-3](https://loris.tools/hip3) | 动态产品页 | 竞争功能；不是独立审计市场份额 |
| S19 | [Loris Builder](https://loris.tools/builder-analytics) | 动态产品页 | 竞争功能；不混用不同时间窗统计 |
| S20 | [CoinGlass 套利](https://www.coinglass.com/FrArbitrage) | 公开产品页 | 费率差工具已存在；空表不解释为零机会 |
| S21 | [CoinGlass 套利 API](https://docs.coinglass.com/reference/fr-arbitrage) | 动态 API 文档 | 同类数据供给；未购买或验证全量数据 |
| S22 | [DEX Screener API](https://docs.dexscreener.com/api/reference) | 动态官方文档 | 行情、交易对、推广等基础能力 |
| S23 | [DEX Screener Boosting](https://docs.dexscreener.com/boosting) | 动态官方文档 | 付费推广影响 Trending Score |
| S24 | [Axiom Pulse](https://docs.axiom.trade/axiom/finding-tokens/pulse) | 文档含较旧表述 | 确认基础筛选已存在；迁移路径不当最新集成规格 |
| S25 | [GMGN New Pair](https://docs.gmgn.ai/index/new-pair) | 动态官方文档 | 已有新池与风险功能；未实测完整产品 |
| S26 | [GMGN Fees](https://docs.gmgn.ai/index/gmgn-fees-settings) | 动态官方文档 | 单笔平台费示例；实际另有执行成本 |
| S27 | [Nansen 交易更新](https://nansen.ai/post/making-onchain-accessible-trading-for-free-users-and-more) | 2026-01-21 | 钱包分析与执行已有整合 |
| S28 | [GoPlus API](https://docs.gopluslabs.io/reference/api-overview) | 动态官方文档 | 安全 API 供给；检测不等于安全保证 |
| S29 | [Pump.fun 生命周期](https://www.coingecko.com/research/publications/average-lifespan-of-pumpfun-tokens) | 2026-06-23；样本至 06-18 | 有交易代币的最后交易日口径；不是欺诈概率 |
| S30 | [Birdeye Pricing](https://docs.birdeye.so/docs/pricing) | 动态价格页 | 套餐与 CU；无定制或再分发报价 |
| S31 | [Birdeye Price](https://docs.birdeye.so/reference/get-defi-price) | 动态 API 文档 | 3 CU/次成本示意；不含产品其他调用 |
| S32 | [Ethena Funding Risk](https://docs.ethena.fi/solution-overview/risks/funding-risk) | 官方风险说明 | 负资金费机制；不继承其历史收益 |
| S33 | [Polymarket Fees](https://docs.polymarket.com/trading/fees) | 动态官方文档 | 逐市场费用；未固定全平台成本 |
| S34 | [Kalshi Settlement](https://docs.kalshi.com/getting_started/market_settlement) | 动态官方文档 | 结算可延迟；不证明跨平台合约等价 |
| S35 | [Jito 执行](https://docs.jito.wtf/lowlatencytxnsend/) | 动态官方文档 | 拍卖与竞价；不证明机器人净利 |
| S36 | [Stripe 稳定币支付](https://docs.stripe.com/payments/stablecoin-payments) | 动态官方文档 | 底层能力；适用地区与产品支持另核 |
| S37 | [Circle 2026 产品方向](https://www.circle.com/blog/building-the-internet-financial-system-circles-product-vision-for-2026) | 2026 产品展望 | 既有产品与路线图分开；未称 Arc 全部功能已上线 |
| S38 | [Cryptio 对账](https://www.cryptio.co/solutions/reconciliation) | 当前产品页 | 企业对账已有供给；不采用自述客户数作审计证据 |
| S39 | [Solana 八月生态](https://solana.com/news/solana-ecosystem-roundup-august-2026) | 2026-09-04 | 覆盖支付/资产/agent；生态宣传不证明客户需求 |
| S40 | [Coinbase Agentic Wallets](https://www.coinbase.com/en-it/developer-platform/discover/launches/agentic-wallets) | 2026-02-11 | 通用 agent 钱包已有供给 |
| S41 | [Coinbase / AWS](https://www.coinbase.com/en-gb/blog/introducing-amazon-bedrock-agentcore-payments-powered-by-x402-and-coinbase) | 2026-05-07 | 支付与企业控制竞争边界 |
| S42 | [八部门通知](https://www.amac.org.cn/xwfb/zjyw/202602/t20260206_27340.html) | 2026-02-06；协会转载 | 银发〔2026〕42号；全文 open 超时，搜索正文可读，另与监管局材料交叉核验 |
| S43 | [证监会深圳监管局](https://www.csrc.gov.cn/shenzhen/c105615/c7638699/content.shtml) | 2026 监管材料 | 内地与境外 RWA 边界；非具体业务法律意见 |
| S44 | [ESMA 过渡期声明](https://www.esma.europa.eu/sites/default/files/2026-04/ESMA75-113276571-1679_Statement_on_the_end_of_transitional_periods_under_MiCA.pdf) | 2026-04-17 | MiCA 最迟过渡期；不替代证券/衍生品分类 |
| S45 | [HKMA 年报](https://www.hkma.gov.hk/media/eng/publication-and-research/annual-report/2025/16_International_Financial_Centre.pdf) | 官方年报及 2026 进展 | 稳定币牌照背景；不代表其他业务自动获准 |

## 采样证据

- [六个接口响应及哈希](snapshot-2026-09-07/manifest.json)
- [字段与时效核验](snapshot-audit-2026-09-07.json)
- 非同时的单次响应没有成交效力。哈希只证明本地文件完整，不证明数据真实、完整或能用于交易。

## 后续需要的商业证据

客户操作与采购流程、竞品实测、留存续费、数据再分发许可、生产报价、具体经营结构法律判断，以及任何自营策略的前瞻执行结果。
