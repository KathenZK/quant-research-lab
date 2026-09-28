# 日K交易路径图

读取原回测结果生成，没有重新计算交易或改变策略。原回测文件、源码与原哈希清单保留。

- [交互图](../artifacts/trade_paths_20260909/hype-ma7-trade-paths.html)：在同一页面切换主方案（18笔）与关闭反手（15笔），不把两套路径混在一张K线中。
- [主方案PNG总览](../artifacts/trade_paths_20260909/primary-trade-paths.png)与[关闭反手PNG总览](../artifacts/trade_paths_20260909/no_reverse_accel1-trade-paths.png)。

## 图怎么看

- 鼠标拖动平移，滚轮缩放；双击或“全历史”返回总览。“最近120天”用于看近期路径。
- 选择交易、点交易行或点击开平仓标记，自动放大到这一笔；上一笔/下一笔连续查看。键盘左右键可平移，Home回总览，正负号缩放。
- 日K下方同步显示RSI6和原小时账的净值，RSI图上的紫点对应提前退出信号。
- ▲开多、▼开空；◆移动止损、●RSI止盈、■样本结束结算。编号与交易表一致。
- 持仓背景区间区分多空；开平仓连线的绿/红表示本笔盈利/亏损，只是首尾连接，真实行情看K线。
- 黄色阶梯线是每笔实际生效的止损，取原 `stops.csv` 共519条记录，多单只上移、空单只下移；不是把最终止损倒画到整个持仓。
- MA7/RSI按完整日收盘时间对齐；蜡烛画在当天中间。开平仓按真实记录时间定位，因此日开盘成交点会在当天蜡烛左侧。
- 盘中止损只知道一小时区间，交互图横线表示该区间，菱形放在中间示意，不声称成交发生在整点或精确分钟。
- 两方案最后一笔均为2026-09-05 00:00 UTC样本结束结算，不是MA、RSI或止损发出的卖出信号。

所有价格标记含原模拟滑点，止损线使用触发参考价；收益仍是扣单边0.05%手续费和0.03%滑点、未计资金费率的原结果。

## 数据及显示检查

- 462根日K与原指标逐值一致；两方案共33笔开平仓、519条止损、各10,393个净值点与原账一致。
- [图数据及来源校验](../artifacts/trade_paths_20260909/chart_audit.json)；[逐值校验](../artifacts/trade_paths_20260909/payload_verification.json)。
- [11项本地交互逻辑检查](../artifacts/trade_paths_20260909/local_interaction_probe.json)涵盖方案切换、逐笔定位、前后笔、重置、滚轮、拖动、键盘、悬停及点选。使用本地最小DOM/canvas执行环境，不等于真实浏览器视觉验收；工具的浏览器安全策略禁止打开本地file URL，未绕过限制。
- 两张PNG使用标准绘图库生成并直接检查；[PNG来源记录](../artifacts/trade_paths_20260909/static_chart_audit.json)。
- HTML为独立文件，图形、交易、脚本全部内置，不需从网络加载任何资源。

## 复现绘图

交互图生成器：[build_trade_paths.py](../scripts/build_trade_paths.py)；页面源：[trade_path_template.html](../scripts/trade_path_template.html)。运行生成器只消费已校验的原结果，不调用回测引擎的simulate。

```bash
.venv/bin/python research/hype/1d-ma7-cross-atr-ratchet/scripts/build_trade_paths.py
```

静态图生成器：[render_trade_path_pngs.py](../scripts/render_trade_path_pngs.py)，依赖Matplotlib 3.10.6和中文字体，仅从上面已校验HTML中的数据绘图。本次绘图库装在临时独立目录，没有修改项目环境或市场数据。
