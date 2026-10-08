---
id: docs-governance-readme
kind: index
status: current
owner: repository maintainers
scope: index of internal governance documents — permission model redesign, permission matrix, permission audit archive, engineering backlog, document retention assessment, archived-evidence index, disclosure reading collector and dual-track protocols, calibration guide, and coordinator-only experiment reports; governance material is not published to the public docs site
last-verified: 2026-10-08
verified-against: ticket11 integration worktree; governance index links and scope
---

# 内部治理文档

> audience: maintainers, security reviewers, release owners<br>
> canonical-path: `docs/governance/README.md`

- [权限模型](../permission-model-redesign.md)
- [权限矩阵](../permission-matrix.md)
- [权限审计（历史）](../archive/2026/permission/permission-model-audit-2026-07-05.md)
- [当前工程待办](../backlog.md)
- [文档留存评估](../document-retention-assessment.md)
- [历史证据归档](../archive/README.md)
- [披露阅读收集器协议](disclosure-reading-collector-2026-10-07.md)
- [披露阅读实验票 09 会话记录](disclosure-readability-experiment-pdr-2026-10-07-ticket09.md)：冻结队列前20槽的采集、失败重试、审计与逐槽评分；slot18失败未评分，且不构成整体验收结论。
- [披露阅读实验票 10 会话记录](disclosure-readability-experiment-pdr-2026-10-07-ticket10.md)：冻结队列后12槽的特殊任务采集、逐答案评分与重试审计；slot24无答案，不构成整体验收结论。
- [披露阅读实验票 11 汇总裁决](disclosure-readability-experiment-pdr-2026-10-07-ticket11.md)：合并32个逻辑槽、39个attempt、评分裁决与门槛复算；正确性和常规字节门槛失败，阅读效果未通过。
- [披露阅读双轨协议 v2](disclosure-dual-track-protocol-v2-2026-10-08.md)：新版六字段答案、八任务域锚点、独立评分和双轨门禁；不改写旧分数。
- [披露阅读双轨校准记录](disclosure-dual-track-calibration-2026-10-08.md)：评分者独立校准程序与裁决记录模板。
- [披露双轨实作票 08 结果](../experiments/disclosure-dual-track-ticket08-results-2026-10-09.md)：六次隔离实作、夹具及 clean-restore 证据；整体 v2 门槛仍未通过。
- [披露双轨票 10 最终裁决](../experiments/disclosure-dual-track-ticket10-final-verdict-2026-10-09.md)：区分工程交付、文档状态、新版未通过与旧轨未执行，并记录归档恢复与当前候选门禁位置。

治理材料默认不发布到公开文档站。
