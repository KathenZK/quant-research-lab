# 一键复现

所需 Python 3.13 与依赖固定在 [requirements-lock.txt](../specs/requirements-lock.txt)。本次独立运行环境为 `/tmp/xa-sast-runtime`，没有改原仓库环境；环境可删除后按锁重新创建。

在仓库根执行：

```sh
SAST_PYTHON=/tmp/xa-sast-runtime/bin/python sh research/asset-portfolios/1d-small-account-slow-trend/scripts/reproduce.sh
```

其他机器在自己的虚拟环境安装上述锁文件，设置 `SAST_PYTHON` 为该环境的 Python。复现读取已留存原生快照，不访问网络、不读取共享数据湖。输入 SHA256 不一致立即拒绝，研究产物写回本家族的 `artifacts/`；可先复制本家族到新输出目录进行复现。

- [run_research.py](run_research.py)：验证合同与输入指纹，检查原生行/日历/分配/拆股，输出12变体逐单、现金、持仓、净值、贡献、压力和图。
- [supplementary_audit.py](supplementary_audit.py)：独立读取导出CSV，重放整股持仓，核算费用/权益/逐资产PnL，输出真实例子、满仓SPY数学参考和最终哈希。
- `run_research.py --fetch` 仅用于重建缺失的新快照，已有原生文件不覆盖。重新下载的数据可能被提供方修订，不能宣称会等于当前冻结版本；正常复现不加此参数。

实现只负责研究；没有券商连接、下单功能、自动化任务或生产 runner 入口。
