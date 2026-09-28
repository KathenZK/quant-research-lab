# 复现入口

在 quant-strategy-lab 根目录运行：

```bash
.venv/bin/python research/asset-portfolios/1d-ma7-atr14-long-transfer/scripts/run_transfer.py
.venv/bin/python research/asset-portfolios/1d-ma7-atr14-long-transfer/scripts/build_trade_paths.py
```

`run_transfer.py` 只调用固定组合的 `require_research_startup` 获取研究价格并使用有效掩码；若校验失败抛错，不回退旧数据。默认拒绝覆盖已存在的 summary.json；复跑使用 `run_transfer.py --run-id replay_20260907_01` 写入全新产物子目录，仍使用原冻结合同，不能删除基线来复跑。已保留输出可以直接运行 HTML 渲染器，不重新读取行情。

`frozen_engine.py` 是会话已核验 HYPE 引擎的逐字节副本，SHA256 固定在合同里。这里只调用其指标和 execute，不调用其旧 HYPE 下载/主程序入口。`source/hype_backtest.py` 是原稿参考，仅抽取已审阅的 backtest 函数对拍，不执行其顶层语句。

所有参数固定，费用使用报告中的不同情景；不搜索阈值。最终回放验证和图表验证分开留存。


## 全市场扩展（2026-09-08）

依次运行 `run_full_market.py`、`analyze_full_market.py`、`build_full_market_report.py`，运行环境仍为 Lab 根目录的 `.venv/bin/python`。前两步拒绝覆盖本次已保留的结果，独立复跑应在另一个研究副本中保留原合同、原七币锚点与明确的数据根；不得删除旧结果来腾出名称。全市场输入由登记的 `load_inputs → require_research_startup` 直接返回；分析器只消费同主题已保留的摘要与交易，渲染器会核对输入文件指纹。

`full-market-contract-20260908.json` 固定 683 个显式标的、原引擎 SHA256 和时间范围。启动按 48 个标的一批；若整批校验失败则递归缩小以隔离失败标的，不改用旧数据。本轮没有标的启动失败。`full-market-analysis-details-20260908.json` 固定跨年标签剔除、按入场月份对齐和末端估值敏感性的实现细节。

验证：`.venv/bin/python -m pytest research/asset-portfolios/1d-ma7-atr14-long-transfer/scripts/test_full_market.py -q`。实际回放另保存 14 个七币锚点精确对拍以及每币原函数、独立因果回放和前缀不变性结果。
