# 决策记录

- 2026-09-27：按最新 QuantGraph v3.1 重新通过认证 HTTP 获取 5813 条记录，41 个模板中合格数为 0。修复候选排序与短缺口径，完成独立 DSR/PBO 数值基准和 v2 离线晋级契约；真实研究继续由准入证据阻断。依据：[v2 验收](diagnostics/platform-v2.md)。

- 2026-09-26：使用现有 quant-strategy-lab 承担研究层，保持三个仓库独立；
  先交付接口与可复现筛选。32 个模板均缺准入证据，真实研究不启动、不晋级。
  依据：[验收结果](diagnostics/acceptance.md)、[冻结范围](specs/pipeline-v1.md)。

- 2026-09-27：切换显式 V3 gate；缺契约 fail closed。独立冻结三个来源改编家族，原始摘要冲突不覆盖。实际下载和补洞后仍缺可信原生字段；两个私有诊断共八组参数，eligible/正式回测/正式回写仍为 0，未触及 Runner。
