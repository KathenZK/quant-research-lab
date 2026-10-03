# 决策记录

- 2026-09-28：V4 绑定冻结合同、完整覆盖与独立许可审核。3 个模板的数据需求已推导，完整历史和原生 schema 仍阻断；ELIGIBLE=0、正式回测=0、正式写回=0，3 组私有诊断单列。未改 runner。见 [V4 审计](diagnostics/evidence-research-v4.md)。

- 2026-09-27：按最新 QuantGraph v3.1 重新通过认证 HTTP 获取 5813 条记录，41 个模板中合格数为 0。修复候选排序与短缺口径，完成独立 DSR/PBO 数值基准和 v2 离线晋级契约；真实研究继续由准入证据阻断。依据：[v2 验收](diagnostics/platform-v2.md)。

- 2026-09-26：使用现有 quant-strategy-lab 承担研究层，保持三个仓库独立；
  先交付接口与可复现筛选。32 个模板均缺准入证据，真实研究不启动、不晋级。
  依据：[验收结果](diagnostics/acceptance.md)、[冻结范围](specs/pipeline-v1.md)。

- 2026-09-27：切换显式 V3 gate；缺契约 fail closed。独立冻结三个来源改编家族，原始摘要冲突不覆盖。实际下载和补洞后仍缺可信原生字段；两个私有诊断共八组参数，eligible/正式回测/正式回写仍为 0，未触及 Runner。

- 2026-09-28：在 main `a94f426` 复现并修复 holdout/尝试范围/PBO 判定问题，新增 ResearchIntegrityAssessment/v1 和轻量 TrialRegistry；仅合成验证，不改冻结结果。历史复现与探索正常完成，独立确认依据另行审查。见 [复现与修复](diagnostics/research-integrity-fixes-v1.md)。

- 2026-10-03：对 M0004 单独审计五个发行人输入。VNQ 日历史仅251点，其十年序列实际为月频；全池市场成交价和复权验收不齐，回测未启动。保存[独立记录](diagnostics/M0004-20261003.md)与可重复覆盖审计，未扩大批次、未发布网站。
