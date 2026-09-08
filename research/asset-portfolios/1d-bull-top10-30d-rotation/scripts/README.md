# 复现入口

先读[冻结规则](../specs/p0-contract.md)。以下是本家族一次性研究脚本，不是线上执行代码。

1. [build_p0_inputs.py](build_p0_inputs.py)：重新调用两份组合启动请求，保存日线状态与4H价格，拒绝覆盖既有输入。
2. [replay_p0.py](replay_p0.py)：核验输入哈希，回放牛市Top10及无牛市对照；持仓缺价即停止账户，另保留逐轮有效/无效标签。
3. [package_p0.py](package_p0.py)：独立核对选币、30日时序和真实价格算术，形成中文报告。历史结算阻塞不通过假价或零填修复。

验证：仓库根运行`.venv/bin/pytest -q tests/test_binance_1d_bt10r30.py tests/test_research_bundle.py`。
