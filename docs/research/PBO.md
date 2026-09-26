# PBO / CSCV 数学语义与 reference validation

依据：[Bailey 等，The Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf) §2.2–3.1。PBO 评估一个试验集合的选择过程，不是某个策略盈利概率。

T×N 收益矩阵按时间切成 S 个等长连续块。枚举全部 C(S,S/2) 个 IS 组合，其补集为 OOS；计算各列非年化 Sharpe。对 IS 最优者取得 OOS 升序排名 r，ω=r/(N+1)，logit=ln[ω/(1−ω)]；PBO 是 logit<=0 的权重比例。

并列政策：所有严格相等的 IS 最优者等权；OOS 使用平均排名。零 logit 计入失败侧，因此全列相同返回1，不是“策略全都亏钱”。不使用任意首列作为赢家。S 为4..12的偶整数，T可整除S且每块至少2期；不足样本、少于2个试验、非有限值或零方差明确拒绝。所有 split 都保留其补集，不把对称组合删掉。

[固定8×3矩阵](../../tests/fixtures/statistical_reference_v2.json) 的6个 split 使用独立 SciPy rankdata 与完整枚举预先冻结排名；结果逐 logit 对照为 -0.5108256、-1.0986123、1.0986123、1.0986123、(0与-1.0986123各半)、-1.0986123，PBO=2/3。另测70个 split 的三列全并列情形，防止浮点累计后 int 截断成69。见 [reference tests](../../tests/test_statistical_reference_v2.py)。

这些是明确标注的数学基准数据，不是真实行情回测。实现没有 purge/embargo；重叠标签、长持仓和跨块泄漏须在研究契约处理。完整 trial 集合、冻结参数与数据质量缺一不可；不得把 PBO 作为继续搜索最优参数的目标函数。
