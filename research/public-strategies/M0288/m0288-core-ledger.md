# PUBLIC-M0288-PATTERN 主账

## 家族身份

- 稳定原始编号：M0288；PatternRecognition，作者 @Mablue。
- 实例：Binance BTC/USDT 现货，日线，多头，1 倍，无借贷。
- 核心：TA-Lib 高浪线负值信号入场，原生 ROI、固定止损和移动止损退出。
- 4 个配置共享同一策略 ID；费用/延迟不是新策略或新增编号。

## 当前版本

| 版本 | 状态 | 核心证据 | 结论 |
| --- | --- | --- | --- |
| M0288-20261003-native-diagnostic-v1 | explore / not promoted / not live-ready | [冻结规格](specs/M0288-first-replay.json)、[结果](artifacts/20261003-first-replay/summary.json)、[恢复](artifacts/20261003-first-replay/recovery-validation.json) | HYPOTHESIS；基准收益180.61%，日MDD23.12%；落后买持441.55%，延迟后降至117.10% |

严格复现 0。源码可执行，源码阻塞 0；历史资产池、作者运行版本、原超参搜索窗口及真实日内执行仍缺失。未触及 runner、交易授权或实盘。

## 共同假设与证据

[数据与环境](specs/data-qa.json)、[依赖锁](specs/requirements.lock.txt)、[重建步骤](diagnostics/rebuild-20261003.md)。新研究显式采用 native spot1d DIAGNOSTIC_ONLY，不冒充标准永续合约数据组合、PIT 或 trusted 输入。95% 原生 stake、8bps 单边费用，滑点未模拟；增加费用和一天延迟为已冻结敏感性。作者原运行规则与本次实例化差异见[完整报告](diagnostics/M0288-20261003.md)。

后续只有取得历史作者环境/样本、可追溯细粒度行情，并预先登记新的未曝光检验窗口后，才讨论新的证据级别。既有证据保持冻结，不以新版本覆盖。
