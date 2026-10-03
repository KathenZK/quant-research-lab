# 决策记录

## 2026-10-03：收益前准备

- 仅认领M0256，遵循固定交接a7b7ea4c09863306ed41427c19af072c0db20139。私有主表字节SHA256核验后仅读本行，不发布主表。
- 原策略2630B SHA256核验通过；冻结参考qtpylib为Freqtrade 2025.9 commit c66e221012cd4d68cfdacf4735b38af33a487961，TA-Lib Python0.6.8/C0.6.4。早期查看2024.12只是源码语义预查，不进入本轮正式冻结。
- 不省略ROI50%/stop−20%，不hyperopt；4h日内路径和执行假设预声明，HYPOTHESIS，不strict/OOS/promotion。
- 合成单位测试涵盖exit优先、stop、ROI、双触发、gap stop/ROI、双边2bps滑点、ROI实际净49.97%、额外bar延迟。没有正式输入或真实收益。
- 发现Binance现行条款需用户先确认；正式数据下载、输入冻结与收益计算仍待授权。测试不构成正式回测次数。

## 2026-10-03 08:23–08:26 UTC：正式冻结、单ID重放及恢复

- 条款授权后官方4h输入4572行，主抓/第二轮实际网络重抓同hash，独立raw→canonical通过；严格finality因API451等未建立，保持DIAGNOSTIC_ONLY
- 收益前加入已知停市证据与1h恢复open代理，未读任何1m；10类合成检查通过。08:23:13.758120 UTC冻结spec/source/code/input/exposure，随后首次计算
- 基准218.06%、回撤23.98%、日Sharpe1.799，落后买持441.87%。4配置+1对照通过独立Decimal账本、原源码信号对照和三处未来扰动
- 全新目录18个确定性输出逐字节一致，独立账本再次通过；没有收益后换参、修正代码或替换输入
- 四策略配置所有卖出均为exit_signal；ROI/stop、14点恢复代理仅合成测试触发，本历史未触发，不能混称历史风险/停市执行验证
- Graph record/detail生成，尚未注册或部署；远端、Library及页面验收由协调者负责
