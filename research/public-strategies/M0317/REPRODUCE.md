# M0317 固定诊断恢复

## 前置材料

保留本目录精确字节及publication-manifest.json。Python3.12.14、NumPy2.3.5、pandas2.2.3、TA-Lib0.6.8与C0.6.4；具体模块摘要见[依赖清单](specs/dependencies.json)。禁止在恢复时重新运行prepare_freeze.py生成新协议或篡改摘要以绕过检查。宿主共享环境无需再安装，源作者环境未知。

须有已授权且与[输入清单](specs/input-manifest-inherited.json)一致的完整本地快照：25份月ZIP、25份CHECKSUM、25份提取CSV，以及4572行/1298564B的BTCUSDT-4h-202212-202412-native12.csv。主快照及独立网络重建快照CSV的SHA256均为9f5cb39c1426ec91098bb8a1b1f0c926b80760e66fe452d6b0c0aa55429d126c。禁止读1m残留、被拒的12h/session或用其他市场替换。

## 既有输入上的离线复算

以下在Bash中执行，先把所有`/absolute/path/...`占位路径替换为实际绝对路径。`OUT`及各输出回执须不存在，但它们的父目录须预先存在。`SOURCE_DIR`须包含三份已验hash的固定源码：`mabStra.py`、`freqtrade-parameters.py`、`freqtrade-interface.py`。`INDEPENDENT_REBUILD_CSV`明确指向另一已验证重建快照的CSV。必须保留`set -euo pipefail`并按顺序执行，light/raw/source任一检查非零时整个shell立即停止，不继续收益步骤。全部运行单线程，实际执行引擎把地址空间限制在1GiB且要求磁盘空闲不少于5GiB。

```bash
set -euo pipefail
PY='/absolute/path/to/python3.12'
SNAPSHOT='/absolute/path/to/primary-snapshot'
CSV="$SNAPSHOT/BTCUSDT-4h-202212-202412-native12.csv"
OUT='/absolute/path/to/new-M0317-replay'
SOURCE_DIR='/absolute/path/to/pinned-sources'
INDEPENDENT_REBUILD_CSV='/absolute/path/to/rebuild-snapshot/BTCUSDT-4h-202212-202412-native12.csv'
cd '/absolute/path/to/M0317'
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
"$PY" scripts/compare_rebuild_manifest.py --snapshot "$SNAPSHOT" --output "$OUT-light-match.json"
"$PY" scripts/audit_raw.py "$SNAPSHOT" "$OUT-raw-audit.json"
"$PY" scripts/check_signals.py --input "$CSV" --source "$SOURCE_DIR/mabStra.py" --parameters "$SOURCE_DIR/freqtrade-parameters.py" --interface "$SOURCE_DIR/freqtrade-interface.py" --output "$OUT-source-check.json"
"$PY" scripts/test_synthetic.py
"$PY" scripts/run_replay.py --input "$CSV" --output "$OUT" --spec specs/protocol.json
"$PY" scripts/validate_ledger.py --work "$OUT" --input "$CSV" --spec specs/protocol.json --output "$OUT-ledger-check.json"
"$PY" scripts/check_execution_prefixes.py --input "$CSV" --spec specs/protocol.json --output "$OUT-prefix-check.json"
"$PY" scripts/independent_oracle.py --input "$CSV" --spec specs/protocol.json --work "$OUT" --output "$OUT-oracle-check.json"
"$PY" scripts/recover.py --input "$INDEPENDENT_REBUILD_CSV" --reference "$OUT" --target "$OUT-recovery" --receipt "$OUT-recovery.json"
```

原源码与框架文件不在公开包；只可从[源码清单](specs/source-manifest.json)所列固定提交URL取得后验SHA256，禁止跟随main/develop。恢复脚本不读取原结果做交易决策；22个输出文件比对中只允许summary峰值RSS不同。实际已完成的恢复证据见[local-recovery.json](artifacts/local-recovery.json)。独立Oracle脚本及回执另随公开清单保存。

## 公共源重新构建配方

本次M0317新行情请求为0，复用既有双快照。`scripts/rebuild_official_bars.py`是原归档重建工具，原样保留且未在本轮联网执行。必需参数是`--timeframe 4h`和全新`--target`，并需要真实的`--terms-reviewed`前置确认。`--expected-manifest`是可选参数，只接受包含`protocol`等字段的完整历史snapshot manifest。

本公开包的`specs/input-manifest-inherited.json`是轻量输入清单，缺少`protocol`等完整字段，**不能作为`--expected-manifest`传入**。拿到完整历史snapshot manifest的恢复者可选择该参数；仅持有公开包时，应走以下两阶段流程。

第一阶段仅在未来另获行情捕获授权、完成许可审查后执行。`NEW_SNAPSHOT`须不存在，且位于操作者的数据湖raw目录，不得覆盖旧快照：

```bash
set -euo pipefail
PY='/absolute/path/to/python3.12'
NEW_SNAPSHOT='/absolute/path/to/data/raw/new-authorized-snapshot'
cd '/absolute/path/to/M0317'
"$PY" scripts/rebuild_official_bars.py --timeframe 4h --target "$NEW_SNAPSHOT" --terms-reviewed
```

此命令故意不传`--expected-manifest`。工具返回`CAPTURED_NOT_INDEPENDENTLY_REBUILT`只表示新capture完成，不能当作已恢复冻结输入。本轮没有执行这条联网命令，也不把保留配方理解为越过已拒绝的数据访问。

第二阶段必须沿用前一阶段同一个fail-closed Bash会话、相同PY和NEW_SNAPSHOT变量，按公开轻量清单做离线比对，再执行原生数据审计。下面也重复严格模式和变量门禁，单独复制且缺变量时立即失败；任一步非零都不能进入后续策略回放：

```bash
set -euo pipefail
: "${PY:?请先定义已验证Python路径}" "${NEW_SNAPSHOT:?请先定义全新已授权快照路径}"
"$PY" scripts/compare_rebuild_manifest.py --snapshot "$NEW_SNAPSHOT" --output "$NEW_SNAPSHOT-light-match.json"
"$PY" scripts/audit_raw.py "$NEW_SNAPSHOT" "$NEW_SNAPSHOT-raw-audit.json"
```

比较器从冻结builder的AST提取VERSION及schema，核对完整snapshot的protocol、4h、起止时间和身份、trusted=False，以及轻量清单与builder SHA256。它要求25个月有序唯一，对75个ZIP/CHECKSUM/提取CSV逐项核对bytes/SHA256和本地实际对象，并拒绝逃出snapshot目录的路径；canonical还核实实物bytes/SHA256、CSV表头及实际4572行。随后raw审计重新证明原12字段无损、完整4572行时间网格及数值约束。任何不一致都必须终止，不覆盖冻结输入、不换市场或窗口；capture自身的初始状态不被原地改写，成功证据保存在独立比较回执。双阶段PASS仍然只支持`DIAGNOSTIC_ONLY`，不升级最终性/PIT/trusted。

本次修订已对既有primary和独立rebuild快照实际运行比较器，均PASS，分别见[primary比对回执](artifacts/recovery-recipe-primary-light-match.json)和[rebuild比对回执](artifacts/recovery-recipe-rebuild-light-match.json)。这两次都是离线验证，不是新网络捕获、也没有新增策略收益运行。

## 2026年10月3日恢复配方修订

v0把可选`--expected-manifest`表述为要求，没有解释light与full manifest差异。v1修正文档并增加补强身份、月份、实物行数及路径门禁的离线比较工具及两份实际回执。收益前协议、18个冻结对象、行情和结果字节均不变；旧文档/清单原字节保留在私有历史记录，旧远端版本不覆盖。详见[修订回执](artifacts/recovery-recipe-revision.json)。

## 可恢复性边界

本地完整材料和新进程恢复已验证；轻量远端包有配方、输入摘要与结果，却不含raw或完整第三方源码，单独离线使用不足以重放。远端C3须另由协调者保存并读回，不能把本地成功写成异地容灾通过。原始历史档案可能修订，未来网络可用性及字节一致性不保证。
