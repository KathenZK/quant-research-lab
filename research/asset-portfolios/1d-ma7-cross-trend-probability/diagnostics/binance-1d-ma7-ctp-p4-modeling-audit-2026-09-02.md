# BIN-1D-MA7-CTP P4 建模审计

状态：`explore / diagnostic-only / not promoted / not live-ready`。裁决：`FULL_B0_REMAINS_REFERENCE`。

## 冻结顺序

- P4 合同 SHA256：`4904a1a3f42c114910ec50c663edd828dd384c8fa4d0aa72c6af18abb290aeec`。
- factor group spec SHA256：`9e3662a078084998f5141fe00ea5d361fd2df1db6e9cac1ee4a7fa0ccfc5053d`。
- contract lock 状态：`FROZEN_BEFORE_P4_LABEL_READ`；`labels_read=false` 审计行数 `54137`。

## 数据与隔离

- 严格样本 `52563`；HYPE/2025+/TradFi `0/0/0`。
- 时间门禁 `< / == / >` 为 `0/52563/0`。
- 所有候选使用同一 D1/D2/D3 训练/验证行；asset holdout 训练排除目标资产组。

## 模型与校准

- 所有候选为 pooled Logistic Regression，训练折拟合中位数、one-hot 和 StandardScaler；没有 long/short 独立头。
- D1 校准保持 raw；D2 只用 D1 OOF；D3 只用 D1-D2 OOF；raw 与 forward-calibrated 概率分列保存。
- paired bootstrap 使用 fold 内 28 日 UTC 日期块，同 draw hash：`91d5d7083dfad0fc2e721ed63b8278ad5ed2574e87000ecacf2bbc3414f6fac5`。

## 禁止产物

- 未生成 HYPE reveal、2025+ 预测、策略仓位、账户权益、Sharpe、live spec、runner handoff 或交易路径 HTML。
