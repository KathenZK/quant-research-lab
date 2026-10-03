# Batch017 固定日线目录假设恢复

本批次M1346/M1270固定消费catalog-daily-cash v1，M1349消费v2的max_completed_closes=25。每ID4配置、合计12，新增控制0。原C0和结果指纹保留不变。HYPOTHESIS / ADAPTED_EXECUTION_PROXY、trusted=false、非OOS、strict=0。

## 精确恢复

先取得本目录所在的**确切发布commit**及清单中的全部公开文件，不能混入旧工作目录或旧结果。共享内核从其canonical路径按SHA256验证；不执行其他策略runner。

1. 固定Python/包版本和环境变量，见payload/frozen/runtime-v1.json；不可默默升级依赖。
2. 在仓库根执行本目录materialize_core.py --repository . --output NEW_PRIVATE_BUNDLE。此步验证所有公开核心文件；原C0中的非执行私有历史日志只保留哈希承诺，不伪称重新执行原准入流程。
3. 使用已获准的50个原生BTCUSDT 1d ZIP/CHECKSUM对象，执行NEW_PRIVATE_BUNDLE/source/rebuild_daily_input.py --raw APPROVED_RAW_CACHE --protocol NEW_PRIVATE_BUNDLE/frozen/M1258-protocol-v1.json --output NEW_PRIVATE_INPUT.csv --receipt NEW_INPUT_QA.json。严格校验所有对象hash/CRC并重建48e4e785…；无行情时停止，不从4h/NAV/他所重建。
4. OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 PYTHONPATH=NEW_PRIVATE_BUNDLE/source/offline-guard python NEW_PRIVATE_BUNDLE/review/restore_core.py --bundle NEW_PRIVATE_BUNDLE --input NEW_PRIVATE_INPUT.csv --expected NEW_PRIVATE_BUNDLE/expected --output NEW_PRIVATE_RESULTS --receipt NEW_REPLAY_RECEIPT.json --ids M1346 M1270 M1349
5. restore_core只回放原固定代码，并要求每个输出payload及manifest与原结果逐字节相等。另用各内核独立verify_account和已保留独立信号审查，不能把哈希清单单独称为恢复成功。

原数据manifest提供固定25个月官方URL；50对象精确hash在M1258 protocol。若重新下载，只能在现有适用授权/未变更条款下有界补取这些官方对象；遇访问限制、身份验证、付费、新条款或不同bytes停止，不使用替代源/绕过，不盲重试。原M0216 builder pins仍在冻结规则中。未来官方可用性不保证。

## 范围边界

公开核心仅含自编代码、冻结规则、目录原值、报告、轻量结果、指纹和重建方案；不含raw价格、完整账户/成交日志、私有Library标识或无关缓存元数据。Binance Vision衍生结果署名并适用CC BY-NC-SA 4.0及既有条款。完整私有包另行保存，Library上传和实际下载恢复须用独立回执证明。此代码没有下单、实盘、站点激活或安全设置权限。
