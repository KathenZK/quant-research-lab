# 本轮交付验收与归档边界

研究结论见[最终报告](final-report-20260908.md)。本页区分研究计算验收、全仓库既有错误和产物预算，不能把“本家族计算通过”写成所有仓库门禁通过。

## 已执行核验

| 项目 | 实际结果 | 证据 |
| --- | --- | --- |
| 可信行情输入 | 874代码、0启动失败；固定bundle与全组件校验，返回帧哈希留证 | [P0](../artifacts/p0-inputs-20260908/summary.json) |
| 旧基线真实对拍 | 2928项通过，默认交易数/MDD一致，误差未超过原门槛 | [对拍](../artifacts/reference-parity-20260908-r1/report.json) |
| 针对性测试 | 30 passed；因果、费用、空头账本、断档、PIT、purge和统计公式 | [测试](../artifacts/engine-tests-final.txt) |
| 全主样本账本 | 206路径、2060候选账、3216120每日权益点独立重建；1236真实前缀通过 | [独立验算](../artifacts/final-replay-verification-20260908/report.json) |
| 分母与二次回放一致性 | 10主候选均205币，17后续配置同分母，C3与unfiltered逐币相等 | [P5](../artifacts/p5-final-evidence-20260908/completed.json) |
| 交付入口参数调整 | 8张统计CSV逐字一致、HTML逐字一致；只增新输出目录参数和澄清锁措辞 | [独立重生成](../artifacts/reproduction-cli-verification.json) |
| 文档一致性 | 正式Lab的20项文档一致性测试通过 | [文档测试](../artifacts/research-docs-final.txt) |
| 本任务消费者 | 3个入口登记，0错误；只读OHLCV/资金入口 | [消费者检查](../artifacts/consumer-check-final.json) |
| 全仓库消费者 | 仍为启动时完全相同的6个无关旧脚本错误；全仓库门禁未通过 | [同一错误集合](../artifacts/consumer-check-final.json) |
| HTML | 14案例197交易，载荷与语法通过；浏览器URL策略拒绝本地文件，视觉验收未完成 | [图形验收](../artifacts/p4-trade-paths-20260908/browser-and-syntax-check.json) |
| 最终文件、源码与同步 | SHA、链接和目标归档清单逐项核验；正式Lab只同步自有文件 | [最终核验](../artifacts/delivery-20260908.json)、[归档清单](../artifacts/sync-manifest.json) |

源码证据起初以.py保存在artifacts，扫描器将两个只读源码快照误识别为新增活动消费者。已按内容哈希验证后，在本任务两个位置将13份快照改为不可执行的`.py.txt`，内容未改，活动脚本仍正常登记；没有扩大白名单或关闭检查。[原失败](../artifacts/consumer-check-source-snapshot-failure.json)、[格式澄清](../artifacts/source-snapshot-format-clarification.json)。

计算时源码快照与当前源码并存。最终交付新增CLI参数不改变引擎；统计/HTML重生成确认结果一致。首次浮点、拼写、依赖和段身份失败均保留，修复没有改变冻结候选、成本、分母或排序。[修复记录](implementation-repair-20260908.md)。

启动pin中的消费者注册文件因本任务新增3个入口而改变；逐字移除这3段自有登记后，SHA与启动pin完全一致，其他25项源文件pin未漂移。该变化不涉及行情算法，不能混称输入源码变更，也没有无条件忽略哈希不匹配。[初始发现](../artifacts/delivery-initial-registry-drift.json)、[精确差异证明](../artifacts/registry-pin-delta.json)。

## 大产物保留及预算

本轮产物约525MiB，超过家族500MiB的C-externalize阈值；两个评估逐笔gzip各约137MiB，属于D-prohibited-new-git。**产物预算不能声称PASS，禁止把这些大文件作为新的普通Git blob。** 本次只在用户要求的本地忽略artifacts和正式Lab归档，没有强制添加到Git、提交大文件、上传外部存储或改写其他家族。

保留原因及可再生性：

- 固定P0返回帧是本次可信启动证据，重现时必须重新走可信接口并比对内容SHA；不是共享数据源，也不写回湖。
- 2份主评估逐笔和数份筛选逐笔由冻结输入/源码生成。修复前副本用来证明旧结论已失效，修复后副本支撑逐币逐笔验算；用户明确要求保留全部失败，因此本轮两种证据均保留。
- SEC原始JSON、HTTP收据、失败日志、选择锁及澄清为来源/过程证据，不能用后来下载的修订数据替换。
- HTML和CSV摘要可由[复现命令](../scripts/README.md)生成。后续禁止无界复制新轮次；本轮有限搜索已经关闭。

本页是可逆外置方案，不实施迁移：先由用户确定有访问权限的制品库/私有对象存储或LFS方案；对两个大逐笔及可再生中间物按当前manifest复制副本，保留原路径；登记不可变对象版本、SHA和取回方法；在干净目录回取校验并完成C3/账本锚点复现后，另行切换指针和文档链接；最后独立确认是否移除本地冗余。回滚按manifest取回原路径并验SHA，不改写Git历史、不动数据湖。预算问题限制产物准入，不改变研究负结果，也不授权此任务迁移数据。

## 完成裁决

用户四项问题均有证据或具体未完成原因，有限候选与第二条适用性路径已经实际计算、验证和归档。本轮研究交付可结束；“双向超过半数有效”仍未实现，“股票长窗/全成本”仍未验证。保持`explore / not promoted / not live-ready`，没有把待新增数据变成无限历史调参或自动实盘。
