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
