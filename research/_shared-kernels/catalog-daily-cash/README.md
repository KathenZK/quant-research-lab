# Catalog daily cash kernel

冻结v1由M1258 C0日线账户、待执行订单和统计提取，不调用其他策略runner、不含信号或新的控制配置。消费者M1396、M1463以逐文件SHA256锁定；指标各归本family。不得原地更改v1，修复另开v2。

来源commit 783cf6ed8962aa782667f0b193d93b187716dcbc。两事件同时出现时exit优先，移除源RSI字段与control生成；详见[v1 manifest](v1/manifest.json)。

- engine.py: `5b92fea2db2a5da7c4ecd90356adaf8cb533dcedd7378992d2b8e8e324d43782`
- verify_account.py: `338aa731bed5c6e2b46897ab2de190082fa29d96d252a686999610efce2d5dbe`
