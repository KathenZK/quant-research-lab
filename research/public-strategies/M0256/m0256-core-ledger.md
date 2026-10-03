# PUBLIC-M0256-EMA-CROSS Core Ledger

## Family Identity

稳定ID M0256 / AverageStrategy，Binance BTCUSDT spot / 4h UTC。变体`M0256-BTCUSDT-4H-EMA8-21-LONG-20261003`，run`M0256-20261003-first-replay`。默认EMA8/21交叉，原ROI50%、stop−20%。BTC实例为研究者预声明，原作者未指定币种池；HYPOTHESIS，非严格复现。

## Current State

`explore / not promoted / not live-ready`；输入`DIAGNOSTIC_ONLY / untrusted`，无runner、生产或交易动作。

| 版本/记录 | 状态 | 关键结果 | 证据 |
| --- | --- | --- | --- |
| 20261003-first-replay，未登记Vx | explore，验证/本地恢复通过 | 基准218.06%、最大回撤幅度23.98%、日Sharpe1.799；买持441.87%；174笔/87回合 | [报告](diagnostics/M0256-20261003.md) |

## Shared Assumptions

100000 USDT，95%含买费预算，只多单仓、无杠杆/加仓。4h收盘信号下一原生open±2bps，单边fee8bps，期末close盯市不强平；暖机不带仓或待执行信号。到期exit优先，后gap风险，再bar内stop优先ROI。已知2023-03-24停市按已核1h恢复open代理预声明处理，不回填12点成交；历史实际未触发此代理。完整契约见[冻结规格](specs/M0256-first-replay.json)。

## Evidence Map

[来源](specs/source-manifest.json) · [曝光](specs/exposure.json) · [独立校验](artifacts/20261003-first-replay/independent-validation.json) · [未来扰动](artifacts/20261003-first-replay/causality-validation.json) · [18文件精确恢复](artifacts/20261003-first-replay/local-recovery.json) · [Graph record](artifacts/20261003-first-replay/graph-record.json) · [结果hash](artifacts/20261003-first-replay/result-manifest.json)。

无结果后修正；4策略配置/1对照不是5个策略ID。当前历史窗口非干净OOS，旧搜索次数及历史运行模型未知。下一门槛为协调者独立取回与Graph小样本页面验收，不能凭文件存在称已上站或扩大批次。
