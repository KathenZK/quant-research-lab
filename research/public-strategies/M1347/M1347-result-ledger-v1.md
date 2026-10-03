# M1347 结果主账 · catalog-v1

| 项目 | 本次实际结果 |
| --- | --- |
| 实现及运行 | 1 个稳定 ID、1 规则实现、4 预定配置；新增对照 0 |
| 原代码 commit | `5ccadf192dfc6381721058d28887cd9bc435a20c` |
| C0 SHA256 | `95c1aaee84657d0d3639c94d282e6e4bfa9934ba9f3b4c6fa5aaed13355dfed3` |
| 实际首次运行 UTC | 2026-10-03 18:46:39.316264 至 18:46:39.486805 |
| 基础配置 | 收益 −27.7031%、MDD −30.1075%、Sharpe −0.8564 |
| 账户 | 47 笔成交、23 笔闭合交易，8 胜 15 负；期末持有 BTC |
| 对照 | M1258 已验 fullcash 买持 +465.1300%；本次不重跑 |
| 本地验证 | 2924 日净值、188 成交、96 月报；独立校验与 31 文件真恢复通过 |
| 策略判断 | 诊断中全部配置亏损，不支持当前假设；不晋升，不挑选改参 |
| 分类 | HYPOTHESIS_FROM_CATALOG_NOT_SOURCE_VERIFIED / ADAPTED_EXECUTION_PROXY；严格 0；非 OOS |
| 保存状态 | 本地私有包另有独立清单；Git 远端和 Library 私有包由 root 分别核验 |

详见[报告](M1347.md)、[结果清单](artifacts/20261003-catalog-v1/private-output-manifest.json)及[本地恢复回执](artifacts/20261003-catalog-v1/local-recovery.safe.json)。清单只是私有输出的指纹，不是公开数据目录或 Graph 展示清单。
