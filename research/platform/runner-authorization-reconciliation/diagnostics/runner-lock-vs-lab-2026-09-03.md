# Runner lock 与 Lab 主状态对账（2026-09-03）

- 对账锚点：quant-runner HEAD `a5a3b2a`（`Disable archived AS6S V6 dry-run instances and renew pilot/parity expiries.`）
- Lock：`configs/active-strategy.lock.json` schema `2.0`，`authority=quant-runner`
- 超期天数按 `2026-09-03` 相对家族最新 `runner-tracking/` Markdown 日期计算
- Glossary：`mode=dry_run` 且 `enabled_allowed=true` 即为 Lab `dry-run` 主状态
- Lab 只记录用户已执行事实，不推断启停

## 到期项（已续期至 2026-12-24）

| 实例 | 字段 | 原到期 | 新到期（`a5a3b2a`） |
| --- | --- | --- | --- |
| `hype-pullback-live` | `approval_expires_at` | `2026-09-24T00:00:00Z` | `2026-12-24T00:00:00Z` |
| `hype-mii-dry-run` | `parity_grandfather_until` | `2026-09-24T00:00:00Z` | `2026-12-24T00:00:00Z` |
| `hype-ema-x-dry-run` | `parity_grandfather_until` | `2026-09-24T00:00:00Z` | `2026-12-24T00:00:00Z` |
| `hype-candle-count-v35-dry-run` | `parity_grandfather_until` | `2026-09-24T00:00:00Z` | `2026-12-24T00:00:00Z` |

到期前须补标准 parity JSON（`conclusion=PASS`），否则 runner CI 将拒绝对应 `enabled`。tiny-live-pilot 窗口只延长授权复核日，不扩大 sizing。

## 对账表

| instance_id | strategy_id | mode | approval_level | enabled_allowed | parity_status | 到期日 | Lab 家族 | Lab ledger 主状态 | Lab live-spec main_status | 最新 runner-tracking | 是否一致 | 动作 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `hype-pullback-dry-run` | `HYPE-5M-PBTR-V6.2.1` | `dry_run` | `dry_run` | `true` | `PASS` | — | `HYPE-5M-PBTR` | `live / tiny-live-pilot`（并行 dry-run） | `live` | `2026-09-03` / 0 天 | 是（并行 dry-run 合法） | 无 |
| `hype-pullback-live` | `HYPE-5M-PBTR-V6.2.1` | `live` | `tiny_live_pilot` | `true` | `PASS` | `approval_expires_at` `2026-12-24` | `HYPE-5M-PBTR` | `live / tiny-live-pilot` | `live` | `2026-09-03` / 0 天 | 主状态是；实例 `halted` 待决 | 记录续期；incident 待用户决定 |
| `hype-mii-dry-run` | `HYPE-15M-MII-V1.4A` | `dry_run` | `dry_run` | `true` | `PENDING` | `parity_grandfather_until` `2026-12-24` | `HYPE-15M-MII` | `dry-run / not live-ready` | `dry-run` | `2026-07-10` / 55 天 | 主状态是；parity 仍 PENDING | 记录 grandfather 续期 |
| `hype-mii-live` | `HYPE-15M-MII-V1.4A` | `live` | `none` | `false` | `PENDING` | — | `HYPE-15M-MII` | `dry-run / not live-ready` | `dry-run` | `2026-07-10` / 55 天 | 是（live 未授权） | 无 |
| `hype-ema-x-dry-run` | `HYPE-EMA-X-V18` | `dry_run` | `dry_run` | `true` | `PENDING` | `parity_grandfather_until` `2026-12-24` | `HYPE-EMA-X` | `dry-run / forward-test required` | `dry-run` | `2026-07-30` / 35 天 | 主状态是；parity 仍 PENDING | 记录 grandfather 续期 |
| `hype-ema-x-live` | `HYPE-EMA-X-V18` | `live` | `none` | `false` | `PENDING` | — | `HYPE-EMA-X` | `dry-run / forward-test required` | `dry-run` | `2026-07-30` / 35 天 | 是（live 未授权） | 无 |
| `hype-candle-count-v35-dry-run` | `HYPE-CANDLE-COUNT-V35` | `dry_run` | `dry_run` | `true` | `PENDING` | `parity_grandfather_until` `2026-12-24` | `HYPE-CC` | `dry-run / forward-test required` | `dry-run` | `2026-07-10` / 55 天 | 主状态是；parity 仍 PENDING | 记录 grandfather 续期 |
| `hype-tb-mii-ens-dry-run` | `HYPE-15M-TB-MII-ENS-V2` | `dry_run` | `dry_run` | `true` | `PASS` | — | `HYPE-15M-TB-MII-ENS` | `dry-run / not live-ready` | `dry-run` | `2026-07-14` / 51 天 | 主状态是；ledger 仍记规范 JSON 缺失 | 只入表，不改该家族文档 |
| `hype-tb-mii-ens-live` | `HYPE-15M-TB-MII-ENS-V2` | `live` | `none` | `false` | `PASS` | — | `HYPE-15M-TB-MII-ENS` | `dry-run / not live-ready` | `dry-run` | `2026-07-14` / 51 天 | 是（live 未授权） | 只入表，不改该家族文档 |
| `hype-ema-tb-v35-1-dry-run` | `HYPE-EMA-TB-V35.1` | `dry_run` | `dry_run` | `true` | `PASS` | — | `HYPE-EMA-TB` | `dry-run / not live-ready` | `dry-run` | `2026-08-17` / 17 天 | 对齐后是 | 本次将 Lab 从 `registered` 迁为 `dry-run` |
| `hype-1d-ma7-abt-v7-1-dry-run` | `HYPE-1D-MA7-ABT-V7.1` | `dry_run` | `dry_run` | `true` | `PASS` | — | `HYPE-1D-MA7-ABT` | `dry-run / not live-ready` | `dry-run` | `2026-08-13` / 21 天 | 对齐后是 | 本次将 Lab 从 `live spec`/`registered` 迁为 `dry-run` |
| `hype-1d-ma7-abt-v7-1-live` | `HYPE-1D-MA7-ABT-V7.1` | `live` | `none` | `false` | `PASS` | — | `HYPE-1D-MA7-ABT` | `dry-run / not live-ready` | `dry-run` | `2026-08-13` / 21 天 | 是（live 未授权） | 无 |
| `six-asset-ensemble-dry-run` | `BIN-1H-AR-MAE-V1` | `dry_run` | `dry_run` | `true` | `PASS` | — | `BIN-1H-AR-MAE` | `dry-run / not live-ready` | `dry-run` | `2026-07-11` / 54 天 | 是 | 只入表，不改该家族文档 |
| `bin-15m-as6s-v6-mark-np-dry-run` | `BIN-15M-AS6S-V6-NP` | `dry_run` | `none` | `false` | `PASS` | — | `BIN-15M-AS6S` | `archived` | `dry-run`（`superseded`） | `2026-09-03` / 0 天 | 家族 `archived` 与 `enabled_allowed=false` 一致；superseded spec 保留历史 `dry-run` | 记录用户停止 |
| `bin-15m-as6s-v6-mark-preemptive-dry-run` | `BIN-15M-AS6S-V6-SBP` | `dry_run` | `none` | `false` | `PASS` | — | `BIN-15M-AS6S` | `archived` | `dry-run`（`superseded`） | `2026-09-03` / 0 天 | 同上 | 记录用户停止 |

## 服务器观察（只记录，不动作）

- `hype-pullback-live`：`strategy_health.status=halted`，自 `2026-08-19T21:31Z` 无新事件。
- live 服务本身 `active`，`NRestarts=0`。
- 用户尚未决定：重启 / 修正最小名义值 / 退出 pilot。
- 来源：服务器 `platform.sqlite3` events 表只读查询（用户转述）；Lab 未改 runner。

## 本次 Lab 文档动作摘要

1. 本家族建档并对账。
2. `HYPE-EMA-TB-V35.1`、`HYPE-1D-MA7-ABT-V7.1` 主状态迁为 `dry-run / not live-ready`。
3. `BIN-15M-AS6S` 记录 V6 双实例停止；家族保持 `archived`。
4. `HYPE-5M-PBTR-V6.2.1` 记录 tiny-live-pilot 续期与 live halted 待决。
5. MII / EMA-X / CC 各记一条 parity grandfather 续期。
6. TB-MII-ENS、AR-MAE 只入表。
