# PUBLIC-M0259-BBRSI Core Ledger

## 身份与当前状态

- 稳定ID M0259，来源 BbandRsi / Gert Wohlgemuth（berlinguyinca）
- 计划变体 `M0259-BTCUSDT-1H-BBRSI-20261003`；独立移植，忠实度 HYPOTHESIS
- 状态 `DATA_BLOCKED`；未建立实际收益记录或登记可晋级Vx
- 实际策略配置回测0、执行敏感性0、买持对照0；合成测试不计市场回测
- 用户已同意数据条款；实际月档743/744行且存在非整小时close_time，完整网格QA失败。先完成官方日档交叉核验并记录阻塞，不冻结或计算收益，不改变原窗

## 核心假设

RSI14<30且close低于典型价BB20/2下轨入场，RSI>70离场。保留源码10% ROI与−25% stoploss。100000 USDT、95%当前现金含买入费预算、单仓只多、下一真实开盘成交、单边费8bps加2bps不利滑点；期末不强平。

qtpylib BB使用 `min_periods=1` 和 `ddof=1`。ROI触发含双边费但不预补卖出滑点，准确触及阈值后净回报9.978%，不保证净10%。已知开盘退出/跳空与未知日内高低点顺序分开处理。细节均在[规格](specs/M0259-first-replay.json)。

## 已有证据

源码hash已核，Python TA-Lib0.6.8/C0.6.4及Freqtrade2025.9的qtpylib源码已锁。4类合成指标序列、10项成交风险检查、5个独立合成账本与日采样导出核验通过。均非真实市场表现证据。

## 限制

窗口已被其他策略曝光，历史搜索次数未知，不宣称纯净OOS或可靠DSR/PBO。BTCUSDT是事前实例，原策略未指定资产池。独立OHLC执行假设不是完整Freqtrade回测器，也不能证明历史可交易性或日内成交路径。未promote、未live-ready、未绑定Graph定义。

## 2026-10-03 数据门控

[独立原始月档审计](artifacts/20261003-data-blocked/independent-monthly-audit.json)确认2023-03缺2023-03-24 13:00UTC，12:00的close_time为12:39:41.646且零量/零交易。官方hash一致只证明取回的是该源文件，不能把缺口升级为有效输入。真实策略收益、指标与账本验证均NOT_RUN。

## 完整原始窗口补充

25月原始归档已观测，18287/18288行，唯一缺口和异常零量bar未变，其余无重复、乱序或基本值错误，仍REJECTED且禁止收益。前4个月12个ZIP/CHECKSUM/CSV对象独立重抓hash一致；其余21月未二次抓取，不宣称全窗双抓恢复。[去原始价QA摘要](artifacts/20261003-data-blocked/full-window-qa-summary.json)。
