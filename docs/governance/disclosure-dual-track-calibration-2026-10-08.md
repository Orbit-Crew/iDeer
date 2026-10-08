---
id: disclosure-dual-track-calibration-2026-10-08
kind: evidence
status: current
owner: repository maintainers
scope: independent grading calibration package for disclosure-reading-v2
last-verified: 2026-10-08
verified-against: docs/governance/disclosure-dual-track-protocol-v2-2026-10-08.md
---

# 双轨阅读协议 v2：独立评分校准记录

本页给评分者独立作答校准题和裁决模板。它是 `disclosure-reading-v2` 的执行辅助；权威锚点与门槛见[协议正文](disclosure-dual-track-protocol-v2-2026-10-08.md)。本校准不重评分、不修改 `pdr-2026-10-07-16cc740f` 的旧答案或 verdict。

## 校准程序

1. A 与 B 分别对协议正文的六个样例标注锚点、适用性、严重错误及候选证据；先各自提交记录，再比较结论。
2. 记录分歧的锚点 ID 和双方依据。第三方只依据冻结题面、答案、候选证据与协议逐项裁定，不查看耗时、成本或另一候选的分数。
3. 记录最后决定、证据定位与所用规则。证据不足时保留 `unresolved`，不能为了完结而猜测。正式轮次存在任何 unresolved dispute 即不通过。

## 独立记录模板

| Anchor ID | A 决定 / 证据 | B 决定 / 证据 | 分歧类型 | 第三方决定 / 规则 / 证据 | 最终状态 |
| --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |

每名评分者只用 `met`、`missed`、`not-applicable`；第三方额外可用 `unresolved`。把答案中支持判断的最短摘录与候选路径/章节并列记录。只给结论而无证据定位，记录无效。

## 必须通过的校准检查

- 同义句与规范术语表达相同 owner 和边界时都给 `met`，不要求 rubric 原词。
- 条件确未触发且答案说明原因时记 `not-applicable`；条件触发但未答时记 `missed`。
- 辅助锚点遗漏单独记分，不使适用必答全通过的答案变错。
- 误把相邻机制当成目标路径（例如以 submit gate 代替 Gateway event dedup）时，目标必答缺失；若建议破坏明确不变量则记 critical。
- 旧报告可支持历史数值，不能证明当前候选通过；错误引用为当前权威时记 historical-authority misuse。

校准产物应随新版正式证据包保存，包括校准答案、A/B 初始决定、第三方裁决、候选证据位置与使用的 protocol ID。此空白模板不代表校准已执行或通过。
