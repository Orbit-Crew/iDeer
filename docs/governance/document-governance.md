# 文档治理契约

> audience: maintainers, release owners, CI owners<br>
> status: current<br>
> owner: repository maintainers<br>
> last-verified: 2026-10-04<br>
> verified-against: worktree f0440eef（对 360 路径清单全量重算 sha256 与行数）<br>
> canonical-path: `docs/governance/document-governance.md`

本文说明 [document-policy.json](document-policy.json) 的结构、消费方式与复现步骤。它只记录基线时点（`867f6709642854721f209a15e362d79a96b3b489`）的清单事实和操作方法，不对任何在册文档做"内容现行"或"已验证正确"的断言。哈希一致只证明字节未变，不证明内容正确。

## policy 文件结构

| 字段 | 含义 |
| --- | --- |
| `baseline` | 基线提交、生成口径（`git ls-files *.md` 过滤规则）、哈希算法、行数口径，以及 `baseline_delta`：工作树与基线捕获之间已知的差异清单 |
| `inventory` | 360 个跟踪 Markdown 路径，每条含 `path`、`classification`、`protected`、`sha256`、`lines`，按路径字节序排序。分类合计必须等于 360：246 `engineering-body-review` + 56 `agent-guidance` + 37 `fixture-or-manual-inventory-only` + 21 `protected-baseline` |
| `exclusions` | 跟踪 Markdown 总数（704）与清单（360）之差为 344：341 条按类别排除，3 条基线后新增文档以补充项登记（见 `supplements`） |
| `protected_files` | 67 条保护指纹，来自基线捕获的 governance-baseline。其中 61 条在清单内（40 个上游轨规则文件 + 21 个 protected-baseline 文档），6 条在清单外（`backend/packages/harness/**` 的 README）。保护文件正文不改，适用性只在这里描述 |
| `guidance` | 28 个 AGENTS.md 规则文件的字节数；每个都有同步生成的 CLAUDE.md 镜像（对应清单中 56 个 agent-guidance 行）。同步命令：`python3 scripts/sync_agent_guidance.py --write` 后跑 `--check` |
| `import_baseline` | 导入基线工作树时保持不变的 10 个文件的哈希 |
| `authority_topics` | 按主题登记的权威来源，只收录当前已声明的权威（`docs/README.md` 的 current-source 表及 AGENTS.md 任务文档图）。产品治理与上游实现按 `scope` 区分，允许同主题不同范围各有一个权威。未定主题不登记 |
| `supplements` | 10 个补充项，每条含 `path`、`registration`、`sha256`、`lines`、`classification`、`protected`、`role`、`referenced_by`：7 个 `reference-closure`（被在册现行文档引用、在 360 种子之外的组件/运维 README，位于排除集合内）+ 3 个 `post-baseline-addition`（基线捕获后新建的工程文档，2026-10-04 登记：`docs/governance/document-governance.md`、`docs/agents/task-routing.md`、`docs/project-state.md`）。登记为 inventory-only，种子数保持 360 不变；检查器把补充项路径视为已覆盖，并要求其在候选中存在 |
| `evaluation_fixture` | 八类任务提示（逐字来自评估契约的 `tasks` 字段）、每任务两次独立会话协议、300 秒定向时限、记录口径。基线运行状态为 `pending` |

清单行不复制文档状态。文档的 `status`/`last-verified` 等 frontmatter 仍是文档状态的唯一来源；清单只记录覆盖事实（分类、保护标记、哈希、行数）。

## 消费方式

按规格（`docs/specs/2026-10-04-doc-governance-dual-track-spec.md` 的 Engineering Documentation Disclosure Track 一节），组 2 将新增只读检查器 `scripts/check_documents.py`（`--repo-root`、`--revision`、`--json`；退出码 0/1/2）。该检查器以本 policy 文件为范围、排除、保护指纹与权威主题的持久来源：无 `--revision` 时检查工作树，有 `--revision` 时只读该候选。检查器落地前，本文件的核验依靠下一节的手工步骤。CI 只在候选修订上做校验，不修复、不改写文档。

标准巡检入口：`scripts/check_doc_hygiene.sh` 一条命令依次运行上述检查器、guidance 镜像一致性（`sync_agent_guidance.py --check`）与保护指纹独立复核（对 `protected_files.fingerprints` 的 67 条重算 sha256），输出按入口前缀区分，任一失败即非零退出并输出聚合摘要；全绿输出一行 PASS。该脚本只检查工作树，指纹读自本 policy（受跟踪），不依赖 git-ignored 的基线捕获文件；候选修订核验仍用检查器的 `--revision`。

## AGENTS.md GitNexus 豁免行

根目录 `AGENTS.md` 的 GitNexus 管理块（`<!-- gitnexus:start -->` 到 `<!-- gitnexus:end -->` 之间）的 "## Always Do" 一节里，有一条手工加入的行，以粗体引导语 `**Doc-only commits are exempt from re-indexing.**` 开头。它的权威语义：纯文档提交（提交中每个变更路径都以 `.md` 结尾，不含代码、配置、工作流、脚本或测试）通过在提交信息里记录 `partial` 结果满足 detect-changes 要求，无需重索引（`--index-only`）；这是唯一允许 `partial` 的情形，其余任何提交仍须完整执行块内的 MUST。

GitNexus 重索引会重新生成整个管理块，可能无声吞掉这条手工行，因此该行受机械守卫：`scripts/check_documents.py` 的 `gitnexus-exemption-missing` 规则断言该粗体引导语出现在 `gitnexus:start` 标记之后。规则只匹配引导语、不匹配整句——引导语之后的措辞可以演进；候选完全没有管理块时不报，整块移除属于明示的治理决定，不是本规则针对的丢失方式。重索引后必须回填该行，检查器报错即为回填提醒；同步镜像 `CLAUDE.md` 的字面一致由 `sync_agent_guidance.py --check` 保证，无须单独守卫。

## 清单核验复现

对一个候选修订（工作树或 `--revision` 指定的检出）：

1. 路径集合：`git -c core.quotepath=off ls-files '*.md'`。清单 360 条、`exclusions` 各类 341 条与 3 条 `post-baseline-addition` 补充项的并集应与输出完全一致（另 7 条 `reference-closure` 补充项在排除集合内）。检查器同时要求补充项路径在候选中存在。
2. 哈希与行数：对 `inventory.files` 逐条重算 sha256 与行数并比对。`baseline_delta` 里登记的差异是唯一预期偏差。
3. 分类合计：246 + 56 + 37 + 21 必须等于 360。
4. 保护指纹：对 `protected_files.fingerprints` 的 67 个路径重算 sha256，全部一致才算干净；指纹失配说明保护文件被改动，按补丁台账流程处理。
5. 规则镜像：`python3 scripts/sync_agent_guidance.py --check` 应通过，且 `guidance.bytes` 与实际字节数一致。

有 `--revision` 时，第 2、4 步用 `git show <rev>:<path>` 或 `git archive <rev>` 读内容，不读本地未提交修改，避免未提交内容掩盖候选问题。

## 阅读评估复现

八个任务类别：`ui`、`chat`、`knowledge`、`permissions`、`runtime`、`tests`、`upstream`、`history`，提示词逐字取自 policy 的 `evaluation_fixture.task_prompts`。

每个类别跑两次独立会话：相同模型与工具配置；会话无历史；只读候选修订内的仓库指引；从候选根目录 `AGENTS.md` 开始；定向时限 300 秒。每次会话记录：`elapsed_seconds`、实际读取字节、是否误把历史计划/决策当现行依据，以及六个答案字段（entry、constraints、authorities、relevant_decisions、validation、unknowns）。

边界：评估者只拿候选修订和任务提示，不读评分细则、阈值或他人会话记录；答案记录不是源码核验的替代品；基线运行在协调者完成干净根运行并评分之前保持 `pending`，任何跟踪文件不得先声称测量结论。

## 清单覆盖不是语义审查

哈希、行数、分类合计、链接与指纹检查只证明清单覆盖和字节状态。一篇文档是否与代码一致、是否仍是当前做法、历史记录适用于哪段时期，靠人工审查判定，结论写进文档自己的 frontmatter（`status`、`last-verified`、`verified-against`），不写进本清单。不要因为某行哈希没变就认定它内容现行，也不要批量刷新验证日期来代替内容审查。

## 基线变化时

接受的基线提交变化后：重新捕获清单与指纹，逐条比对旧行，把全部差异记入 `baseline_delta`（路径、旧/新哈希与行数、原因），同步更新分类合计；不得静默覆盖行或吞掉差异。保护文件变动必须先走对应补丁台账，再更新指纹。种子数保持 360；新增文档先进 `supplements`，随下一轮基线捕获决定是否入种子。
