# 复现入口

## 资料审计与分类（2026-09-24）

`python3 research/asset-portfolios/multi-public-strategies-100/scripts/build_public100_taxonomy_20260924.py`读取已归档inventory、R2状态和学习说明JSON，输出74项原因表、100项多维分类、来源目录与输入指纹至`artifacts/classification-audit-20260924/`及对应文档。只重建本次资料分析，不读取市场行情或执行回测；不覆盖旧结果。人工撰写的总体分析位于[类型与历史演化](../notes/public100-types-history-evolution-20260924.md)。

## R2续测（2026-09-09）

新契约为`specs/continuation-*-20260909.*`，输出全部位于`artifacts/continuation-r2/`，不覆盖R1。使用仓库`.venv/bin/python`在仓库根执行：

1. `backtest_public100_b5.py`：复用首轮冻结Yahoo数据，恢复原优化器，分别执行22日/21日版；原优化器收敛状态和权重约束必须通过。
2. `backtest_public100_r2_equities.py`：依次执行A2、A55、C10及同窗对照。`public100_r2_inputs.py`按具体清单重验原始响应和分区哈希；Coinbase原生日线及共同交易时刻必须存在，日内网格缺行/零量会拒绝。
3. `backtest_public100_funding.py`：先用`continuation-perp-net-request-20260909.json`调用净收益启动门禁，实际使用返回帧；补充API markPrice只可与返回事件逐条匹配，不能替换费率。原始API响应与每日原生字段分区留湖。重复运行须原分区指纹一致。
4. `diagnose_public100_boros.py`：读取官方Boros历史归档，计算同到期三合约的部分币本位费率仓位。并非完整美元账户回测，缺项和费用近似见独立契约。
5. `backtest_public100_source_corrections.py`：先完成`capture_public100_source_etfs.py`保留缺少的IVV/VEU原生日线；按来源修正契约分别补测A36两种一月起算口径和C1来源ETF版。复用旧数据时重定向审计输出，旧账户结果不覆盖。
6. `build_public100_r2_report.py`：合并旧19项与新7项及来源修正变体，D6单列，输出完整100项状态及分窗口排名。
7. `test_public100_r2.py`：费用方向、无追领费用、真实持仓盈亏、8小时退出、未来数据隔离、B5调仓相位、缺行/零量拒绝、Boros退出估值，以及C1绝对动量先后次序/A36一月起算差异。加上R1共22个针对性测试。

采集入口`continue_public100_data.py`和缺口重查`probe_public100_gaps.py`只写原始源层。额外2分钟、早期markPrice与Boros查询的精确URL、响应指纹、分区指纹在本轮相应manifest/receipt中；复现使用留存快照，不依赖今天重新下载的数据仍相同。完整验证与文件指纹见`artifacts/continuation-r2/validation.json`和`delivery-manifest.json`。

## R1入口（保留当时说明）

本轮是明确未接受数据上的诊断，不是trusted策略复现。报告中的100条状态不能都计为已回测。输入与结果已留存；从下列已有快照重新运行不会需要交易密钥，也不会下单。

## 环境

仓库 `.venv` 提供numpy/pandas/pyarrow/scipy/exchange-calendars/pytest。原生现货回测另用临时隔离环境 `/tmp/public100-freqtrade-env`，版本见 [freqtrade-requirements.lock.txt](../specs/freqtrade-requirements.lock.txt)，核心 `freqtrade==2026.8`。如临时环境消失，使用 `uv venv /tmp/public100-freqtrade-env` 与 `uv pip install --python /tmp/public100-freqtrade-env/bin/python -r research/asset-portfolios/multi-public-strategies-100/specs/freqtrade-requirements.lock.txt` 恢复。月相补充用 `ephem==4.2.1`。绘图额外使用matplotlib，不改变回测计算。

## 依赖顺序

1. [collect_sources.py](collect_sources.py)：解析原清单，映射A1–A60的教程目录与公开网页。已审阅的代码快照在 `artifacts/sources`，原生回测直接用快照；不执行下载项目中的启动/交易/优化程序。
2. [collect_equity_raw.py](collect_equity_raw.py) 与 [collect_spot_raw.py](collect_spot_raw.py)：按冻结范围抓取、SHA/官方CHECKSUM校验、原子写入按日raw分区。已有快照直接复用；变化需另起v2，不覆盖v1。
3. [prepare_freqtrade.py](prepare_freqtrade.py)：先逐一验证raw指纹、时间网格，再做UTC完整桶聚合，生成可重建Feather adapter。当前故意不发表trusted现货数据。
4. [backtest_equity_diagnostic.py](backtest_equity_diagnostic.py)：ETF日线语义变体三档成本与SPY对照。输出每日净值、订单、权重和年度汇总。[supplement_calendar_diagnostics.py](supplement_calendar_diagnostics.py) 计算独立冻结的A31/A37近似，不覆盖主契约。
5. [run_freqtrade.py](run_freqtrade.py)：四个原生策略×三档摩擦。原始源码不修改，结果包含实际解析后的配置和源码。只使用backtesting子命令。
6. [summarize_native.py](summarize_native.py)：解析12个ZIP，逐笔买卖数量×成交价×双边费率独立复算，再核对期末余额；保存wallet曲线与固定池买入持有对照。
7. [probe_free_sources.py](probe_free_sources.py)：保留12项实际数据访问证据，包括HTTP200但非有效数据的响应。失败不意味着世界上没有免费替代。
8. [test_public100.py](test_public100.py)：现金/复利/漂移/费用/借券周末/无前视，以及D4/D5源码反例。`python -m pytest research/asset-portfolios/multi-public-strategies-100/scripts/test_public100.py -q`。
9. [build_report.py](build_report.py)：由已有数值和逐项状态生成中文报告、100行机器表、全部源文件SHA清单。

在仓库根执行脚本；数据采集脚本前加 `PYTHONPATH=src`。不运行清单来源项目的实盘入口。新的试验参数/数据范围不能改写本轮冻结规格，应新建版本。

## 审计限制

`artifacts/accounting-tests.log` 记录7项针对性测试。`artifacts/freqtrade/independent-accounting-audit.json` 是实际12次回测逐笔复算，不是单凭单元测试宣布结果正确。

消费者检查为本主题按具体路径/函数登记raw生产、raw诊断与输出生成，没有给整个家族放宽权限。全仓检查仍可能被其他在研家族的未登记读取器阻塞；完整输出在 `artifacts/consumer-check.log`，不能把本主题无新增错误说成全仓通过。原始source、市场数据和大部分artifacts被Git忽略，当前交付在本工作区，本轮未提交或推送。
