# Binance 衍生 OHLCV 对账

日期：2026-09-02  
输入：accepted normalized 15m priority union v1；输出：`1h/4h/1d.from_15m.v1`。

## 15m 与已知 P0/P3

| 窗口 | 现场行数 | 现场 symbols | 已知行数 | 已知 symbols | Δ |
| --- | --- | --- | --- | --- | --- |
| P0 `< 2026-07-01` | 56,358,042 | 790 | 56,358,042 | 790 | 0 / 0 |
| P3 `< 2026-08-25` | 60,266,362 | 853 | 60,266,362 | 853 | 0 / 0 |

## 1d 与 P0 完整日

`binance.perp.ohlcv.1d.from_15m.v1` 在 `ts < 2026-07-01T00:00:00Z`：586,612 行 / 790 个合约，与 P0 完整日完全一致。

全历史 derived 1d 为 627,283 行 / 853 个合约，与 P3 家族面板行数一致。

## 公共日K缓存（月档优先）

| 指标 | 值 |
| --- | --- |
| 完整日键匹配 | 586,771 |
| 完整日 OHLC mismatch | 0 |
| 完整缓存独有键 | 0 |
| derived 多出的完整日 | 40,512（627,283 − 586,771，含缓存截止日期之后） |
| 全部缓存独有键 | 817（不完整日，衍生层正确丢弃） |

结论：旧缓存的完整日与新 canonical 1d 在键和 OHLC 上一致；缓存不是全量完整日集合。

## 六资产 15m→4h vs legacy 1h→4h

OHLC 在重叠时间戳上基本一致（close/high 全 0 mismatch）。覆盖上 derived 4h 明显更长；legacy 1h 只能覆盖较短窗口。`quote_volume` 大量 mismatch，因为 1h 成交额再求和 ≠ 15m 成交额直接求和。P0R-DATA 必须全程使用 15m 衍生数据，不能混用 legacy 1h 的 ADV。

逐字段表：[binance_4h_six_asset_15m_vs_1h_mismatch_2026-09-02.csv](../artifacts/binance_4h_six_asset_15m_vs_1h_mismatch_2026-09-02.csv)

## 新版 4h 覆盖（数据范围，不是策略裁决）

- 总 symbols：853
- ≥30 日：825
- ≥365 日：533
- 2020–2026 每年均 ≥50 个 symbols（2019 年只有 2 个）

判断：数据范围**可以支撑**全市场历史 `P0R-DATA`。这不是策略能否通过的结论。

年度表：[binance_4h_from_15m_year_coverage_2026-09-02.csv](../artifacts/binance_4h_from_15m_year_coverage_2026-09-02.csv)
机器结果：[binance_ohlcv_reconciliation_2026-09-02.json](../artifacts/binance_ohlcv_reconciliation_2026-09-02.json)
