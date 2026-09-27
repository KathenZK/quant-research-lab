# QuantGraph 市场账户内核

`v1/engine.py`：闭合栏信号、下一栏开盘、现货只做多、逐笔费用和不利滑点、保守止损/止盈及期末清仓。
只做确定性计算；数据准入与 V3 候选门槛在调用层完成。直接调用不产生正式研究证据。
本版冻结后不原位改算法；新行为新增版本。数学诊断继续引用 `quantgraph-diagnostics/v2`。

冻结 SHA256：`v1/engine.py` = `fc2161abeef0cc06303e0e41945f875e11c9c75758bfa125971a709ab770254b`。
消费方：platform/quantgraph-integration/scripts/research_v3.py；BTC 三个 quantgraph-source 家族。
