# V3全参数消融与邻域检查，2026-09-24

唯一正式结果入口：[交互HTML](html/index.html) · [中文报告](../../diagnostics/v3-parameter-stability-results-20260924.md)。仅冻结HYPE数据，未全市场扩跑，未更新到研究日，未晋升策略版本。

121个不同参数配置：基线1、结构对照20、非基线单参数44、双参数新增组合24、联合32；分组重复成员不当额外账户。32联合向量因一项条件未影响交易有16种经济路径，不视为独立市场样本。

- `started.json`：回放前固定的全配置、代码SHA、范围与标签规则。
- `input.json`、`input_daily.parquet`、`input_hourly.parquet`：原冻结质量通过帧及来源指纹。
- `window.json`：统一自然就绪起点和原起点。
- `reference_original_start/`：原+544.76%的逐笔复现。
- `accounts/`：所有同起点完整账户；summary、交易、止损、机会、小时权益。
- `comparison.csv`、`parameter_stability.csv`、`trade_pairs.csv`、`calendar_periods.csv`：可独立复算的汇总。
- `audit.json`、`tests.json`、`html_audit.json`、`final_checks.json`：独立算术及输出核验。
- `registry_correction_verification.json`：登记表去重前110行均精确复现；只补齐原定不同联合向量。
- `source_manifest.json`、`source_snapshot/`：本轮引擎、消费脚本、审计、规格、报告与直接依赖；原始历史输入链仍按input.json的SHA核验。

上一草稿保存在同级`v3_parameter_stability_20260924_registry_draft/`，标记SUPERSEDED_REGISTRY_DEFECT，不能混用旧账户数量/联合数量标签。没有因结果更改参数范围。

约54 MiB，本地忽略、可再生，保留完整轨迹用于复核；没有添加大Git对象。复现需在独立输出位置运行，避免覆盖本目录。

费用每边0.1%+滑点0.04%；缺完整资金费。共121账户2,197笔、27,146止损、2,577,338权益点核验通过，23项测试通过，HTML离线脚本覆盖121方案和全部交易。未声称真实浏览器视觉布局通过。
