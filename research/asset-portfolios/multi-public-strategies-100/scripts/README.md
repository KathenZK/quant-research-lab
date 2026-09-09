# 复现入口

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
