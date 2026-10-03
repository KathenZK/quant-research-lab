# v1 冻结接口

- `account.replay(frame, spec, case, closed_bar_cutoff_ms=None)`：返回完整5m净值、日净值、成交、指标。
- `source_adapter.features(data, spec, sources, adapter)`：固定原类／参数／qtpylib；对照 ID 的独立入出场 Boolean；价格均为原始 OHLCV。
- `oracle.validate(input_path, result_dir, spec_path)`：Decimal 独立重做决策及账户，不导入 account；标准库独立重算指标，预期零值严格相等，非零值绝对容差0、相对1e−9。入口断言初资100000、滑点2bps、预算95%；不独立复算日志phase、有效时间及notional字段。
- `workflow.py run|source|prefix|oracle`：固定输入、ID协议与共享文件哈希，网络连接禁用。ID脚本以 SHA pin 入口。

范围固定为本批 spot native5m、100000初资、95%含买费预算、2bps滑点、完整UTC日窗口；不作为任意市场生产平台。原limit成交改编必须在每ID标 ADAPTED_EXECUTION_PROXY。原始行情和完整5m输出只在私有恢复目录。

C0后不可原地修改任何本版本文件；消费者列表与版本来源见上一层 README。源码派生部分按 GPL-3.0-or-later。
