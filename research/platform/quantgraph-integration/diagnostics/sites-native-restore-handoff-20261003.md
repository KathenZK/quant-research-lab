# 原Site原生源码恢复：工具侧交接

当前官方Sites hosting技能提供Git源码恢复路径：在空的指定源码目录中运行插件自带 `scripts/site-workflow.mjs --project-id <原项目ID>`，以隐藏stdin提供原生工具返回的短期源码凭证，不传archivePath，保存返回的source对象及checkout_path。无需先下载164MB部署归档。原项目身份只能从已核实的Sites响应复用，不能新建替代Site。

## 当前最小缺项

1. **官方插件脚本的可执行本地路径**：当前是portable执行环境，executor技能列表为空。在允许的技能资源路径读取插件根及hosting包下的site-workflow.mjs均返回 `failed to read skill resource`；技能Markdown可读。未扫描凭证目录，未自行实现替代上传/认证脚本。
2. **明确的短期源码凭证授权**：get_site没有返回可复用source_repository_credential。官方 `create_source_repository_write_credential` 会创建短期仓库限定Git凭证；用户仍禁止创建凭证，父线程已提交精确授权问题，尚未收到回复。未调用该工具。

## 父线程可接手的恢复步骤

1. 在具有官方Sites插件脚本的已授权执行器中读取同版本hosting技能，取得真实plugin-root路径；不能猜远端下载URL或拆分归档绕过工具上限。
2. 复用已核实原项目ID调用get_site，复核现有所有者、访问范围和版本。当前已核实owner-private、version8 active；若状态变化应重新协调。
3. 仅在用户明确允许短期源码凭证后调用 `create_source_repository_write_credential({project_id: 原ID})`，不指定publish_on_push。凭证仅存在会话内存及隐藏stdin，不写文件或shell参数，不回传token。
4. 在空目录启动官方工作流，TTY开启、yield_time_ms=1000；等候隐藏stdin提示，再传一行JSON，yield_time_ms=30000。首次打开不指定archivePath，不触发源码修改或发布。
5. 返回工作流的checkout_path、verified commit_sha及无秘密的完成状态。父线程路径不能假定在本执行器存在；如换执行器，应在持有源码的执行器继续工作或走正常授权传输。
6. 检查恢复源码是否实际包含现站基线资源及所需私有runtime。Git检出成功只证明源码恢复，不证明R2/D1或私有研究库已恢复。仍应通过既有工具取得必要组件，不使用公共样例、空数据库或旧元数据冒充。

本交接没有授权网站数据写入、激活、部署或共享变更；现有批注overlay和CAS父批次要求保持。行情许可确认未完成时，新增派生成果发布继续暂停。官方脚本缺失是执行环境问题，与用户凭证授权是两个独立阻塞。

## 授权及接口实测更新

2026-10-03 08:03:59 UTC用户已明确批准原Site短期源码凭证及此次Site操作，无须再问。随后原生凭证接口调用成功：provider为cloudflare_artifact，Git认证模式http_extra_header，publish_on_push_accepted=false。秘密只保留在会话内存，没有写入文件、Git或消息。官方工作流脚本仍不可读取，因此尚未开始Git检出，源码和runtime均没有恢复回执。现在唯一的源码打开前置阻塞是官方脚本在执行器中的可用性；短期凭证若届时过期，可在已批准相同范围内重新取得，不能扩大权限。
