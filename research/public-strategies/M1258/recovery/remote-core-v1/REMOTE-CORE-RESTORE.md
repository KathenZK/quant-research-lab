# M1258 远端核心恢复

2026-10-03 已实际 fetch Lab 的 `origin/codex/catalog-hypothesis-batch015-integration-20261003`，固定提交 `2a2e33e0de2b4897d6ccb460e72dcb5e73aa4153`。取回 37 个 M1258 文件和 6 个已钉住的支持文件，以既有合法缓存重建输入后，运行一次原恢复入口：37 项完整输出及输出清单共 38 文件逐字节一致，独立 Fraction 信号 / Decimal 账本复核通过。没有使用执行者本地代码或旧结果替代远端文件。

这是原 4 策略配置加 1 买持配置的恢复验证，新增研究试验、控制和严格复现计数均为 0。完整安全证据见同目录 `M1258-remote-core-recovery.safe.json`。M1258 仍为基于目录规则的 HYPOTHESIS；原作者网页实现未独立验证。

## 必要依赖

- 可访问上述 Lab Git 对象；使用现有授权的 `origin`，不创建凭证或扩大访问。
- 预装精确环境，见取回后的 `M1258/specs/environment-lock.json`。实际环境是 Python `3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]`，numpy 2.3.5、pandas 2.2.3、python-dateutil 2.9.0.post0、pytz 2026.3.post1、tzdata 2026.3、six 1.17.0。环境不匹配即停止，不自动安装或放宽锁。
- 25 个 BTCUSDT 原生日线月 ZIP（2022-12 至 2024-12）及对应 25 个 `.zip.CHECKSUM`，放在一个已有合法缓存目录。精确文件名、字节数、SHA256 在取回后 `M1258/specs/protocol-v1.json` 的 `input.raw_files`。缓存不属于 Git 内容。
- 新的空恢复目录、至少 5 GiB 剩余磁盘空间。不要覆盖任何旧证据。

下面命令的路径是占位符，需替换为现有仓库、正确 Python、既有原档缓存及新目录。`SAFE_RECEIPT` 指向本目录安全回执的本地副本。第一阶段只有 Git fetch 需要网络；后续原档重建与回放启用复用的 Python socket 审计拦截器，不是 OS 网络命名空间。

## 取回并验证精确远端对象

```bash
set -euo pipefail
export LAB_REPO='/path/to/authorized/quant-research-lab'
export RECOVERY_ROOT='/path/to/new/empty/m1258-recovery'
export RAW_CACHE='/path/to/existing/daily-raw-cache'
export PINNED_PYTHON='/path/to/exact/python'
export SAFE_RECEIPT='/path/to/M1258-remote-core-recovery.safe.json'

test ! -e "$RECOVERY_ROOT"
mkdir -p "$RECOVERY_ROOT"
git -C "$LAB_REPO" fetch --no-tags origin codex/catalog-hypothesis-batch015-integration-20261003
git -C "$LAB_REPO" cat-file -e '2a2e33e0de2b4897d6ccb460e72dcb5e73aa4153^{commit}'

"$PINNED_PYTHON" - <<'PY'
import hashlib,json,os,subprocess
from pathlib import Path
repo=Path(os.environ['LAB_REPO']); out=Path(os.environ['RECOVERY_ROOT'])/'core'
r=json.loads(Path(os.environ['SAFE_RECEIPT']).read_text())
pin='2a2e33e0de2b4897d6ccb460e72dcb5e73aa4153'
assert r['source']['commit']==pin
assert len(r['remote_objects'])==43
for x in r['remote_objects']:
    rel=Path(x['path']); assert not rel.is_absolute() and '..' not in rel.parts
    b=subprocess.check_output(['git','-C',str(repo),'show',pin+':'+x['path']])
    blob=subprocess.check_output(['git','-C',str(repo),'rev-parse',pin+':'+x['path']]).decode().strip()
    assert len(b)==x['bytes'] and hashlib.sha256(b).hexdigest()==x['sha256'] and blob==x['git_blob']
    p=out/rel;p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('xb') as h:h.write(b)
f=out/'research/public-strategies/M1258'
for name in ['publication-manifest.json','specs/C0-v1.json']:
    for x in json.loads((f/name).read_text())['files']:
        p=f/x['path'];assert p.stat().st_size==x['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==x['sha256']
assert hashlib.sha256((f/'publication-manifest.json').read_bytes()).hexdigest()=='a6a38fc7270c56741c756dcd1219d534e51bf1fe89ac5f59067da0c44a360d81'
assert hashlib.sha256((f/'specs/C0-v1.json').read_bytes()).hexdigest()=='472a448a5e948e1ac7bbf82e4a386dd628e01851ef80dc83493142b10c78eb06'
PY
```

此处所有 43 对象都来自固定提交的 Git blob，回执中的字节数、SHA256 和 blob ID 同时校验。未来分支前进不改变恢复使用的固定提交。原始行情和执行者私有结果不用于源码回退。

## 离线重建和一次恢复

```bash
export M1258_FAMILY="$RECOVERY_ROOT/core/research/public-strategies/M1258"
export RECOVERY_HELPER="$RECOVERY_ROOT/core/research/public-strategies/M1358/recovery/remote-core-v1"
export PYTHONPATH="$RECOVERY_HELPER/offline-guard"
export M1358_OFFLINE_AUDIT_LOG="$RECOVERY_ROOT/offline-processes.jsonl"
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1

mkdir "$RECOVERY_ROOT/expected"
cp "$M1258_FAMILY/artifacts/20261003-catalog-v1/private-output-manifest.json" "$RECOVERY_ROOT/expected/manifest.json"

"$PINNED_PYTHON" "$RECOVERY_HELPER/locked_exec.py" --family "$M1258_FAMILY" \
  "$M1258_FAMILY/scripts/rebuild_input.py" \
  --raw "$RAW_CACHE" --output "$RECOVERY_ROOT/input.csv" \
  --receipt "$RECOVERY_ROOT/input-rebuild.json"

"$PINNED_PYTHON" "$RECOVERY_HELPER/locked_exec.py" --family "$M1258_FAMILY" \
  "$M1258_FAMILY/scripts/restore_run.py" \
  --input "$RECOVERY_ROOT/input.csv" \
  --expected-manifest "$RECOVERY_ROOT/expected/manifest.json" \
  --fresh "$RECOVERY_ROOT/fresh" --receipt "$RECOVERY_ROOT/remote-restore.json"

cmp "$RECOVERY_ROOT/expected/manifest.json" "$RECOVERY_ROOT/fresh/results/manifest.json"
sha256sum "$RECOVERY_ROOT/input.csv" "$RECOVERY_ROOT/fresh/results/manifest.json"
```

`rebuild_input.py` 按协议的原始文件顺序校验 50 个对象、25 个 provider checksum、25 个 ZIP CRC及成员名，逐条保留 12 字段，以冻结 CSV 表头和换行重建。必须得到 128196 字节、762 行、SHA256 `48e4e785ee3366a459cf09f64617c89e04fb19b91da6c6125e86835506f6b9f5`；31 行预热和完整 731 行评价不能更改。实际验收还给 `--reference` 传入原已验 canonical CSV 做了额外逐字节检查；上面的独立恢复只需要 50 原档，固定输入 SHA、长度和网格校验仍全部执行。

`restore_run.py` 校验并复制 19 个冻结对象和 C0，以新目录运行一次原引擎及独立验证器，比较完整 37 项输出和清单。清单来自远端公开的 hash-only 文件，原样复制，不能用恢复输出生成期望值。预期清单 SHA256：`1b6d18dfc74cfb560559f207ebadfff1887e95cdd9e94cf64d848b06c2930eb7`。

成功时 `remote-restore.json` 应为 PASS / 37 payload exact / manifest exact；`fresh/oracle.json` 应为 PASS，包含 762 features、3655 NAV、3655 decisions、120 monthly、493 fills。验证器沿用原实验字段 `new_control_configurations=1`，表示原实验唯一买持控制；本次恢复计数新增控制为 0。环境锁在执行入口断言，原回放及验证子进程继承 Python socket guard。实际验证记录 4 个进程启用拦截器，0 socket 请求/拦截事件。不得将只读校验或恢复重复登记为策略运行。

## 缓存缺失时和使用范围

精确来源 URL、历史获取时间和 25 个原 ZIP 指纹在 `source/input-origin-manifest.json`，50 对象指纹及重建合同在 `specs/protocol-v1.json`。只有在授权、许可及服务可访问性均允许时，才可另行依法取得完全相同字节；本次没有请求市场数据。若原 URL 消失或字节更新导致 hash 不符，就报告该输入无法恢复，不能静默替换、购买数据或扩大访问。未来公网永久可得性未承诺，纯 Git 也不含原始行情。

本恢复不升级数据可信度：旧输入来源清单中的历史 `trusted=true` 保持原字节，当前结论仍是 DIAGNOSTIC_ONLY / trusted=false / PIT finality 未证明。原作者完整实现、真实交易所执行和样本外有效性均不由本回执证明。

本次确实恢复了 `buyhold-reference-v1.json` 所绑定的唯一 100% 含费预算买持控制（该引用 SHA256 为 `ea4fb4687cffe69b7ee877312e19ec49b263bf5d21705d0dcfa2e791c24be00a`）；后续仅同输入、窗口、资金预算、费率、滑点和估值口径可以引用，不计新增控制。

Library 完整私包上传/取回仍是单独未通过的持久化通道（已报告 helper HTTP 401），此远端 Git 核心恢复成功不代表 Library 备份成功。完整 Python 环境亦需另行提供，不能宣称仅有 Git 就能无依赖恢复。
