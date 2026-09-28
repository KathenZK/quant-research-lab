# HYPE 1D MA7 MLT P8：MA7 Cross First-Hit Event Atlas

> 2026-08-31。裁决：`INSUFFICIENT_SAMPLE`。状态：`diagnostic-only / not promoted / not live-ready`。
> 本轮不训练机器学习、不优化参数、不读取 HYPE 后81日、不修改 P0-P7 或 exact V7.1。

## 结论

P8 在五个资产截断到 `2026-05-31 00:00 UTC` 的数据上保留所有 raw `SMA7` cross。完整 primary 路径事件 `624` 笔，primary 成功率 205/624 = 32.9% [29.3%–36.6%]，成本后单事件净收益均值 `+0.36%`。

HYPE 前365日事件 `85` 笔，完整 primary `82` 笔，episode cluster `2` 个；四个供体事件 `554` 笔，完整 primary `542` 笔，episode cluster `16` 个。

## 分资产与方向

| 资产 | 事件 | episode cluster | primary 成功率 | 净收益均值 | PF |
| --- | ---: | ---: | --- | ---: | ---: |
| `BNBUSDT` | 126 | 4 | 31.7% | +0.03% | 1.01 |
| `BTCUSDT` | 142 | 5 | 31.7% | +0.03% | 1.01 |
| `ETHUSDT` | 144 | 2 | 27.8% | -0.48% | 0.86 |
| `HYPEUSDT` | 82 | 2 | 37.8% | +1.54% | 1.35 |
| `SOLUSDT` | 130 | 5 | 37.7% | +1.21% | 1.34 |

| 方向 | 事件 | primary 成功率 | 净收益均值 | PF |
| --- | ---: | --- | ---: | ---: |
| `long` | 312 | 33.7% | +0.39% | 1.13 |
| `short` | 312 | 32.1% | +0.32% | 1.10 |

## 匹配基准

| 对照 | success uplift | net uplift | control rows |
| --- | ---: | ---: | ---: |
| 非穿越同侧 B | 3.3%；bootstrap [-2.2%, 6.1%] | +0.57% | 1283 |
| 7日动量 C | 5.8%；bootstrap [0.4%, 12.1%] | +1.13% | 2929 |
| 随机匹配 D | 3.6%；bootstrap [-1.9%, 6.5%] | +0.58% | 3101 |

同一 `1h` 同时触及有利和不利 primary 屏障的模糊事件为 `0`，占 `0.0%`；主标签按合同采用保守不利先触发。

## 去重与独立性

14日同资产同方向去重后 primary 成功率为 83/280 = 29.6% [24.6%–35.2%]，净收益均值 `-0.29%`。
统计独立性按资产 `5` 个、raw-cross episode `18` 个、日历块 `8` 个记录。

## 状态图谱

单变量分箱和十个二维矩阵均完整写入 artifact；`n<30` 的格子标记 `INSUFFICIENT_SAMPLE`，不据此提出交易规则。HTML 中可按资产、方向、斜率档、穿越幅度和结果过滤事件路径。

几个样本数足够的预注册状态只呈现弱描述性差异：

- MA7 方向化斜率 `<=0`：313 笔、31.6%、净均值 +0.03%、OK；`>0.10`：131 笔、35.9%、净均值 +1.05%、OK。斜率不是严格单调关系。
- 穿越幅度 `>0.50 ATR`：384 笔、36.2%、净均值 +0.78%、OK；`(0.25,0.50]`：155 笔、24.5%、净均值 -0.74%、OK。大幅穿越较好，但 matched baseline 和去重后不足以构成规则。
- 反侧停留 `2-3日`：156 笔、35.9%、净均值 +0.52%、OK；`4-7日`：189 笔、35.4%、净均值 +0.28%、OK；`>=8日`：116 笔、27.6%、净均值 +0.11%、OK。中等停留较好，长停留转弱。

小样本状态主要集中在分资产 × 斜率、极小穿越幅度、HYPE 高斜率/高成功率格子和多数二维交叉格；这些格子即使成功率高也只能作为下一轮问题定义线索，不能提出交易规则。

## 裁决

最终裁决为 `INSUFFICIENT_SAMPLE`。即使某些斜率或方向格子表现较好，本轮也只是事件图谱，不登记版本、不 promotion。是否进入下一轮 ML 取决于 matched control uplift、bootstrap 下界、供体一致性、HYPE 前365日方向和成本后期望，而不是单个最好格子。

本轮不建议直接进入机器学习筛选：raw cross 相对 controls 的优势太浅，非穿越同侧和随机匹配的 cluster bootstrap 下界仍小于 0，供体资产只有 2/4 相对 Baseline B 为正，且 14 日去重后净期望转负。若继续，应先重定义 episode 独立性或延长跨资产样本，而不是训练模型去挑这批格子。

## 证据

- [冻结合同](../specs/hype-1d-ma7-mlt-p8-ma7-cross-first-hit-event-atlas-contract-2026-08-31.md)
- [研究脚本](../scripts/run_hype_1d_ma7_mlt_p8_ma7_cross_first_hit_event_atlas.py)
- [事件表](../artifacts/hype_1d_ma7_mlt_p8_ma7_cross_first_hit_event_atlas_2026-08-31_events.csv)
- [64组 first-hit 矩阵](../artifacts/hype_1d_ma7_mlt_p8_ma7_cross_first_hit_event_atlas_2026-08-31_first_hit_matrix.csv)
- [matched controls](../artifacts/hype_1d_ma7_mlt_p8_ma7_cross_first_hit_event_atlas_2026-08-31_matched_controls.csv)
- [cluster bootstrap](../artifacts/hype_1d_ma7_mlt_p8_ma7_cross_first_hit_event_atlas_2026-08-31_cluster_bootstrap.csv)
- [摘要 JSON](../artifacts/hype_1d_ma7_mlt_p8_ma7_cross_first_hit_event_atlas_2026-08-31_summary.json)
- [交互式 HTML 图谱](../artifacts/hype_1d_ma7_mlt_p8_ma7_cross_first_hit_event_atlas_2026-08-31.html)
- [开发冻结清单](../artifacts/hype_1d_ma7_mlt_p8_ma7_cross_first_hit_event_atlas_2026-08-31_development_manifest.json)
