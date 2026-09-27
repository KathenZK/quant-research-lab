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

## Evidence V3

- `select_candidates.py --url ... --target 20 --minimum-required 1`：通过 SDK 获取显式 READY/V3 候选；缺字段或未知契约拒绝。
- `fetch_market_v3.py --contract <frozen.json> --rights-audit <private-review.md> [--proxy <url>]`：需要 requests（或已安装 QuantGraph SDK 的环境）。保存原始 HTTP 字节/请求摘要，遇 403/429 停止；缺字段不伪造，不写 normalized。
- `research_v3.py --contract <frozen.json> --manifest <private-data-manifest.json> --output <family/artifacts/new-run> --private-diagnostic`：只允许运行明确 raw_unaccepted 私有诊断。没有该显式标志则拒绝当前数据源的正式研究；调用不会自动写回。
- 账户内核 [quantgraph-market v1](../../../_shared-kernels/quantgraph-market/README.md) 和数学诊断 [quantgraph-diagnostics v2](../../../_shared-kernels/quantgraph-diagnostics/README.md) 均在载入前检查 SHA256。数据 URI/哈希、代码/config/候选快照与结果采用 schema 2.0，未来正式研究需额外通过全部 gate。
- 2 个私有探测输出是同一冻结基准/全网格结果，不是选择最好参数；其本机原文与经济输出不得纳入公开 PR。见 [验收](../diagnostics/evidence-research-v3.md)。
