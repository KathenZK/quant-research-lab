# M1358 主账

稳定ID M1358；当前ADAPTED诊断v2。参数与原来源见[协议](specs/protocol-v1.json)。源提交 `11a101a855c9ef83a2b4223d49dfa9a6b48d4a51`。

| 版本 | 身份 | 实际历史配置 | 结论 |
| --- | --- | ---: | --- |
| v1 | float64 EMA | 0 | 恒价伪信号，收益前拒绝，证据原样保留 |
| v2 | Decimal EMA / Fraction QA | 4 | 固定配置已运行并验证；严格0，非OOS |

完整中文结论和边界见[M1358.md](M1358.md)。全局进度和远端发布由root维护；本ID不写全局索引。
