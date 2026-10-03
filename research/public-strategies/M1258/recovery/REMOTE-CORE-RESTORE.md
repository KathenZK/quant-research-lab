# M1258 远端核心恢复配方

从 root 验证过的远端精确 Git commit 取出本 ID 的全部文件。在冻结依赖环境中，使用合法持有的 50 个原始 ZIP / CHECKSUM 文件（本身不入 Git）执行：

```sh
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python research/public-strategies/M1258/scripts/rebuild_input.py --raw PRIVATE_RAW --output NEW_PRIVATE/input.csv --receipt NEW_PRIVATE/input-QA.json
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python research/public-strategies/M1258/scripts/restore_run.py --input NEW_PRIVATE/input.csv --expected-manifest research/public-strategies/M1258/artifacts/20261003-catalog-v1/private-output-manifest.json --fresh NEW_PRIVATE/fresh --receipt NEW_PRIVATE/restore.json
```

输出应精确匹配公开的私有产物指纹清单；该清单不含行情和完整账户内容。数据如需重新获取，只能遵循已审条款从 input manifest 的官方月档来源正常取得，并逐项核对既有字节。来源被删除、限制或修改时必须报告失败，不换来源补数。此处没有自动联网脚本。原网页 / 作者项目不包含在恢复范围：仅恢复独立目录假设。

完整私有 ZIP 和环境包不是 Git 核心的内容；运行仍依赖匹配版本的预装 Python / 包。root 将单独执行远端获取后恢复，本执行者不能把本地成功称远端成功。
