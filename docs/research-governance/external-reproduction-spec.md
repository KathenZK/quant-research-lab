# 对外复现规格

本格式用于只拿到一份 Markdown、没有仓库的复现者；普通内部研究规格无需套用。

- 文件名包含 `reproduction-spec`，front matter 声明 `document_type: external_reproduction_spec` 和非空 `intended_audience`；声明用途或文件名任一命中即适用。
- 正文完整定义版本、参数字面值、数据获取/质量/闭合 bar、市场/标的/周期/UTC 范围与 schema；给出指标公式、窗口、初始化、EWMA/`min_periods`/lag 语义及信号、过滤、状态机伪代码。
- 定义复现所需的成交时序、同 bar 冲突、跳空、保护/追踪更新、超时、仓位、成本/费率与适用时的组合仲裁。提供验收指标、交易数、冻结契约要求的切片及逐笔锚点。
- 仓库路径、脚本命令和证据链接放在明确标为“仓库内校验（非复现依赖）”的独立附录；正文不依赖附录补齐参数或逻辑。
- 交付前按“仓库不存在”核对变量和步骤，并用 [文档一致性检查](../../tests/test_research_docs_consistency.py) 检查格式。版本参数或逻辑变化时写新日期规格，旧规格标为 `superseded`。
