# M1358 脚本

本 ID 独立冷启动适配；不使用 native5m 内核。`run_replay.py` 使用 M0215 已审日线账户公式，替换信号、显式记录延迟意图，完全不引入旧 SMA、回撤停机或跟踪止损。

`metrics.py` 的函数为 M0216 run_replay.py SHA256 `03e9eddb24c127ec779fbe5f20c0764d47cf6aa291b8f5bbb25f628aee6c2911` 的 metrics 精确提取；M0215 参考 SHA256 `b49ded161dab91cc0fb14e9d0e6c163cb642b16c839d5f5b99eefd857c14ce63`。

先运行 `verify_input.py --raw RAW --input INPUT --output 新QA.json` 与 `check_synthetic.py --report 新合成.json`；冻结 C0 并取得独立代码审查 PASS 后，运行 `run_replay.py --input INPUT --output 新目录`；随后 `verify_replay.py --input INPUT --results 新目录 --report 新验证.json`。均离线且拒绝覆盖已有输出。

原论坛源码许可未证，不打包源码。source 下仅自写摘要、URL/hash 和合成结论。实际作者工程不在恢复范围；重建本适配实验不需原论坛类。
