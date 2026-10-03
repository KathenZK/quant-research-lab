# M0274 重建与独立恢复

## 已实际验证的恢复边界

本包是阻塞交付，未持有完整25月输入，没有任何真实回测产物可恢复。已实际在新本地目录复制审计脚本并重跑：合成因果反例、固定源码静态审计、已有14月854根的独立文件/行校验。确定性结果一致，详见offline-recovery-v1.json。合成输入只证明指标管线缺陷，不是行情替代。

第二轮完整网络抓取、25月逐hash重建、真实完整特征/信号/收益均NOT_RUN。14月.partial不是完整数据集。工作盘不是备份。当前访问拒绝仍有效，不应直接执行后面的网络配方；配方仅记录今后经授权恢复访问时的操作。

## 环境和低资源设置

审计Python3.12，ta==0.11.0、numpy==2.3.5、pandas==2.2.3。精确版本/ta模块摘要在artifacts/dependencies-v1.json。新环境依赖应来自官方常见Python包仓库并核对版本和源码模块hash；本任务没有并发修改依赖。运行前确认至少5GiB剩余空间，单进程不超过1.5GiB虚拟内存，OMP_NUM_THREADS=OPENBLAS_NUM_THREADS=MKL_NUM_THREADS=1。

## 无需网络的合成反例恢复

从该策略目录运行，输出路径必须不存在：

```bash
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
ulimit -v 1572864
python scripts/audit_synthetic_causality.py --out /new/local/synthetic.json
```

合成输入SHA256应为36ac6ad5bb3a71af3318c456adf9728a87bfebfff910e699ef68f2d73c06eed9；4个checks应与artifacts/synthetic-causality-v1.json逐字段完全一致。时间、峰值RSS允许因运行不同而变化。预期状态FAIL_FULL_TRANSFORM_PREFIX_CAUSALITY，11列变化，实际回测0。

## 已有源码/partial输入的离线恢复

源码必须是6802字节，SHA256 48e405f6d073944da9b993dfbce03aa980d0eea8a5da3c4a6b60f2f1b7264b86。源文件未在公开包附带；从授权本地保存或固定官方来源恢复后先核hash。

```bash
python scripts/audit_source_static.py --source /local/GodStra.py --out /new/local/static.json
python scripts/audit_partial_capture.py --partial /local/native12h-primary.partial --out /new/local/partial.json
```

将脚本SHA、每个native对象bytes/SHA、rows854、months14、43对象库存与公开partial-input-independent-qa-v1.json比较。不存在原始部分快照时此离线检查不能执行；只拿hash列表不能证明已经恢复行情。

## 尚未执行的完整网络重建配方

只有访问限制解除且有适用授权后，才在新的不存在目录执行：

```bash
python scripts/rebuild_native12h.py --timeframe 12h --target /new/local/native12h-capture --terms-reviewed
python scripts/verify_native12h.py --snapshot /new/local/native12h-capture --out /new/local/full-qa.json
```

脚本固定BTCUSDT现货、2022-12至2024-12共25月；每次下载ZIP和CHECKSUM、验证CRC/12列/时间网格/OHLCV。不存在已成功的完整manifest/hash可与之声称匹配。已有14月对象必须先逐hash比对；任何差异保留.partial/新快照、拒绝替换原冻结证据。

第一次完整抓取若将来成功，再在另一个新目录执行第二次抓取：

```bash
python scripts/rebuild_native12h.py --timeframe 12h --target /new/local/native12h-recapture --terms-reviewed --expected-manifest /new/local/native12h-capture/manifest.json
```

该参数需要完整原生manifest的protocol等字段，不能给轻量partial摘要。两轮一致只说明本次归档稳定，仍不能替代尚未建立的strict current finality/PIT证明。不得为补齐数据改域名、代理或绕过拒绝。

scripts/audit_causality.py保留完整1524行审计入口，但需要另行冻结有效输入contract；本包的blocked-diagnostic-freeze-v1.json含null input hash，故不能被该脚本接受为正式输入。即使将来补齐行情，也不能忽略已证实的完整管线前视缺陷自行启动回测。

## 公共包检验

publication-manifest.json的public_allowlist是相对本目录的逐文件bytes/SHA；self_excluded=true，manifest自身另验hash。只分发allowlist及manifest本身，不用递归打包整个work目录或策略目录。被排除的草稿、pycache、源码、行情、日志不能混入。
