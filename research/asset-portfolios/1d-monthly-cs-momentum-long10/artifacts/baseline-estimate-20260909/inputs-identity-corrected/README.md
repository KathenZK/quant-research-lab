# 已确认身份错误的独立输入修正版

状态：`EXPLORE_UNTRUSTED_BASELINE_IDENTITY_INPUTS_CORRECTED`。本目录另存修复后的 76 月、760 条持仓及完整月初执行参考表，原 `../inputs/` 和原价格账不变；本脚本没有计算新的账户收益。

修复先冻结于 `identity-correction.json`，仅将两个已由官方公告确认的形成身份错误按**原有排序**补位：

| 持有月 | 错误形成标的 | 原排序下一个合资格标的 | 原排名 | 入场参考价 | 次月退出参考价 |
| --- | --- | --- | ---: | ---: | ---: |
| 2025-05 | AERGO：旧期货终止后占位值跨新上线合约 | LAYER | 12 | 3.0443 | 0.7735 |
| 2026-01 | LIT：旧 Litentry 与新 Lighter 跨资产 | Q | 11 | 0.016639 | 0.018295 |

LAYER 排名之前的 ALPACA 已因官方终止限制被原规则排除，POPCAT 已在原十只中；未使用持有期收益选择替代。其余 **758 条持仓逐列与原输入相同**。价格均来自原治理返回帧的月初 00:15 open，活动有效性仅读取此前已闭合的 00:00–00:15 bar；四个参考端点及前一根活动校验都通过，无需新请求交易端点。

## 新增形成连续性核验

两条请求先写入 `formation-requests-frozen.json`。同次运行重新验证 bundle v2 的全组件 pin，完成覆盖 2025-03-31 23:45 至 2026-01-01 00:00 UTC 的严格全市场 catalog 审计，然后仅对同一已验证文件清单做两次有界读取，各自执行价格帧与连续段核验。状态仍是 `EXPLORATORY_SCOPED_EQUIVALENT_AUDIT`，没有冒称 `require_research_startup()` PASS。

| 标的/形成窗口（UTC） | 预期与实际 15m bar | 缺失 | 不合资格 | 连续有效段 |
| --- | ---: | ---: | ---: | ---: |
| LAYER：2025-03-31 23:45 至 2025-05-01 00:00（不含后端） | 2,881 / 2,881 | 0 | 0 | 1 |
| Q：2025-11-30 23:45 至 2026-01-01 00:00（不含后端） | 2,977 / 2,977 | 0 | 0 | 1 |

这两段未观察到旧标的那种终止、零成交占位或重开边界，起止端点均有效；这不等于全池 PIT 身份证明。公开官方说明中 LAYER 为 Solayer、期货自 2025-02-11 15:45 UTC 上线；Q 为 Quack AI、自 2025-09-02 07:30 UTC 上线，都早于本次形成期。[币安官方 LAYER 上线说明](https://www.binance.com/en/square/post/20167436634409)、[币安官方 Q 上线公告](https://www.binance.com/es-LA/support/announcement/detail/e1826e566e5b454ba7b439082bfbbc4f)。未将一般性检索未发现终止公告当作全历史不存在事件的证明。

## 消费接口与净额交易

- `holdings.parquet`：与父输入相同字段；hash `2765cc3fade0b8c571871c5e2bfff88ad6e5bc65198a5fff35e261afa6df61e4`。
- `monthly_execution_prices.parquet` 与 `execution.parquet`：内容相同，hash 均为 `4ab5bd31b6c0e51b205d983c868574cb3eab18e1b149043c6b2d305ee48ece1d`。已按修复后的每月旧持仓与新名单重新生成并集，原价格保留；同一时间/标的不重复。
- `summary.json`：兼容 `months`、`holdings`、`missing_nonterminal_exit_prices`、`files`；hash `bbd466ffa7029c586e67925cf50cc7d97634a60c3aa8172aec25f649b764fc9f`。父日价与输入摘要用相对路径及 hash 引用。
- `replacements.json`：两个资金费窗口；其余 758 窗口不变。

注意原 LAYER 持仓是 **2025 年 4 月**，修复后 5 月仍持有，因此 2025-05-01 00:15 的 LAYER 行同时 `held_old=true`、`selected_new=true`，需要净额调仓。6 月 1 日为退出，不应在 5 月强行先全平再买入。全部持仓 entry 与非终止 exit 均逐行匹配执行表，非终止退出缺口为 0。

本次修复不修改原 ADV、覆盖率、成本、换仓时刻、五个既有终止限制或其他筛选参数。仍保留全池 PIT、其他 30 条短零成交形成段以及终止价格/资金费估算等已有边界；不能把修复两处已确认错误等同于策略严格验证或实盘批准。
