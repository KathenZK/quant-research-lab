# M0302 重建入口

使用私有批次包中的shared snapshot、sources与repo结构；保留相对路径。安装[固定依赖](../specs/requirements.lock.txt)，Python3.12.14、TA-Lib C0.6.4、OMP/OPENBLAS/MKL threads1。无市场网络请求，程序socketconnect禁用。先核[协议](../specs/protocol.json)source/input/kernel逐文件hash。

```bash
python research/public-strategies/M0302/scripts/run.py run --input "$INPUT" --sources "$SOURCES" --output "$NEW_RESULTS"
python research/public-strategies/M0302/scripts/run.py source --input "$INPUT" --sources "$SOURCES" --output "$NEW_SOURCE_QA"
python research/public-strategies/M0302/scripts/run.py oracle --input "$INPUT" --results "$NEW_RESULTS" --output "$NEW_ORACLE_QA"
python research/public-strategies/M0302/scripts/run.py prefix --input "$INPUT" --sources "$SOURCES" --output "$NEW_PREFIX_QA"
```

所有输出须使用不存在的新路径。run共4策略配置；买持只用协议内M0311控制hash，不重跑。适配器与原类Boolean完全对照，原类/qtpylib字节在私有sources；原始代码下载路径固定于protocol，离线恢复不下载。共享内核[manifest](../../../_shared-kernels/native5m-execution-proxy/v1/manifest.json)逐文件pin；任何修复新版本，不覆盖v1。

数据恢复一次全批执行：私有 `restore_batch.py` 复制共享snapshot与代码，在新目录用M0311已固定audit_input验证39原档→canonical，再逐ID重建14输出并比hash；M0311自身此前已完成一次恢复，不重复。最末打包脚本与逻辑路径映射在私有manifest。公开只含派生每日净值与明确成交样本，不含原始OHLCV。
