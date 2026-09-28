# Binance 15m 增量刷新与质量验收 V2

用户已授权把 15m 数据治理并补齐至本次运行时点；优先控制磁盘占用。本轮是数据工程，不读取策略标签或运行策略。

- 保留 normalized 15m v1 和已发布 derived v1；新增 `binance.perp.ohlcv.15m.refreshed.v2`，在同一数据湖的独立 staging 构建，验收后发布、登记。
- 冻结截止取准备阶段币安 serverTime 向下取整至 15 分钟边界；只接受 `open_time + 900000 <= cutoff` 且 `close_time == open_time + 899999` 的 bar。执行过程中不追逐移动截止。
- 范围是原 v1 合约集合与当前 exchangeInfo 中 USDT 的 PERPETUAL / TRADIFI_PERPETUAL 合约的并集，并核对官方历史归档目录。保留当前 contractType、underlyingType、status、onboardDate、deliveryDate；传统资产、指数、加密币分别报告，历史身份未知不伪造 PIT 元数据。
- 数据来源：原 v1 先经 catalog 严格内容指纹和全量 SQL 验证；新增来自 Binance FAPI `/fapi/v1/klines`，保存原始响应、参数、获取时间和 SHA256。只增量下载；没有全历史重新下载或重新核对全部 Vision CHECKSUM 的声明。
- 每币至少重取衔接前一日；现存业务键以原已接受 bar 为准，重叠差异单独导出，不悄悄覆盖。新币从可得 onboardDate 开始；无 metadata 的历史归档候选只探测本轮增量窗口，其历史覆盖保留限制。
- 历史内部缺口逐段尝试官方 API；只将实际返回的合法 K 纳入，空响应、下架无接口、首尾未知、休市等逐项记录，不插值或补零。
- 整库通过重复、有限数值、OHLC、成交量/额/笔数、时区网格、闭合与来源审计才发布。内部缺口另列，不将行质量 PASS 解释为历史无缺口。
- 活跃 COIN/INDEX 永续在 cutoff 前已上市者，必须覆盖最近闭合 bar；传统资产不套用 24/7 活跃尾部判据，逐币报告其时点和内部缺口。新增窗口的加密币内部缺口另行核查。
- 同源重叠不得存在矛盾记录；原始响应至规范新增字段逐行对齐。浮点对账容差事先固定：OHLC/笔数精确；volume `atol=1e-9, rtol=1e-12`；quote_volume `atol=1e-6, rtol=1e-10`。
- 15m 快照审计完成后可生成新版本 1h/4h/1d；每桶仍需 4/16/96 根完整 bar。此次用户优先 15m，其他周期的旧 v1 截止不得被宣称已刷新。
- 输入、代码、config、原始响应、产物保留哈希；旧输入末尾再次验指纹。磁盘少于 30 GiB 停止。本轮不自动迁移旧研究脚本。

脚本：[refresh_binance_15m_v2.py](../scripts/refresh_binance_15m_v2.py)。配置与审计：[本轮产物目录](../artifacts/binance_15m_refresh_v2_20260905/)。
