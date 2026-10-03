---
research_classification: diagnostic_topic
---

# 批019：M1266固定数量与持仓收盘峰值预检


仅冻结收益前规则、来源指纹和输入QA，执行者为母端dot，尚未启动历史。原公开论坛两个源码版本明确区分；选择修正版，不公开全文。BTCUSD/Bitfinex原实例改为BTCUSDT/Binance的研究代理，严格复现0。

- [规则](M1266-root-frozen-rules.json)、[执行输出契约](../catalog-fixedqty-batch019-output-contract-20261003.json)及[分配](../claims-20261003-batch019.json)。
- [原草案](draft-v2-original.json)、[来源审查](source-review.safe.json)、[独立草案审查](independent-draft-review.safe.json)。root新增明确卖出Decimal分组及输入pin，未运行历史。
- [输入manifest](input-manifest.json)、[输入QA](input-qa.safe.json)、[独立QA](independent-input-review.safe.json)、[新增6请求回执](input-fetch-receipt.json)。831行=100预热+731评估；原853行中前22行只保留于raw，不作EMA种子；旧762行不改。
- [离线输入重建](build_input.py)：`python build_input.py --raw AUTHORIZED_RAW --output NEW_PRIVATE_DIR --expected a21612759ddd7e849f4a5e5b3ac62f74b003c84bf9e0e77d45ab8670b59eb550`。默认离线；重新获取需仍在既有授权范围，不调用被拒绝FAPI路线。完整源码附件及raw仅私有保留。
- [决策](decision-log.md)。规则与输入通过不等于代码或历史放行。

- [root最终冻结差分独审](independent-rootfreeze-review.safe.json)：输入pin、卖出Decimal分组及规则保持通过；仍不替代实际代码C0门禁。
