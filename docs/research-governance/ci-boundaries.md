# CI 与私有研究验收的边界

GitHub 分支保护继续要求 `governance`，检查公开仓库的契约、索引、来源消费登记、产物登记、冻结代码和无私有输入的测试。通过表示仓库变更符合这些检查，不表示研究收益有效、完整资金费已验证或可以实盘。

Python 最低版本与 CI 均为 3.12。已有冻结研究脚本使用 3.12 的 f-string 语法；旧的 3.11 配置无法解析这些脚本。本机验证使用 3.12，保留冻结脚本原样。

## 私有数据测试

需要未入 Git 的数据湖、训练产物或冻结回测输出的测试使用 `local_data` 标记。为保持已有研究 manifest 中的测试文件摘要不变，旧测试的精确函数登记在 `tests/local_data_cases.json`，每项说明输入和原因。新增独立单元测试不得因所属家族有私有数据而整文件跳过。

公开 CI 执行 `uv run --locked --extra dev --extra ml pytest -q -m "not local_data"`。本机备齐对应研究输入后执行 `uv run --locked --extra dev --extra ml pytest --run-local-data -m local_data`，也可指定单个家族的测试文件。显式运行时，缺失输入和断言失败保持失败，不再把 `FileNotFoundError` 改成跳过。

已移除 GitHub 托管环境里无法取得私有数据、且允许失败的 `research-local-data` 作业。现有测试自行声明的其他跳过条件仍按原测试契约处理。

## 冻结源码和历史证据

- 活动研究源码扫描覆盖 `scripts/` 下的嵌套目录；`research/**/artifacts/` 内的保存副本属于证据，不作为新活动入口重复登记。显式登记的活动消费者仍须存在并满足调用契约。
- 已归档的第三方原文快照允许只在本机保存。只有同时满足 `archived-third-party-source` 分类和 `artifacts/` 路径的登记项允许在 Git checkout 缺席。
- 共享内核支持 README 直接登记文件 SHA256，也支持 README 固定 manifest 的 SHA256、manifest 再固定文件 SHA256；每层都校验。MTCS 原始 `capture.py` 是 TSPR 提取来源，保留其精确路径与原始摘要，其他新增复制继续拒绝。
- 已保存的九个历史测试文件含旧格式写法。仅对列明的文件和规则保留 lint 例外，`tests/frozen_test_lint.json` 固定其字节摘要，CI 校验摘要与配置一致。修改这些测试必须移除相应例外并修复格式，不得让例外覆盖新代码；其他错误规则继续运行。

这些边界只决定在什么环境运行检查，不改变冻结研究的输入、引擎、参数、结论或晋升状态。
