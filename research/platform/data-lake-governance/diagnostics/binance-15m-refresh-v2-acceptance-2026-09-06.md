# Binance 15m V2 增量刷新验收

## 结论

本轮下载、独立版本发布和发布后可信读取验收已完成；**历史完整性治理仅部分完成**。不把行质量 `PASS`、当前活跃合约尾部对齐解释为全历史无缺口。

- 数据集：`binance.perp.ohlcv.15m.refreshed.v2`，注册为 `TRUSTED_DERIVED / FULL_MARKET`；它是原 15m 底座加官方 API 缺失键的同周期快照，不是重采样。
- 冻结闭合截止：`2026-09-05T15:45:00Z`，即北京时间 **2026-09-05 23:45**。最后一根 bar 开盘为北京时间 23:30。本次执行跨到 9 月 6 日，未追逐移动截止，不能称为验收时刻的实时数据。
- 最终 61,291,949 行、874 个合约、2,946 个 parquet；含历史合约及传统资产永续，不是 874 个当前活跃加密币。
- 原底座 60,266,362 行全部保留，新增 1,025,587 个业务键。尾部抓取返回 1,012,747 行，历史缺口探测返回 80,352 行；扣除 67,512 行重叠后得到新增量。重叠冲突为 0。
- 当前元数据下须达到最新闭合 bar 的 COIN/INDEX 合约 526 个，全部达到截止；这些活跃合约在本次新增窗口内部缺口为 0。此结论不是历史 PIT 成分证明。
- 发布后 catalog 读取执行 `strict_content` 验指纹及全量 SQL：行质量 `PASS`，重复键、未闭合、网格错误、非法 OHLC、非有限值均为 0。原始响应到落地 raw parquet 对齐 `PASS`，缺行和多行均为 0。

## 尚未完成的历史覆盖工作

原底座 132 段 / 89,152 根内部缺口中，本轮补回 80,352 根，仍有 17 段 / 8,800 根未补回。API 空响应或不可用不等于已证明交易所没有该数据。

**最终快照的总内部缺口实际为 143 段 / 286,882 根时间网格位置，不能只报上述 17 段。** 额外 126 段 / 278,082 个位置来自当前 `SETTLING` 合约：旧数据末尾为 2026-07-31 23:45 UTC，尾部探测返回数据从 2026-08-23 23:45 UTC 起，中间每段 2,207 个位置。

代码核查发现：对非 `TRADING` 旧合约，准备阶段使用全局旧尾部前一日探测，而非该合约自身尾部前一日。因此这些衔接区间没有被本轮原始缺口任务覆盖，未完全实现契约中“每币至少重取衔接前一日”的要求。当前不能判定其属于休市、停交易、历史接口行为还是漏抓；不得把它们全部解释成真实交易期间漏数，也不得当作已完成治理。已发布 V2 保留实际官方返回记录，不补零、不改写旧版本。

按当前元数据，最终缺口分布为：COIN/TRADING 12 段 / 6,201 个位置；COIN/SETTLING 129 段 / 278,430 个位置；INDEX/SETTLING 1 段 / 2,207 个位置；UNKNOWN 1 段 / 44 个位置。该分类仅用于审计，不是历史交易日历。

后续门禁：先核实上述 126 个非活跃合约的完整衔接窗口与交易状态证据，再处理原 17 段未解缺口；如新增数据，另建不可覆盖的新版本。研究必须显式选择 `reject` 或 `contiguous_segments`；本次验收的 `report_only` 仅用于治理，不能无条件跨缺口计算市场风格或收益。

## 空间、保护与验证

- 新快照含 manifest：2,224,829,027 字节；本轮压缩原始响应：40,454,540 字节；新增 raw parquet：42,826,220 字节。三项合计约 **2.15 GiB**，审计附件另约 8 MB。验收时磁盘可用约 **187.5 GiB**。
- 原 normalized 15m 前后内容库存指纹相同：`c615a4c12cd8392fbf083ad2b0ffaa693d65837da19f797813e7f726d377475a`。未覆盖旧 v1，也未删除旧 raw、缓存或研究产物。
- 新快照 parquet 库存指纹：`835c37fd55eff583780124dfc7c8e7a94f9570eb5c512174ab6242109a383002`。
- 最终 builder SHA256：`93b481cb85e25d0dd819b4c684c47688545d61c66757b1657895389e47513804`，以发布 manifest 为准。准备阶段 config 中的脚本哈希保留当时状态，不冒充最终 builder 哈希。
- `.venv/bin/python -m pytest tests/test_binance_15m_refresh_v2.py tests/test_ohlcv_round3_governance.py -q`：18 passed；对应刷新脚本与测试的 Ruff 检查通过。
- **没有**全历史重新下载、全历史 Vision CHECKSUM 复核、1m/5m 下载、1h/4h/1d 刷新、旧研究消费者自动迁移或策略回测。旧高周期 v1 仍停留在其原截止。

## 证据与读取

- [冻结契约](../specs/binance-15m-refresh-v2-contract-2026-09-05.md)
- [发布后独立验收](../artifacts/binance_15m_refresh_v2_20260905/acceptance.json)
- [合并审计](../artifacts/binance_15m_refresh_v2_20260905/build_audit.json) · [全部剩余缺口](../artifacts/binance_15m_refresh_v2_20260905/remaining_gaps.csv)
- [逐合约新鲜度](../artifacts/binance_15m_refresh_v2_20260905/symbol_freshness.csv) · [历史缺口探测结果](../artifacts/binance_15m_refresh_v2_20260905/gap_outcomes.json)
- [原始数据对齐](../artifacts/binance_15m_refresh_v2_20260905/raw_normalized_alignment.json) · [旧底座保护](../artifacts/binance_15m_refresh_v2_20260905/old_base_protected.json)
- [发布 manifest](../../../../data/derived/datasets/binance_perp_15m_refreshed_v2/_MANIFEST.json)

```bash
.venv/bin/python research/platform/data-lake-governance/scripts/example_binance_ohlcv_usage.py load-research \
  --dataset-id binance.perp.ohlcv.15m.refreshed.v2 --scope FULL_MARKET \
  --end 2026-09-05T15:45:00Z --gap-policy contiguous_segments --max-materialize-rows 0
```

该命令是消费入口示例，不代表本轮已经运行市场风格研究；必须进一步落实合约分类、历史成分与缺口分段边界。
