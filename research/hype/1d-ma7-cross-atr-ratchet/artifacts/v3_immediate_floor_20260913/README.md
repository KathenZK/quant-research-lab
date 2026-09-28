# HYPE双触发一步收紧 · 2026-09-13

[HYPE全部路径](html/coins/HYPE.html) · [四方案与交易对照](html/index.html) · [中文结论](../../diagnostics/v3-immediate-floor-results-20260913.md) · [固定规格](../../specs/v3-immediate-floor-20260913.md)。只运行HYPE，保留同一原数据、成本、自然就绪和截止。

`B`为当前V3；`A`只加反向0.2ATR一步到0.5；`S`仅四日停滞一步到0.5；`AS`为用户指定双触发方案。四个账户的完整成交、止损、权益、事件位于accounts；comparison.csv与trade_comparison.csv分别保存账户和每笔得失；floor_triggers.csv保存所有一步收紧的生效原因。

先固定规格、v7代码散列与运行源，再验证和回放。`started.json`绑定源，`input.json`保留原HYPE来源；`tests.json`和`extra_tests.json`记录16项执行边界检查，`audit.json`为独立公式复核，`dom_audit.json`为离线交互检查。最后[交付记录](delivery.json)与[产物散列](artifact_checksums.json)绑定交付内容，不修改原结果。

复算入口为本家族scripts/run_immediate_floor_20260913.py（输出目录须为空）及scripts/build_immediate_floor_20260913.py；独立止损公式位于audit_immediate_floor_20260913.py，图表交互核验为audit_immediate_floor_dom_20260913.cjs。共享内核用[消费方pin](../../specs/v3-immediate-floor-engine-pin-20260913.json)定位，不能用未来代码替换。

本轮仅保留一份HYPE正式输出。批量账户与HTML为可再生本地产物，不新增普通Git大文件，不上传、不迁移、不删除旧证据。未知资金费、既有源证据边界和样本末未平仓估值保持披露。
