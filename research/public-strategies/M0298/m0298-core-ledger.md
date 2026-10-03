# M0298 家族主账

## 当前状态

- ID M0298；Simple；PUBLIC-M0298-SIMPLE
- 当前版本 M0298-calendar2024-execution-v1-20261003；变体 M0298-BTCUSDT-NATIVE5M-SIMPLE-20261003-v1
- 已测试假设实例：HYPOTHESIS / DIAGNOSTIC_ONLY，strict0，非OOS，不晋升、不部署
- 固定4配置+同窗buyhold共5个首次运行；独立恢复复制同5配置，无新增参数化或搜索
- base +31.51%、全5m MDD−39.68%；buyhold +115.03%/−32.02%。成本与延迟敏感，实例落后对照
- 1828 fills/527040 bar账户标记独立Decimal审计PASS；31/33恢复文件字节一致，summary仅RSS差异，业务内容全相同
- [完整结果](diagnostics/M0298-native5m-results-20261003.md)、[C0](specs/C0-20261003-v1.json)、[放行](artifacts/execution-v1/M0298-C0-release-v1.json)、[原始数据QA](artifacts/execution-v1/independent-canonical-qa-v1.json)、[实际账本审计](artifacts/execution-v1/M0298-historical-ledger-audit-v1.json)、[恢复](artifacts/execution-v1/recovery-receipt.json)

## 历史与冻结

- [原21文件预审版本](history/preparation-v0/README.md)全部原字节保留；manifest SHA1af70a7a555e4e8260d7380d59cc3aca082491184e3c3c4a3501e0a3170397f6
- 首次403不抹去；成功来自后来用户授权的同源重试，未换源/周期/窗口
- C0于12:48:26.079295UTC冻结；独立放行12:50:14.681680UTC；首跑12:50:59.442338429UTC启动，均为2026-10-03
- 原源码、规则、执行代码、输入和环境固定；完整代码/输入hash见C0。任何后续改动须另建版本，不回写该冻结
- 作者runtime/资产池未知；PIT/finality/tradability均未建立。远程备份/分支发布须以上层实际回执为准，本主账不代为宣称
