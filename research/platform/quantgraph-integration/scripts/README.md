# 复现入口

先启动相邻 quant-knowledge-graph 服务，并在环境配置 `QUANTGRAPH_TOKEN`。
使用该仓库已安装的 SDK 环境运行：

```bash
uv run --project ../quant-knowledge-graph python \
  research/platform/quantgraph-integration/scripts/select_candidates.py \
  --url http://127.0.0.1:8000 \
  --summary-output research/platform/quantgraph-integration/artifacts/candidate-summary.json \
  --private-output research/platform/quantgraph-integration/artifacts/local/candidates.json
```

合成指标由 `synthetic_demo.py` 重建。共享内核的 SHA256 固定于该脚本及
[内核登记](../../../_shared-kernels/quantgraph-diagnostics/README.md)，未来变动须新版本。
`tests/test_quantgraph_integration.py` 覆盖候选去重、各准入条件、缺失结果、统计边界与 paper 制品。

真实语料不在 Git，CI 使用自有合成记录；HTTP 真语料联通统计由 QuantGraph 的
`docs/ingestion-validation.json` 保存。日志和完整候选只留本机。

## Evidence V3（历史记录）

- `select_candidates.py --url ... --target 20 --minimum-required 1`：通过 SDK 获取显式 READY/V3 候选；缺字段或未知契约拒绝。
- `fetch_market_v3.py` 已退役并拒绝执行；历史下载记录保留。新下载必须使用 V4 结构化许可凭证。
- `research_v3.py --contract <frozen.json> --manifest <private-data-manifest.json> --output <family/artifacts/new-run> --private-diagnostic`：只允许运行明确 raw_unaccepted 私有诊断。没有该显式标志则拒绝当前数据源的正式研究；调用不会自动写回。
- 账户内核 [quantgraph-market v1](../../../_shared-kernels/quantgraph-market/README.md) 和数学诊断 [quantgraph-diagnostics v2](../../../_shared-kernels/quantgraph-diagnostics/README.md) 均在载入前检查 SHA256。数据 URI/哈希、代码/config/候选快照与结果采用 schema 2.0，未来正式研究需额外通过全部 gate。
- 2 个私有探测输出是同一冻结基准/全网格结果，不是选择最好参数；其本机原文与经济输出不得纳入公开 PR。见 [验收](../diagnostics/evidence-research-v3.md)。

## Evidence V4

- `select_candidates.py` 当前要求 READY / Gate V4 / ELIGIBLE，默认最多选择 20 个模板。
- `fetch_market_v4.py --contract <research-contract-v4.json> --rights <reviewed-rights.json> --output <新 raw 目录>`：冻结合同必须先于下载；只引用已有审核凭证，不创建授权。原始字节及完整窗口覆盖都保留。
- `research_v4.py --contract <同一合同> --manifest <manifest.json> --candidate <当前候选.json> --output <新家族 artifacts 目录>`：默认正式模式，先核验所有绑定与质量；`--private-diagnostic` 是显式受限诊断，永不生成正式 envelope。
- 正式模式输出 schema 3.0，包含 contract/code/config/dataset/manifest/rights hashes。`submit_market_evidence` 通过 SDK 写回并读回；Graph chain API 查询全部关联。V3/schema 2.0 新正式写回被拒绝。
- 原生质量合同继续使用 `docs/data-lake-spec.md`。本轮三组数据都不满足，因此只运行私有诊断。

## Trusted Market v1

- [fetch_market_paged.py](fetch_market_paged.py)：`--contract`、`--rights`、`--output`；可显式配置 `--proxy`。完整双次抓取、边界审计、静默截断二分重抓；任何下载结果先保持 raw_unaccepted。只引用已有 reviewed rights。
- [audit_market_core.py](audit_market_core.py)：`--contract`、`--capture`、`--output`；独立从 raw 重建，全部通过才原子创建标准 normalized 分区内的新快照，拒绝覆盖。
- 在 Graph 使用 `scripts/admit_market_dataset.py --db ... --contract ... --manifest ... --output ...` 追加审查，读取 Gate 计算的 candidate.json；该脚本不导入 Lab 代码。
- [research_v4.py](research_v4.py) 接收上述同一合同、manifest 和候选；正式入口在计算前后复核数据、权利与摘要。输出交给 Graph evidence API，读回 chain 确认同一 run。
- 核心契约是明确 opt-in；旧原生字段 validator 保留，完整规则见[唯一数据湖规范](../../../../docs/data-lake-spec.md)。
