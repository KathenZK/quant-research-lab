# V3 机会与损耗 · 固定研究证据

2026-09-13，正式 V3 不变。先冻结两个互斥局部实验，诊断原全部就绪穿越与持仓退出后的价格路径，再逐臂回放，独立核验，交付 HTML。

[中文结论](../../diagnostics/v3-opportunity-results-20260913.md) · [计算前规格](../../specs/contract-v3-opportunity-20260913.md) · [主账](../../bin-1d-ma7-car-gen-core-ledger.md) · [交互总览](html/index.html)。

| 目录／文件 | 用途与可再生性 |
| --- | --- |
| `before_results.json`、`preimages/` | 新结果前的规格和来源散列、相关文档修改前备份；规范证据 |
| `inputs/` | 680候选／975原交易段、原V3复用摘要、启动返回数据与旧结果的10,320份散列；没有复制行情湖 |
| `diagnostics/` | 全部原MA7穿越、自然退出、四日停滞和短止盈事件的5/10/20日路径，可由固定源重算 |
| `accounts/E_STATE/`、`accounts/TP_PROTECT/` | 两臂各975独立连续账户、成交、止损、权益、候选记录；可再生 |
| `pairs/` | 原22,028入场逐笔对照；3,109短止盈重放、18,919不可达分支证明复用 |
| `analysis/` | 完整期间、部分历史分列和原段账户；全部粗分组及未来路径表，可再生 |
| `interpretation/` | 独立描述统计与正反解释；`supplement/`另记恢复前新增逆行，使用自己的清单 |
| `audit/` | 独立重建账户、候选、保护线、未来路径与配对；每次源代码快照保留在相应审核目录 |
| `html/` | 681份本地自包含HTML，全部680代码入口及975段路径；无远程图表依赖 |
| `delivery_audit/` | 导出数值与离线HTML交互检查；不代表实际浏览器视觉验收 |
| `delivery/` | 最终文档、代码和所有子目录的验收清单；快照代码以 `.py.txt` 保存，避免误识别为新数据入口 |

## 复算顺序

在相同仓库结构、可用原冻结输入且本轮输出目录为空的环境，使用仓库虚拟环境执行以下入口。完成目录不可原地覆盖；中断回放仅在源散列完全一致时用 `--resume`。不得把原来的数据路径换成当前默认湖文件。

1. `scripts/v3_opportunity_inputs_20260913.py`：原输入与原结果散列检查。
2. `scripts/check_v3_opportunity_baseline_20260913.py`：HYPE、BTC、ETH原字段兼容性。
3. `scripts/diagnose_v3_opportunity_20260913.py --contract <本轮规格路径> --contract-sha256 269d9aa2d3c2de2c89c43df2b602d5b5151cfcbbf54fff4313576ce97c7c3dd9 --workers 4`。
4. `scripts/run_v3_opportunity_20260913.py --arm E_STATE --workers 4`，完成后再以 `--arm TP_PROTECT` 执行另一臂。
5. `scripts/pair_v3_opportunity_20260913.py --workers 4`：等待两个实验完成，再配对。
6. `scripts/build_v3_opportunity_report_20260913.py`、`scripts/build_v3_opportunity_html_20260913.py`：固定汇总及HTML。
7. `scripts/audit_v3_opportunity_20260913.py`及独立交付审核；实际审核参数和源码见各 `started.json`、`source_script.py.txt`。

共享内核 v6 通过[消费方 pin](../../specs/v3-opportunity-engine-pin-20260913.json)加载，SHA `dd00f099ad8a4419c78cc337dede52284da75cac8675d9ccdd0eeeb8aa2de46b`。每边手续费0.001、不利滑点0.0004，关闭反手。源日期、开始/结束和成本都属于复算身份，不随当前默认配置变化。

## 保留与体积

本轮约1.8GB、约3.2万文件，主要是连续账户权益、每段诊断和独立审核；最大单文件约43MB，为全部穿越诊断表。全部二进制和批量HTML在本地忽略路径保留，不作为普通Git blob新增；无需、也没有执行外传或历史删除。

保留上限是一份本轮正式结果及必要失败尝试记录。新规则必须建立另一次明确授权的研究，不把重复导出复制成多套大产物。用于回取的不可替代最小材料是规格、源与输出散列、执行源码、汇总、审计和报告；大表由这些输入重算。

可逆冷存储方案：若以后授权外置，先按当前清单复制到私有对象存储，记录对象版本和SHA；在新目录回取核验；更新引用后仍保留本地副本至复验完成，再决定是否移除。当前没有执行迁移、删除或上传，原始源仍由原研究归档管理。

本轮计算和审核通过不弥补原价格来源冲突、历史可交易身份或资金费缺口，也不构成完整全市场牛熊盈利证据。
