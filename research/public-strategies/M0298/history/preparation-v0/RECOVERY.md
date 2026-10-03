# 离线准备包重验与未来行情恢复

## 当前限制

本次首个官方 CHECKSUM GET 在 2026-10-03 12:17:23.507340Z 遇 Tunnel403，输入未恢复。当前代码与证据恢复不等于原始行情恢复。父级持有用户后来授权的一次同源等待重试；该网络操作仅由父级管理，本 ID 脚本不主动执行。无权自行换host/窗口/环境、代理绕行或搬入别处原始行情。

## 源码与合成检查

在兼容环境准备 Python3.12.14、numpy2.3.5、pandas2.2.3、TA-Lib Python0.6.8/C0.6.4；不自动安装或升级。通过已授权 GitHub 连接器读取 [固定 Simple.py](https://github.com/freqtrade/freqtrade-strategies/blob/f3340ce11f5bdf62f598522e64d1f5638eaa13f5/user_data/strategies/berlinguyinca/Simple.py)，将精确原字节保存到 PRIVATE_SOURCE/Simple.py，2695B且SHA256必须为812a8d63b0e0ddff6b9bae582c4d573ab9a4ffec6dd0d1c5b8f8180f11db6d0b。文件不导入、不执行，也不公开重分发。

从包含 research/public-strategies/M0298 的包根执行，输出文件必须不存在：

```bash
set -euo pipefail
mkdir -p LOCAL_OUTPUT
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
  /path/to/compatible/python \
  research/public-strategies/M0298/scripts/preflight_synthetic.py \
  --source PRIVATE_SOURCE/Simple.py \
  --output LOCAL_OUTPUT/source-synthetic-preflight-recovered.json
```

此命令只验证源码 AST 和合成输入；不接受历史行情参数，不运行市场模拟，不执行第三方策略原码。结果中的 RSS 随进程浮动，语义测试与源码/脚本指纹应一致。

## 未来固定行情配方，当前不可擅自执行

以下保留原交接用法，只能在父级确认访问恢复、数据许可与本次执行授权后使用。固定 Lab 交接提交48851ef54b5fba6fef1da6825983864e1665fe1e，源文件见[原生5m交接](../batch007-native5m-preflight-20261003/README.md)。从该固定 Lab checkout 根执行；目标目录及.partial必须不存在，保留至少5GiB空闲。首次请求失败即停，不自动重试。

```bash
set -euo pipefail
python3 research/public-strategies/batch007-native5m-preflight-20261003/scripts/builder_5m_calendar2024.py \
  --timeframe 5m \
  --target /tmp/batch007-native5m-restore-authorized/snapshot \
  --expected-manifest research/public-strategies/batch007-native5m-preflight-20261003/specs/expected-manifest.json \
  --terms-reviewed
# 只有上一条成功、完整39来源对象及规范input均验hash通过后，才运行：
python3 research/public-strategies/batch007-native5m-preflight-20261003/scripts/verify_raw_rebuild.py \
  /tmp/batch007-native5m-restore-authorized/snapshot
```

builder原字节SHA256 e217666105d2a454b61bb93d4306f2c91af9d6356182baaf57d145645556f182；verifier原字节SHA256 4972fedfbe54517423c94d834efda557a99a2667ddd067be31acc5ed5927f746。expected-manifest必须为兼容FULL字段/有protocol的原文件，SHA256 c7ec9966dbebde94fe65538542b77c3e40a09216513bd7054c204ae67e502102，不能用摘要替换。

--terms-reviewed只表示已审适用条款，不是绕过未来授权或403/451的开关。固定data.binance.vision来源，最多26GET，任何重定向/403/451/校验失败/缺口/重复/零量/非标准close_time均硬停，保留失败证据。

两条数据命令即使未来通过，也仅证明输入恢复，不能直接启动策略。本包没有历史引擎、C0冻结或收益结果。后续须明确确认完整QA，并另建执行代码/协议/环境/输入/曝光冻结及独立审计。

## 独立标量公式复验

本包附[独立标量oracle](scripts/scalar_formula_oracle.py)，原字节SHA256 38a62443daee5feae1cda9e97efa2b3274199c0c1b2a296a27b0f171d2be673b。它对6000自造bar重算标量指标及prefix/未来扰动，可在没有市场数据时独立运行。下例提供源码时只做AST/哈希检查，不执行原码；不提供--source则输出明确source_check=NOT_RUN_NO_SOURCE_SUPPLIED，不能称源码也验过。

```bash
set -euo pipefail
mkdir -p LOCAL_OUTPUT
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
  /path/to/compatible/python \
  research/public-strategies/M0298/scripts/scalar_formula_oracle.py \
  --record-id M0298 --source PRIVATE_SOURCE/Simple.py \
  --output LOCAL_OUTPUT/independent-scalar-oracle-recovered.json
```

这是同批次共用数学oracle，因此JSON包含两ID公式的合成计数；M0298选项只选择需要核验的源码。本ID实际历史配置数依然为0。[本次实际复验回执](artifacts/independent-scalar-oracle-replay.json)可逐字段核对（运行时间允许不同）。
