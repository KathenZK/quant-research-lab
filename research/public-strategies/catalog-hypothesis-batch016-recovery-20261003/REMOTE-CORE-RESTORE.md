# Batch016 远端哈希参照恢复

M1396/M1463 于 2026-10-03 实际从 Lab 远端取回固定提交 `fad9d65c74b4346c0ed992a742b91d70514fc6d1`，验收状态为 `REMOTE_HASH_REFERENCE_REBUILD_PASS`。两个 publication manifest 的并集为 96 对象、305705 字节，另取回 4 个支持对象。各原引擎执行一次固定 4 配置，各原独立核算器执行一次，60 项输出长度及 SHA256 与远端公开期望一致，两份清单原字节一致。没有完整旧结果 payload 用于 byte-to-byte 对照，不把该限制写成“62 个旧结果原件逐字节比较”。

冻结 `restore_run.py` 的原 CLI 要求本地旧完整结果目录，因此未调用。外层 driver 按它的实际步骤复制 C0/内核/输入，调用原 `run_replay.py` 和 `verify_replay.py`，随后独立比较远端清单。所有被冻结的算法、参数、C0、内核及公开结果均未改。曾草拟的返回新结果 bytes 的参照适配方法已在任何历史运行前放弃；本 driver 不使用自比较方法。

本目录 `restore_remote_core.py` 是实际 driver 的可迁移版本，仅五个路径/运行时绑定改为环境变量；计算、原执行命令和验收逻辑不变。文件 SHA256：`7b0a8ce8f37d69dc811764530433dc8dc9a5c5265d6c7fdfc820597d8b7402e5`。实际使用的原 driver 指纹和资源记录在安全回执中。可迁移版本只做静态解析，未以它另跑一次历史。

## 前置依赖

- 现有授权的 Lab Git `origin`，含固定提交；不创建凭证、扩大权限或写远端。
- 精确预装 Python/包版本，取回后的各 ID `specs/environment-lock.json` 是执行时断言来源。Python 必须匹配完整版本字符串：`3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]`。numpy 2.3.5，pandas 2.2.3，python-dateutil 2.9.0.post0，pytz 2026.3.post1，tzdata 2026.3，six 1.17.0。失败就停止，不放宽锁。
- 已合法取得的 50 个 BTCUSDT 日线原始对象：2022-12 至 2024-12 的 25 ZIP 和 25 `.zip.CHECKSUM`。文件名/大小/SHA 在两 ID 协议的 `input.raw_files`，源 URL/原获取时间在钉住的 M0216 `input-manifest.json`。这些市场原档不在 Git 中。
- **已实际远端恢复的 M1258 买持控制 7 文件**，其期望值取自本批远端 `recovery/control-release-v1/control-reference.json`。控制来源为提交 `2a2e33e0de2b4897d6ccb460e72dcb5e73aa4153`，实际远端恢复安全回执 SHA256 为 `448e6996f1562999bb47e455fdac460f77fda0d688391a160139510f61c22131`。本次只读校验并引用这 7 文件，未执行买持。
- 新空目录、磁盘至少留 5 GiB。不要复用或覆盖旧恢复目录。

下面所有 `/path/...` 必须替换为明确绝对路径。`CONTROL_RECOVERY_RECEIPT` 必须是上述 M1258 已发布安全回执的原字节；若 7 控制文件丢失，应先按该 M1258 恢复合同进行获准的恢复，不自行创建新基准。

## 取回、验证 96+4 对象

```bash
set -euo pipefail
export LAB_REPO='/path/to/authorized/quant-research-lab'
export RECOVERY_ROOT='/path/to/new/batch016-recovery'
export PINNED_PYTHON='/path/to/exact/python'
export RAW_CACHE='/path/to/existing/50-raw-objects'
export CONTROL_CACHE='/path/to/accepted/M1258/fresh/results'
export CONTROL_RECOVERY_RECEIPT='/path/to/M1258-remote-core-recovery.safe.json'
export SAFE_DIRECTORY='/path/to/this/safe-delivery'

test ! -e "$RECOVERY_ROOT"
mkdir -p "$RECOVERY_ROOT"
git -C "$LAB_REPO" fetch --no-tags origin codex/catalog-hypothesis-batch017-20261003
git -C "$LAB_REPO" cat-file -e 'fad9d65c74b4346c0ed992a742b91d70514fc6d1^{commit}'

"$PINNED_PYTHON" - <<'PY'
from pathlib import Path
import hashlib,json,os,subprocess
q=Path(os.environ['RECOVERY_ROOT']);g=Path(os.environ['LAB_REPO'])
s=Path(os.environ['SAFE_DIRECTORY'])
r=json.loads((s/'batch016-remote-core-recovery.safe.json').read_text())
pin='fad9d65c74b4346c0ed992a742b91d70514fc6d1'
assert r['source']['commit']==pin
assert hashlib.sha256((s/'restore_remote_core.py').read_bytes()).hexdigest()=='7b0a8ce8f37d69dc811764530433dc8dc9a5c5265d6c7fdfc820597d8b7402e5'
core=q/'core';records={}
def save(x):
    rel=Path(x['path']);assert not rel.is_absolute() and '..' not in rel.parts
    b=subprocess.check_output(['git','-C',str(g),'show',pin+':'+x['path']])
    blob=subprocess.check_output(['git','-C',str(g),'rev-parse',pin+':'+x['path']]).decode().strip()
    assert len(b)==x['bytes'] and hashlib.sha256(b).hexdigest()==x['sha256']
    if 'git_blob' in x:assert blob==x['git_blob']
    if x['path'] not in records:
        p=core/rel;p.parent.mkdir(parents=True,exist_ok=True)
        with p.open('xb') as f:f.write(b)
        records[x['path']]=dict(path=x['path'],bytes=len(b),sha256=x['sha256'],git_blob=blob)
    return b
for ID,x in r['source']['publication_manifests'].items():
    m=json.loads(save(x))
    for item in m['files']:save(item)
assert len(records)==96
assert sum(x['bytes'] for x in records.values())==305705
for item in r['source']['supports']:save(item)
assert len(records)==100
for ID in ['M1396','M1463']:
    family=core/f'research/public-strategies/{ID}'
    c0=json.loads((family/'specs/C0-v1.json').read_text())
    assert hashlib.sha256((family/'specs/C0-v1.json').read_bytes()).hexdigest()==r['IDs'][ID]['C0_sha256']
    for item in c0['files']:
        p=family/item['path'];assert p.stat().st_size==item['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==item['sha256']
    for item in c0['shared_files']:
        p=core/item['path'];assert p.stat().st_size==item['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==item['sha256']
(q/'source-materialization.private.json').write_text(json.dumps(dict(status='PASS_REMOTE_ONLY_SOURCE',commit=pin,publication_union=96,publication_union_bytes=305705,support_files=4,objects=list(records.values())),indent=2)+'\n')
(q/'review.lock').touch(exist_ok=False)
PY
```

这一步只从固定 Git blob 写文件，原公共清单自身也由安全回执的 hash 固定。后续分支前进不改变恢复 pin。无需 checkout 执行者分支或取执行者的旧结果。

## 一次恢复及独立远端参照比较

```bash
"$PINNED_PYTHON" "$SAFE_DIRECTORY/restore_remote_core.py"
```

driver 的步骤固定为：

1. 非阻塞 `flock`，检查剩余空间和全部远端对象指纹。对两协议的同一输入定义做等值检查。
2. 校验已有 M1258 恢复回执及 7 控制文件，并对两 ID 的远端原授权副本只增加 `local_path` 字段，不改变状态、C0、控制身份或批准范围。
3. 复用取回的 M1358 `locked_exec.py` 和 socket guard，调用远端 M1396 `scripts/rebuild_input.py --raw RAW_CACHE --output NEW_INPUT --receipt NEW_RECEIPT`。50 原档长度/hash、25 provider checksum、25 ZIP CRC 和成员结构均验证，再拼成固定 CSV。两 ID 原重建脚本和输入定义相同，只重建一次。
4. 为每 ID 新建独立目录，复制其 23 个 C0 payload 加 C0、固定内核，以及已重建输入。通过锁定环境入口各执行一次远端原 `scripts/run_replay.py --input INPUT --output NEW_RESULTS --root-gate GATE`，然后执行原 `scripts/verify_replay.py --input INPUT --results NEW_RESULTS --output VALIDATION`。
5. 对每个新目录严格检查 31 文件集合；30 payload 分别比较**远端期望长度与 SHA256**，再比较远端公开输出清单与新清单的完整字节。期望值从 `artifacts/20261003-catalog-v1/private-output-manifest.json` 取回，不从新结果生成。
6. 再核原 source/C0/kernel 未变、每个独立 oracle PASS、socket guard 五个进程均启用、空间仍足够，输出私有总回执和逐 ID 回执。

预期输入为 128196 字节、762 行，SHA256 `48e4e785ee3366a459cf09f64617c89e04fb19b91da6c6125e86835506f6b9f5`；含 31 日指标预热和全部 731 日评价。M1396 期望输出清单 SHA256 `77b980470ba4c78a0af62f5855539589ff57b4aaedafbf194c46e4d24ce1c1f5`；M1463 为 `fbd8aa6085f08b4546b03c1c703b7b885198ea87b9b345cfca454ecc11c9f881`。

成功时每 ID `recovery.private.json` 为 `REMOTE_HASH_REFERENCE_REBUILD_PASS` / 30 hash-exact / manifest-byte-exact。M1396 独立核算应覆盖 762 特征、2924 净值/决策、96 月度、488 成交；M1463 相应为 762、2924、96、156。任何指纹、锁、核算或集合差异均停止并保留失败，不能复制旧结果补齐。

## 边界

运行期间采用 Python socket 审计拦截；这是已复用并验证的进程级保护，不是 OS 网络命名空间。唯一实际网络操作是先前 Git fetch；没有市场请求或依赖安装。指标和完整账户输出保持私有，只允许发布另行审查的轻量结果。

本批复现的是目录规则 HYPOTHESIS / ADAPTED_EXECUTION_PROXY；原作者实现未验证，已曝光窗口不算 OOS，严格复现仍为 0。当前数据为 DIAGNOSTIC_ONLY / trusted=false / PIT finality 未证明，历史来源清单的旧 trusted 字段不升级本批状态。

纯 Git 没有原始行情、完整旧财务证据或 Python 环境。若缓存缺失，只能在许可和授权允许时另行取得匹配原 URL/指纹的数据；未来公网可访问性和原字节永久可得性均不保证。Library 完整私包通道仍未成功（已报告 helper HTTP 401），本回执不代表该通道备份成功。

这里两次引擎执行只恢复原有 8 个配置，未运行新基准；新增研究试验、控制、严格复现计数均为 0。
