# BIN-1D-MA7-CER P0 实现审计

- 状态：`explore / diagnostic-only / not promoted / not live-ready`
- 全局裁决：`NO_EXPANSION_EDGE`
- 合同锁：`FROZEN_BEFORE_P0_EXPANSION_OUTPUT_READ`
- config sha256：`8e017a3ce60e809f8bb61dac01740d0bc4a12bfc9158e3f4da3daa87e8c66fd9`
- contract sha256：`c520e924462264a7f62a2b044093f711e5864916c12e3b1b3440417face54be9`
- manifest sha256：见 [`binance_1d_ma7_cer_p0_manifest.json`](../artifacts/binance_1d_ma7_cer_p0_manifest.json)

## 输入隔离

- HYPE 原始分区读取：`False`
- HYPE 行数：`0`
- HYPER 行数：`322`
- files_read 含 `hype_usdt_usdt`：`False`
- 未读取 P7 产物：`True`

## 冻结口径

- 主 outcome 无方向；未使用 P0R 方向 first-hit 成功标签。
- ATR 锚点只来自事件日 `atr_anchor`。
- 主 horizon 固定 5D。
- 无 ML、无权益曲线、无综合 Expansion Score。
- 图表为手写 SVG，不依赖 matplotlib。
- Event-time 数组按 T0 索引，不再二次加 offset。
- 日期匹配只对同时存在 Cross 与 non-cross 的日期加权。
- 2025+ 官方 identity 与 P5 哈希一致；另有 58 条 2025+ probe 不在 P5 验证集，已排除出官方样本。
- DuckDB 日K 为 `datetime64[us, UTC]`，day number 用 `Timedelta(days=1)` 换算，不用假定纳秒 `asi8`。
- same-asset MC 500 次与 exact expectation 绝对差 `0.00024` ATR，低于 0.02 容差。
- `entry_ref` / `atr_anchor` 与下一 UTC 日开盘及当日 `atr14` 错配均为 0。

运行命令：`/Users/ZK/OpenCode/quant-strategy-lab/.venv/bin/python research/asset-portfolios/1d-ma7-cross-expansion-regime/scripts/run_binance_1d_ma7_cer_p0_direction_agnostic_expansion_audit.py`
