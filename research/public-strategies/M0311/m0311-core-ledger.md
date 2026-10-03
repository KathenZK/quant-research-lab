# PUBLIC-M0311-TECHNICAL-EXAMPLE-CMF 主账

| 字段 | 记录 |
| --- | --- |
| ID／版本 | M0311 / M0311-BTCUSDT-5M-CMF21-EXECUTION-PROXY-2024-20261003 |
| 分类 | ADAPTED / ADAPTED_EXECUTION_PROXY；严格 0 |
| 原逻辑 | CMF21<0 入、>0 出，严格 ROI>1%，止损−5%，原委托 limit |
| 改编 | 下一开盘、足额分数成交，市价式止损／ROI 阈值代理 |
| 研究窗口 | BTCUSDT spot，2024 年；31 天预热，已接触且可用性选择 |
| 计数 | 1 ID、4 策略配置、1 买持；无参数搜索 |
| 结论 | 四配置明显亏损，base−99.995765%；不晋升 |
| QA／恢复 | 源信号、独立 Decimal、严格小余额、因果、一次离线恢复 PASS |
| 备份／部署 | 私有证据等待统一批次保存；远端未验证；Graph 未部署 |

[协议](specs/M0311-first-replay.json) · [报告](diagnostics/M0311-20261003.md) · [结果清单](artifacts/20261003-first-replay/result-manifest.json)。冻结原件不覆盖。
