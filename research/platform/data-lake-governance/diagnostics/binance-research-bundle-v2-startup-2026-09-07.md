# Binance 组合 v2 与研究启动交接验收

日期：2026-09-07。家族：`Binance-OHLCV-Data-Lake-Governance`。契约：[组合发布与启动契约](../specs/binance-v3-research-input-bundle-v2-2026-09-07.md)。唯一消费规范：[data-lake-spec 第 19 节](../../../../docs/data-lake-spec.md)。

## 已交付内容

- [固定组合 v2](../specs/binance-v3-research-input-bundle-v2.json) 绑定价格 15m V3、高周期 1h/4h/1d v2、费率 v2；SHA256 为 `d2a729d03be71d67aa9c5522fb242bbf010b6c64400233c27d9cb2406f567008`。五组全内容指纹已通过现场核对，未发布新价格或费率数据。
- [当前指针](../specs/current-research-inputs.json)、[请求示例](../specs/research-startup-price-example-v2.json)、AGENTS 和研究入口统一指向规范第 19 节。旧组合 v1 明确标为绑定费率 v1 的历史发布，不再充当当前组合。
- [启动 API](../../../../src/strategy_lab/data/research_bundle.py) 返回已验证帧及有效窗口 mask；[检查入口](../../../../scripts/governance/check_research_startup.py) 区分契约检查、物理内容检查、具体研究窗口检查。无数据湖契约检查已接入既有 preflight/CI；新 API 消费者仍须登记，不自动扩大冻结白名单。
- BTC 日线示例 `[2026-08-01,2026-09-05)` 真实读取通过：35 根闭合 K，7 根回看与 1 根未来长度得到 28 个有效窗口，缺 K/无效行均为 0；只获得价格诊断资格，不获得费率/PIT/策略资格。

## 最终验收记录

本层交付状态为 `BUNDLE_V2_STARTUP_DELIVERED`。机器证据：[acceptance.json](../artifacts/binance_research_bundle_v2_20260907/acceptance.json)、[测试详情](../artifacts/binance_research_bundle_v2_20260907/test_summary.json)、[旧输入保护](../artifacts/binance_research_bundle_v2_20260907/protection.json)。

| 检查 | 结果与资格边界 |
| --- | --- |
| 无本地数据的契约门禁 | `CONTRACT_ONLY_NOT_DATA_READY`；临时独立目录只复制清单和冻结读取器的测试通过 |
| 五组当前组合全内容指纹 | [最终物理检查](../artifacts/binance_research_bundle_v2_20260907/bundle_integrity_final.json) 通过，不替代研究范围检查 |
| 真实 BTC 价格启动 | [最终价格报告](../artifacts/binance_research_bundle_v2_20260907/price_startup_final.json) 通过，35 根 K / 28 个完整窗口；费率/PIT/策略资格保持 false |
| 现场负向检查 | [6 个拒绝案例](../artifacts/binance_research_bundle_v2_20260907/negative_checks.json)：缺身份证据、越截止、旧组合、错哈希、非 COIN 混入纯币范围，以及真实 9 月费率日历不足 |
| 定向回归 | 139 项数据/组合/文档测试通过；另 8 项消费者扫描单测通过（排除全仓现状断言）；共 147 项，新增文件和治理脚本 lint 通过 |
| 旧输入保护 | 对照此前结构审计，10 个已发布 derived 数据集的 manifest 与全部 Parquet 内容指纹未变；旧组合及指定冻结读取器、构建器、原费率契约未变。这不是重新扫描全部 raw/normalized |
| 仓库整体 preflight | **仍失败**，唯一失败步骤为消费者登记；其余步骤通过，组合相关及文档联合检查 80 项通过 |

现场费率负向案例只调用底层日历门禁，明确使用非正式测试标签，不伪造真实身份证据或声称完整净收益链通过。合成单测另验证身份证据、事件缺失/歧义、跨片段、缺 K/零成交与回看/未来窗口；合成净收益通过不能用于真实研究结论。

全仓未登记的 6 处来自其他研究脚本：CTP P6/P7/P7a/P7b、CER P0，以及 HYPE-CC maker-entry audit，完整路径见测试详情。去掉本轮新增启动 API 扫描标记后，错误集合相同；不是本轮新增标记引入的回归，也没有为通过检查而放宽白名单。旧消费者迁移不在本轮授权内，不能把本层交付称为“全仓治理已全绿”。

复核入口：[audit_binance_research_bundle_v2.py](../scripts/audit_binance_research_bundle_v2.py)。再次运行须用 `--output-dir` 指向本家族 `artifacts/` 内新的审计子目录，保留本次证据；[发布器](../scripts/publish_binance_research_bundle_v2.py) 对相同清单幂等，对不同内容拒绝覆盖。

## 保留的边界

总冻结截止仍是 `2026-09-05T15:45:00Z`（北京时间 23:45），不是发布日。高周期仅到各自最后完整桶；费率 v2 仍为 `PARTIAL_COVERAGE`。净收益模式要有独立复核身份文件及完整请求范围的费率日历证据，缺项中止，不填零或自动降级。

身份材料的事实真实性仍由研究方负责；启动器只核对文件哈希、复核声明及时间范围，不认证全市场 PIT。手续费、滑点、订单执行、跨缺口持仓和 OOS 门禁另行验证。全市场大窗口按标的读取，但返回帧和完整费率事件仍需要内存；本轮不是全仓消费者迁移或策略运行器。

同目录 Agent 可立即循入口发现；其他 checkout/worktree 必须完整同步代码与规格，并显式配置可访问的数据根。Git 忽略本地数据与大部分大产物。本次执行未主动提交或推送；没有重下载、改写旧数据或做清理。
