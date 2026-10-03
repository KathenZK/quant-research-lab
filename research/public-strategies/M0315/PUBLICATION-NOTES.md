# M0315 公开交付映射

执行者原冻结提交保存在私有恢复材料。公开前检查发现来源预检包含私有 Library 定位信息；原文件及原发布候选清单均未推送公开远端。新公开树从干净 Lab 主分支构造，不包含该私有本地提交的祖先历史。

- C0 协议、冻结运行代码、数据／代码哈希、指标和结果全部保持原字节，不重新冻结或重跑选择参数。
- C0 的 `supporting_evidence_hashes["specs/source-preflight.json"]` 仍为原私有证据 `954a37ef354def5bed39c9a074abc052bd49ac319c1bda163bc495de4128d108`。该原文件留在私有恢复包，公开 Git 不包含它。
- [公开来源预检](specs/source-preflight-public.json) 去除了私有 Library ID 和读取回执指纹；原文、公开出处、源码指纹、参数与预审结论不变。它是明确派生件，不能拿它冒充 C0 原文件。
- 中文研究报告仅更新来源链接并说明此映射，原报告留在私有包。原发布候选清单未作为公开清单使用；本树 [publication-manifest.json](publication-manifest.json) 精确列出实际允许文件。
- 本地恢复包和 root 独立恢复不是 Library 远端备份。当前 Library 支持上传流程阻塞，无新备份成功声明。公开 Git 保存代码、逐策略说明和轻量结果，不包含原行情或完整账户序列。
