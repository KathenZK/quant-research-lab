# V3 历史合约别名补充

首次 API 取证之后、V3 发布之前发现原代码 API 的历史可用性受合约重开影响，故增加显式、限时段的别名取证；原契约不改写，补充证据也进入发布哈希。

- `BNXUSDTSETTLED → BNXUSDT`：仅回补原 BNX 历史缺口，截止不超过旧合约结算时刻 `2023-02-11T04:00:00Z`。币安 [重新上线公告](https://www.binance.com/zh-CN/support/announcement/detail/940d0e48493e4627889c3f46371df70b) 明确旧合约更名、旧 K 线仍可用该代码经 `/fapi/v1/klines` 查询。新合约上线 `2023-02-22T14:45:00Z`，不得跨结算/重开区间推定连续可交易。
- `LITUSDTSETTLED → LITUSDT`：只探测现存 2022 年两段缺口和左右端点，不扩展到 2025 年新 LIT 合约。官方 [S3 历史目录](https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?list-type=2&delimiter=%2F&prefix=data%2Ffutures%2Fum%2Fmonthly%2Fklines%2FLIT) 同时返回 LITUSDT 与 LITUSDTSETTLED；以原 2022 年已接受历史两端 OHLCV/笔数匹配作为限区间映射门禁，不以名字相似推断全历史资产同一性。

API 原始回执仍记录实际请求代码，规范行沿用已有底座的原历史代码，映射只在已登记缺口内生效。别名必须至少匹配该缺口一个原有端点；任何数值不一致停止发布。零填充、比例换算、把当前 metadata 回填历史身份均禁止。LIT 的更晚资产身份转换不由此映射解决，研究仍须按历史连续段隔离。
