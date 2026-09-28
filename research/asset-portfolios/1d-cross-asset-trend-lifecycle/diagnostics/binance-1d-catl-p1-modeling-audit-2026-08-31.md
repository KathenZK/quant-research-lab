# BIN-1D-CATL-P1 建模审计

## 审计结论

`PASS / explore / diagnostic-only / not promoted / not live-ready`

P1 严格使用 P0R donor-only panel。所有模型/特征/轮数/校准选择在读取 2025+ donor terminal 标签前锁定；HYPE 全资产仍封存。

## 输入完整性

- P1 contract SHA256：`1c386235a52780824915e6030dfe5a0d0774afb265ce3cf6d552da6e5adf992b`。
- P0R manifest SHA256：`033e12bf77c5d67f4871845e3fc2650dfa26a09ca8f74983f379d84e388f93ef`。
- P0R feature spec SHA256：`c3fb333a597b90b613da7e4316233d31f2af081f4c4da5523fec75da69aba346`。
- P0R manifest 的 `21` 个 artifact 哈希全部匹配，panel 文件集合无额外分区。
- donor panel：`1,128,880` 行、`732` 资产；HYPE `0` 行；HYPER `806` 行。

## 时间与 terminal lock

- Pre-terminal lock SHA256：`9cbbe1c6c4f5c6f619511d2e8c760090c3a0526184a4ee29b77ec4ca17696da0`。
- D1/D2/D3 validation 固定为 2022/2023/2024；每折训练都执行目标专属 `label_end_ts < validation_start_ts` 精确 purge。
- Entry 与 continuation 均在 joint pre-terminal lock 落盘后才调用 terminal loader。
- terminal 重训只用 `label_end_ts < 2025-01-01`；2025+ 不参与模型、特征、参数、轮数或校准选择。

## 预处理与特征边界

- X 严格由 P0R `all_allowed_features` 派生；资产、方向、时间、价格、资格、标签、future、result、收益、MFE/MAE 均不进入 X。
- LightGBM 类别字典逐折只在训练集拟合；数值缺失走 LightGBM 原生 missing。
- Logistic baseline 的中位数、缺失指示、均值/标准差和 one-hot 字典逐折只在训练集拟合，未知类别为全零 one-hot。
- 同一 asset-day 的 long/short 由 UTC 日期边界共同切分；OOF 主键唯一。

## Bootstrap 与稳定性

- `entry`：28d paired bootstrap `1000` 次，共享 draw SHA `6252d561dbefd6d9127c7c6741031bc334d6958953e3bbef2b7770e759b66aae`；leave-group AUC median/min `0.5527/0.5490`。
- `continuation`：28d paired bootstrap `1000` 次，共享 draw SHA `c7e170865ff776439ccf8db04418b63b6227a6cb57015d00ae32bbebb66dfb48`；leave-group AUC median/min `0.5554/0.5462`。

## HYPE fail-closed 证明

- 精确禁止对象为 `HYPE/USDT:USDT`；输入检查、开发 loader、terminal loader、OOF、terminal predictions、summary/model card 均断言 0 行。
- `HYPER/USDT:USDT` 使用精确字符串区分并保留。
- 本轮没有 HYPE reveal，也没有 HYPE prediction artifact。

## 非策略证明

- 输出没有仓位、杠杆、组合回测、交易阈值、订单、权益曲线、runner、live spec、dry-run 或 live-ready artifact。
- 标签净收益只在概率十分位内报告均值/中位数，未累加或年化。

## 精确复现

```bash
cd /Users/ZK/OpenCode/quant-strategy-lab
uv run --extra ml python research/asset-portfolios/1d-cross-asset-trend-lifecycle/scripts/run_binance_1d_catl_p1_donor_walk_forward_modeling.py --run --force
uv run --extra ml pytest -q tests/test_binance_1d_catl_p1_donor_walk_forward_modeling.py tests/test_binance_1d_catl_p0_dataset_label_atlas.py tests/test_binance_1d_catl_p0r_modeling_input_repair.py
```
