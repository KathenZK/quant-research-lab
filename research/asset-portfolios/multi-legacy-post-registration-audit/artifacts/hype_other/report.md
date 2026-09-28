# HYPE 日内策略后续回放：其余21家

已完成 15 家、25 条事先定义的配置观察。25 行不能当成25家策略；剩余6家具体缺件见下。数据截止统一为 2026-09-05 15:00 UTC；每家从规格落档或登记日期的次日UTC空仓起跑，保留之前价格作指标预热。每次成交/换手手续费 0.10%、逆向滑点 0.04%；资金费按原引擎方法加入已观测事件估计，未确认完整覆盖，因此所有收益都不能称为完整资金费净收益。

15家中6家至少有一个原定配置累计赚钱：30m Keltner、1h MMTF、1h MHEF、15m MTPP、15m SDS、15m PBTR。SDS只有3笔，PBTR只有2笔；MTPP不能从三档风险中挑收益最高者当默认。历史失败配置这次赚钱，不等于其既有风险或验证问题消失。

| 家族/配置 | 起跑 UTC | 累计收益 | 最大回撤* | 笔数/方向入场 |
|---|---|---:|---:|---:|
| bksb_15m | 2026-07-24 | -30.36% | 32.37% | 57 |
| keltner15_outer_break_mid_exit | 2026-07-22 | -32.28% | 38.32% | 54 |
| keltner15_compression_expansion_break | 2026-07-22 | -14.85% | 19.28% | 28 |
| keltner15_trend_pullback_mid_reclaim | 2026-07-22 | -20.09% | 20.26% | 52 |
| mapt_opposite_cross | 2026-07-31 | -72.07% | 72.71% | 157 |
| mapt_close_through_ma7 | 2026-07-31 | -79.88% | 80.58% | 264 |
| mmtf_15m_v3 | 2026-07-23 | -14.22% | 16.85% | 10 |
| mtpp_long_1pct | 2026-08-04 | 2.05% | 5.21% | 6 |
| mtpp_long_3pct | 2026-08-04 | 6.11% | 13.84% | 6 |
| mtpp_long_10pct | 2026-08-04 | 20.69% | 32.19% | 6 |
| mtpp_short_1pct | 2026-08-04 | -0.25% | 0.25% | 1 |
| mtpp_short_3pct | 2026-08-04 | -0.75% | 0.76% | 1 |
| mtpp_short_10pct | 2026-08-04 | -2.11% | 2.13% | 1 |
| mdtp_v1 | 2026-08-01 | -7.46% | 9.92% | 62 |
| pbtr | 2026-07-01 | 2.57% | 3.02% | 2 |
| sds | 2026-07-29 | 7.84% | 7.20% | 3 |
| sma | 2026-07-29 | -5.12% | 15.65% | 38 |
| ar_v4 | 2026-07-08 | -14.49% | 21.76% | 9 |
| bksb_1h | 2026-07-24 | -10.90% | 21.22% | 24 |
| mhef_1h_buffer0.00 | 2026-07-15 | 8.10% | 10.80% | 20 |
| mhef_1h_buffer0.10 | 2026-07-15 | 9.19% | 10.11% | 20 |
| mmtf_1h_v3 | 2026-07-23 | 2.43% | 10.72% | 11 |
| pktsc_long | 2026-08-04 | -0.78% | 2.12% | 7 |
| pktsc_short | 2026-08-04 | -0.35% | 0.35% | 1 |
| keltner_v3 | 2026-07-14 | 22.34% | 30.15% | 18 |

*最大回撤取可重建收盘权益与原引擎保守持仓不利价格统计中较大者。两种统计在每个summary分开保留。MHEF表中20次为方向入场；真实调仓成交含最终平仓分别1264/196次，不能当成1264/196次完整交易。

## 必须保留的限制

- PKTSC 是按规格交易规则做的因果修正回放，不是原代码逐字复现。移除原代码对测试行未来标签存在性的过滤；保留每日固定超参数重训，训练标签在拟合前已成熟。多头仍发生20次风险预算越限，最大开仓风险1.00468%超过原1%上限；该问题没有因完成回放而解除。
- MDTP沿用原按仓位比例计算收益的模型，缺少明确合约数量流水，属于规则诊断。PBTR只回放主账明确列出的bracket代表，不代替有执行状态问题的V3.3追踪止盈迁移。
- BKSB原引擎留下最终持仓。现已用原平仓函数按最后实际收盘退出并扣手续费与滑点：15m从原未退出费用的-30.2596%修正到-30.3572%；1h从-10.7766%修正到-10.9015%。
- MHEF补齐最后实际收盘盯市、资金费估计及最终平仓成交，所有统计重算，原引擎截至最后开盘的统计独立保留。MAPT保留原终止扣费后的权益，并将原开盘标价曲线重建为收盘标价。

## 复核结果

- 全部25条曲线与回放汇总终值相符；有原净值指标者逐一比对，原指标未导出的行写明不适用，并用最后平仓账户值验证。显式终止适配和原引擎结果分开标记。
- 全部25条在8月15日截断数据后，截断前、避开末尾强制退出影响的权益前缀一致。AR、MMTF两周期、30m Keltner另外逐笔核对已完成交易；PKTSC预测前缀一致，全部训练标签严格成熟。
- 全部月收益连乘得到最终权益。每份summary明确说明K线时间是开盘标签还是实际估值时间；按实际可见收盘时间分月，月底收盘不落错到新月。

## 剩余6家

- **15m-factor-ml**（2026-07-16）：artifacts/model_round2_final_oos/model_manifest.json and trained LightGBM ensemble model files are absent; directory contains README only
- **15m-multi-horizon-ema-forecast**（2026-07-28）：artifacts/hype_15m_mhef_v2_prefit_candidate.json is absent; report specifies selected fields but not every searched calibration/volatility field, so defaults cannot substitute
- **15m-price-kinematics-continuation**（2026-08-02）：No frozen entry/exit/position sizing; pure prediction/statistical association study
- **15m-riptide**（2026-06-30）：Original external acceptance was not reproduced (419 vs 431 trades), no external source spec retained here; source short return is entry/exit-1 rather than linear perpetual 1-exit/entry; fixed and rolling-cut observations have no accepted unique local strategy
- **1h-price-kinematics-continuation**（2026-08-02）：No frozen entry/exit/position sizing; pure prediction/statistical association study
- **30m-keltner-breakout-retest**（2026-07-17）：864 searched entries, zero selected candidate; closest failed row is described, but no strategy/spec freeze or registered version. Not choosing that row merely because it was the best search result

所有曲线、逐笔和月度文件见各配置子目录；完整日期/身份路径及文件哈希在inventory.json；验收逐行结果在verification_all.json。