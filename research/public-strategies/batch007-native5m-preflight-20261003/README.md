---
research_classification: diagnostic_topic
---
# Batch007 原生5m输入恢复交接

本来源QA支持M0298/M0304的dot后续研究及root独占M0315；不计策略执行、严格复现或备份完成。个人非生产诊断，原始marketdata不入Git。2023年3月旧输入缺口/零量/非标准close_time失败完整保留，没有豁免或修bar。

固定Binance BTCUSDT spot原生5m，输入2023-12-01至2025-01-01 exclusive，共114336行；预热31天，评估2024共105408行。窗口按数据可用性事前选择，非OOS，不能直接比较旧两年总收益。PIT、历史finality、实盘流动性未知，DIAGNOSTIC_ONLY/untrusted。每ID开始历史运行前仍须协议、参数、代码、数据、依赖冻结及曝光。

## 固定身份和许可

- 输入规范CSV：31428289B，SHA256 `91e5bb0ba80ba2b70c5d6a5924c590459b0ffbe3e5955ba177abc981fb2a0af2`。
- 原完整manifest：`fb84e080d97ed85ec92227bc43b9468de331b3399e6b8254dba4afa7ccc8d058`；该原文件未发布。
- [expected-manifest](specs/expected-manifest.json)为保留全部compare_expected字段、13月×ZIP/CHECKSUM/CSV共39对象哈希的兼容派生清单，SHA256 `c7ec9966dbebde94fe65538542b77c3e40a09216513bd7054c204ae67e502102`。已去HTTP请求标识、主机盘信息等，不冒充原manifest字节，也不是缩减成不兼容的light对象。
- [builder](scripts/builder_5m_calendar2024.py)原字节：`e217666105d2a454b61bb93d4306f2c91af9d6356182baaf57d145645556f182`。
- [独立verifier](scripts/verify_raw_rebuild.py)原字节：`4972fedfbe54517423c94d834efda557a99a2667ddd067be31acc5ed5927f746`。
- Python3.12.14、标准库，无第三方依赖。来源字段与许可URL/hash见expected-manifest；适用Binance Vision Dataset Terms和CC BY-NC-SA4，个人非生产使用已审，禁止自动扩大商用/实盘/分发权限。

## dot精确恢复命令

以下从仓库根执行，目标目录及其.partial必须不存在；这会最多发送26个官方GET。保持至少5GiB余量。仅允许原data.binance.vision路径；任何403/451、重定向或QA失败立即停止，不重试、不换源、不代理绕过，不清理旧失败证据。

```bash
python3 research/public-strategies/batch007-native5m-preflight-20261003/scripts/builder_5m_calendar2024.py --timeframe 5m --target /tmp/batch007-native5m-restore-v1/snapshot --expected-manifest research/public-strategies/batch007-native5m-preflight-20261003/specs/expected-manifest.json --terms-reviewed
python3 research/public-strategies/batch007-native5m-preflight-20261003/scripts/verify_raw_rebuild.py /tmp/batch007-native5m-restore-v1/snapshot
```

--terms-reviewed表示本次已审许可范围，不绕过未来授权或服务限制。第一命令成功才执行第二命令。builder会核39源对象和规范输入hash；verifier不发网络请求，另在snapshot父目录独占写independent-rebuilt-native12.csv与independent-rebuild.json，已有则拒绝覆盖。恢复后使用snapshot/BTCUSDT-5m-202312-202412-native12.csv，各执行者另验其hash再消费。

## 本次已实际证明的范围

原抓取26GET全200；13月完整原QA无放宽。已在独立本地目录复制并验39个既有源文件，使用这里复制出的verifier重新构造31428289B输入，逐字节一致；复制出的builder.compare_expected对原manifest与本派生expected实际通过。见[安全回执](specs/local-validation-receipt.json)。此次交接验证网络GET=0，不称网络回抓、dot恢复成功或异地备份；dot须完成自己的真实恢复并报告失败。

[窗口合同](specs/window-contract.json) · [QA摘要](specs/independent-qa-summary.json) · [决策记录](decision-log.md)。无原始行情、网页全文、LibraryID、凭证或私人批注。
