# M0299 核心主账

- 稳定ID：M0299；名称：SimpleBollinger；family `PUBLIC-M0299-SIMPLE-BOLLINGER-CLOUD`
- 版本：source-rule-audit-v1；stage `SOURCE_RULE_DEDUP_AUDIT_ONLY`；冻结审计日2026-10-03 UTC
- 源码：`7c91e0a37bf62165790120d730442e4f6eb00364` / `SimpleBollinger/__init__.py`；SHA256 `746cc0f8644a7fae12089f597448b573d4d482a3855c870d18b4a7bfeb0a5255`
- 规则结构canonical SHA256：`f8e29bcc282b75b797deb9fab14dadbe267b6d83176bcc4ba5b342300ed1bcca`（JSON排序、无空白，排除此自描述hash字段）
- 原catalog记录号：300（含header）；原11字段保持
- 当前状态：来源核验通过；规则差异/运行依赖已登记；原作者runtime UNKNOWN；strict replication未建立
- 实际运行：市场请求0、历史0、原生Jesse/Rust0；合成16项；不是策略参数试验
- 升级/部署：否；strict reproductions0；没有收益指标或曲线
- 重复处理：PRESERVE_ID_NO_AUTOMATIC_MERGE，已记录相关或不同定义，exact duplicate未确认
- 可恢复证据：公开脚本/manifest+私有原源码与参考依赖；本地恢复与异地备份状态由实际receipt记录，不因存在下载URL视作完成

[完整规格](specs/source-rules-v1.json) · [中文报告](notes/source-rule-audit-v1.md) · [合成](artifacts/synthetic-audit-v1.json) · [来源](specs/source-manifest-v1.json) · [决策](decision-log.md)
