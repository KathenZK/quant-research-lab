# ATR止损虚线显示修复

本次为2026-09-13的展示修复，没有新策略版本，没有重新计算交易和收益。旧[HTML](html/index.html)、固定契约和既有回测证据保留。

打开[HYPE全部路径](html_stoplines/coins/HYPE.html)或[全市场入口](html_stoplines/index.html)。默认显示全部逐笔实际止损，虚线按记录中的生效时间呈阶梯变化，在各自平仓处终止。空心圆表示ATR倍数减少；下方1.5至0.5的倍数阶梯独立显示，避免把倍数减少误读为止损价格必然移动。选中单笔可核对逐日倍数、实际止损、停滞天数与启动状态。进出场、持仓方向和交易盈亏使用不同标记；MA30为可选参考。

生成681个页面，其中680个币页面含975个连续段、三种原方案。保留原始所有行情、交易、止损与诊断数组，只增加封存证据的每日止损明细和指标，共804,714条止损明细。未获取新行情，未修改正式V1/V2/V3或费用设置。

核验结果：

- [全量数据核验](ui_stoplines_audit/data.json)：原HTML校验和与原数据数组不变，新增明细逐字段与封存CSV一致；次日生效、持仓边界、倍数及价格止损只收窄均通过。
- [离线交互核验](ui_stoplines_audit/dom.json)：运行真实图表JavaScript并检查画布绘制指令；覆盖HYPE、BTC、BLZ全部方案与连续段、653次桌面单笔选择、390px HYPE及320px空数据/零交易/单日场景。虚线阶梯、持仓截断、空心圆、MA7收盘时间与两图同步均通过。
- 另使用本地画布渲染检查HYPE全图、第一笔和390px图表像素；没有使用真实浏览器，不据此宣称已验证完整页面布局或浏览器字体。

修复实现：[展示生成器](../../scripts/revise_v3_stoplines_20260913.py) · [图表逻辑](../../scripts/v3_stoplines_chart_20260913.js)。独立核验：[数据](../../scripts/audit_v3_stoplines_data_20260913.py) · [离线交互](../../scripts/audit_v3_stoplines_dom_20260913.cjs)。所有输入和输出分别见[输入清单](html_stoplines/consumed_files.json)、[输出校验和](html_stoplines/artifact_checksums.json)、[完成记录](html_stoplines/completion.json)及[修复交付记录](ui_stoplines_revision.json)。旧研究交付记录不重写。
