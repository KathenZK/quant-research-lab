# MU-HYPE-XFER 研究脚本

本目录保存只服务于 `MU-HYPE-XFER` 的复现、对齐、迁移和报告生成脚本。

当前入口：

- [`refresh_and_audit_mu_binance_15m.py`](refresh_and_audit_mu_binance_15m.py)：刷新并审计 Binance MUUSDT 15m OHLCV 与 funding。
- [`audit_mu_v14_latest.py`](audit_mu_v14_latest.py)：按严格执行口径重跑 V14 最新分片与自然前向段。
- [`research_mu_v35_session_aware.py`](research_mu_v35_session_aware.py)：历史 V1-V14 时段研究与 legacy 台账生成器。
- [`research_mu_polygon_hype_v35_transfer.py`](research_mu_polygon_hype_v35_transfer.py)：Polygon 真股交叉验证。
- [`compare_mu_binance_polygon_alignment.py`](compare_mu_binance_polygon_alignment.py)：Binance / Polygon 对齐检查。
- [`compare_mu_binance_yahoo_alignment.py`](compare_mu_binance_yahoo_alignment.py)：Binance / Yahoo 对齐检查。
- [`migrate_mu_equity_ohlcv.py`](migrate_mu_equity_ohlcv.py)：将旧
  `data/external/us_equities` 原始文件按来源和 UTC 日期迁入统一 raw OHLCV，
  生成 SHA256/行数/round-trip 迁移清单；默认只审计，实际迁移需显式
  `--apply --remove-source`，迁移后可用 `--verify-existing` 重验全部目标 hash。
- [`accept_mu_polygon_ohlcv.py`](accept_mu_polygon_ohlcv.py)：使用 XNAS calendar
  过滤 Polygon 15m regular session，保留原生 `vwap`、映射
  `transactions -> trade_count`、显式派生 `quote_volume`，在缺口、闭合和
  raw/normalized 对齐通过后原子写入 canonical normalized。默认 dry-run；
  隔离 worktree 使用实际数据时运行：

  ```bash
  uv run python research/mu/scripts/accept_mu_polygon_ohlcv.py \
    --data-root /Users/ZK/OpenCode/quant-research-lab/data \
    --apply
  ```

  该脚本只接受 `source=polygon_api`；Yahoo 仍为 `raw_unaccepted`，不会填充
  缺失的 `trade_count`。
- [`mu_hype_xfer_kernel.py`](mu_hype_xfer_kernel.py)：冻结的本地 HYPE EMA 迁移内核。

脚本只服务 MU 研究时保留在本目录；长期结论写回上级 Markdown，保留的 JSON/CSV/HTML 写入 [`../artifacts/`](../artifacts/README.md)。只有成为可复用数据基础设施后才可提升到 `src/strategy_lab/`。不得从持续变化的 HYPE 家族研究脚本直接导入实现。
