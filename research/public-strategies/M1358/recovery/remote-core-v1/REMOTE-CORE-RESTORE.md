# M1358 远端 Git 核心恢复验证

本次按补充授权验证：代码、规则、C0、轻量结果与行情指纹从远端 Git 取回，结合已合法持有的原始行情缓存，实际重新生成完整结果。它证明本适配实验的远端代码核心可恢复；不表示 Git 含原始行情，不表示 Library 完整私包上传成功，也不表示原作者 QuantConnect 工程可严格复现。

固定仓库为 `KathenZK/quant-research-lab`，远端 `origin`，取回分支 `codex/public-strategies-batch014-20261003`，精确提交 `dba8d1d64318f9909cdcfd3bc9c382842a1a742b`。root 已完成 fetch 和远端 105 对象读回；本独立验证从这个精确 remote-tracking Git 对象提取 M1358 全部 51 件共 169238 字节，不读取执行者工作树源码或旧结果作为替代。治理 rev2 保留原 README/decision/publication manifest；C0-v1/v2 与策略代码均保持原字节。

环境须已有 `specs/environment-lock.json` 中的 Python 3.12.14、numpy2.3.5、pandas2.2.3、python-dateutil2.9.0.post0、pytz2026.3.post1、tzdata2026.3、six1.17.0。此次使用精确锁定环境，未安装依赖。`locked_exec.py` 每阶段核环境；`offline-guard/sitecustomize.py` 通过 Python audit hook 禁止 socket 事件，且由恢复程序子进程继承。这是 Python 进程断网约束，不是操作系统网络命名空间声明。

数据依赖是既有 Binance spot BTCUSDT 原生日线 2022-12 至 2024-12 的 25 ZIP + 25 CHECKSUM。每件 SHA/字节数在远端 M1358 `specs/protocol-v1.json`，25 个原采集 URL 和时间在同提交的 `research/public-strategies/M0216/artifacts/20261003-first-replay/input-manifest.json`，其 SHA 为 `17d1e72e3fc42f71ed94a771847ea4b4b3dd61c9ad290d0e73d05eca32ed23fc`。该旧清单的 `qa.trusted=true` 不带入新研究；M1358 仍是 DIAGNOSTIC_ONLY、trusted=false、PIT未证。

`rebuild_daily_input.py` 依远端协议核验全部50对象、25 provider checksum 和 ZIP CRC，按协议顺序解析各月 native12 CSV，使用 Python csv 默认 CRLF 写入固定列头与762行。canonical必须为128196字节、SHA `48e4e785ee3366a459cf09f64617c89e04fb19b91da6c6125e86835506f6b9f5`，否则停止。研究仅取2023-01-01至2025-01-01前731日，EMA从评估首日空状态启动，前31日不喂指标，前48日现金净值保留。

以下命令使用已连接并授权的仓库、已合法持有的原档目录和空的新恢复目录。`helper_dir` 指本说明同目录；`python_bin` 指锁定版本的 Python。所有数据保留在私有目录。此验证没有重新下载行情；若缓存丢失，须在当时的访问权限和数据许可内从清单来源重新取得，逐哈希验证。来源未来可能改变或不可访问，本验证未检验当前下载可用性，不提供永久可恢复保证，不用其他数据替代失败。

```bash
lab_checkout=/absolute/path/to/authorized/lab-checkout
raw_cache=/absolute/path/to/lawfully-held/50-raw-files
restore_root=/absolute/path/to/new-private-restore-directory
helper_dir=/absolute/path/to/this-helper-directory
python_bin=/absolute/path/to/locked/python

git -C "$lab_checkout" fetch origin codex/public-strategies-batch014-20261003
test "$(git -C "$lab_checkout" rev-parse refs/remotes/origin/codex/public-strategies-batch014-20261003)" = dba8d1d64318f9909cdcfd3bc9c382842a1a742b
mkdir "$restore_root"
mkdir "$restore_root/core" "$restore_root/expected"
git -C "$lab_checkout" archive dba8d1d64318f9909cdcfd3bc9c382842a1a742b research/public-strategies/M1358 research/public-strategies/M0216/artifacts/20261003-first-replay/input-manifest.json | tar -x -C "$restore_root/core"
family="$restore_root/core/research/public-strategies/M1358"
export PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
export PYTHONPATH="$helper_dir/offline-guard"
export M1358_OFFLINE_AUDIT_LOG="$restore_root/offline-processes.jsonl"

"$python_bin" "$helper_dir/locked_exec.py" --family "$family" "$helper_dir/rebuild_daily_input.py" --protocol "$family/specs/protocol-v1.json" --raw "$raw_cache" --output "$restore_root/input/input.csv" --receipt "$restore_root/input-rebuild.json"
"$python_bin" "$helper_dir/locked_exec.py" --family "$family" "$family/scripts/verify_input.py" --raw "$raw_cache" --input "$restore_root/input/input.csv" --output "$restore_root/input-qa.json"
"$python_bin" - "$family" "$restore_root/expected" <<'PY'
from pathlib import Path
import json, sys
family, expected = map(Path, sys.argv[1:])
files = json.loads((family / 'artifacts/20261003-coldstart-v2/private-output-manifest.json').read_text())['files']
assert len(files) == 22
with (expected / 'RESULT-MANIFEST.json').open('x') as out:
    out.write(json.dumps(files, indent=2) + '\n')
PY
"$python_bin" "$helper_dir/locked_exec.py" --family "$family" "$family/scripts/restore_run_v2.py" --input "$restore_root/input/input.csv" --output "$restore_root/regenerated" --expected "$restore_root/expected" --receipt "$restore_root/restore-receipt.json"
"$python_bin" "$helper_dir/locked_exec.py" --family "$family" "$family/scripts/verify_replay_v2.py" --input "$restore_root/input/input.csv" --results "$restore_root/regenerated" --report "$restore_root/independent-oracle.json"
```

原输出无需事先存在。预期结果清单仅来自远端 hash-only 文件的 `files` 数组，保持顺序并以 `json.dumps(indent=2)+newline` 写出；预期清单 SHA 为 `35fc722891e9f51aed24e5b2b8b2222d1f4396ccb2de6367e085fe4125228d8d`。恢复程序核 C0，执行远端 v2，再比22个payload及RESULT-MANIFEST逐字节；独立Fraction/Decimal oracle核731指标、4×731账户与全部事件。此次22+1全部精确。

这是因授权变更而新增的远端来源恢复验证：只重放已有4配置，新增研究试验0、控制0、严格复现0。原始行情和完整账本未放进Git；论坛全文、原类和Lean源文件未要求或外传。Library完整私包远端保存仍单列未验证，不能将本次Git核心验证改写为完整私包备份成功。
