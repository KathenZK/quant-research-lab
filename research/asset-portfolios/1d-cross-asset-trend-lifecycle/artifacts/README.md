# BIN-1D-CATL Artifacts

本目录保存 `Binance-1D-Cross-Asset-Trend-Lifecycle` 的 P0 可审计产物。P0 只做数据集与标签诊断，不训练模型、不生成交易策略。

## P0 Dataset and Label Atlas

- [p0_asset_day_feature_panel/](p0_asset_day_feature_panel/)：按 `asset_slug_partition/year` 分区的 Asset-Day Feature Panel；每行只含评估日收盘前可知字段。
- [p0_directional_landmark_panel/](p0_directional_landmark_panel/)：按 `asset_slug_partition/year/side_partition` 分区的 Directional Landmark Panel；每个 asset-day 生成 long/short 两行。
- [binance_1d_catl_p0_field_dictionary.md](binance_1d_catl_p0_field_dictionary.md)：标签定义与字段字典。
- [binance_1d_catl_p0_summary.json](binance_1d_catl_p0_summary.json)：P0 summary 与结构化诊断。
- [binance_1d_catl_p0_manifest.json](binance_1d_catl_p0_manifest.json)：脚本、合同、报告、HTML 与 panel 分区文件的 SHA256 manifest。
- [binance_1d_catl_p0_label_quality_atlas.html](binance_1d_catl_p0_label_quality_atlas.html)：自包含标签质量检查 HTML；不是交易策略，没有使用冻结验证期。
- [_catl_p0_hourly_from_15m.parquet](_catl_p0_hourly_from_15m.parquet)：由 normalized `15m` 重聚合的 P0 `1h` 路径审计产物；不作为策略信号或 runner 输入。

## P0R Modeling Input Repair

- [p0r_donor_directional_modeling_panel/](p0r_donor_directional_modeling_panel/)：物理排除 `HYPE/USDT:USDT` 的 donor-only 方向建模面板；按 `year/side_partition` 分区。
- [binance_1d_catl_p0r_feature_blocks.json](binance_1d_catl_p0r_feature_blocks.json)：P1 唯一允许的特征清单、类别字段、标签字段与禁止字段。
- [binance_1d_catl_p0r_summary.json](binance_1d_catl_p0r_summary.json)：修复后样本、资格排除和逐方向标签审计；不含 HYPE 标签表现。
- [binance_1d_catl_p0r_manifest.json](binance_1d_catl_p0r_manifest.json)：P0 输入血缘与 P0R 产物 SHA256。

## P1 Donor-Only Walk-Forward Modeling

- [binance_1d_catl_p1_contract_lock.json](binance_1d_catl_p1_contract_lock.json)：读取分折标签率前冻结的 P1 合同 SHA256。
- [binance_1d_catl_p1_preterminal_lock.json](binance_1d_catl_p1_preterminal_lock.json)：读取 2025+ donor terminal 标签前锁定的模型、特征、轮数、校准与裁决规则。
- [binance_1d_catl_p1_oof_predictions.parquet](binance_1d_catl_p1_oof_predictions.parquet)：D1-D3 donor OOF raw/calibrated 与 baseline 概率；HYPE 0 行。
- [binance_1d_catl_p1_terminal_predictions.parquet](binance_1d_catl_p1_terminal_predictions.parquet)：2025+ donor terminal 一次性 OOS 概率与排序诊断字段；HYPE 0 行。
- [binance_1d_catl_p1_fold_metrics.parquet](binance_1d_catl_p1_fold_metrics.parquet)：参数/特征选择、raw/calibrated、十分位、分层、non-overlap、asset-balanced、leave-group 与 bootstrap 指标。
- [binance_1d_catl_p1_model_card.json](binance_1d_catl_p1_model_card.json)：两个目标的 donor-only 模型身份、训练截止、特征哈希、固定参数和禁止用途。
- [binance_1d_catl_p1_summary.json](binance_1d_catl_p1_summary.json)：Entry/Continuation 裁决、开发期、terminal、稳定性及 HYPE 隔离汇总。
- [binance_1d_catl_p1_manifest.json](binance_1d_catl_p1_manifest.json)：P1 合同、脚本、测试、报告、模型卡与核心 artifacts 的 SHA256。
