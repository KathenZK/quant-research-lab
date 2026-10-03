# M1347 固定核心恢复

此配方恢复已冻结四个配置，不运行新的控制、不换数据、窗口或参数。协调者必须先实际取回经独立核验的远端精确 Git commit，再核对本家族 `publication-manifest.v1.json` 及 `specs/C0-v1.json`，并取回 `specs/kernel-pin.json` 中四个精确共享内核对象。

原始行情不入 Git。使用合法持有的固定 25 ZIP 与 25 CHECKSUM，或已验 canonical CSV。固定原档可以离线重建；若原档丢失，只有另行已获授权的正常官方获取流程可取得，访问限制或内容哈希变化必须报告。这里没有联网、替代来源或删除文件的代码。

```bash
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
python research/public-strategies/M1347/scripts/rebuild_input.py --raw EXISTING_FIXED_RAW --output NEW_PRIVATE/input.csv --receipt NEW_PRIVATE/input-qa.json
python research/public-strategies/M1347/scripts/restore_core_v1.py --input NEW_PRIVATE/input.csv --fresh NEW_PRIVATE/fresh --receipt NEW_PRIVATE/restore-receipt.json
```

`restore_core_v1.py` 将 C0 全部对象和四个固定内核文件复制到新目录，重新映射已授权 root 放行的独立代码回执路径，再调用原冻结回放与独立校验器。预期结果只取自原公开的 hash-only `private-output-manifest.json`，不是新输出自比较：30 个 payload 和 manifest 共 31 文件必须逐项精确匹配。M1258 的七文件仅作既有基准引用，不执行买持。

`root-release.portable.json` 只对原 root 放行文件中的本机绝对回执路径作可移植映射；原 gate SHA 记录在 portability 字段，原字节保存在私有包。批准的 ID、C0、source commit、四配置、控制和独立回执 hash 均不变，不能用于其他新试验。

必须预装 `specs/environment-lock.json` 所锁 Python 和依赖；这不是空机器一键环境。首次本地恢复已对原完整 31 文件 reference 逐字节验证；此远端配方本身不表示远端恢复已经执行。远端 Git 核心、行情重建能力与完整私有 Library 包分别报告，既知 Library 401 未被本地 ZIP 消除。
