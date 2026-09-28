# 每周Top10：完整价格研究材料

本轮主结果在`terminal-complete/`，不是本目录首次失败的`summary.json`。

- [主报告](../../diagnostics/binance-1d-mcsm-weekly-top10-20260924.md)
- [固定规则](../../specs/binance-1d-mcsm-weekly-top10-20260924.md)及[终止补充](../../specs/binance-1d-mcsm-weekly-top10-terminal-amendment-20260924.md)
- [八账户结果](terminal-complete/summary.json)及[独立核账](terminal-complete/independent-audit.json)
- [318期每周名单和盈亏](terminal-complete/weekly-holdings-and-pnl.md)
- [73个月持仓、收益、盈亏](terminal-complete/monthly-holdings-and-pnl.md)及[逐年汇总](terminal-complete/yearly-results.md)
- [最终检查](terminal-complete/completion.json)及[测试与登记边界](terminal-complete/qa.json)

2020-06-01 00:15至2026-07-01 00:15 UTC，均从100,000 USDT开始；单边费0.10%+滑点0.04%、未含资金费、条件指数终止价下，每周Top10累计+64.51%、年化8.53%、最大回撤-97.42%；月Top10同期+925.13%、年化46.63%、回撤-95.43%。周频不采纳为实盘候选。

## 目录与保留链

1. 本目录原`plan.json`、`holding-windows.parquet`和B0/W7目录：首次运行。B0四条成功，W7四条因COCOS无效日线停止，不发布截断收益。原76个月、旧75个月基线复现见[baseline-reproductions.json](baseline-reproductions.json)。
2. `terminal-evidence/`：BZRX/KEEP公告、官方指数日档、CHECKSUM、60分钟窗口和请求回执。
3. `terminal-complete/terminal-evidence/`：一次性全持仓扫描后补COCOS/MEMEFI。COCOS60分钟、MEMEFI30分钟窗口均在下载和全期周收益前固定，未删除亏损币、未拼接改名后的币。
4. `terminal-complete/`：仅补实际终止时刻，名单/入场/仓位不改，完整8账户。每个账户含逐日/边界权益、调仓、终止、逐腿价格损益、逐月、逐期表。`summary.json`固定所有输入和输出哈希；`independent-audit.json`固定独立复核脚本及主结果；`completion.json`固定交付、测试和存储规模。

## 读表口径

- 月表按自然月00:00 UTC估值，首尾为实际00:15。月初换仓前15分钟仍可能持有上月旧币，因此“当月持有过”可能超过10个；周账户月内也会多次换币。完整当期十币名单见周表及原始持仓表。
- 周表收益为本次换仓后到下次换仓后，含下次换仓费用；第一期还含初始建仓成本，最后一期只有2天。期收益连乘等于全期结果。
- 价格利润、手续费、滑点是同一复利路径上的实际现金累计；报告成本栏以正数表示支出，净盈亏=价格盈亏−手续费−滑点，不是已运行的无费反事实。
- B0为月Top10；W7为周Top10；`4bp/8bp`是滑点，不是全部费用。`low/high`只为指定终止代理的条件敏感性，不是真实收益的上下界。
- 全部不含资金费；币安原生股票/TradFi合约未另作资产类别排除。历史全池身份、资金日历、日内回撤、保证金、强平及成交容量未认证。研究计算通过不等于策略或实盘通过。

## 复现与存储

使用仓库虚拟环境并设置`PYTHONPATH=src`。首次轮`research_weekly_top10_20260924.py prepare/execute`；补充轮`complete_weekly_top10_20260924.py collect/prepare/execute`；接着`audit_weekly_top10_20260924.py`、`report_weekly_top10_20260924.py`和`finalize_weekly_top10_20260924.py`。所有命令拒绝覆盖已存结果，复现请在独立工作副本中使用相同冻结输入，勿在此重复覆盖。

新材料预算30MiB，实际见completion；复用旧返回帧，未复制原始大行情，未修改旧代码/旧结果/数据湖，无实盘、自动化或生产变更。家族既有体积超500MiB，本地二进制不自动进入普通Git；本轮不删除或迁移历史。
