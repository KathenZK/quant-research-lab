# BIN-1D-MA7-CTP P5 Weekly Causality Audit

- 裁决：`PASS_NO_WEEKLY_LOOKAHEAD`
- 周期定义：UTC Monday 00:00 至下一 Monday 00:00，仅 7 个完整日 K 组成的闭合周可用。
- As-of 规则：日线事件使用最近一个 `weekly_feature_known_at <= feature_known_at` 的完整闭合周。
- 事件行：99555
- 周线特征行：79509
- `weekly_feature_known_at < feature_known_at`：86136
- `weekly_feature_known_at == feature_known_at`：13419
- `weekly_feature_known_at > feature_known_at`：0
- 缺失周线 known-at 行：0
- 缺失处理：数值特征不删除 MA7 事件，由训练折中位数填充；`weekly_history_13w_complete` 保留 0/1 完整性标记。
