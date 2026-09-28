# B0E 有界输入读取补充（收益运行前）

日期：2026-09-09。仅补充 `binance-1d-mcsm-baseline-estimate-20260909.md` 的输入工程方式，不改变选币、成本、时期或估算价格精度。

本次需 77 个换月点、原完整日 K 缺失的部分上市月末以及少量内部缺日。统一 startup 只支持单个矩形时间窗，每个细窗重复全 bundle 哈希会反复验证同一不可变文件。独立估算使用本次运行的等价有界审计，而不冒充原 startup 成功：

1. 在任何研究收益计算前留存明确 bundle pin、总审计窗口及子请求生成规则。
2. `read_bundle_contract` + `verify_bundle_files` 验证本次全组件内容、父子关系和冻结reader。
3. `load_trusted_research_dataset` 以明确15m V3 ID、`FULL_MARKET`、`STRICT_CONTENT`、`contiguous_segments` 审计 2020-01-01 至2026-07-01 00:30 UTC 的总价格范围；只保留本次已验证文件身份。
4. 从上述同一个 verified load 用 `read_verified_ohlcv` 读取预先声明子窗口，逐项保证其范围不越过总审计起止及闭合截止，不直接读取raw/cache/normalized湖目录。
5. 每个子返回帧依照冻结 `validate_price_frame` / 分段与mask规则检查；返回原始无效行，形成期不得跨未解释内部缺口。日线投影仍核对原来源/请求/报告和内容哈希后消费。
6. 保留整个读取链、精确请求、原帧投影、行质量和缺失覆盖；消费者登记为有界等价审计。状态 `EXPLORATORY_SCOPED_EQUIVALENT_AUDIT`，不授予 `NET_INPUT_WINDOW_VERIFIED`、历史身份、资金日历或实盘资格。

这一显式方式属于数据湖规范第10节要求说明理由和等价质量审计的独立诊断消费，不修改共享入口，不绕过内容/范围/行质量检查，也不把过去一次PASS当作现在直接扫描湖的许可证。
