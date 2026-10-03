# M1266 协调验收增补（2026-10-03）

本次冻结的4个策略配置及1个原始控制已通过协调验收。分类仍为来源修正版的执行适配诊断；严格复现0、trusted=false、OOS=false、PIT=UNKNOWN。

原[研究报告](M1266.md)、C0、代码和12件发布载荷保持原字节；其中“协调验收待完成”是发布时的冻结状态。当前验收由本增补及[协调验收收据](recovery/coordinator-acceptance-20261003/acceptance.safe.json)记录。

验收依据包括：原始历史独审回执及实际Library恢复回执已准确接收；35项跨证据核对通过，原7件结果指纹与公开恢复锚点一致。父端独立Decimal核验323587个数值节点、23个前缀和5个未来扰动；父端实际恢复原292项完整包并由原runner验证132个C0指纹，7件结果4660509字节一致。协调执行器没有重跑历史或材料化该完整私包；后来432项扩展包也不在这两份回执的验收范围。

base总收益60.13%，声明的90%信号时固定数量买持控制419.02%。base持仓193/731天，较小回撤与更低风险暴露并存，未做收益归因，也未建立策略优越性。fee0、fee20、delay2保留为事前冻结的敏感性，不能根据结果选择最佳参数。完整指标及失败场景见原报告。

- [原回执的脱敏交叉审核](recovery/coordinator-acceptance-20261003/receipt-evidence-review.safe.json)
- [12文件公开范围审核](recovery/coordinator-acceptance-20261003/publication-review.safe.json)

PR39已合并至 `475ee92d451b581b8565dc1ef487437cdc39b743`，精确main CI通过。原Graph投影保持冻结；此次验收不创建实体revision，也未部署Site。
