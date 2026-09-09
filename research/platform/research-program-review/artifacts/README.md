# 审计证据

- [research-inventory-2026-09-08.json](research-inventory-2026-09-08.json)：所有 126 份研究主账及同目录 README 的路径、哈希和状态原文候选；不是 126 次完整复现，也不据关键词统计策略胜负。
- [family-outcome-audit-2026-09-08.md](family-outcome-audit-2026-09-08.md)：跨家族结果、门槛、成本和实盘试运行的只读证据记录。
- [data-engine-audit-2026-09-08.md](data-engine-audit-2026-09-08.md)：数据与回测代码证据、定向测试、最小反例及适用边界。
- [methodology-ml-audit-2026-09-08.md](methodology-ml-audit-2026-09-08.md)：近期事件研究和 ML 的裁决边界、复现问题与前瞻状态。
- [audit-source-manifest-2026-09-08.json](audit-source-manifest-2026-09-08.json)：本次证据文档所引用的现存仓库文件哈希及交付校验。

目录盘点脚本：[inventory_research_program.py](../scripts/inventory_research_program.py)。脚本仅读取文档及文件元信息，不读写行情数据。

绩效数字以原冻结研究报告为来源，本次未全量重跑。人工阅读、元数据扫描、现有测试和最小反例分别记录，不能互相替代。
