# M1347：实际远端核心恢复配方

已完成一次恢复，状态 `REMOTE_HASH_REFERENCE_REBUILD_PASS`。来源是 quant-research-lab 的实际远端提交 `2d1a1257e6fa6e43dafa3cff81e24aad2f318855`，分支 `codex/catalog-monthturn-batch018-20261003`。67 个 M1347 公开对象共 270695 B；共享内核 4 个对象从规格指定的原提交 `fad9d65c74b4346c0ed992a742b91d70514fc6d1` 获取，不能用当前分支 README 代替。另取回 2 个既有环境/离线辅助文件，共 73 个对象。

本配方复现已冻结四配置，不新增策略试验或控制，不修改 C0、参数或参考结果。原公开 `restore_core_v1.py` 已实际运行一次；不需要替换器或自引用的 reference 对象。30 个新输出分别与远端长度/SHA256 匹配，结果 manifest 与远端原字节相同。没有读取执行者原完整收益作为参考，也不声称持有那些原完整字节。

## 前置依赖

- 可读取该 Lab 远端的授权 Git checkout；以下命令只 fetch，不 checkout、提交或推送。
- 全新私有恢复目录，磁盘空闲至少 5 GiB；不删除旧证据。
- 已合法持有的 50 个原档：2022-12 至 2024-12 每月 BTCUSDT 原生日线 ZIP 和其 CHECKSUM 各一份。完整文件名、长度、SHA256 位于远端 `M1347/specs/protocol-v1.json` 的 `input.raw_files`。这些市场原档不在 Git。
- 已验 M1258 远端恢复的 7 个 buyhold 文件，可按 `specs/control-reference.json` 只读复核；恢复策略无需重新运行控制。该对照仅匹配 base 的 8 bps 费和 2 bps 滑点。
- 精确预装的 `specs/environment-lock.json` 运行环境：Python 完整版本字符串及六个包全部匹配。此次使用 Python 3.12.14、numpy 2.3.5、pandas 2.2.3、python-dateutil 2.9.0.post0、pytz 2026.3.post1、tzdata 2026.3、six 1.17.0。不要自动安装、换锁或放宽断言。
- 与本配方一起保留 `remote-core-files.json`，其 SHA256 为 `404d9fd4745a0b490e76d29b514e07c775bcf0571a2f7579a31ea0718f0982b0`。

Git 不含原始行情或完整私有包。缺少原档时停止；未来经授权重新取得来源数据后，也必须通过同一 50 对象指纹，禁止静默替换数据、缩窗或接受新哈希。第三方未来可访问性及原字节可得性没有永久保证。Library 私有 ZIP 的 HTTP401 缺口单列，此次 Git 恢复不等于该私包远端保存成功。

## 提取精确远端对象

先由操作者设置下列变量为明确路径：`GIT_REPO`（授权 Lab checkout）、`RECOVERY_ROOT`（尚不存在的私有目录）、`RAW_CACHE`（50 原档目录）、`CONTROL_CACHE`（已验七个 M1258 buyhold 文件目录）、`PINNED_PYTHON`（精确环境 Python）、`REMOTE_OBJECTS`（本次 remote-core-files.json）。此处不创建凭证或改变访问设置。

```bash
mkdir "$RECOVERY_ROOT"
exec 9>"$RECOVERY_ROOT/recovery.lock"
flock -n 9

git -C "$GIT_REPO" fetch --no-tags origin 2d1a1257e6fa6e43dafa3cff81e24aad2f318855
git -C "$GIT_REPO" fetch --no-tags origin fad9d65c74b4346c0ed992a742b91d70514fc6d1

export GIT_REPO RECOVERY_ROOT RAW_CACHE CONTROL_CACHE PINNED_PYTHON REMOTE_OBJECTS
"$PINNED_PYTHON" - <<'PY'
import hashlib, json, os, shutil, subprocess
from pathlib import Path
q=Path(os.environ['RECOVERY_ROOT']); repo=Path(os.environ['GIT_REPO'])
assert shutil.disk_usage(q).free > 5*1024**3
m=Path(os.environ['REMOTE_OBJECTS']).read_bytes()
assert hashlib.sha256(m).hexdigest()=='404d9fd4745a0b490e76d29b514e07c775bcf0571a2f7579a31ea0718f0982b0'
d=json.loads(m); assert len(d['objects'])==73
core=q/'core'; core.mkdir()
for r in d['objects']:
    rel=Path(r['path']); assert not rel.is_absolute() and '..' not in rel.parts
    b=subprocess.check_output(['git','-C',str(repo),'show',r['source_commit']+':'+r['path']])
    assert len(b)==r['bytes'] and hashlib.sha256(b).hexdigest()==r['sha256']
    p=core/rel; p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('xb') as f: f.write(b)
f=core/'research/public-strategies/M1347'
s=json.loads((f/'specs/protocol-v1.json').read_text())
raw=q/'raw-cache';raw.mkdir()
for r in s['input']['raw_files']:
    b=(Path(os.environ['RAW_CACHE'])/r['name']).read_bytes()
    assert len(b)==r['bytes'] and hashlib.sha256(b).hexdigest()==r['sha256']
    with (raw/r['name']).open('xb') as h: h.write(b)
control=json.loads((f/'specs/control-reference.json').read_text())
assert len(control['files'])==7
for r in control['files']:
    b=(Path(os.environ['CONTROL_CACHE'])/r['path']).read_bytes()
    assert len(b)==r['bytes'] and hashlib.sha256(b).hexdigest()==r['sha256']
PY
```

## 离线重建及原入口恢复

以下 Python socket audit guard 是从同一远端取回的既有工具，阻断被测 Python 进程的 socket 事件并由子进程继承；它不是操作系统网络命名空间。Git fetch 在启动该离线恢复阶段前完成。没有新市场请求。

```bash
M1347_FAMILY="$RECOVERY_ROOT/core/research/public-strategies/M1347"
M1347_HELPER="$RECOVERY_ROOT/core/research/public-strategies/M1358/recovery/remote-core-v1"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$M1347_HELPER/offline-guard"
export M1358_OFFLINE_AUDIT_LOG="$RECOVERY_ROOT/offline-runtime.jsonl"

"$PINNED_PYTHON" "$M1347_HELPER/locked_exec.py" --family "$M1347_FAMILY" \
  "$M1347_FAMILY/scripts/rebuild_input.py" \
  --raw "$RECOVERY_ROOT/raw-cache" --output "$RECOVERY_ROOT/input.csv" \
  --receipt "$RECOVERY_ROOT/input-rebuild.json"

"$PINNED_PYTHON" "$M1347_HELPER/locked_exec.py" --family "$M1347_FAMILY" \
  "$M1347_FAMILY/scripts/restore_core_v1.py" \
  --input "$RECOVERY_ROOT/input.csv" --fresh "$RECOVERY_ROOT/fresh" \
  --receipt "$RECOVERY_ROOT/restore-core-receipt.json"

"$PINNED_PYTHON" "$M1347_HELPER/locked_exec.py" --family "$M1347_FAMILY" \
  "$RECOVERY_ROOT/fresh/research/public-strategies/M1347/scripts/check_causality.py" \
  --input "$RECOVERY_ROOT/fresh/private/input.csv" \
  --root-gate "$RECOVERY_ROOT/fresh/private/root-release.json" \
  --output "$RECOVERY_ROOT/feature-causality.json"
```

`rebuild_input.py` 对 50 对象逐项验证长度/hash、25 份 provider checksum 和 ZIP CRC，按冻结格式重建 762 行、128196 B 的 canonical CSV，SHA256 必须为 `48e4e785ee3366a459cf09f64617c89e04fb19b91da6c6125e86835506f6b9f5`。31 个预热日和全部 731 个评价日保留；重建步骤不计算策略收益。

`restore_core_v1.py` 自行验证并复制 28 个 C0 对象及 4 个原内核对象；只将既有已授权 root-release 内独立审查回执的位置映射到新目录，不创建新放行。它调用原 `run_replay.py` 一次生成四配置、比较远端输出指纹及 manifest 原字节，再调用原 `verify_replay.py`。后者独立 Decimal50 核 2924 NAV、2924 决策、188 fills、96 月报及事件/闭合交易/统计。`check_causality.py` 验 16 个前缀与 16 个未来扰动，不重跑账户。

## 外层独立比较

期望只能取本次远端 `artifacts/20261003-catalog-v1/private-output-manifest.json`。下列检查不读取原执行器输出：

```bash
"$PINNED_PYTHON" - <<'PY'
import hashlib,json,os
from pathlib import Path
q=Path(os.environ['RECOVERY_ROOT']); f=q/'core/research/public-strategies/M1347'
p=f/'artifacts/20261003-catalog-v1/private-output-manifest.json'
assert hashlib.sha256(p.read_bytes()).hexdigest()=='efae9bdac67125d12fde252f1e8fd1a506e455c6fbe215ea397e989cd3133d95'
expected=json.loads(p.read_text()); assert len(expected)==30
out=q/'fresh/private/results'
assert {x.name for x in out.iterdir()}=={r['path'] for r in expected}|{'manifest.json'}
assert (out/'manifest.json').read_bytes()==p.read_bytes()
for r in expected:
    b=(out/r['path']).read_bytes()
    assert len(b)==r['bytes'] and hashlib.sha256(b).hexdigest()==r['sha256']
assert json.loads((q/'fresh/private/account-validation.json').read_text())['status']=='PASS'
assert json.loads((q/'feature-causality.json').read_text())['status']=='PASS'
assert not any(json.loads(x)['event']=='DENIED' for x in (q/'offline-runtime.jsonl').read_text().splitlines())
print('PASS: 30 remote length/SHA pairs plus byte-identical manifest; 0 new trials/controls')
PY
```

此次实际执行另保留 flock、逐阶段 UTC/wall/CPU/RSS、精确 Python/包版本断言、socket 拒绝自检、五个恢复 Python 进程的离线记录、73 个对象的来源 commit/blob/长度/hash 清单及完整新结果。自检使用独立日志；恢复日志零网络事件。恢复后重新核对所有远端对象与新目录 C0/内核原字节，未改变任何冻结代码。

本次结果只支持可恢复性和执行核验，不升级来源可信度、PIT、样本外性质或策略质量。四个研究配置此前均亏损，仍为目录假设/改编执行，严格复现数保持 0。
