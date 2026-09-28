# P0独立价格输入与过去窗口核验

日期：2026-09-08。家族：`Binance-1D-Trend-Strength-Pullback-Restart`。本阶段只核验输入、过去覆盖及读取来源，没有计算研究信号、趋势强度、未来标签或收益。

**结果：`PRICE_INPUTS_READY_WITH_RECORDED_EXCLUSIONS`。** 全部652个明确请求的COIN观测代码均完成覆盖调查；648个具有至少60根连续过去日K，重新通过正式研究启动接口并保存本次返回帧。没有启动失败、旧家族帧回退或数据湖写入。

## 固定输入

- 组合：`binance.v3.research_inputs.v2`，清单SHA256为`d2a729d03be71d67aa9c5522fb242bbf010b6c64400233c27d9cb2406f567008`。
- 日线：`binance.perp.ohlcv.1d.from_15m.v2`；请求2019-09-09 00:00 UTC开盘至2026-09-05 00:00 UTC完整收盘，最后可能开盘为9月4日。
- 价格诊断、`crypto_only`、`contiguous_segments`；调查`backward=1/forward=0`，正式帧`backward=60/forward=0`。60根包含当前日K。
- 明确固定正式Lab代码根和数据根，全部价格通过本次`require_research_startup`返回取得；仅复制了旧研究的请求参数和读取包装逻辑，没有读取旧家族价格帧或研究面板。

证据：[输入合同](../specs/input-contract.md)、[请求](../specs/input-request.json)、[当前源码pin](../specs/source-pins.json)、[观测代码及排除分类](../specs/observed-universe.json)。代码观测分类不等于完整历史PIT。

## 覆盖和排除

| 项目 | 本次结果 |
| --- | ---: |
| 明确请求代码 | 652 |
| 正式启动返回代码 | 648 |
| 不足60根连续过去日K | 4 |
| 接口或启动失败代码 | 0 |
| 返回总行数 | 597,968 |
| 观测合资格行 | 549,737 |
| 完整过去60根窗口 | 510,856 |
| 合资格连续段 | 659 |

4个排除均由过去历史长度决定：`DOS/USDT:USDT`为24根、`GRVT/USDT:USDT`为35根、`MARSCOIN/USDT:USDT`为3根、`牛来/USDT:USDT`为5根。没有根据后续走势、完整未来窗口或收益选择标的。

资格不足行仍保留在原返回帧；未来研究只能按连续段构建特征，不能先删除这些行再拼接。完整清单见[coverage.csv](../artifacts/p0-inputs/coverage.csv)与[segments.csv](../artifacts/p0-inputs/segments.csv)。

## 来源与独立复核

P0约463秒完成，退出码0；[完整日志](../artifacts/p0-inputs-run.log)、[执行状态](../artifacts/p0-inputs-run-status.json)、[启动记录](../artifacts/p0-inputs/started.json)、[结束摘要](../artifacts/p0-inputs/summary.json)均已保留。

运行后使用独立[核验脚本](../scripts/verify_p0_inputs.py)检查所有648个返回帧：

- 706项去重文件哈希，包括全部帧、请求及返回报告、覆盖清单、输入合同/配置，以及当前37个源码文件和1个组合清单。
- 每帧业务身份、行数、Pandas内容哈希、时间单调与无重复、显式闭合截止。
- 每条已保存请求与启动报告一致，且正式请求均为`backward=60/forward=0`；没有使用调查帧代替正式返回帧。
- 全部返回帧的过去窗口mask独立按连续段重算一致；每个有效连续段的日线时间间隔为1日。
- 本次启动前后源码pin、输入合同和相关家族配置未变化。

上述检查全部通过；[独立核验收据](../artifacts/p0-independent-verification.json)保存范围和各文件哈希。新返回帧清单SHA256为`82a6fc9267a212d7566340d00903d0bde32688a0ee447c5a99dc5ed580b766fa`，见[frame-manifest.json](../artifacts/p0-inputs/frame-manifest.json)。

新可信消费入口已分别登记于worktree和正式Lab，精确入口检查均PASS。全局检查另有5项和6项其他家族问题，未将局部通过写成全仓通过，详见[消费者检查收据](../artifacts/consumer-preflight.json)。

## 允许的下一步与边界

在研究定义与统计合同冻结后，可以从本家族这次API返回帧开始构建研究面板。P0没有提供任何新研究结论；重新核验相同历史不会使其成为未见样本或独立OOS。

本阶段仍不证明历史PIT、资金费完整结算窗口、订单可成交性或策略可用性。价格模式通过不能写成完整净收益通过；无资金费证据时不得补零。后续未来标签完整性只能作为评价状态，不能反向取消当时真实产生的观察机会。
