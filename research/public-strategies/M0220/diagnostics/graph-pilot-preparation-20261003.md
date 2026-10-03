# M0220 Graph 离线兼容准备

本次仅适配既有冻结证据，没有启动研究、下载行情、创建私有runtime或操作站点。原始策略仍为HYPOTHESIS；打包通过不代表严格复现或Graph导入完成。

## 实际完成

新增 [prepare_graph_pilot.py](../scripts/prepare_graph_pilot.py)，先核验外部固定的原运行manifest，再逐一校验其全部文件哈希。原始26份文件（含原manifest）保留字节，代码作为惰性证据复制，不被导入或执行。

在明确名为 `projection-draft/` 的目录生成4份派生草稿：规格、指标、日收益、已保留验证结果。日收益从已存净值及原始初始资金转换，保留首日费用影响，逐日检查时间连续性，并与原指标总收益校对；成本敏感性、延迟、基准各分支均与原summary核对。现金仍是USDT，不为满足旧V1契约改写成CASH。

真实本地运行保留617天观察；26份原文加4份草稿共30文件、521264字节逐项校验一致。准备回执SHA256为 `03835e60ebb031a27659cfd090c2c2069bcec74285f4763020dbf0ce354d58f0`。实际准备包留在私有协调目录，不加入公开Git；此说明和适配代码不构成派生数据发布。

18项合成契约测试和Ruff通过。测试覆盖原件篡改、错误外部pin、丢文件、符号链接与路径越界、日期缺口/重复、指标矛盾、复现级别降格、原文件保留、首日费用，以及定义版本/规则哈希/WAL不一致。合成SQLite仅为测试fixture，没有冒充用户runtime。

## 尚不能导入的原因

准备回执始终声明 `native_import_ready: false`。以下5个原生文件没有伪造：`run_manifest.json`、`run_summary.json`、`all_record_coverage.csv`、`record_audit.jsonl`、`source_verification.json`。其中需要核清真实来源范围和原文定义，不能用行情哈希充当6973条原表的corpus哈希，也不能把本次适配文件称为历史生产者原件。

可选 `--catalog` 只接受已存在、由外部SHA256固定的私有Catalog一致性副本，使用SQLite `mode=ro`；有未归并WAL、缺现有研究宇宙、定义版本不一致、规则或来源字段不一致时失败。不会初始化空库。绑定检查通过也不会自动导入、发布或解除许可暂停。

后续应沿Graph既有V3保留原件的契约完成包装，明确记录适配来源，保留虚拟USDT及原运行ID；再经既有导入器、ResearchWorkView定义绑定门和Sites不可变/CAS流程。当前真实私有Catalog、来源范围及站点基线仍未恢复，所以这些阶段均未执行。

## 重复准备

在全新私有目录执行；同一输出目录不可覆盖：

```sh
.venv/bin/python research/public-strategies/M0220/scripts/prepare_graph_pilot.py \
  --family research/public-strategies/M0220 \
  --expected-manifest-sha256 c444874baa4ca96c59c39848155422628d2ffaab85d7bd7eb262d1cb7a4ad34a \
  --output /tmp/m0220-private-graph-preparation
```

这不是行情重建命令；需要原冻结文件均已存在。公开Git不能单独恢复全部私有原件，本命令在缺件时停止，不默默重新下载。行情许可与发布暂停状态见 [许可核验](data-license-review-20261003.md)。
