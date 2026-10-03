# M0304 执行v1恢复

## 当前已证明

固定协议/代码在新复制目录、独立raw重建的CSV上成功重放全部4+1，22个输出文件相同；仅summary的峰RSS不要求一致。源码、依赖与C0不因恢复改写。本次没有新的参数搜索。

## 离线重新生成并独立审计

需要已经恢复并重新校验的固定CSV，不能拿其他窗口/周期/别人的临时路径替代。依赖已安装为Python3.12.14、numpy2.3.5、pandas2.2.3、TA-Lib0.6.8；原C库版本和二进制hash见协议。下面输出目录和审核文件必须不存在。INPUT/OUT换成当前执行机真实路径。

```bash
set -euo pipefail
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
INPUT=/absolute/path/to/BTCUSDT-5m-202312-202412-native12.csv
OUT=/tmp/m0304-execution-recovery-NEW
python research/public-strategies/M0304/scripts/execution-v1/replay_engine.py \
  --input "$INPUT" --output "$OUT" \
  --spec research/public-strategies/M0304/specs/execution-v1/protocol.json \
  --gate research/public-strategies/M0304/specs/execution-v1/run-gate.json
python research/public-strategies/M0304/scripts/execution-v1/historical_ledger_oracle.py \
  --record-id M0304 --results "$OUT" \
  --output /tmp/m0304-independent-ledger-NEW.json
```

该引擎在读取数据/收益前验证固定源CSV bytes/hash、全部执行脚本hash、包版本、TA-Lib二进制、compatibility和RSI unstable设置。读入后再核全网格和OHLCV约束。独立账本审核脚本调用同目录ledger_decimal_core模块的独立verify函数；两个文件均无原审计工作区路径依赖。

对新生成结果和公开summary、result-manifest逐项核对。若持有原私有22文件结果包，还可使用同目录recover_run.py，参数为 --input、--source-run、--output、--spec、--gate、--receipt；该程序严格比较文件集、21文件SHA和summary除RSS外全部内容。

## 原始输入尚不存在时

先遵守[原始输入恢复配方](recovery.md)：许可/访问获准后才使用原官方host的builder与完整expected manifest；真实shellguard保障任一失败不继续verifier。39源对象、114336行和独立重建全部通过才进入上述回放。历史第一次403与后来用户授权单次同源成功是不同事实，成功不授权未来绕过403/451、改host或无限重试。

## 合成审核

执行层test_execution.py和check_execution_prefix.py将输出写入其所在目录，为保持公开包不可变，应把scripts/execution-v1目录复制到新的临时目录再运行，不能覆盖已冻结证据。它们使用同目录planned-protocol.json及自身生成的合成OHLC/信号，不读取真实行情。无需市场输入即可跑原formula_probe.py；独立scalar_formula_oracle.py见前版恢复说明。
