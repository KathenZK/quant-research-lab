# Binance 15m 全历史扫描与缺口治理 V3

## 结论与范围

本轮针对 V2 **全部已观测历史**的扫描、官方补洞、来源对账和边界分段治理已收口，状态 `GOVERNED_WITH_EXPLICIT_BOUNDARY_EXCLUSIONS`。这表示可恢复记录已补入、剩余边界均有明确处置及拒绝跨越检查；**不表示原始时间网格没有空位，也不表示整套历史交易日历/PIT 身份已获证明**。

数据集为 `binance.perp.ohlcv.15m.history.v3`，独立发布为 `TRUSTED_DERIVED / FULL_MARKET`。闭合截止沿用 **北京时间 2026-09-05 23:45**（UTC 15:45），不是执行结束时的实时行情；最后 bar 开盘为 UTC 15:30。

| 项目 | 本轮结果 |
| --- | --- |
| 历史跨度 | 2019-09-08 17:45 UTC 至 2026-09-05 15:30 UTC 的 bar open |
| 最终库存 | 61,577,807 行，874 个合约，2,971 个 parquet |
| V2 原问题 | 143 段，286,882 个缺失网格位置 |
| 实际补回 | 285,858 根官方 K；131 段完整恢复，其余 12 段保留边界处置 |
| 剩余网格空位 | 12 段 / 1,024 个位置；不能写成 0 |
| 来源对账 | 新来源间冲突 0；与旧数据重叠冲突 0；raw 落地往返不一致 0 |
| 旧数据保护 | 旧 V2 业务行丢失/改变 0；V2 内容指纹不变；原 normalized V1 另行复核 |
| 当前加密币及指数尾部 | 526 个须达到冻结截止的 COIN/INDEX 合约全部齐全 |
| 行质量 | 全量 SQL PASS；重复键、非有限值、非法 OHLC、未闭合、错网格均为 0 |
| 额外数值治理 | VWAP 公式错误 0；volume=0 但 quote_volume 非零错误 0 |

874 包括历史合约与传统资产永续，不能把它解释成“874 个当前活跃加密币”。未下载 1m/5m，没有刷新旧 1h/4h/1d，也没有自动迁移旧研究消费者或运行策略。

## 修复来源与逐段证据

对全库重扫出的每一段缺口查询官方 API（含左右端点），核对 143 份月度 ZIP/CHECKSUM，并对未覆盖日期核对日度归档；第一次日度探测 98 份，加入历史合约别名后实际消费清单为 78 份（73 份校验通过、5 份官方 404）。早一轮多取的原始证据保留，没有删除。

额外对 BNX/LIT 的 6 段历史缺口使用官方归档中的 settled 代码，原始回执保留真实请求代码；只在有限历史窗口映射回已有底座代码，并验证旧端点数值匹配。新入库按最终裁决来源分为：月度 Vision **278,082** 行、日度 Vision **5,856** 行、官方 API（历史别名）**1,920** 行。

数据表中的零成交 K 来自官方响应/ZIP，不是本地插值。全库共有 **5,163,158 根 volume=0 的原生记录**。这类记录以及上市前/结算后的静止价格，不得不加筛选地用于市场宽度、动量或可成交收益计算。

币安明确说明归档有每日/月度文件与 SHA256 CHECKSUM，历史归档也可能更新；本轮校验的是实际下载文件，不声称已重新验证每个旧历史月的远端最新版。[官方归档说明](https://github.com/binance/binance-public-data)

## 剩余 12 个边界：保留并隔离，不造 K

下表是残余空位的右端点。8 项有本轮已核实的官方上线公告，另 4 项使用冻结官方 exchangeInfo 的精确 onboardDate；后者只证明当前合约元数据匹配，不替代完整历史停交易日历。全部仍走保守的分段/拒绝门禁。

| 合约 | 右端点 / 上线 UTC | 空位 | 证据口径 |
| --- | --- | ---: | --- |
| AERGO | 2025-04-16 11:00 | 44 | [官方上线公告](https://www.binance.com/en/support/announcement/detail/82f730b7ef444a38b323ab7a2e56b757) |
| AIA | 2026-01-20 11:15 | 45 | [官方公告](https://www.binance.com/zh-CN/support/announcement/detail/4e7c59d4078e4babbc191c80fe6698e7)明确说明下架后图表缺口；元数据吻合 |
| BNX | 2023-02-22 14:45 | 59 | [重新上线公告](https://www.binance.com/zh-CN/support/announcement/detail/940d0e48493e4627889c3f46371df70b)；旧合约结算并更名 |
| CTK | 2025-04-30 10:15 | 41 | [官方公告](https://www.binance.com/ru/support/announcement/detail/63155163bce541f5856d416efa71c6e8) UTC+3 13:15；元数据吻合 |
| CVC | 2025-05-16 08:30 | 34 | 冻结官方 exchangeInfo 精确 onboardDate |
| CVX | 2025-07-23 11:30 | 46 | 冻结官方 exchangeInfo 精确 onboardDate |
| ICP | 2022-09-27 02:30 | 490 | [重新上线公告](https://www.binance.com/zh-CN/support/announcement/detail/adabdfbc53344094808a7bea464f101b)；旧合约于 2022-06-10 结算 |
| LIT | 2025-12-23 17:30 | 70 | [Lighter 上线公告](https://www.binance.com/en-AE/support/announcement/detail/6a33be00231c4539b3a4a625538e4d1e)；不假定旧 LIT 与 Lighter 是同一资产 |
| MAVIA | 2025-03-26 17:00 | 68 | 冻结官方 exchangeInfo；原公告为 16:15，本轮不把其未更新时点强行覆盖 API 元数据与首根 K |
| PUMP | 2025-07-10 07:30 | 30 | [Pump.fun 盘前合约公告](https://www.binance.com/en-AE/support/announcement/detail/4bc8b483d10d4619babb2015066b2d89)；元数据吻合 |
| SLP | 2025-07-23 11:45 | 47 | 冻结官方 exchangeInfo 精确 onboardDate |
| TLM | 2023-03-30 12:30 | 50 | [官方上线公告](https://www.binance.com/en/support/announcement/detail/bd18df283ead40d09fd60c8eab984e41) |

机器裁决见 [boundary_disposition.csv](../artifacts/binance_15m_history_v3_20260906/boundary_disposition.csv)；冻结元数据见 [exchange_info.json](../artifacts/binance_15m_refresh_v2_20260905/exchange_info.json)。`unclassified_residual_intervals=0` 只表示这 12 段均有边界排除处置，**不是**“所有历史覆盖 blocker 清零”。未解的完整 PIT/交易日历、旧代码资产身份不能由此晋升为已验证。

## 独立验收与实际消费门禁

发布后重新通过 catalog 做严格内容哈希与全量 SQL 审计，结果见 [acceptance.json](../artifacts/binance_15m_history_v3_20260906/acceptance.json)。随后独立重算逐合约库存和连续段，检查段内网格行数和全库行数一致；对每个残余边界验证跨越请求被拒绝、边界后的单段请求可定位，并实际调用 catalog 的研究 `reject` 拒绝 AIA 跨界窗口。

- [完整治理验收](../artifacts/binance_15m_history_v3_20260906/history_governance_closeout.json)
- [逐合约质量库存](../artifacts/binance_15m_history_v3_20260906/symbol_quality_inventory.csv)
- [全历史连续段清单](../artifacts/binance_15m_history_v3_20260906/history_segments.csv)
- [窗口分段检查实现](../scripts/closeout_binance_15m_history_v3.py)：`assert_window_within_segment()`；不声称其他家族已自动接入。

研究必须走 `load_trusted_research_dataset(..., end=..., gap_policy="reject"|"contiguous_segments")`。`contiguous_segments` 是消费契约，不会自动帮任意研究代码修改 rolling/pct_change；特征和标签必须按清单分段计算。零成交/历史资产身份还需研究侧显式有效性屏蔽。治理用的 `report_only` 不能作为新研究缺口默认策略。

## 空间、测试和不可变性

V3 快照含 manifest 约 **2.08 GiB**；本轮 raw API、归档和 raw parquet 合计约 **11.8 MB**，加审计附件后新增持久占用约 **2.09 GiB**。构建期间的临时磁盘占用不等于永久增长；完成时可用空间以机器验收值为准。

V3 parquet 指纹 `716cfc0ae265dd2c3d35c99eab15f92acb511b0426bdbf5b2683f43aae1833ff`；builder SHA256 `817cab49d0114f57cf5464875ce9730bfd49a613353611ec410e81274e451301`。详见 [发布 manifest](../../../../data/derived/datasets/binance_perp_15m_history_v3/_MANIFEST.json)、[旧 V2 保护](../artifacts/binance_15m_history_v3_20260906/protected_v2.json)、[raw 对齐](../artifacts/binance_15m_history_v3_20260906/raw_alignment.json)。

本轮刷新/补洞/分段/第三轮治理定向测试 **29 passed**，对应新代码 Ruff 通过。全仓 `check_trusted_consumers.py` 仍有 **5 个原先已有的未登记直读脚本错误**（CTP P6/P7/P7a/P7b 与 CER P0）；本轮没有新增该类错误，也没有为了通过门禁扩白名单或修改那些研究脚本。因此不能写成“整个仓库所有消费者已治理完成”。

契约：[V3 主契约](../specs/binance-15m-history-v3-contract-2026-09-06.md) · [别名补充](../specs/binance-15m-history-v3-alias-evidence-2026-09-06.md) · [边界证据配置](../specs/binance-15m-history-v3-boundaries-2026-09-06.json)。
