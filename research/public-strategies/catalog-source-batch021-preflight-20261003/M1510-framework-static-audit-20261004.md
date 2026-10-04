# M1510：2023.10 框架静态参考增补

父端完成了独立来源审计；root 另行核对了下列官方固定源码。2023.10 标签对应 `f142abfb76138848937b0a9b3be9181a00f6556e`，但这只是可追溯的框架参考版本，**没有证明它是原作者运行版本或有效配置**。状态保持 `BLOCKED_SOURCE_FRAMEWORK_SEMANTICS`；C0、合成策略执行、历史运行和新增对照均为零。

盈利退出门使用包含开、平仓费用的利润率；该参考实现先把利润率格式化到八位小数并转回 float，再与 offset 作严格大于比较。这里不将这种格式化等同于 Decimal 运算，也不据此指定原策略的 offset。[利润计算](https://github.com/freqtrade/freqtrade/blob/f142abfb76138848937b0a9b3be9181a00f6556e/freqtrade/persistence/trade_model.py#L853-L915)、[八位小数返回值](https://github.com/freqtrade/freqtrade/blob/f142abfb76138848937b0a9b3be9181a00f6556e/freqtrade/persistence/trade_model.py#L999-L1027)、[退出门](https://github.com/freqtrade/freqtrade/blob/f142abfb76138848937b0a9b3be9181a00f6556e/freqtrade/strategy/interface.py#L1116-L1142)。

回测会把信号列移后一根，再把当前处理行的开盘价传给退出判断。因此，相对形成信号的K线，盈利门使用下一处理K线的开盘价；这不是保证最终订单在该价成交。[信号移位](https://github.com/freqtrade/freqtrade/blob/f142abfb76138848937b0a9b3be9181a00f6556e/freqtrade/optimize/backtesting.py#L385-L398)、[退出调用](https://github.com/freqtrade/freqtrade/blob/f142abfb76138848937b0a9b3be9181a00f6556e/freqtrade/optimize/backtesting.py#L733-L747)。

止损和 ROI 标志在盈利退出门之前计算，且不共同受该盈利门条件限制。但候选退出的返回顺序是**信号／自定义退出→止损／清算→ROI→移动止损**，回测随后顺序尝试；不能表述成“止损／ROI 总在信号之前成交”。这些静态顺序仍不是 M1510 的获准执行契约。[标志计算和候选顺序](https://github.com/freqtrade/freqtrade/blob/f142abfb76138848937b0a9b3be9181a00f6556e/freqtrade/strategy/interface.py#L1093-L1163)。

该版本 qtpylib 的布林中轨使用 `min_periods=1`。对于有效数值输入，不能把前19根一概设为 NaN；这也不证明 EMA、交叉或整个策略在首根就可交易。[布林带实现](https://github.com/freqtrade/freqtrade/blob/f142abfb76138848937b0a9b3be9181a00f6556e/freqtrade/vendor/qtpylib/indicators.py#L420-L431)。

回测以订单价格落入K线高低区间作为触达成交判定。这种 OHLC 模型不证明真实挂单的排队、成交量、部分成交或交易所可成交性；原代码的限价和盈利门不能被无声删除。[成交判定](https://github.com/freqtrade/freqtrade/blob/f142abfb76138848937b0a9b3be9181a00f6556e/freqtrade/optimize/backtesting.py#L582-L614)。

父端独立取得的 M1510 源码为1,813B，SHA256 `64846c265b53f34dfdd117cc31b195466f09e1dc154a9f3c3835cf1eab4600fd`，与原源卡一致。[原固定策略](https://github.com/davidzr/freqtrade-strategies/blob/9623c1f3d8c7f60c8b411010fa26377e6ca99ab9/strategies/Babico_SMA5xBBmid/Babico_SMA5xBBmid.py#L10-L36)。旧 sell/buy API 到参考框架的属性映射、有效配置、依赖数值、风险和订单优先级仍须后续明确核验；本增补没有导入或执行框架。

父端报告其**独立审计包**已通过正常 Library 保存及实际取回恢复：129,820B、22成员、21清单哈希、CRC、9个官方 blob 和原11字段核验通过。root 本轮只确认 Library 文件元数据，并独立静态读取4个官方框架文件及标签引用，没有 materialize 或验证该压缩包。它不覆盖 root 原25成员来源包，也没有修复 root 上传401。公开登记只保留摘要和包指纹，不含 Library ID、原11字段或源码全文。

具体核对范围、四份源码指纹及恢复声明边界见 [安全审计记录](M1510-framework-static-audit-20261004.safe.json)。
