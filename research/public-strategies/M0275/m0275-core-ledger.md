# M0275 主账

| 字段 | 固定身份 / 当前状态 |
|---|---|
| 家族 | PUBLIC-M0275-HERACLES |
| 原始目录ID | M0275 |
| 原作者 / 名称 | Mablue（Masoud Azizi）/ Heracles |
| 来源commit | f3340ce11f5bdf62f598522e64d1f5638eaa13f5 |
| 来源SHA256 | 5b25d85297329243d7a3c65770975b5a70e52ec2684b1e007e5d8a3d1a7e3718 |
| run | M0275-20261003-first-replay |
| variant | M0275-BTCUSDT-4H-HERACLES-15-9-20261003 |
| 冻结协议SHA256 | 95bea6e9c9f1dfe4f72e125506a95e43b723cef6491b7619f89a8db935621798 |
| 保真分类 | HYPOTHESIS，严格复现0 |
| 数据状态 | DIAGNOSTIC_ONLY / trusted=false / EXPLICIT_DIAGNOSTIC |
| 当前结论 | 已完成真实历史行情回测；基础回报、回撤、Sharpe均不及同仓位成本买持 |
| 验证 | 源码AST/独立公式、107指标前缀、55执行前缀、独立Decimal决策及账本、风险时钟、22文件本地恢复均通过 |
| 晋升 / OOS / 实盘 | 全部否；历史窗口已曝光，未知历史搜索次数不填0 |
| 保存状态 | 本地C2完成；远端C3待协调者真实读回，不以工作盘冒充备份 |

## 证据定位

- [冻结规格](specs/protocol.json)：标的、资金、费用、风险优先级和分钟ROI代理
- [来源清单](specs/source-manifest.json)：与私有主表M0275原行核对，未发布主表全文
- [曝光账](specs/exposure.json)：本轮参数搜索0；不宣称未见样本
- [完整研究报告](diagnostics/M0275-20261003.md)
- [独立审核](artifacts/independent-real-result-audit.json) / [C2回执](artifacts/C2-validation-receipt.json)
- [重建/恢复](diagnostics/rebuild-20261003.md)

不能由一个BTC实例推论作者全币池效果；AgeFilter原始运行、原作者环境、逐笔路径、PIT及严格历史终局均未证明。
