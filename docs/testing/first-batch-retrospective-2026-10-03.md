---
id: docs-testing-first-batch-retrospective-2026-10-03
kind: evidence
status: archived
owner: test maintainers
scope: first test-system batch session retrospective (2026-10-03) — severity-ranked environment and workflow proposals on comparable diagnosis evidence, GitNexus worktree and deletion coverage, guidance-file side effects, ticket baselines, and durable handoff artifacts
archived-reason: retrospective of the pre-recovery batch session; the recovery batch continued the work and its retrospective is first-batch-retrospective-2026-10-06.md — recommendations here are historical input to that batch, not a current plan
---

# 首批测试改进主会话复盘

本次按既定票据执行，01、04、05、06 已完成；02 incomplete、03 blocked、07 incomplete。PR 标准验证通过，Mock 全量 358 passed、55 failed。这里按严重程度提出环境与工作流改进建议，不将尚未确认的产品原因写成事实。

## 高优先级：让诊断证据可比较

T2 首次通过 tee 记录目标探针时丢失真实退出码，后来用原命令重跑取得 exit 1；部分独立探针没有外层耗时。T7 的日志重定向及退出码捕获保留了完整 lane 结果。建议提供一个本地命令记录器，保存开始/结束时间、真实退出码、候选 SHA、配置指纹和完整 argv；有管道时显式捕获 PIPESTATUS。已有 runner 证据写入器应继续作为正式 lane 的唯一入口，诊断记录器不引入第二套结果契约。

T2 显式使用 dev-server 和 CI 条件，T7 正式 lane 使用 production webServer。history 排序目标在前者通过、在后者因重复文案定位失败，前序和服务模式同时变化，无法证明顺序因果。建议诊断入口保存有效服务模式、worker 数、retry 设置及浏览器版本，比较前拒绝环境不一致的因果结论。报告只能说本次实际观察到一 worker，无可靠重试证据；本次曾基于 CI 条件推测两次重试，已更正。

## 高优先级：核对 GitNexus 的工作树和删除覆盖

本次 hook 曾提示另一提交 c7844a2 的索引过期，但当前工作树 meta.json 指向自己的批次基点。建议 hook 用 git worktree 的绝对路径绑定索引，并校验 repoPath 与 lastCommit，避免同名仓库注册项混用。

三组删除的 detect_changes 只映射文档，未映射已删测试。报告因此保留 UNKNOWN，并用删除前影响分析、路径引用检索、成对通过基线及逐项断言映射补充证据。建议给工具增加删除文件覆盖检查，对比 git diff 文件集与图谱映射文件集，明确列出未解析路径。零受影响流程不应被当作这些路径的安全证明。

## 中优先级：控制测试启动的指导文件副作用

Next dev 多次自动追加 frontend/AGENTS.md，停止服务后只恢复该自动片段；最终 28 对指导文件检查通过。仓库已有 scripts/sync_agent_guidance.py 和 CI revision check，不需要新增一套同步规则。建议测试记录器保存启动前后的指导文件差异，结束后提示已确认的生成片段，避免误提交或覆盖其他人的有效修改。

## 中优先级：把环境初始化和票据基准写清楚

独立 uv 环境与 node_modules、精确 pnpm 10.26.2、示例配置及浏览器预检使本批没有携带原工作树改动。受限 Chromium/socket 探针失败后，相同命令在允许环境通过；Doctor Ready 不能替代浏览器预检。建议新工作树初始化脚本一次输出这些实际检查和配置指纹，不写入真实凭据。

本地票据最初把批次起点称为“起点”，与每票开始 HEAD 混淆，造成复审往返。已明确批次基点 a1bb73a，每票固定基准为实施开始 HEAD。后续票据模板应分别填写 batch_base 与 ticket_base，并让审阅入口验证该 SHA。

## 低优先级：减少会话依赖并保留可接手产物

冲突台账原始 message-merge 历史实际位于 deerflow-v2.1.0，而一般导航指向 main 台账；本次核对后在正确历史处追加记录。建议测试迁移票直接指向相关历史段落。

T7 子智能体在报告收尾触发使用额度限制。主会话使用已完成日志和版本化草稿继续审阅，没有重跑通过的 lane。建议长 lane 定期保存候选、日志路径、运行 session 和实际摘要，便于接手；审计结果应尽快写入版本控制文档，不能只留在即将清理的 dev-log 中。现有 pre-commit 已包含 lint、format 和本地文件拦截，本次不再提出重复的检查体系。
