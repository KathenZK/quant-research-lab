# V3取消额外预热 · 2026-09-13执行修订

[HYPE交易路径](html/coins/HYPE.html) · [全市场HTML](html/index.html) · [中文结果](../../diagnostics/v3-no-extra-warmup-results-20260913.md) · [计算前规格](../../specs/contract-v3-no-extra-warmup-20260913.md)。

取消固定前28根日K的信号屏蔽，保留指标有效及行情质量检查。共享内核仍为冻结v6，SHA为`dd00f099ad8a4419c78cc337dede52284da75cac8675d9ccdd0eeeb8aa2de46b`；按原指标数据重建ready，不改原内核或旧特征文件。每边手续费0.001、不利滑点0.0004。

| 内容 | 路径 |
| --- | --- |
| 计算前源清单和运行身份 | started.json、inputs/ |
| 全部990段输入范围 | inputs/catalog.json、results/ranges.csv |
| 979段×3方案的交易、止损、权益与事件 | accounts/ |
| 逐币汇总及全部入场变化 | results/ |
| 新旧、共同旧起点、固定时期成对比较 | analysis/ |
| 独立公式复核全部新账户 | audit/、audit_checkpoints/ |
| 680币加总览、旧新六方案路径 | html/ |
| 纯汇总缺失值修复的原始失败记录 | technical_export_fix/ |
| HTML数值、离线交互、最终散列和保留说明 | delivery/ |

使用相同仓库与原冻结输入时，以仓库Python环境执行：

1. `scripts/v3_no_extra_warmup_20260913.py prepare`：输出目录须为空，绑定原680代码及全部连续段。
2. 同一入口 `smoke`：原三方案复现、自然就绪和未来前缀验证。
3. 同一入口 `run --workers 4`：新三方案回放；已有完整checkpoint复用，部分已有账户必须和重算完全一致。
4. 同一入口 `audit --workers 4`：独立核对全部新账户。
5. `scripts/report_v3_no_extra_warmup_20260913.py tables`，再 `html`：比较并导出；已有HTML不覆盖。
6. `scripts/check_v3_no_extra_warmup_delivery_20260913.py`及既有离线图表交互核验器检查新HTML。

旧结果只复用，不重跑。生成器消费方路径均在本家族`scripts/`。若修复了导出程序，技术修订同时保留修复前源码、原运行身份和说明，不重写历史身份。

本目录为可再生产物与必要规范证据，不是新行情湖。批量权益和HTML超过家族普通Git预算，均留在本地忽略路径，不新增Git大文件。保留上限为本次一份正式输出，必要失败证据仅保留小型源码、摘要。旧研究结果保持原样。可逆外置方案为先复制到经授权的私有存储、记录版本及散列、回取完整验证，再更新引用；尚未迁移或上传任何数据。
