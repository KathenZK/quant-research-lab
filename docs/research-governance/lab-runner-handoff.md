# Lab / Runner 交接与观察记录

仅在交接实现、核对运行表现或准备状态迁移时使用本文件。生产执行与实例授权在 quant-runner，Lab 保留研究证据和实现合同。

## 交接规格

- 文档放在家族 `live-specs/`，按 [模板](lab-live-spec-template.md) 与 [schema](schemas/lab-live-spec-frontmatter.schema.json) 写明身份、准确参数、数据/warmup、执行恢复、成本、TOML、证据和缺口。
- `runner_kind`、模块路径、字段和 TOML 对应当前实现。Lab 与 runner SPEC 双向链接；参数/模块变化同步两侧，未同步差异写入 decision log。
- 每个 `(strategy_id, runner_kind)` 只有一份 active Lab SPEC 与一份 active runner SPEC；旧版本标记 `superseded`。联合实现逐一映射 `implementations`。
- 引用的标准 parity 产物随版本管理保留，在干净 checkout 中可取得；缺失时保留缺口，不从报告文字编造或重建。
- 资金由子账户或 runner 管理时，规格链接相应资金边界即可；Lab 不生成 runner 授权 manifest 或 lock。

## 执行与运行证据

- 核验信号可得时点、下单/成交顺序、保护单与跳空、费用/滑点、仓位风控、重启恢复、缺失数据和紧急停止行为。具体测试取决于实现，不要求无关部件也套流程。
- 进入 dry-run 时建立家族 `runner-tracking/`。运行观察可通过 quant-runner `scripts/lab_sync/sync_to_lab.sh` 回流，按 `<family-id>-runner-<YYYY-MM-DD>.md` 保存来源、配置、观察窗口、交易、费用、偏差与结论。
- 线上开平仓对账保留信号/bar、预期与实际开平仓时间、方向、数量、成交/参考价、费用、滑点和可用事件 ID；缺失字段注明未验证，CSV/JSON 放入家族 `artifacts/`。
- 生成报告在来源、缺项、逐笔对账和差异复核完成前保持 DRAFT，不能作为已核验证据。复核可由人或 Agent 完成，记录依据与结果；取消“只能人审”的主体限制，不自动提升报告状态。
- live 准入需要无未解决重大偏差的线上对账，离线 parity 或 smoke 不能替代；其他要求见 [状态迁移](strategy-validation-gates.md)。主账链接影响决策的最新报告，decision log 记录状态决定。
- 实例启停、重启、模式和资金配置变化在用户授权范围内执行；研究报告的 keep/stop/adjust 建议本身不是操作授权。历史外部 runner 记录同样只作证据，不自动复制或迁移实例。
