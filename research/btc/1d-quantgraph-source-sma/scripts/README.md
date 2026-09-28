# 复现入口

当前使用 [正式研究入口](../../../platform/quantgraph-integration/scripts/research_v4.py)，显式传本家族新冻结合同、经过独立审核的 manifest 和 Graph 计算的 ELIGIBLE 候选。

[audit_trusted_result.py](audit_trusted_result.py) 接受 `--contract`、`--manifest`、`--result-dir`，从原始数据验证入口重新读取，独立重算前 n 根收盘 SMA 信号并对账全部参数的成交、费用、滑点及每日权益。

历史 [V3 脚本](../../../platform/quantgraph-integration/scripts/research_v3.py)只用于明确 raw_unaccepted 诊断，不产生正式证据。
