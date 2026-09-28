# Artifacts 非破坏性治理

## 目标与边界

本规范管理 `artifacts/` 的存储与证据保留。目录盘点工具只建立清单，不删除、移动或改写产物；实际清理和迁移在用户授权范围内执行，不能把“未被 Markdown 引用”当作删除依据。

清单只允许读取：

- 路径、文件大小、数量、后缀和目录结构；
- `artifacts/` 目录外 Markdown 的链接与路径引用，用于判断具体产物是否被文档精确引用。

目录盘点不读取 artifacts 内容、不计算哈希、不跟随符号链接；正式复现和证据验收仍按研究契约读取内容、验证哈希。目录级链接、代码动态构造路径和运行时依赖不计入 Markdown 引用覆盖率，因此覆盖率不证明产物是否被使用。

## 预算分级

文件预算：

| 级别 | 文件大小 | 新增或更新要求 |
| --- | ---: | --- |
| `A-normal` | `<= 10 MiB` | 可按普通证据评审；仍须有清楚来源和用途。 |
| `B-review` | `> 10 MiB` 且 `<= 50 MiB` | 合并前说明保留原因、生成命令和可再生性。 |
| `C-externalize` | `> 50 MiB` 且 `<= 100 MiB` | 默认进入 externalize/LFS 评估，不应继续复制版本。 |
| `D-prohibited-new-git` | `> 100 MiB` | 禁止作为新的普通 Git blob；必须外置、LFS 或获得书面例外。 |

家族/主题总预算：

| 级别 | `artifacts/` 总大小 | 要求 |
| --- | ---: | --- |
| `A-normal` | `<= 100 MiB` | 正常审阅。 |
| `B-review` | `> 100 MiB` 且 `<= 500 MiB` | 建立保留说明，阻止无界增长。 |
| `C-externalize` | `> 500 MiB` | 制定可逆外置计划；新增大产物默认不得进入普通 Git。 |

默认门禁按当前工作树实时判定：`B-review` 输出 warning 但不阻断，`C-externalize` 与 `D-prohibited-new-git` 输出 error 并返回非零状态。门禁只约束产物准入和预算，不授权自动删除、迁移或改写历史；确需保留 C/D 级证据时，先完成 externalize/LFS 评估并记录获授权的例外。

## 保留类别

1. **规范证据（`normative-evidence`）**：被版本规格、诊断、主账、decision log 或 runner tracking 精确引用的产物。优先保留；迁移时必须同时更新链接并验证可获取性。
2. **可再生大产物（`regenerable-large`）**：大型训练矩阵、中间特征、搜索网格、缓存预测或可由冻结输入和脚本重建的导出。Git 只保留生成说明、参数、必要摘要和小型验收锚点；禁止按轮次无限累积完整矩阵。
3. **Scratch（`scratch`）**：临时试跑、缓存、调试和本机中间结果。应存入系统临时目录或明确的本地忽略路径，不作为长期证据引用。
4. **本地数据集（`local-dataset`）**：行情湖、训练数据集、DuckDB/SQLite 快照等本地数据。默认不进入 Git；保留来源、UTC 范围、schema、质量门禁和可重新获取方法。
5. **待分类保留（`retained-unclassified`）**：仅凭路径、大小和引用状态无法可靠归类，保留待查；进一步核对生成来源与使用依赖后再决定用途，不能按启发式标签自动删除。

清单中的类别是保守启发式提示：路径含 `scratch/tmp/temp/cache/local` 才提示 scratch；明显的数据集路径和容器后缀才提示本地数据集；大于 `10 MiB`、未引用且后缀常见于矩阵或导出的文件才提示可再生大产物。

## 清单和检查

- 实时检查：[`check_artifact_inventory.py`](../../scripts/governance/check_artifact_inventory.py)。它复用清单生成逻辑，在内存中计算文件/家族预算、引用与保留类别，不读取 artifacts 内容，也不读取或写入持久 snapshot。
- 临时清单导出器：[`inventory_artifacts.py`](../../scripts/governance/inventory_artifacts.py)。默认将 JSON 和 Markdown 输出到系统临时目录；也可显式指定输出路径，用于当次盘点，不将可过期的全量清单作为长期证据提交。

```bash
uv run python scripts/governance/check_artifact_inventory.py
uv run python scripts/governance/inventory_artifacts.py
uv run python scripts/governance/inventory_artifacts.py \
  --json-output /tmp/artifact-inventory.json \
  --markdown-output /tmp/artifact-inventory.md
```

清单按 artifacts 根目录的父路径汇总为“家族/主题路径”，包含文件数、总大小、最大文件和 Markdown 精确引用覆盖率；逐文件路径、大小、引用来源、预算级别和保留提示写入 JSON。导出结果是当时的盘点快照，不代表之后的磁盘状态。

## Git 白名单与 SHA256 sidecar

`.gitignore` 默认忽略所有 `**/artifacts/**`，只放开目录本身和 `*.md`。非 Markdown 产物若要进入 Git，必须同时满足：

1. 路径匹配 [`tracked-artifacts-allowlist.txt`](./tracked-artifacts-allowlist.txt) 中的某一 glob（一行一个 glob，行尾注释家族路径）；
2. 使用 `git add -f` 加入索引。`scripts/governance/check_tracked_artifacts.py` 会检查 `git ls-files` 中所有 `research/**/artifacts/**` 文件，未匹配清单则 FAIL。该检查已加入 `preflight.py` 的 governance 步骤。

已 tracked 的文件不得因白名单迁移而删除。新增大文件时，优先在 Git 中只保留小型摘要、生成说明和 **SHA256 sidecar**（`<file>.sha256`），完整二进制留在本地忽略路径或外置存储；不要把大矩阵、完整预测缓存或原始行情湖提交进仓库。sidecar 用于在干净环境校验回取对象，而不是替代预算门禁。

当前清单覆盖仓库里已 tracked 的全部 artifacts 文件（含 Markdown 与历史治理证据）。新增非 Markdown 证据时先扩 glob，再 `git add -f`。

## 新产物准入

- 先说明产物是不可替代证据还是可再生输出，并记录生成脚本、输入身份和参数。
- 对可再生训练矩阵、特征宽表、模型缓存和批量搜索导出设置轮次/版本保留上限；Git 中只保留能支持结论审计的最小集合。
- 单文件进入 `B-review` 及以上，或家族进入 `B-review` 及以上时，必须在对应研究报告或 decision log 记录保留理由。
- “未引用”只提示待复核。清理前核对代码依赖、运行时依赖和历史审计价值，在用户授权范围内执行并保留恢复依据。

## 可逆 externalize / LFS 迁移方案

获授权的迁移按以下要点保持可恢复性：

1. **冻结基线**：生成清单，记录 Git commit、文件路径、大小、用途、生成命令和文档引用；对拟迁移文件另行计算 SHA256。
2. **选择目标**：不可再生或频繁读取的大二进制优先评估 Git LFS；可公开重建或冷存储的大产物优先对象存储/制品库。敏感数据不得进入公开远端。
3. **并行复制**：先上传副本，不删除 Git 文件；记录稳定 URI、对象版本、SHA256、大小、访问权限和恢复命令。
4. **验证回取**：在干净环境下载并校验 SHA256，运行最小复现或验收锚点；确认文档链接和权限不会失效。
5. **切换引用**：单独提交 pointer/manifest 和文档更新。至少保留一个发布周期的旧对象或可恢复 tag。
6. **受控移除**：验证完成后，在用户授权的处置范围内移除工作树副本。默认不改写 Git 历史；若确需历史瘦身，须另有明确授权，并备份、演练回滚和协调受影响的克隆。
7. **回滚**：从保留 tag、LFS 对象或对象存储按 manifest 恢复原路径，校验 SHA256，再恢复原文档链接。

任何迁移都不得把外部 URI 本身当成证据完整性保证；manifest、内容哈希、可访问性检查和恢复演练缺一不可。
