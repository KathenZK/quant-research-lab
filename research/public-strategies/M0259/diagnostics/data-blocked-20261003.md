# M0259 原窗口数据阻塞结论

## 结论

`DATA_BLOCKED`，真实市场回测 **0**。原定BTCUSDT spot / 1h、输入2022-12至2024-12、评估2023–2024保留。未取得满足原契约的完整输入，未冻结输入/代码/规格/曝光运行对象，未计算市场指标或收益。没有净值、交易、敏感性、买持或收益恢复结果；这些不是零收益，也不是策略失败表现。

## 完整窗口追加审核

后续已完成原请求全部25个月官方1h原始归档观测，共18287/18288行。唯一缺口仍是2023-03-24 13:00UTC；唯一零量/异常close_time仍是12:00UTC，无其它缺口、重复、乱序、网格外bar或基本值错误。状态仍为REJECTED / consumer_eligible=false / strategy_returns_permitted=false，真实运行0。

本ID重新核了完整manifest和拒收CSV的字节hash，并独立扫描18287行开收盘网格、重复/顺序/缺失集合与基本OHLC/量值，没有计算任何市场指标或收益。完整拒收CSV5133368字节，SHA256 `db094a83de18f45f50313b775a4ac54d93cdf0f4ea7456e28f196f8c8b834d2d`；私有完整manifest98218字节，SHA256 `df9c1d2953d799c73dc974b5d6e5db7349987e8d51c6649faa0bb5f1c74c7373`。公开仅保留[去原始价的全窗QA摘要](../artifacts/20261003-data-blocked/full-window-qa-summary.json)及75个原对象的轻量hash/字节/时间信息。

首次失败抓取的2022-12至2023-03四个月，其ZIP/CHECKSUM/CSV共12个原对象已独立重抓且hash一致。其余21个月仅本轮首次观测；不宣称25个月全部双抓、完整窗口恢复或TRUSTED。

## 首次失败及日档交叉证据

1. 官方2023-03月ZIP的SHA256与官方CHECKSUM一致，ZIP CRC通过，解出CSV只有743行，原定连续1h月网格应为744行
2. 缺少2023-03-24 13:00 UTC bar；12:00 UTC bar的原生volume及trade_count为0，原生close_time为12:39:41.646 UTC，不能按原协议当作截至12:59:59.999的完整小时
3. 同官方站点2023-03-24日ZIP同样通过CHECKSUM与CRC，只有23行；所有原生字段与月档同日23行完全相同。日档没有提供可替换修复行
4. 本ID用独立脚本重新核验上述月/日字节、网格及逐字段相等关系，未排序、去重、补值、删零、重采样或改数据窗口
5. 官方[维护结束公告](https://www.binance.com/en/support/announcement/detail/813a31506e9f478ea8c1058b425df87a)说明该日14:00 UTC恢复现货交易。这提供了交易中断背景；它不创造缺失bar，也不能证明12:00小时中的实际可成交路径
6. 另一个严格finality门的Spot REST time请求返回HTTP451，已停止且未绕过。缺provider clock/newer-current-bucket也不能宣称TRUSTED，即使其他行审计通过

独立证据：[月档审计](../artifacts/20261003-data-blocked/independent-monthly-audit.json)、[日/月交叉核验](../artifacts/20261003-data-blocked/independent-daily-crosscheck.json)、[來源hash/字节/拉取时间](../artifacts/20261003-data-blocked/source-input-manifest.json)、[时钟请求阻塞](../artifacts/20261003-data-blocked/provider-clock-unavailable.json)。

## 精确指纹

| 对象 | SHA256 |
|---|---|
| 官方2023-03月ZIP | 7f2afb8e0179a57ac31eab5205660298ba5eb77039ac2e21aef9b715ff3d06ce |
| 月CSV | 9608d74f112518d3e4941cd9673f96f887f752120a7ed6c29240a75795f15974 |
| 官方2023-03-24日ZIP | ea9d94f28a39ad8029c9c2863cbb7769137188edd957fea35d0313ae4183561f |
| 日CSV | 17bb536be486876f0c73ced1ef1a0d46ce5cca3d4a08baa30343a04cb3aa9c76 |

以上四项为月/日失败源对象hash。新增完整25月拒收CSV的hash见上节，但它仍不是已接受或已冻结的策略输入。原始价、CSV、ZIP和网页HTML均只在私有证据目录保留；公开只提供自写诊断与hash元数据。

## 为什么不能继续算

原策略不存在volume>0过滤。删除零量bar、前值填充13:00或将14:00拼接成下一根，会改变RSI/BB周期和下一open执行含义；持仓跨中断期间的ROI/stop路径同样没有被完整bar证明。识别到真实交易停顿不等于原连续时间契约已接受不规则数据。不得用额外1bar延迟敏感性“吸收”此缺口，不改成日线，也不跳过2023后只跑2024。

代码已按完整输入预备并通过合成测试，包括source class精确方法对照、独立指标/账本、每小时和公开逐日equity/drawdown/close_ts、下一open、ROI/stop/同bar顺序、含费预算、真实未来扰动工具和路径无关恢复工具。合成结果不构成市场QA或收益证据。`freeze_run.py`已实际验证拒绝DATA_BLOCKED且不生成freeze。

## Graph与后续

[Graph阻塞record](../artifacts/20261003-data-blocked/graph-record.json)明确tested_variants=0、implementations=[]、related_results=[]，无metrics/curve或null收益。没有虚构definition_revision或已展示页面状态。完整未来收益detail必须使用私有输出路径，不能混入公开manifest。

原窗口本次交付终态为DATA_BLOCKED。若以后希望做“交易中断感知”适配，需要另行明确数据可用性、分段/状态连续、跨缺口持仓、指令有效期和真实成交规则，预先授权并建立新规格；不能把本次阻塞覆盖成通过。只保留本条ID，不扩量。

Binance衍生诊断署名Binance Vision，适用CC BY-NC-SA4.0及[已确认版本附加条款](https://github.com/binance/binance-public-data/blob/f446ce3812bd4e5521f21faecd4ae3c6460e49fc/TERMS_AND_CONDITIONS.md)；软件许可单列，不覆盖数据。
