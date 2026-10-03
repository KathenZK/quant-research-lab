# PUBLIC-M0315-UNIVERSAL-MACD 主账

| 字段 | 内容 |
| --- | --- |
| 稳定 ID | M0315 |
| 版本 | M0315-BTCUSDT-5M-DEFAULTS-2024-20261003 |
| 运行 | M0315-20261003-first-replay |
| 原规则 | 5m EMA12/26 比率负区间；保留空卖出区间；原 ROI／止损 |
| 实例 | BTCUSDT spot，2024-01-01..2025-01-01 excl |
| 分类 | HYPOTHESIS；历史诊断；严格复现 0 |
| 状态 | explore / 未晋升 / 非实盘 |
| 数量 | 1 ID，4 策略配置，1 控制，0 参数搜索；旧总搜索次数 UNKNOWN |
| 核心结果 | base +8.3399%，MDD10.0628%，7 完整交易；同窗买持 +115.0304% |
| 验证 | 原类信号一致、独立账户核验、因果探针、本地离线恢复 PASS |
| 远端恢复 | 未验证；由 root 协调保存，当前 Library401 阻塞 |

依据：[冻结协议](specs/M0315-first-replay.json)、[完整报告](diagnostics/M0315-20261003.md)、[结果清单](artifacts/20261003-first-replay/result-manifest.json)、[恢复凭据](artifacts/20261003-first-replay/local-recovery.json)。后续研究不能覆盖此版本。
