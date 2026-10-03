# M0304 恢复说明

## 当前可执行：离线准备包验证

本包只恢复源码指纹、移植公式、计划和阻断证据，不能恢复尚未执行的市场收益。使用已验证 Python3.12.14 / numpy2.3.5 / pandas2.2.3 / TA-Lib0.6.8 环境；本次不安装或升级依赖。输出目录必须不存在。

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
python research/public-strategies/M0304/scripts/verify_preparation.py \
  --output-dir /tmp/m0304-preparation-recovery-NEW
```

脚本核 publication-manifest 所有已列文件 bytes/SHA256，并重跑合成指标测试。0网络、0行情、0历史收益。独立审计与实际准备包恢复回执如已取得，见 artifacts。

独立标量公式oracle也可单独重跑；不提供原文件时源码校验明确为NOT_RUN，不影响合成公式对照。它不读取市场行情，也不是交易账本审核：

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
python research/public-strategies/M0304/scripts/scalar_formula_oracle.py \
  --record-id M0304 --output /tmp/m0304-scalar-audit-NEW.json
# 如另已合法取回并验证固定源文件，可加 --source /path/to/Strategy002.py，仅AST读取
```

## 未来才可执行：固定原始输入恢复

当前首请求 tunnel403 硬停，本条目不会自动重试、换host/周期/窗口/环境/代理，也不会搬运其他工作区的raw数据绕过限制。新增的同源有限重试由整合方按用户明确授权独占执行；以下配方本身不是新权限。访问恢复和条款审核获准后才可运行，任一403/451、重定向、校验失败或低于5GiB磁盘余量立即停止并保留失败目录。

继承builder SHA256 e217666105d2a454b61bb93d4306f2c91af9d6356182baaf57d145645556f182，verifier SHA256 4972fedfbe54517423c94d834efda557a99a2667ddd067be31acc5ed5927f746，兼容完整expected manifest SHA256 c7ec9966dbebde94fe65538542b77c3e40a09216513bd7054c204ae67e502102。没有删改 `--expected-manifest`。目标目录及.partial必须不存在。

```bash
set -euo pipefail
python research/public-strategies/M0304/scripts/builder_5m_calendar2024.py \
  --timeframe 5m \
  --target /tmp/m0304-native5m-authorized-NEW/snapshot \
  --expected-manifest research/public-strategies/M0304/specs/input-expected-manifest.json \
  --terms-reviewed
# 仅上一步实际成功后运行（本次还未成功）
python research/public-strategies/M0304/scripts/verify_raw_rebuild.py \
  /tmp/m0304-native5m-authorized-NEW/snapshot
```

builder最多26次原官方GET，验证13月×ZIP/CHECKSUM/CSV共39源对象；verifier不发网络请求，独占写snapshot父目录的独立重建与回执。规范CSV必须为31428289B、SHA256 91e5bb0ba80ba2b70c5d6a5924c590459b0ffbe3e5955ba177abc981fb2a0af2，114336行。

适用来源条款与hash见expected manifest。该数据范围为个人非生产诊断，Binance Vision Dataset Terms与CC BY-NC-SA4许可边界不因本准备包扩大。`--terms-reviewed`表示实际已审的本次许可范围，不是绕过审批开关。即使恢复成功，也不能跳过完整执行C0与明确历史运行许可。
