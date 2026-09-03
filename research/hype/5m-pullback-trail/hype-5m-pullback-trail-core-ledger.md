# HYPE-5M-PBTR Core Ledger

## Family Identity

- 完整家族名：`HYPE-5M-Pullback-Trail`
- 别名：`HYPE-5M-PBTR`
- 市场：Binance USD-M `HYPEUSDT` 永续，`5m`
- 机制：趋势背景 → EMA21 回踩/恢复 → next-open → 固定 ATR bracket/timeout；旧版本曾使用 min-hold + trailing。
- 边界：不是 15m EMA-TB 或 EMA-X；本家族版本号只在此目录有效。

## Current State

- 当前版本：`HYPE-5M-PBTR-V6.2.1`。
- 状态：`live / tiny-live-pilot`，并行保留独立 `dry-run`；证据缺失不改变既有用户授权。
- 授权复核截至 `2026-12-24T00:00:00Z`（quant-runner 提交 `a5a3b2a` 将 `hype-pullback-live.approval_expires_at` 自 `2026-09-24` 续期）；资金边界为专用子账户余额，禁止未记录增资。
- 已通过 research/runtime signal parity；真实成交生命周期、保护单、重启恢复与滑点仍阻塞 production sizing。
- `hype-pullback-live` 于 2026-08-19 起 `strategy_health.status=halted`，live 服务仍 active；待用户决定重启 / 修正最小名义值 / 退出 pilot。见 [halted incident](runner-tracking/hype-5m-pbtr-live-halted-incident-2026-09-03.md)。
- 实际配置、服务和运行账本只以 quant-runner 为准；并行 dry-run 不是状态降级。

## Version Rules

- V1/V2 是旧 trailing 基线；V2.1.x 为参数清理/过滤变体。
- V3.x 为移除 final HTF 后的高频旧机制；V4 是其样本内组合，均被 strict fill 审计否决。
- V5.x 是 executable-first 修复批次，未形成交接版本。
- V6 是固定 bracket 新机制；sizing/exit/HTF 小改用 V6.x，核心机制改变才升 V7。
- 带小数点版本文件名用 `v6-2-1`，不得压成 `v621`。

## Version Table

| Version | Status | Role / Core Idea | Key Frozen Metrics | Evidence | Decision |
| --- | --- | --- | --- | --- | --- |
| `V1` | historical / not live-ready | R05732 旧 trailing 基线 | strict PF `0.637`、return `-87.29%` | [audit](diagnostics/hype-5m-pbtr-v1-strict-live-audit-2026-06-27.md) | 不可回退 |
| `V2` | research observation | V1 同步微调 | 旧口径高收益、strict 假设未修复 | [archive](notes/hype-5m-pbtr-v1-v6-historical-archive-2026-08-06.md) | 历史观察 |
| `V2.1-clean` | simplified observation | V2 干净等价表达 | 与 V2 基本等价 | [archive](notes/hype-5m-pbtr-v1-v6-historical-archive-2026-08-06.md) | 仅解释基线 |
| `V2.1A` | historical monitor / not live-ready | 放开 RSI | strict PF `0.54` | [audit](diagnostics/hype-5m-pbtr-v21a-live-realistic-audit-2026-06-24.md) | 不扩仓 |
| `V2.1B/C` | research observations | 去 ROC / 提 HTF / ADX14 | 不改变 strict 失败 | [archive](notes/hype-5m-pbtr-v1-v6-historical-archive-2026-08-06.md) | 归档 |
| `V3` | historical candidate | 去 final HTF 的高频版 | 旧口径 9108 笔；执行敏感 | [V3 audit](diagnostics/hype-5m-pbtr-v3-ablation-audit-2026-06-24.md) | 不 promotion |
| `V3.1` | historical candidate | min-hold `6→9` | 旧口径 7263 笔、DD 扩大 | [diagnostic](diagnostics/hype-5m-pbtr-v31-min-hold-9-2026-06-24.md) | 归档 |
| `V3.2` | historical candidate | 清理入场过滤 | 旧口径 8025 笔 | [diagnostic](diagnostics/hype-5m-pbtr-v32-clean-entry-filters-2026-06-24.md) | 归档 |
| `V3.3` | archived / not live-ready | 最小 min-hold + trailing | strict PF `0.58` | [diagnostic](diagnostics/hype-5m-pbtr-v3-3-minimal-2026-06-24.md) | 不交接 |
| `V3.3.1` | historical / not live-ready | stop-arm retry overlay | 乐观 PF `0.580`、最差归零 | [retry audit](diagnostics/hype-5m-pbtr-v33-retry-arm-2026-06-26.md) | 可审计但无期望 |
| `V4` | registered / not promoted | V3.3 样本内增强 | strict 依赖未解 | [audit](diagnostics/hype-5m-pbtr-v4-live-viability-audit-2026-06-24.md) | 禁止 dry-run |
| `V6` | registered / not promoted | EMA21/55 long + TP3/SL7/tx36 | 147 笔、PF `1.15`、DD `-11.28%`、OOS PF `1.45` | [search](diagnostics/hype-5m-pbtr-v6-live-executable-search-2026-06-25.md) | paper 候选 |
| `V6.1` | registered sizing observation / not promoted | TP2.5/SL7/3x | `+408.95%`、PF `1.773`、DD `-25.63%` | [sizing](diagnostics/hype-5m-pbtr-v6-tp25-sizing-2026-06-27.md) | sizing 风险高 |
| `V6.2` | registered / not promoted / not live-ready | V6.1 long + short rank2，单仓 | `+833.71%`、PF `1.771`、DD `-22.38%`；short OOS 5 笔 | [ablation](ablations/hype-5m-pbtr-v6-2-full-parameter-ablation-2026-06-28.md) | 仅小额验证 |
| `V6.2.1` | live / tiny-live-pilot / forward-test required | V6.2 + long HTF `>=0` | `+1022.25%`、PF `1.804`、DD `-22.35%`；short OOS 5 笔 | [audit](diagnostics/hype-5m-pbtr-v6-2-1-live-feasibility-audit-2026-06-30.md) · [tracking](runner-tracking/hype-5m-pbtr-runner-2026-07-30.md) | tiny pilot，非 production sizing |

## Shared Assumptions

- 数据：标准 HYPEUSDT `5m` 数据湖，约 `2025-05-30T10:30Z` 至 `2026-06-25T05:50Z`。
- 成本：fee `4.1466 bps/成交额`、开仓滑点 `10.73 bps`、平仓 `-2.64 bps`；版本比较以实盘成本诊断为准。
- 执行：闭合 K、next-open、单仓、stop-first；V6 起入场即 bracket，不使用旧 crossed/stale stop fill。
- 仓位：研究基线 1x；V6.1+ 的 3x 只属冻结观察，live 风险由专用子账户边界控制。

## Evidence Map

- 历史归档：[V1–V6 历史研究](notes/hype-5m-pbtr-v1-v6-historical-archive-2026-08-06.md)
- 规格：[specs/](specs/) · [live-specs/](live-specs/)
- 诊断与消融：[diagnostics/](diagnostics/) · [ablations/](ablations/)
- runner：[runner-tracking/README.md](runner-tracking/README.md) · 决策：[decision-log.md](decision-log.md)
- 脚本与产物：[scripts/README.md](scripts/README.md) · [artifacts/README.md](artifacts/README.md)
