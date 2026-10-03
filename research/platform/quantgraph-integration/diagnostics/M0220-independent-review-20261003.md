# M0220 独立只读契约审查

审查时间：2026-10-03 07:16:09 UTC。结果：**静态契约审查PASS（限下列代码hash）；不是运行结果QA或原TradingView严格等价认证。** 未执行策略、未增加参数变体，未改M0220家族文件、全局或Git。实际model/effort：UNKNOWN。

## 审查对象

- 作者Pine：research/public-strategies/M0220/artifacts/20261003-source-preflight/author-source.pine，SHA256 `8231266815c7ce26940f3254cd7574057612f0ad388b57a45874fa23e4cebc04`。
- 主执行脚本：research/public-strategies/M0220/scripts/run_replay.py，SHA256 `67e3480423d046c046fc31fa23c9fb0e55245a9fa708d882bf81ad363ba217d3`。
- 主规格：research/public-strategies/M0220/specs/M0220-first-replay.json，SHA256 `94dda14cf3da031e6069d56705b716d982bbb7aa9163a222fdbef060d25e1b41`。
- 同目录来源预审报告。没有读取凭证、登录材料或会话。

## 核查结果

| 项目 | 结论与实现核对 |
| --- | --- |
| 跟踪止损基底 | 源默认是low，窗口最高low（7），脚本rolling(7).max作用于low，未错写highest(high)或lowest(low)。谨慎条件另用highest(high,7)。 |
| ATR5 | 初始TR为high−low，后续取真实振幅三项最大；首5个TR均值种子，之后(旧值×4+TR)/5，符合声明Wilder种子。源完整平台历史的初始点未知，不能声称平台数值一致。 |
| 昨日谨慎 | 候选止损取当天ATR和最高low，以caution[i−1]选择0.2或1倍，正确区别于当天caution。 |
| stop状态 | 发买入信号时清空旧stop；成交后首次持仓收盘初始化；以后取max只抬不降。退出以更新后的stop和当前周EMA比较。卖出后残留stop不能影响flat分支，下一买信号重新清空。 |
| 日EMA与谨慎 | EMA alpha2/21，首输入收盘种子；bullish限定、7日最高high减当前low、1.5ATR、日收盘低于日EMA均有保留。 |
| 周EMA映射 | 历史源request.security默认lookahead_off先返回日图映射值，再外层偏移一根日bar；UTC日图假设下周日刚完成周EMA从周一收盘决策可见。脚本将完整周值映射至下一周start，周日仍用更早完整周，未把周末值泄漏到同周周一。 |
| 完整周与预热 | 周一起始分组只纳入7行完整周；首完整周2022-12-05—12-11，第20完整周结束2023-04-23；Apr24首决策、Apr25首可能成交。源码本身未强制20周，规格已把此列为保守假设；EMA种子残差仍存在。 |
| 开盘及收盘状态顺序 | 先成交待执行单，再日终指标、持仓ratchet及信号；买入当天收盘允许退出信号，其卖单仍下一开盘成交。没有日low触碰即按stop价成交，也没有同收盘成交。 |
| 费用和现金 | 买名义额cash/(1+fee)，数量再除含滑点成交价；现金扣名义额+手续费，零现金残差归零，避免源100%权益再收费用可能透支。卖出量−qty，现金增加卖出金额减费，仓位清零。此为声明的含费现金假设而非原模拟器精确复制。 |
| 成交价格 | 买为对应成交bar原始open×1.0002，卖为open×0.9998；不会按止损价或合成信号价成交。lag1为nextopen，lag2为第二后续open，benchmark首评估open。 |
| lag2队列 | 多日重复信号可形成多个待执行动作；不符合当前状态的BUY/SELL会被忽略。规格明确保留stale order，不是隐藏修改；需在报告保留该敏感性与源单一订单ID行为不同。 |

## 结论范围与剩余检查

未发现当前主脚本在上述冻结假设下的执行bug。源与假设区别（UTC周界、起始种子/20周、手续费包容仓位、滑点、lag2队列）均已写规格，fidelity应保持HYPOTHESIS，严格0。

本审查没有运行策略或独立账本；收益、逐行净值、成交、未来扰动与恢复一致性仍由主执行者的独立验证流程实际证明。读取时该目录仅run_replay.py，尚无独立校验脚本可审。若主脚本/规格hash改变，本报告不能自动覆盖修改后版本；需另核差异或补充hash记录，不能把本PASS当后续文件的通行证明。
