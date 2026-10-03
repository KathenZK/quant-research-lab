# native5m-execution-proxy

身份：Binance BTCUSDT 现货 2024 年公开策略诊断的固定 OHLC 成交代理。初始资金100000，95%现金含买费，单仓多头，双边2bps滑点；不是 Freqtrade 完整回测引擎，不证明原限价成交。

v1 消费者：M0300、M0302、M0305、M0306、M0307。每个消费者的 `specs/protocol.json` 逐文件 SHA256 pin 此版本；一旦 pin，整个 v1 目录不再修改。变更必须新版本，旧 M0311 继续引用自己原冻结代码。

代码哈希见 [v1/manifest.json](v1/manifest.json)。核心为 [account.py](v1/account.py) 与独立 Decimal [oracle.py](v1/oracle.py)，规则在 ID 内 adapter，原源码与行情仅私有。source_adapter 核实际原类参数加载与独立 Boolean 规则一致；复杂 TA 指标调用固定 TA-Lib，不声称独立重写这些算法。

v1 相对 M0311：预物化 itertuples 替四处逐行 iloc；在信号退出上增加可配置严格盈利门，risk ROI／stop 不受此门限制。Profit gate=raw_open×(1−fee)/(entry_fill×(1+fee))−1>offset；先判断后执行不利滑点，故边缘成交可微亏。五 ID 原 limit 入出均明确改编为下一开盘代理；M0300 的 limit 止损也改为市价式代理。

原账户预算／费用／同柱冲突规则不变；risk ROI 使用严格大于、stop 使用小于等于；无挂单队列／超时／最小订单额。五个评估协议均只跑四个预定策略配置，买持精确引用已验证 M0311 控制，不新增控制试验。

加速候选在 M0311 既有4+1历史上，15个净值／成交 CSV 和指标完全等价；新增盈利门由合成边界和独立 Decimal 合成账户验证。真实新 ID 的来源、因果、账户与一次批次恢复证据存于各 ID artifacts，非本内核目录。

冻结登记：v1 manifest SHA256 `8daf7c9182e055197f2541672911ac817a4bb7165409557566581aa09f1a4e1d`。清单逐文件记录代码与v1说明的哈希；本入口可追加版本登记，不修改任何已pin的v1文件。

2026-10-03 batch011消费者追加：M0260、M0265、M0282、M0283。各ID协议逐文件pin同一v1（manifest SHA256 `8daf7c9182e055197f2541672911ac817a4bb7165409557566581aa09f1a4e1d`）；内核原字节不变。新增独立事件核对脚本属于各消费方，不属于v1。
