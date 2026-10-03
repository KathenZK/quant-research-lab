# 后续版本索引（只增补冻结根README）

根README.md及v1已由批016 C0锁定，不修改原字节。此文件作为后续版本索引；v2对应的全局治理识别由root另行集成。

| Version | Scope | Consumer |
| --- | --- | --- |
| [v1](v1/manifest.json) | 原账户/pending/统计，不含持仓期限 | M1396/M1463；M1346/M1270继续使用v1 |
| [v2](v2/README.md) | 可选实际成交后持仓收盘计时和强制退出锁存；默认v1兼容 | M1349待独审后pin，不在本变更执行历史 |

v2 engine SHA256 `2b3354dc5c210c66749c5b1e595831abb2adc3f6fff6b9b5f06d22e9fcb39219`；独立 verifier `191961bece1b80c02d074894a8f48fde8c3f6360b5ab564cc69484fae3b14712`。见[v2 manifest](v2/manifest.json)全部文件指纹。没有消费方代码、旧C0或全局登记改动。
