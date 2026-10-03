# M0298 当前恢复入口

当前状态：2024原生5m固定4个策略配置和1个同窗买入持有对照已执行，独立全账本审计及使用独立重建输入的新目录冻结重放通过。保真仍为HYPOTHESIS，数据与结果为DIAGNOSTIC_ONLY；严格复现0，不是OOS，不晋升或部署。

## 当前版本

使用[执行版本v1完整恢复命令](RECOVERY-execution-v1.md)：包含固定输入恢复前提、shell失败硬停、兼容Python/依赖、原字节C0和release、冻结4+1重放及可运行独立Decimal账本CLI。输入/代码/环境的完整hash必须一致，不能套用旧C0运行改版。

[实际恢复回执](artifacts/execution-v1/recovery-receipt.json)：新目录与新Python进程，使用独立重建的规范输入，33输出文件中31个逐字节一致；summary仅峰值RSS与其manifest不同，业务summary完全一致。市场输入、全长净值/信号/交易/订单不包含在公共包；新网络恢复仍需具备适用授权，不得绕过403/451或以改变来源/窗口/周期替代原冻结数据。

## 历史准备阶段

[2026-10-03约12:29UTC的原准备阶段恢复说明](history/preparation-v0/RECOVERY.md)及[原21文件准备包](history/preparation-v0/README.md)按原字节保留。当时首次请求Tunnel403、尚无输入/C0/历史结果，是当时的真实状态；后续用户授权同源重试成功后的执行版本见上方当前入口。不能把旧阻塞说明当成现在仍未完成。
