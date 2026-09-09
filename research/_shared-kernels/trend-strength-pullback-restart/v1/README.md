# 共享内核v1冻结身份

首次结果计算前，由消费者的`specs/computation-lock.json`锁定本版本manifest及代码。版本内容冻结后不可修改；实现错误使用新版本，并保留失败运行。

- engine.py：20日窗口锚点波动标准化强度、固定5日顺序回撤、MA7首次严格重穿、过去窗口与未来完整标签。
- statistics.py：24个固定目标、调和共同支持权重、完整估计量日期块bootstrap和最大标准化误差联合区间。
- capture.py：单币单连续段固定数量20日持有；手续费/滑点双场景，不含资金费/强平/容量。
- tests/：在历史结果前执行的公式、边界、支持与重复观察核对。

capture.py来源于[MTCS捕获实现](../../../asset-portfolios/1d-medium-term-continuation-state/scripts/capture.py)，原字节复制，SHA256=`42585a7289aacdb8b6a3727fcc575ec8b97294bcd70912fbf713799ef91dc351`。旧文件不变；新版本不在运行时引用旧家族模块或输出。

研究定义与判定以消费者的[研究合同](../../../asset-portfolios/1d-trend-strength-pullback-restart/specs/research-contract.md)和[统计合同](../../../asset-portfolios/1d-trend-strength-pullback-restart/specs/statistics-contract.md)为准。本内核不提供独立的交易资格。
