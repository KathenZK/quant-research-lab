# M1358 只读源码预审

结论：信号规则可以明确重建，但目前尚不能进入严格复现。此次仅完成固定目录、公开原类、参考引擎和合成边界预审；历史运行、行情请求、认领、全局修改和 Git 提交均为 0。根协调者可在单独冻结 ADAPTED 协议后继续，不能将修正后的账户初始化称为原策略严格完成。

本地交付以 `M1358-sourcecard.safe.json`、`catalog-field-audit.safe.json` 和本说明为安全摘要；完整源码/论坛页面、原目录内容及元数据副本属于本地证据，不在安全交接清单中。没有远端备份成功声明。

## 原记录与原文

固定 Graph commit `26712be68a662d15dcdb636a197a8062457246b5` 的 M1358 原记录已按 11 个字段逐项检查，blob 为 `e1a37c5c5be0188805abc3d57c4c337d4086c632`。目录内容未修改。

[原论坛主题](https://www.quantconnect.com/forum/discussion/13690/ema-crossover-on-crypto/)可读取完整可见 Python 类，包括 Initialize 与 OnData。核心为日线 EMA 13/48 与当前仓位状态比较；不要求从下到上交叉，等值不交易，正常路径仅做多/清仓。slow 尚未就绪时直接返回；类中没有外部预热，也没有止损、ROI 或跟踪止损。`previous` 不参与交易判断。回复里的多空工程、五倍周期预热不是楼主原类的一部分。

目录名称/标题的“上穿”措辞不精确。原目录日期为未知；本次主题 HTML 的 `datePublished` 为 `2022-05-13 01:26:56`，未标时区，故不能补成一个确定的 UTC 时间。固定源码 hash 是当前可见字节证据，不是作者最初版本的 Git pin；原项目、项目依赖和当时引擎未取得。

## 当前参考引擎带来的关键限制

本次只读获取并核对了当前 Lean commit `705b9551be1aaa821c7f77896a7eb8fcd07b92ee` 的 17 个源码/配置文件，每个 Git blob 与树对象一致；**没有运行 Lean**。这些内容不证明作者在 2022 年的环境相同。

- [EMA 源码](https://github.com/QuantConnect/Lean/blob/705b9551be1aaa821c7f77896a7eb8fcd07b92ee/Indicators/ExponentialMovingAverage.cs)使用首 N 个样本的 SMA 作第一个就绪值，随后采用 α=2/(N+1)；48 次更新就绪。就绪不意味着 EMA 已与更长历史完全收敛。
- [现金初始化](https://github.com/QuantConnect/Lean/blob/705b9551be1aaa821c7f77896a7eb8fcd07b92ee/Common/Securities/SecurityPortfolioManager.cs)与 [CashBook](https://github.com/QuantConnect/Lean/blob/705b9551be1aaa821c7f77896a7eb8fcd07b92ee/Common/Securities/CashBook.cs)静态代码显示默认存在 100000 USD；设置 100000 USDT 的调用本身不会清除 USD 或改账户币种。因此不能仅凭原片段声称总初始资金只有 100000 USDT；实际引擎启动、换汇订阅及平台初始化仍需核验。[当前官方模型文档](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/brokerages/supported-models/binance)要求 Binance 账户使用其支持的币种。
- [Binance 模型](https://github.com/QuantConnect/Lean/blob/705b9551be1aaa821c7f77896a7eb8fcd07b92ee/Common/Brokerages/BinanceBrokerageModel.cs)的现货 Margin 上限是 3 倍；[目标仓位计算](https://github.com/QuantConnect/Lean/blob/705b9551be1aaa821c7f77896a7eb8fcd07b92ee/Common/Algorithm/Framework/Portfolio/PortfolioTarget.cs)会按杠杆归一化，目标 1 不等于下单 3 倍资产。默认现金缓冲、订单门槛、手续费及 lot 舍入也不能简化成无费满仓或此前 95% 现金预算。
- [费用源码](https://github.com/QuantConnect/Lean/blob/705b9551be1aaa821c7f77896a7eb8fcd07b92ee/Common/Orders/Fees/BinanceFeeModel.cs)当前 maker/taker 默认均为 10 bps，现货买入扣 BTC、卖出扣 USDT。当前模型使用即时成交、零滑点模型及空的利息模型；这些不是实际交易所保证，也不是已证实的作者当时费用。
- [市场日历配置](https://github.com/QuantConnect/Lean/blob/705b9551be1aaa821c7f77896a7eb8fcd07b92ee/Data/market-hours/market-hours-database.json)为 UTC 连续七天；算法默认时区却是 New York。事件何时送达、收盘值何时更新、订单当根/下根成交、首尾日期及缺口处理必须在所选执行环境中独立确认。原代码未给出下一日 open 成交承诺。

## 现有输入与候选协议

只读 M0216 输入清单/协议：现有 BTCUSDT 1d 共 762 行，2022-12-01 至 2024-12-31，输入清单记录 SHA256 `48e4e785ee3366a459cf09f64617c89e04fb19b91da6c6125e86835506f6b9f5`；2023-01-01 前有 31 行。本次未读取 canonical 价格、收益、净值或交易，不重新宣称完成输入 QA。原作者设定的 2021-04-01 至 2022-03-31 区间不在此输入内。

根协调者提出的候选是 **2023-01-01 指标冷启动**：不向 EMA 喂入已有 31 天前史；从评估开始累计 48 个完整日样本前保持无交易。这保留“无显式预热、等待 slow ready”的行为，但仍改变原样本，并须明确仅有 USDT 现金及成交/费用假设，分类只能 ADAPTED。尚未据此签 C0、认领或运行；账户模块复用适配由另一位审查者独立预检。

如果未来改为“评估第一天之前必须就绪”，在明确 UTC 日线边界的方案下至少需要 48 根完整前史；当前缺 17 根，2022-11-14 至 2022-12-31 才覆盖 48 根。此方案需要后续补取并 QA，属于改变初始化的选择，不能与冷启动混用。采用 5×48 根预热也必须另标适配，不能伪装成原文要求。

若坚持原窗口复现，须以后补取原窗口的合规行情并解决原版本/账户问题。此次委托不取行情。现有窗口曾被研究使用，不称新样本外验证。

## 合成验证与交接边界

`synthetic_preflight.py` 本地运行 18 项 PASS：实际可见原类在方法记录 stub 中检查了初始化参数、非就绪阻断、状态入场、等值、只多不空、持有不重复调仓、`previous` 不构成交叉门；独立数学 EMA 检查 31/47/48 次更新和首值/递推。耗时约 1 ms，RSS 约 11 MiB。这不是 Lean/C# 实际执行、账户或历史回测通过的证据。

后续 C0 必须逐项声明：账户初始现金及币种、Margin/Cash 差异、目标与费用币种、lot/min-notional、EMA 初始化、完整日线时戳与下单时序、填补缺口、终值/基准。不能把 native5m 的 ROI/stop、95%预算、2bps 滑点或 8/0/20bps 成本直接套入并称原策略。

[论坛现行条款](https://www.quantconnect.com/terms/)未为此次抓到的论坛代码建立可再分发开源许可。Lean 仓库的 Apache-2.0 仅适用于其仓库；不传递给社区帖子。原论坛全文、其他评论及代码不进入 Git、Graph 或可转交包；安全交接仅为自写摘要、URL、hash 和合成结论。保留本地证据不等于对外传输获准；如将来需要正文外传，应先明确权利依据。
