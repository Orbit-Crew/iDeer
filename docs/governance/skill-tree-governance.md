---
id: docs-governance-skill-tree-governance
kind: reference
status: current
owner: repository maintainers
scope: skill-tree authority relationship (resources/skills authoritative, skills/public upstream landing zone), the upstream skill upgrade flow with lock-SHA diff command and enterprise adaptation checklist, first-round overlap curation verdicts, and the skill review waiver/acceptance principles
last-verified: 2026-10-06
verified-against: worktree docs/doc-disclosure-followup @ d202ae1c3
---

# 技能树治理与上游升级流程

> audience: maintainers, skill maintainers, release owners<br>
> canonical-path: `docs/governance/skill-tree-governance.md`

本文件是技能区（`resources/skills/` 与 `skills/public/`）的治理专节：权威关系、上游升级流程、锁定 SHA 登记、重叠技能清点结论、评审豁免原则与部署态技能发现解析的豁免裁定。它不重复根 `AGENTS.md` 与 `skills/public/README.md` 的声明，只把可执行流程和登记事实集中在一处。

## 1. 权威关系

| 树 | 角色 | 事实依据 |
| --- | --- | --- |
| `resources/skills/` | **权威技能树**（86 个技能）：docker 运行时 bind mount（`../resources/skills:/app/skills:ro`，实际消费边界见 §6）、内网离线包打包源、评审门控 pathspec（`scripts/review_changed_public_skills.py` 的 `SKILL_PACKAGE_PATHSPEC`）、脚本级测试加载器（`backend/tests/unit/skills/skill_loader.py`）与豁免清单（`resources/skills/` 前缀约束）的唯一消费对象 | 根 `AGENTS.md` 项目结构段；票 17（cc3e5b674）把全部消费方从 `skills/public` 切换至此 |
| `skills/public/` | **上游落地区**（15 个技能）：只接收原始上游技能包，不做企业改造（治理 frontmatter、离线行为、rebrand）；上游合并可随时整树覆盖 | `skills/public/README.md`；根 `AGENTS.md` 同款声明 |

推论：对 `skills/public` 与 `resources` 之间的差异做 diff 时，**resources 侧携带企业适配是预期噪声**（见 §3 改造清单）；`skills/public` 侧不回移企业适配，也不为对齐而修改。

## 2. 上游技能升级流程（一条命令可决策）

**升级触发**：上游合并落入 `skills/public/`（或你想主动采纳某个上游技能改进）。

**第 1 步 — diff 决策**：对目标技能执行锁定点对照命令，回答"上游改了什么、我要不要"：

```bash
git diff <锁定SHA> -- skills/public/<skill>
```

当前锁定 SHA 见 §4 登记行（本候选为 `cc3e5b6745f62e79050dc483bdbbc7c915af9ce6`）。输出即上游相对锁定点的全部变更，逐块判定"采纳/不采纳"。

**第 2 步 — 复制**：把采纳的文件复制到 `resources/skills/<skill>/`（手工字节拷贝 + git 提交；两树间不存在任何自动同步机制，见票 16 诊断 `dev-log/d16-resources-tree-sync.md`）。

**第 3 步 — 应用企业改造清单**（复制后逐项核对；除第 3 项为票 18 新增外，均来自票 16 登记的有意适配，缺一项即运行时行为回退）：

1. `description_zh` frontmatter 键（显示层中文描述；上游没有）。
2. `requires-internet` frontmatter 键（离线模式隐藏策略 `app/agentplatform/skills/storage.py` 依赖它）。
3. 脚本示例路径改写：SKILL.md 中 `python /mnt/skills/<name>/scripts/...` → `python /mnt/skills/public/<name>/scripts/...`（沙箱契约：公共技能挂载于 `/mnt/skills/public/<name>/`，见 `SkillsConfig.get_skill_container_path`、`LocalSandboxProvider` 的 `{container_path}/public` 映射、provisioner 的分类卷，以及票 17 promoted 的 music-generation 写法）。
4. rebrand：`deerflow` → `ideer`（如 systematic-literature-review 的 SKILL.md 正文与 `arxiv_search.py` User-Agent；claude-to-deerflow 在 resources 侧整包对应 `claude-to-ideer`）。
5. 离线强制：data-analysis 的 `_require()` fail-fast 替代上游自动 `pip install`，且不下载 DuckDB spatial 扩展；academic-paper-review 的仅离线（不抓取 URL）改写。
6. skill-creator 企业超集：保留 resources 侧多出的 7 个脚本、`LICENSE.txt`、`references/` 与 `quick_validate.py` 的 frontmatter 超集（对应 backend `skill_validation.py`）。

**第 4 步 — 评审 + 测试**：

```bash
# 评审门控（与 CI 同逻辑，可先对单包强制执行）
backend/.venv/bin/python -m deerflow.skills.review.cli resources/skills/<skill> --format json --fail-on error --fail-on-incomplete
# 全量门控口径（diff 驱动；--base-ref/--head-ref 或 --before/--after）
backend/.venv/bin/python scripts/review_changed_public_skills.py --before <old> --after HEAD
# 测试（全部 86 技能的 frontmatter 目录 + 4 个脚本套件 + 豁免清单契约）
cd backend && PYTHONPATH=.:tests .venv/bin/python -m pytest tests/unit/skills tests/test_skill_review_waivers.py tests/test_review_changed_public_skills.py -q
```

**第 5 步 — 更新锁定点**：采纳完成后，把 §4 登记行的锁定 SHA 推进到 `skills/public` 的最新提交（`git log -1 --format=%H -- skills/public`），追加一条巡检行写明日期、新 SHA、依据；同时更新 §4 头部的对照命令。锁定点定义：**`skills/public` 树最后一次被提交触碰的提交**——此后任何上游落地的 diff 只显示真正的上游变更，不含企业侧历史修复噪声。

## 3. 首轮重叠技能清点结论（2026-10-06，票 18）

`skills/public` 全部 15 个技能与 resources 侧逐一 diff + 强制评审（`dev-log/run_force_review.py` 复用生产门控 `run_review`）+ 测试。结论：

| 技能（public ↔ resources） | 结论 | 依据 |
| --- | --- | --- |
| academic-paper-review | 接受 resources 版 | 差异仅为 description_zh、`requires-internet: false`、离线改写（去 URL/arXiv 抓取）——票 16 有意适配；public 侧无更新的上游内容 |
| bootstrap | 接受 resources 版 | 差异仅 description_zh |
| chart-visualization | 接受 resources 版 | 差异仅 description_zh + `requires-internet: true` |
| claude-to-deerflow ↔ claude-to-ideer | 接受（按一对处理） | 差异为整包 deerflow→ideer rebrand（名称、正文、脚本提示串）；public 保留上游原名，resources 为运行时版 |
| code-documentation | 接受 resources 版 | 差异仅 description_zh |
| consulting-analysis | 接受 resources 版 | 差异仅 description_zh |
| data-analysis | 修正 + 豁免 | SKILL.md 9 处脚本示例路径 `/mnt/skills/<name>/` → `/mnt/skills/public/<name>/`（陈旧漂移，运行时路径契约）；`_require()` 的 `__import__` 为票 16 有意离线适配 → sha256 豁免；其余（离线 Excel 装载替代 spatial 扩展）为有意适配，接受 |
| image-generation | 修正 | SKILL.md 3 处脚本示例路径同上；脚本两树本已逐字节一致（票 17） |
| music-generation | 接受（票 17 已对齐） | 差异仅 description_zh + `requires-internet: true`；secret-env-assignment 已有豁免 |
| newsletter-generation | 接受 resources 版 | 差异仅 description_zh + `requires-internet: true` |
| podcast-generation | 修正 | SKILL.md 2 处 + `templates/tech-explainer.md` 1 处脚本示例路径同上；脚本两树本已逐字节一致（票 17） |
| skill-creator | 修正 + 豁免 | `aggregate_benchmark.py:198` 局部变量 `tokens` → `token_counts`（行为不变的重命名，消除 secret-env-assignment 误报，字典键不动）；`eval-viewer/generate_review.py:291` lsof 端口清理 → sha256 豁免（固定可执行文件 + argv 列表 + shell=False，与既有两条 Claude CLI 豁免同型）；企业超集（7 脚本等）接受 |
| skill-reviewer（public 独有） | 接受现状 | 语义评审技能，从未进入运行时树；harness AGENTS.md 明确其 public 定位（评审工具技能） |
| systematic-literature-review | 修正 | SKILL.md 1 处脚本示例路径同上；deerflow→ideer rebrand 为有意适配，接受 |
| video-generation | 修正 | SKILL.md 2 处脚本示例路径同上 |

修正共 6 个文件 18 处路径 + 1 处变量重命名；public 侧一律不动（落地区只收原始上游包，改了也会被上游合并覆盖）。resources 侧自此与 public 的差异 = §2 第 3 步企业改造清单的各适配项（含本次新增的路径改写），均为预期 diff 噪声。

## 4. 上游锁定登记

对照命令（锁定点 `git diff` 见 §2 第 1 步）：

```bash
git diff cc3e5b6745f62e79050dc483bdbbc7c915af9ce6 -- skills/public
```

巡检记录（沿用根 `UPSTREAM_PATCH_LEDGER.md` 巡检行格式；该账本头部已声明其范围仅 `backend/packages/harness/`，技能区登记以本节为准）：

| 日期 | 候选 | 结果 |
| --- | --- | --- |
| 2026-10-06 | 票 18（重叠技能清点 + 升级流程 + 锁定登记） | 初始锁定 `cc3e5b6745f62e79050dc483bdbbc7c915af9ce6`（2026-10-06，"point skill review and tests at resources tree"，skills/public 树最后一次被触碰的提交——内容为 landing-zone README 声明；`git diff cc3e5b674 HEAD -- skills/public` 为空，即当前树与锁定点逐字节一致）。依据：① 此前最近的上游内容变更为 afe9f3502 / 27e571842（企业侧修复恢复）与 0f632ade4（v2.1.0 合并）、a22c6169b / a5e99ab0c（2026-09-13 image/video provider 上游工作）；② 以"最后一次触碰提交"为锁定点使后续上游 diff 零历史噪声；③ 本轮 14 对重叠技能全部完成清点与强制评审，门控 0 未豁免 error，`tests/unit/skills` + 豁免契约 677 用例通过。 |

## 5. 评审豁免与接受原则

- **error 级发现**：修复（首选，如本次变量重命名）或 sha256 精确豁免（`.github/skill-review-waivers.v1.json`，含文件哈希、行号、证据、到期日；文件一变即失效，须重新评审）。禁止为凑零放宽规则或删除断言。
- **有意企业适配被扫描器误报为 error**：以豁免登记，理由写明适配来源（如 data-analysis `python-dynamic-import` 注明票 16 离线改造）；接受理由同时留痕于本文件 §3 清点表。
- **warning 级发现**：不阻塞门控（CI 口径 `--fail-on error --fail-on-incomplete`）。现存 warning 主体为上游 Markdown 围栏被资源解析器误读的样式噪声（`resource.missing` 指向代码块、`escaping-link` 指向 `/mnt/user-data`），接受为上游文档风格产物，不做企业侧改写。
- **豁免到期**：到期即重新评审；若适配仍在，续期并复述理由；若上游已修复，删除豁免行。

## 6. 部署态公共技能发现豁免（票 28，2026-10-06）

**观察**（票 18 §6 相邻观察，票 28 实测确认）：`deerflow` 存储层的 `_iter_skill_files` 只发现 `{skills_root}/{public,custom,legacy,integrations}/` 分类子目录；docker 与内网 compose 把扁平的 `resources/skills`（87 个技能目录，无 `public/` 子目录）直接挂载为容器 `/app/skills` 并以其为 `skills_root`（内网 compose 显式 `DEER_FLOW_SKILLS_PATH=/app/skills`，docker compose 经 `project_root()/skills` 解析到同一路径）。复现实测：扁平根下 `_iter_skill_files` 0 条、`load_skills()` 0 个、`public_skill_exists()` 恒 False；同代码对 `{root}/public` 分类根正常发现（复现脚本与输出：`dev-log/t28-skill-discovery.md`）。

**裁定：设计如此，不改发现逻辑。** 部署态技能可见性走 canonical（Resource 目录）链路，不经文件系统发现：

1. 内容入库：bundled 播种（`bundled-resources.json` 59 个 skill 条目，`source: resources/skills/<slug>`）经 `../resources:/app/resources` 挂载由 `scripts/seed_bundled_resources.py` 复制进 Resource 目录版本库——读的是 `/app/resources`，不是 `/app/skills`。
2. 用户可见面：前端技能页列表走 `/api/resources?type=skill`（DB）；Agent Run 与 workflow 节点消费冻结 resource versions（`frozen.skills` + `create_run_skill_view`）；canonical 沙箱把 `/mnt/skills` 直接映射到冻结运行视图，绕过投影契约（`backend/app/agentplatform/resources/canonical_sandbox.py` 模块头自述；`backend/app/agentplatform/agent_bootstrap.py`："AgentPlatform is canonical-only"）。
3. 依赖文件系统发现的仅有上游非 canonical 面（`GET /api/skills`、bootstrap 代理、IM 渠道斜杠技能、非 canonical 沙箱投影）：企业前端不调用 `GET /api/skills`（仅 `/api/skills/custom/<path>` 导出，读每用户 custom 目录，不受影响），bootstrap 代理在网关组合期被 canonical 包装替换（`app/gateway/services.py` `_install_canonical_agent_bootstrap()`）。部署态无用户可见面因扁平根变暗。
4. `/app/skills` 挂载的现存作用：为上游运行时的 `skills_root` 解析（`skills.path` / `DEER_FLOW_SKILLS_PATH` / `project_root()/skills`）提供一个真实存在的根（每用户 custom 目录树的父根、container-path 身份等）；其公共发现为空是预期，不是缺陷。
5. 非回归：`a942aef14`（2026-08-18）把挂载源从 `../skills`（当时不入 git，无 `public/`）换成 `resources/skills`（自入库起即扁平）——部署态文件系统公共发现从未工作过，无回归点。`IDEER_HOST_SKILLS_PATH`/`DEER_FLOW_HOST_SKILLS_PATH` 自 v2.1.0 起废弃（managed `/mnt/skills` 投影取代宿主技能路径翻译），与宿主侧发现布局无关。

**规则**：除非出现 canonical 面诉求，禁止为部署态给 `_iter_skill_files` 加扁平根自动兼容——仅改发现会造成"清单可见但沙箱投影（`/mnt/skills/public`、`public_skill_exists`、`projection._load_public_skills`、`_source_signature` 各自独立假设分类布局）挂载不出内容"的不一致半修；全修则波及 storage/projection/provider 多个已评审契约（`backend/tests/unit/skills` 677 用例钉住分类布局）。上游升级流程（§2）落地到 `resources/skills` 后，部署态可见性经由 bundled 播种同步进 Resource 目录获得，无需文件系统发现参与。
