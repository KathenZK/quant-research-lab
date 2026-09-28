# 产物索引

[成功回放](20260908-r1/summary.json)：683 个请求输入，678 个可回放标的，16,008 个版本×分段窗口，三成本共 48,024 次回放。

- [完整主窗口逐币结果](20260908-r1/main-symbol-results.csv)
- [同币配对统计](20260908-r1/paired-comparisons.csv)
- [全部年度和成本结果](20260908-r1/all-window-results.csv.gz)
- [多头入场退出路径对应](20260908-r1/long-path-summary.csv)
- [运行文件指纹](20260908-r1/run-manifest.json)
- [逐币独立账本核验](20260908-r1/validation.json)
- [首次核对失败记录](20260908/failure.log)：浮点表示差异，未覆盖原结果；成功回放使用冻结容差，交易时点和方向仍严格相等。

完整多空成交/权益保留在成功回放下的 `full-history-replays` 和 `main-replays`，来自同一可信输入。主题总产物约 108 MiB（B-review）：保留一轮成功回放和首次核对证据以复核反手顺序、本金归零及历史窗口，不继续累积搜参版本，不作为普通 Git 大文件提交。

## 适用性规律扩展

- [数据与原回放逐项对齐](applicability-20260908/feature-summary.json)
- [全部入场前条件统计](applicability-20260908/entry-feature-contrasts.csv)
- [条件跨年稳定性](applicability-20260908/rule-stability.csv)
- [年初已知的币种类型与后续表现](applicability-20260908/annual-asset-type-atlas.csv)
- [币种收益排名持续性](applicability-20260908/coin-year-persistence.csv)
- [压缩的逐笔入场前特征](applicability-20260908/trade-features.csv.gz)
- [输入与特征指纹](applicability-20260908/feature-manifest.json)

新增有界特征和归因表不复制全量价格；前一轮108 MiB路径证据仍原样保留。全主题继续按B-review保留，未增加普通Git大文件。
