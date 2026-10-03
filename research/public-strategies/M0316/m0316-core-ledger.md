# M0316 家族主账

- 固定身份：PUBLIC-M0316-HLHB；原catalog M0316；run M0316-20261003-first-replay；variant M0316-BTCUSDT-4H-HLHB-LIMIT-20261003
- 当前状态：TESTED_HYPOTHESIS_ONLY，未晋升，strict0；代码重放事实不等于策略通过
- 已冻结规格 SHA fc960036072e98f4105ed955abd1abcedc9b0ad37e47ca7b881bf85967cb2289
- 输入 SHA 9f5cb39c1426ec91098bb8a1b1f0c926b80760e66fe452d6b0c0aa55429d126c；DIAGNOSTIC_ONLY/trusted=false
- 核心发现：base -10.6117%/MDD36.7327%；四case均负。买持+441.8735%；成本敏感性非单调由fee-aware风险路径变化引起
- 版本：20261003 first replay；1策略配置族，4预设成本/延迟执行case+1控制；新增调参搜索0；历史搜索未知
- [报告](diagnostics/M0316-20261003.md) · [结果](artifacts/results/summary.json) · [独立复算](artifacts/independent-real-result-audit.json) · [恢复](artifacts/local-recovery.json)
- 重放身份与原参数固定；任何未来规则变化须新版本，不能覆盖此证据。无原作者runtime/universe/成交流动性保证
- 待协调者C3远端保存与实际回读；此主账不宣称已发布或生产交接
