# Binance V3 统一研究输入治理契约

## 授权、范围与不可变输入

用户接受统一 V3 底座建议。本轮沿用 `2026-09-05T15:45:00Z`，不延伸实时窗口、不下载全市场 1m/5m、不改冻结策略和缓存。V3 为 `binance.perp.ohlcv.15m.history.v3`，manifest SHA256 为 `e90fe921e03bccf78dea0b29675470a3661baa5cd38af8dadc2202bb0e475e8f`。V1/V2/V3 及旧高周期发布目录不覆盖。

## 交付与门禁

1. 从严格验证的 V3 已裁决行生成 `binance.perp.ohlcv.{1h,4h,1d}.from_15m.v2`。沿用 UTC 00:00 相位和 4/16/96 根完整组件公式；保留 V3 日度修复来源，不重新应用旧 V1 来源过滤。截断到每个周期最后完整闭合桶；未完整桶不补造。发布前 SQL 全量检查，发布后 catalog 严格验证，并记录输出连续段。
2. 资金费率以本地标准化主目录为库存输入，保留输入指纹和来源。重叠记录只有数值一致才能裁决；毫秒时间保留，不把相近时间自动归并。旧 `funding_interval_hours` 不直接作为历史结算日历。真实费率事件不是 OHLCV，不经 OHLCV catalog 冒充价格数据。
3. 对 V3 标的的资金费率尾部、内部可疑长间隔、缺少历史头部进行官方查询；保留 URL、参数、抓取时点、原文和哈希。完整分页、不把网络失败归为无数据；429/418 停止或按要求退避，不绕过限制。缺失率不得填 0，当前 fundingInfo 不回填为历史已知日历。若官方无法补回或无法证明历史频率，保留机器可读限制，不宣称全历史 funding complete。
4. 有效标的规则区分观测有效性与资产/交易资格：零成交、断档必须重置连续计算；当前 exchangeInfo 只作为当前身份快照，不能证明历史 PIT。不能用当前活跃名单过滤全部历史后声称无幸存者偏差。研究若要求身份确认，必须额外给出有证据的有效期。
5. 新读取接口显式选择固定版本、cutoff、缺口策略，分段计算，不自动替换旧消费者。测试覆盖缺 K、零成交、乱序、重复、未来截止、身份未知、资金费率缺失与冲突拒绝。
6. 所有新发布记录 source、input hash、builder hash、配置、质量、已知限制；新增数据写 staging 后验收发布。支持阶段续跑，已有阶段校验身份后复用。磁盘低于 30 GiB 停止。

## 明确不承诺

不是全历史行情重新下载、不是完整历史资产身份/交易日历认证、不是全市场盘口/持仓量治理、不是策略 PASS 或实盘准备完成。不能以狭窄的行质量 PASS 覆盖 funding 或 PIT 未完成项。

规范：[data-lake-spec](../../../../docs/data-lake-spec.md)。上游：[V3 验收](../diagnostics/binance-15m-history-v3-closeout-2026-09-06.md)。官方资金费率字段、分页和限额：[Binance market data](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data#get-funding-rate-history)。
