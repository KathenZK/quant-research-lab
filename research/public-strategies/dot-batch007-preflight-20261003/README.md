---
research_classification: diagnostic_topic
---

# dot007：MultiRSI 与 PowerTower 来源预检

59条freqtrade来源记录排除31条既有研究或认领后，余28条中恰2条通过本批固定5m内核的来源与合成校验。另26条仅不兼容当前批次，不能记作全局策略失败。原预检初判、pending卡及追加结果按原字节保留在source-preflight；最终状态以FINAL-READY-v2.json及独立追加回执为准。

M0287保留原SMA比较和本地10m/40m闭合重采样；M0289保留绝对价格幂次、退出小于关系及分钟ROI表。禁止为凑数量而改周期、关闭trailing、规范化价格或修改共享v1。原作者运行环境/选池及成交队列未建立，后续只能标执行改编代理，严格复现0。

root把M0287/M0289独占分配给dot；当前未写策略C0、未启动历史运行。两ID各四配置、复用既有买持对照，不新增对照。仅使用dot已独立取得的dd09采集清单和91e5原生5m输入；本合同直接绑定该采集身份，不能套用dot006的四ID权限范围。

[执行契约](../dot-batch007-output-contract-20261003.json) · [独占分配](../claims-20261003-batch012.json) · [最终预检](source-preflight/FINAL-READY-v2.json) · [原字节清单](source-preflight/FINAL-SAFE-MANIFEST-v2.json) · [决策记录](decision-log.md)

代码Git持久化、完整私有恢复包和Library异地恢复分别记账；本来源预检不是私有行情备份或回测完成。历史次数、盈利、OOS、PIT及网站上线状态均不能从合成PASS推断。
