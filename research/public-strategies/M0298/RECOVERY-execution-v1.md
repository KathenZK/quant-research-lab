# M0298 执行版本v1：恢复与独立账本核验

本版本已完成4+1，并使用独立重建输入在新目录重跑。恢复复制同一冻结实验，不增加参数搜索或制造OOS结果。Python3.12.14/numpy2.3.5/pandas2.2.3/TA-Lib Python0.6.8/C0.6.4，Linux RLIMIT_AS1GiB，BLAS线程1。命令不自动安装或升级。

## 输入恢复先决条件

使用同包[M0304恢复配方](../M0304/diagnostics/recovery.md)内附的固定builder和verifier；它们来自原batch007-native5m-preflight-20261003交接，字节与下列原始pin完全一致。原始市场数据不包含在本公共包。任何新网络恢复仍须具备适用的数据许可和执行授权，不能把保留的--terms-reviewed标志当作未来许可。不得为复现换host/窗口/周期/环境或绕过403/451。

从Lab仓库根执行，目标及.partial必须不存在，保留至少5GiB空闲；下列bash失败会立即退出，不会继续调用verifier：

```bash
set -euo pipefail
python3 research/public-strategies/M0304/scripts/builder_5m_calendar2024.py \
  --timeframe 5m --target /tmp/M0298-authorized-restore/snapshot \
  --expected-manifest research/public-strategies/M0304/specs/input-expected-manifest.json \
  --terms-reviewed
python3 research/public-strategies/M0304/scripts/verify_raw_rebuild.py \
  /tmp/M0298-authorized-restore/snapshot
```

expected-manifest为FULL兼容字段及protocol原文件，SHA256 c7ec9966dbebde94fe65538542b77c3e40a09216513bd7054c204ae67e502102。builder SHA256 e217666105d2a454b61bb93d4306f2c91af9d6356182baaf57d145645556f182；verifier SHA256 4972fedfbe54517423c94d834efda557a99a2667ddd067be31acc5ed5927f746。规范CSV必须为31428289B/114336行/SHA256 91e5bb0ba80ba2b70c5d6a5924c590459b0ffbe3e5955ba177abc981fb2a0af2，39源对象及完整QA须通过。

历史snapshot或脚本地址不能保证未来可重获相同输入。恢复失败时保留失败证据并停止，不降低QA或换成另一个文件。

## 合成测试和冻结4+1重放

设置PY为预先验证的兼容Python，INPUT为已通过上述完整QA的规范CSV。OUTPUT目录必须不存在；工具拒绝覆盖。以下以原字节C0和release验证全部pin，使用公共release旁边的三份原字节审计收据；不依赖私有review目录。

```bash
set -euo pipefail
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
PY=/path/to/compatible/python
INPUT=/tmp/M0298-authorized-restore/snapshot/BTCUSDT-5m-202312-202412-native12.csv
mkdir -p LOCAL_OUTPUT
"$PY" research/public-strategies/M0298/scripts/replay_v1/test_engine.py \
  LOCAL_OUTPUT/M0298-synthetic-engine-new.json
"$PY" research/public-strategies/M0298/scripts/replay_v1/replay.py \
  --input "$INPUT" \
  --freeze research/public-strategies/M0298/specs/C0-20261003-v1.json \
  --approval research/public-strategies/M0298/artifacts/execution-v1/M0298-C0-release-v1.json \
  --out LOCAL_OUTPUT/M0298-frozen-replay-new
"$PY" research/public-strategies/M0298/scripts/audit_v1/historical_ledger_oracle.py \
  --record-id M0298 --results LOCAL_OUTPUT/M0298-frozen-replay-new \
  --output LOCAL_OUTPUT/M0298-independent-ledger-new.json
```

恢复不能修改冻结代码/协议再借用旧C0。必须重放全部4策略配置和同窗buyhold；本CLI不支持选择最优配置或改成本/窗口。全长NAV/信号/交易/订单仅写本地，包含原始价格字段的输出不要擅自公开或上传。

原执行输出哈希见[本地结果指纹](artifacts/execution-v1/full-local-result-hashes.json)。同环境重放预计31个文件逐字节相同；summary包含进程峰值RSS，该字段允许变化，因而summary及依赖它的result-manifest通常不逐字节一致。完整业务summary剔RSS后必须一致，全部其他文件必须匹配；不能把这两项差异泛化成收益/交易容差。

独立账本CLI只读取输出，不运行策略；它从前一现金重建数量、费用和摩擦，逐bar核验账户，并独立计算全5m MDD与日Sharpe。50位Decimal不是原始数据真实性证明；与[输入独立QA](artifacts/execution-v1/independent-canonical-qa-v1.json)和[原恢复成功回执](artifacts/execution-v1/data-recovery-safe-v2.json)分开理解。

私有远程备份和Git远程读回由上层交接另行验证，本文件不宣称已经完成。日度展示不是原始行情或全部净值的替代，本地恢复也不等于异地容灾。
