# M0316 决策记录

- 2026-10-03 10:51Z：核唯一协调者最新claims、固定分配commit，开始C0。旧预审READY_NOT_ASSIGNED仅历史快照；不改其他ID/全局清单
- 10:53Z：固定官方源码3821B/SHA核同；无新的市场数据请求。冻结actual hl2、原参数与limit GTC/market stop，不静默改market
- C0：原类匹配、双数据快照、17合成通过。独立审查指出并核清offset相等原stop边界、terminal取消，以及非native路径/保守ROI时钟标签
- 11:05:41Z：独立draft静审通过后，冻结C1完整协议及26对象；审查者复核最终hash放C2，收益前无本ID结果
- 11:06:43Z至11:06:46Z：真实历史回放exit0，4预设case+1控制，singlethread、1GiB cap
- 11:07Z：四策略case负收益；不做结果导向调参或追加实验。费用非单调需核其机制，不能删改异常结果
- 11:08Z：独立Decimal全5case逐订单/成交/风险/账户/指标PASS；45prefix与异快照本地恢复通过；只投影轻量/月末/私有日Graph，不新增回测
- 交付：HYPOTHESIS/DIAGNOSTIC_ONLY/strict0，未晋升、未部署。最终QA锁publication manifest后不再改写；父协调者完成C3远端保存/回读

## 2026-10-03 11:23Z 发布修订v1：恢复说明格式兼容性

父协调者C3实际恢复发现v0文档把继承轻量manifest传给旧builder的--expected-manifest；该接口要求protocol，轻量清单无此字段。已离线复现错误并保留v0文档/发布清单原字节于私有历史及原Library版本。仅修非冻结恢复文档，新增离线比较工具，primary/rebuild两快照均实际核25月75对象bytes/SHA与canonical、schema/timeframe/builder匹配。未来可合法捕获时先无expected捕获再独立light比较；--expected仅能使用真实完整原始manifest。旧C1规格与26对象hash、全部收益/风险结果不变，无新策略、收益计算或网络请求。修订需独立复审新publication manifest，父线程保存同Library ID新版本；原结果仍HYPOTHESIS/DIAGNOSTIC_ONLY/strict0。
