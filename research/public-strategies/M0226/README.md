---
research_classification: diagnostic_topic
---
# M0226 BTC动态定投：规则预审

状态 **BLOCKED_RULE_EXECUTION**；研究ID 1、回测0、严格复现0。尚未冻结执行版本，不建立core-ledger。

[预审报告](diagnostics/M0226-20261003-source-preflight.md) · [决策记录](decision-log.md) · [结构化来源审计](artifacts/20261003-source-preflight/source-review.json)。

catalog经协调者合法读取：@CryptoPainter 日频BTC定投，金额依长均线距离与RSI调整，下限约500U/天，满额约1000U/天；均线周期与映射公式未公开。这些仅是catalog规则描述，不等于本执行者已核实原帖。

两个X链接正常打开均返回403 Forbidden；另一个协调者提供的URL提示工具不可访问。没有重试或另找访问路径。每日投入公式、外部资金流和退出/终值定义未闭合，不能以标准DCA代替原策略。现金流投资不能使用自融资策略净值公式宣称收益。
