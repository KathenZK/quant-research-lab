# 恢复范围与执行门禁

当前只有C0与人工序列，不存在已验证历史结果或本ID远端恢复。root统一保存代码/允许轻量结果/指纹；私有原始行情及账户不得自动公开。Library ZIP上传缺口独立记录，不声称成功。

恢复先用scripts/rebuild_input.py --raw EXISTING_50_RAW --reference FROZEN_CSV --receipt NEW_JSON校验固定输入；若恢复后只剩重建配方，不能称快照备份。源档案改变必须停，不能更新旧hash。

历史命令在独审及root解除control门禁之后：

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python research/public-strategies/M1463/scripts/run_replay.py --input PRIVATE_INPUT --output NEW_PRIVATE_OUTPUT --root-gate ROOT_GATE
```

ROOT_GATE必须含status=ROOT_APPROVED_HISTORY_AFTER_INDEPENDENT_QA、id、C0_sha256、control_independently_accepted=true，以及control.remote_commit和identity：M1258 buyhold、input48e4、100000、fraction1、entry_fee_inclusive、fee8/slip2、2023-01-01至2025-01-01、731行、Decimal_precision50。control.files至少2个root核验文件，各含local_path/bytes/sha256；字段格式见scripts/run_replay.py。本执行者不自行创建批准文件。

完整本地恢复用restore_run.py --input PRIVATE_INPUT --root-gate ROOT_GATE --results FROZEN_RESULTS --destination NEW_DIRECTORY，按C0复制代码/内核，重放及独立核验后逐字节比较。远端core恢复由root另外验，不将这个本地重跑冒称远端。
