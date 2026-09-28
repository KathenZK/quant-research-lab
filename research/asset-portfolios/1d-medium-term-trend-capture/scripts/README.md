# 本轮脚本

本目录只服务BIN-1D-MTTC本轮研究。生产规则、输入与代码由[计算前清单](../specs/computation-lock.json)固定，不应按已经看到的收益覆盖它们。

| 脚本 | 作用 |
| --- | --- |
| [audit_inputs.py](audit_inputs.py) | 从固定V3可信入口重新取得日线并核对输入；不用旧家族的价格帧代替 |
| [run_research.py](run_research.py) | 校验锁定文件，生成共同候选、单位机会、三种资金账户及主要统计 |
| [audit_funding.py](audit_funding.py) | 读取内容验证的资金费资料，完整窗口与真实标记价/日线价格近似分开报告 |
| [test_audit_funding.py](test_audit_funding.py) | 资金费窗口、未知值和现金计算测试 |
| [export_findings.py](export_findings.py) | 只读取已保留结果，导出胜率、年度机会与贡献删除等解释表 |
| [explain_capture_gaps.py](explain_capture_gaps.py) | 事后分解等待与最大回撤路径，不新增策略或重选参数 |
| [plot_equity_and_drawdown.py](plot_equity_and_drawdown.py) | 只读取保留的账户日表和指标，绘制中文权益与回撤图，并核对图中终值和回撤 |
| [audit_research.py](audit_research.py) | 从保留输入独立重建特征、候选、每个机会和全部账户，不调用生产规则实现 |
| [test_audit.py](test_audit.py) | 独立审计的合成时序、持仓、现金案例 |
| [audit_statistics.py](audit_statistics.py) | 显式展开抽中的日历行，独立重建两档各10000次联合统计及解释表 |
| [audit_funding_independent.py](audit_funding_independent.py) | 独立核对资金费来源、覆盖、归属事件与现金；保留首次运行的原始字节 |

共享规则实现与测试在[固定v1内核](../../../_shared-kernels/medium-term-trend-capture/README.md)。本轮的运行日志、审计源码快照、校验收据和产物均在[artifacts](../artifacts/README.md)；资金费独立脚本原先从临时产物目录执行，随后原字节移到本目录，[迁移收据](../artifacts/funding-independent-relocation.json)记录原路径与同一SHA256，不改写旧审计记录。

复现需使用正式Lab环境与本轮固定数据组合；原始日线、费用资料、启动清单与源码指纹缺一不可。不要为了使脚本运行而改用当前最新行情或其它家族缓存。后续修改实现应另建版本并保留本轮锁定结果。
