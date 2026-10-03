---
triage: ready-for-agent
---

# Mock E2E 剩余失败诊断与修复扩展规格

用户已授权实施本规格。起点 af4254571b791906485c53022b4ad572ce3047ee，分支 fix/test-system-first-batch，工作树 /home/neowyh/code/AgentPlatform/.worktrees/test-system-first-batch。保留原工作树改动，不推送、不合并。原 01/04/05/06 complete，02 incomplete、03 blocked、07 incomplete。原范围以本扩展规格为准，历史结果保留。

## 目标和边界

原 Mock 全量 413 项，358 passed、55 failed。本批修复全部 55，既有 413 和新增回归全部实际执行。允许按当前已确认产品契约修正过期测试，逐断言记录等价替代。确认产品缺陷时独立修复子票，最小修改，保留生命周期、权限、持久化和事件契约。不能 skips、缩小 lane、放宽断言、增加超时或通过重试掩盖缺陷。不运行 core-full 或真实模型凭据测试。

## 02 诊断

从 frontend/playwright-report/index.html 的内嵌 ZIP 提取实际 55 项失败信息。稳定编号沿用 docs/testing/first-batch-final-validation-2026-10-03.md 中 1..55。每项保存文件、标题、错误、基线完整命令、候选、收集数量、退出码、耗时、环境和实际配置。生产构建模式取得各组聚焦失败基线，分类为过期契约、Mock 缺口/污染、产品缺陷、环境问题、尚未确认。逐项有证据、主归属和修复子票。环境问题不当作产品根因。

单跑失败不能认定顺序污染。顺序依赖必须目标新上下文单跑连续五次通过，指定前序后连续五次失败，实际执行顺序记录、最小前序和状态/请求因果证据。若不成立，记录重新分类，不能虚构修复。重点核验 SSR e2e-user 与浏览器身份、preferences 读写、资源发布/草稿接口、streamedThreadHeads 跨页面清空、迁移路由/语言、删除邻居导航、真实重复消息。

## 03 修复子票

共享基础 F0 只修已证明缺口，类型约束新选项，默认兼容。所有调用者影响核验。
A 能力目录/插件/技能：10-14、20-26、40-41，14项。保留搜索、筛选、独立权限失败、Lark安装授权、导出和移动阻断。
B 账户偏好/模型：27-37，11项。保留身份激活、账户隔离、跨页收藏、恢复、线程设置不覆盖账户、慢读、存储清空恢复。
C Agent/Workflow资源：2-6、50-51、53-55，10项。保留草稿隔离、Unicode码点长度、稳定名称/路由/上下文、技能徽标、创建编辑保存运行。
D 会话消息：15-19、39、42-49，14项。保留陈旧提交取消、项目赋值、编辑重跑、模板阻断、归档恢复、删除重试/清理、邻居/无邻居导航、历史唯一和顺序、压缩追加、滚动。
E 产物：7-9、52，4项。保留流式参数、刷新恢复、草稿预览/冲突、图形和代码回退。
F 移动端：1、38，2项。保留触发器真实点击、无溢出、桌面入口。

## 工作流和验证

每票全新实施子智能体 fork_turns=none，只提供工作树、票据和技能路径。读取 ask-matt/implement/tdd/code-review 以及最近 AGENTS。已有规格直接实施，不重新索要用户许可。一次仅一个实施智能体；两轴审阅由两个智能体并行，以该票起始HEAD为固定基准。每个符号修改前刷新/核验本工作树索引并影响分析，HIGH/CRITICAL先报告，UNKNOWN核验源引用；提交前 detect_changes scope=all 完整结果，partial/truncated不是通过。
每修复片先红后绿，最窄静态检查。原复现生产模式 --workers=1 --retries=0 --repeat-each=5 连续通过，再完整所在spec和默认配置。契约更新逐断言记录依据和替代，不能 first() 隐藏消息重复。产品票匹配合同/集成检查。修复共享Mock核验受影响调用者。独立锁定依赖，UV_CACHE_DIR=/tmp/deer-flow-uv-cache，pnpm10.26.2。doctor和lane预检通过，不绕过浏览器/socket要求；受限环境原样重跑于允许环境。会话日志 dev-log，结论版本控制，秘密不入日志。

## 07 最终验收

冻结候选，python3 scripts/test_inventory.py --collect --json；frontend/pnpm check；根目录 CI=1 UV_CACHE_DIR=/tmp/deer-flow-uv-cache bash scripts/run-test-lane.sh pr-standard；CI=1 bash scripts/run-test-lane.sh frontend-mock-e2e。生产服务器，不覆盖正式workers/retries/timeout/lane范围；显式保存有效值。55个原失败各自按稳定复现命令单worker、零重试、repeat-each=5通过。聚焦重复验收与正式lane分开记录；正式全量及标准lane各运行一次，Mock完整收集并执行既有413项及新增回归，全量无回归且两lane通过。记录子lane和父 TEST_LANE_DURATION，failed/environment-blocked/unexecuted/incomplete分开。同步coverage matrix/migration ledger/inventory/冲突记录，主会话retro，交付提交/工作树/分支/验收报告，清理会话临时文件。不完整不得宣告完成。
