# M2903 决策记录

- 2026-10-03：root在5e92b97冻结batch020规则并分配实现。本家族严格照事件cross而非state；source机器人门禁保留为独立层。
- 本阶段只人工合成，未读取真实价格为数值、未计算历史特征/账户。真实输入仅许可hash校验。
- 复用shared cash v1不改；共享input/view由m0217负责，消费者等待独审pin后才冻C0。不得把手工slice测试当已验证正式适配层。
- 合成测试涵盖独立Fraction逐运算round EMA、等值/初始flat、因果、挂单取消、费内全仓及独立账户。完整合成账本私有，不计研究试验。

- 门禁修订v2：保留fc93d03及pre-C0-draft-v1原收据，加入读取输入前5GiB+64MiB预算、严格相对pin/无符号链接/精确必备文件集合/无重复JSONkey及int非bool放行计数；31项合成负测通过。正式C0仍待适配层独审远端pin。

- 门禁v3：m0288人工check_gate反例证实旧source_commit列表/非hex被接受；保留失败收据。现拒绝非str、非lowerhex40，并校验相关SHA64/本地审查receipt路径类型与symlink/traversal；实际check_gate人工metadata30项通过。无历史。

- 适配层集成：merge43becf3c而非复制源；其带入的root上游治理/M1266文件未自行编辑。831完整人工EMA投影762会计视图、独立2924NAV/96月/1762fill通过；真实仅bytes/schemaQA。新进程33文件逐字节一致（含manifest）。正式C0另冻，禁止历史。

- C0-v1冻结：实际source commit531a0d1e，必备文件集合逐文件核Git blob等于工作盘bytes；exact-C0审查待m0288，root未授予历史。
