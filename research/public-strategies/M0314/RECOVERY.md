# M0314 离线审计恢复

这是源码/规则审计恢复，不下载行情、不回测、不import/exec第三方源代码。需要Python3.12标准库；不需Jesse/Rust/NumPy安装。共享审计脚本只存于M0296；恢复本批4目录应保持同级。

从仓库根目录（包含 research/public-strategies/）运行，公开无原始源码时可验证合成：

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python research/public-strategies/M0296/scripts/audit_batch.py --synthetic-only --ids M0314 --out /tmp/M0314-synthetic.json
```

先切换到私有恢复包根目录（当前目录须同时含 public/、private/、PRIVATE_MANIFEST.json），再运行完整源hash/AST+合成检查：

```bash
ulimit -v 1048576
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python public/research/public-strategies/M0296/scripts/recover_audit.py --package-root . --out /tmp/batch005-recovery.json
```

以上manifest/AST都是输入完整性与分支审计，不是依赖安装/原引擎恢复或盈利复现。private证据必须来自原包；单靠重新下载URL不满足原字节恢复。许可与hash见source-manifest-v1.json。没有raw market、NAV或交易文件。
