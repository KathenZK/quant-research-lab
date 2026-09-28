# BIN-1D-MA7-CTP P5 Modeling Audit

- 裁决：`NO_NEW_INCREMENT_B0_REMAINS_REFERENCE`
- 模型：pooled direction-aligned `LogisticRegression(penalty="l2", solver="lbfgs", max_iter=1000, random_state=20260901)`。
- 候选：六个预注册候选；无 LightGBM/XGBoost/RandomForest/ExtraTrees/神经网络、L1/ElasticNet、自动特征选择、超参搜索、多空独立模型或临时交互项。
- 训练/预处理隔离：D1-D3 使用训练折拟合填充、编码、Scaler 与模型；2025+ 没有参与训练、预处理、校准或阈值拟合。
- 最终外层验证：模型用全部严格 pre-2025 重训；Platt 校准器和 frozen threshold 仅来自 pre-2025 OOF。
- Bootstrap：开发期与 2025+ 分开使用 28 日 UTC 日期块、2000 次、固定种子 `20260901`；同一 period 内所有挑战者共享 draws，每次在完整重采样事件集上重新计算非线性指标。
- 2025+ 验证复用历史：['P1 已读取/观察 2025+ donor terminal history；P5 将其正式标记为 ITERATIVE_REUSED_VALIDATION_2025_PLUS。', 'P5 不使用 2025+ 训练模型、预处理器、校准器或阈值，只用于六个预注册候选的迭代验证比较。']
- Known TradFi：主统计排除，单独标记 `unsupported_tradfi_diagnostic`；排除事件 100。
- HYPE：原始 price 分区读取为 `false`，OOF/验证/指标均为 0 行；`HYPER/USDT:USDT` 保留。
