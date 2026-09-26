# DSR 数学语义与 reference validation

DSR 表示在多次试验和非正态收益下，样本 Sharpe 超过零技能试验最大值基准的概率近似，不是预期盈利评分。

依据：[Bailey & López de Prado 2014](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf) Eq. 1–2、pp.9–10 数值例；[VectorBT v0.28.5](https://github.com/polakowo/vectorbt/blob/v0.28.5/vectorbt/returns/metrics.py) 作为外部实现对照。外部源码只读检查后在本机运行，未复制到仓库。

- 输入收益为每期超额收益；risk-free 必须由研究契约先处理。Sharpe=mean/sample_std(ddof=1)。年化 SR 必须除以 sqrt(periods/year)，跨试验年化 SR 方差必须除以 periods/year。
- skew=mean(z³)、Pearson kurtosis=mean(z⁴)，z 使用总体标准差 ddof=0；不是 excess kurtosis。与 SciPy bias=True、fisher=False 对齐。
- 基准 SR0=std(trial SR, ddof=1) × [(1−γ)Φ⁻¹(1−1/N)+γΦ⁻¹(1−1/(Ne))]。
- DSR=Φ[(SR−SR0)sqrt(T−1)/sqrt(1−skew×SR+(kurtosis−1)SR²/4)]。
- N 是事先声明的有效独立试验数，不能通过隐藏失败试验降低；高度相关参数不自动算独立。保存 observed trials 和 effective trials。当前实现仅接受 N>=2 且不大于实际试验数；不足样本、零方差、NaN/Inf 明确拒绝。
- IID 近似不消除自相关、选择偏差或数据缺陷；reference PASS 只证明数学实现，不能批准策略。

原文三个固定算例：年化 SR=2.5、T=1250、年化 trial variance=0.5、每年250期；N=100/skew=-3/kurtosis=10 得0.9004；N=46 得0.9505；N=88/skew=0/kurtosis=3 得0.9505（原文四位小数容差5e-5）。

固定测试矩阵和逐字段参考值见 [fixture](../../tests/fixtures/statistical_reference_v2.json)；[tests](../../tests/test_statistical_reference_v2.py) 同时检查 SR/skew/kurtosis/SR0/DSR；独立 SciPy 参考 DSR=0.7196294320273796，Lab=0.7196294320273795，外部 VectorBT 同值，误差1.11e-16。见 [external comparison](../../research/platform/quantgraph-integration/artifacts/reference-v2/vectorbt-comparison.json)。
