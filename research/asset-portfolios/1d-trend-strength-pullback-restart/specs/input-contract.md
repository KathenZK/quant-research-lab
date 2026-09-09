# P0独立输入冻结合同

日期：2026-09-08。先于本家族新状态、强度分组、标签和收益计算。P0只核对输入及事前历史覆盖，不计算研究结果；统计与研究合同另行冻结。

- 组合固定`binance.v3.research_inputs.v2`；清单`research/platform/data-lake-governance/specs/binance-v3-research-input-bundle-v2.json`，SHA256=`d2a729d03be71d67aa9c5522fb242bbf010b6c64400233c27d9cb2406f567008`。
- 日线`binance.perp.ohlcv.1d.from_15m.v2`，2019-09-09 00:00 UTC开盘至2026-09-05 00:00 UTC完整收盘；最后开盘为9月4日。
- 从固定组合观测分类选择全部652个COIN代码，配置中明确列出；UNKNOWN和非COIN排除。不是当前活跃币名单，也不是完整历史PIT。
- 正式Lab代码与共享数据根显式固定，通过`require_research_startup`使用本次返回帧。不得借用MTCS或其他家族的保存价格帧/panel作为新事实源。
- `mode=price_diagnostic`、`asset_policy=crypto_only`、`gap_policy=contiguous_segments`。先以backward=1/forward=0调查覆盖，再对可形成60根连续历史的代码以backward=60/forward=0重新启动；只保存第二次返回帧。
- 请求、失败、返回报告、帧内容与字节哈希、覆盖与连续段、当前读取源码pin均保留。全局bundle/hash/接口错误停止，不通过拆币或降级输入规避；仅明确标的范围错误允许隔离定位。
- 未来有效性不得影响事前合资格或交易机会。标签在单独阶段使用完整窗口mask；缺失、未成熟与已知中断不得填0。
- 所有历史是ITERATIVE_REUSED_DIAGNOSTIC。资金费全窗、历史身份/PIT与可交易性未证明；价格模式通过不能声称净收益有效。

本次与MTCS固定相同观测范围，目的是使两个新命题共享可解释范围；这是独立重新核验，不把重复数据当成新增独立证据。P0未筛选新研究结果，且不写入数据湖。
