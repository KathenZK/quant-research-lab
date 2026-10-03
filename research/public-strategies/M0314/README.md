# M0314 TurtleRules：源码、规则与重复审计

状态：SOURCE_RULE_DEDUP_AUDIT_ONLY。只完成来源与规则审计，不是历史回测完成。行情请求0、历史运行0、原生引擎运行0、严格复现0；没有净值/收益率/交易输出。

原11字段与原文均未修改，6973条主表SHA256 `15cc0ecbcb23261e3cd7f2fb0851815daed59951090d9ce3e759ef224ea6f415`；含header记录号315，物理行315。原catalog“可回测=高”是原记录字段，不代表本次执行状态。

- [独立中文审计](notes/source-rule-audit-v1.md)
- [主账](m0314-core-ledger.md) · [decision log](decision-log.md)
- [规则结构](specs/source-rules-v1.json) · [来源固定清单](specs/source-manifest-v1.json)
- [原11字段CSV](artifacts/catalog-original11.csv) · [精确行定位](artifacts/catalog-original11.json)
- [源码指纹](artifacts/source-ast-fingerprint-v1.json) · [去重关系与边界](artifacts/dedup-review-v1.json)
- [合成检查](artifacts/synthetic-audit-v1.json) · [独立静态复审](artifacts/independent-source-review-v1.json)
- [公开Graph结构](artifacts/graph-record.json) · [离线恢复](RECOVERY.md) · [公开文件清单](publication-manifest.json)

当前原作者runtime与完整执行契约未知；未设置/补造4h路由。相关不等于重复；保持ID，不自动合并、删除或重编号。未晋升，未部署。
