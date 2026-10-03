# M3710 家族主账

- 家族：M3710，BTCUSDT 现货原生日线 SMA20 状态目录假设。
- 来源层：HYPOTHESIS_FROM_CATALOG_NOT_SOURCE_VERIFIED；执行层：ADAPTED_EXECUTION_PROXY。
- 当前阶段：收益前代码与人工合成验证，等待精确 C0 历史门禁；历史策略配置实际运行 0、新对照 0、严格复现 0。
- 固定合同：batch020 commit `5e92b97a3f5d1c07d980516d0e06d8991d2024ac`；规则 SHA256 `e5200ca8aa62f787e32101702e2d638c0d37959b5ff6ff5f713058544156eb6d`。
- 输入：完整 831/100，账户 762/31，offset 69；真实输入本轮仅核字节及哈希。
- 代码：复用 catalog-daily-cash/v1；共享 input-view/v1 已经独审并取回精确远端 pin；独立家族代码验收和 root 历史放行仍分立。
- 拟运行：base/fee0/fee20/delay2 四配置；引用 M1258 已有 base 买持，不新增控制。
- 证据：[说明](M3710.md)、[协议](specs/protocol-v1.json)、[合成脚本](scripts/check_synthetic.py)、[门禁负测](scripts/check_gates.py)。
- 当前无真实策略结论；全局计数、索引、claims、公开展示与远端写入仅由 root 协调。
- 后续门禁：完整 C0 → 独立实际代码/人工合成验收 → root 精确 C0 放行 → 首次四配置 → 独立结果和恢复验收。

获准后新增的真实结果以独立结果附录保存；本准备阶段被冻结对象不得覆盖。
