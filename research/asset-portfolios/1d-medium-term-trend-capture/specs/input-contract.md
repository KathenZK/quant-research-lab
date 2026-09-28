# BIN-1D-MTTC P0 独立价格输入合同

日期：2026-09-09。按[研究合同](research-contract.md)和[配置](config.json)固定本轮输入；P0先于本家族候选、信号、未来标签和收益计算。

- 固定组合 `binance.v3.research_inputs.v2`，清单 `research/platform/data-lake-governance/specs/binance-v3-research-input-bundle-v2.json`，SHA256=`d2a729d03be71d67aa9c5522fb242bbf010b6c64400233c27d9cb2406f567008`。
- 日线 ID `binance.perp.ohlcv.1d.from_15m.v2`；开盘从2019-09-09 00:00 UTC起，完整收盘截止2026-09-05 00:00 UTC，最后开盘为2026-09-04。
- 本次冻结清单中全部652个COIN代码明确列入请求；非COIN及UNKNOWN列入排除记录。不按现在TRADING、将来收益或未来完整性缩减标的，不声称完整历史PIT。
- 代码根固定 `/Users/ZK/OpenCode/quant-strategy-lab`，共享数据根固定其 `data/`；本家族唯一价格入口是 `require_research_startup`。复制旧TSPR的两阶段入口逻辑，不读取旧家族保存帧、面板或策略结果。
- 使用 `mode=price_diagnostic`、`asset_policy=crypto_only`、`gap_policy=contiguous_segments`。第一阶段backward=1/forward=0审查观测覆盖，第二阶段仅对至少存在60根连续历史的代码以backward=60/forward=0重新启动，保存第二次API返回帧和官方mask。
- 缺口、零成交、无效值及身份边界重置连续段；先删除无效行再拼接的做法禁止。未来未成熟不得改变候选；后续状态、标签和账户按新研究合同单独计算。
- 当前37份data读取源码与组合清单共38个pin重新生成；请求、入口、输入合同、来源pin、观测清单在运行时再次固定。运行结束复核不变，所有请求、失败、返回报告、帧文件SHA256、DataFrame内容哈希、覆盖和分段统计保留。
- 全局组合/哈希/接口错误中止；仅明确到标的的范围错误可分批定位，原拒绝回执不得丢弃，不改变模式、版本或范围逃避失败。
- P0仅获得价格诊断资格。历史身份、PIT、资金费整窗和真实可执行性均不自动通过；缺资金费不填0。后续资金费覆盖及真实mark/前一日收盘代理分别在独立费用审计中披露，不把观察身份声明伪装成net_research通过。
- 全部历史为 `ITERATIVE_REUSED_DIAGNOSTIC`。P0不写入数据湖、不修改旧家族，也不计算候选、收益或新规则。

本轮与TSPR固定相同价格范围，是为了比较新A/B/C完整规则；仍重新获取当前可信返回帧，重复历史不是新增独立验证。
