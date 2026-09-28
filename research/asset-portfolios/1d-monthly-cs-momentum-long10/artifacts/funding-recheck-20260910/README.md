# 2026-09-10 资金费收益差复核

结论见[报告](../../diagnostics/binance-1d-mcsm-funding-recheck-20260910.md)。原四账户完整独立复算，未发现方向、数量、重复入账或复利错误；官方API仅核到16,211/97,421笔，全历史来源未完成。3,695个可得原生mark优先的实际对照总收益+10,084.17%，相比原中心+10,085.43%仅少1,259.03 USDT；仍为估算，不是实盘认证。

- [accounting](accounting/summary.json)：四账户独立区间现金算法、同价格账户数量资金现金、月度/年度拆分；[新原生对照独立复算](accounting/native-priority-check.json)。
- [marks](marks/summary.json)：实际使用的全部分钟/原生价格原文、哈希、单位；[原生覆盖与同数量现金误差](marks/native-combined-cash-coverage.json)。
- [sources](sources/summary.json)：全760窗口查询计划、134本日成功与4个旧请求原文；[网络停止回执](sources/network-halt.json)。HTTP403后停止，不再联网。
- [retained-sources](retained-sources/summary.json)：原正式来源清单范围内的官方API/ZIP旁证，类型/mark缺失不补。
- [legacy-lineage](legacy-lineage/summary.json)：沿旧下载器声明路径检查1,393个资金费率ZIP，原目录未找到目标文件；转换表不代替原文认证。
- [combined-sources](combined-sources/summary.json)：完整保留97,421原事件ID，16,211明确类型API匹配，81,210未覆盖，3,695可得原生mark；月档费率旁证另列。
- [native-replay](native-replay/summary.json)：只改变明确官方唯一匹配的mark及出处、其余沿用原估算；[运行前固定输入](native-replay/started.json)。
- [completion.json](completion.json)：最终测试、哈希、链接与总体限制。

本轮总产物约48.8MiB，未复制原分钟大包或四套大账户明细。全部本地保留，不加入普通Git大文件；未移动或删除任何历史数据。原生重算目录存在即拒绝覆盖，重新核对请使用独立新输出目录；来源重现仅离线。
