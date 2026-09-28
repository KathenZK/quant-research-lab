# HYPE MA7研究脚本

## 2026-09-24 V3参数检查

- `v3_parameter_study_20260924.py prepare`：先固定121配置、11参数网格、比较起点规则与代码指纹。
- `v3_parameter_study_20260924.py run`：只消费原冻结HYPE输入，复现原V3并输出所有共同起点账户。完成目录禁止prepare覆盖；复现应使用新的目录副本，不覆盖历史证据。
- `audit_v3_parameters_20260924.py`：独立指标、入场、退出、止损和账户核验，不导入新引擎。
- `report_v3_parameters_20260924.py`：从结果生成中文报告、全部配对与可交互HTML，不重跑策略。
- `audit_v3_parameter_html_20260924.cjs`：离线执行交互脚本检查全部121方案，不代替真实浏览器视觉检查。

使用共享[v8内核](../../../_shared-kernels/ma7-cross-atr-ratchet/v8/README.md)，按[引擎pin](../specs/v3-parameter-engine-pin-20260924.json)的SHA固定；运行前started.json同时固定引擎SHA与runnerSHA。v8不是策略V8，正式策略仍为V3。原v7及旧产物不改。

研究范围和所有数字以[本轮报告](../diagnostics/v3-parameter-stability-results-20260924.md)为准。
