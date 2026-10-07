---
id: disclosure-readability-ticket09-pdr-2026-10-07-16cc740f
kind: evidence
status: current
owner: repository maintainers
scope: ticket 09 formal sessions for the frozen 32-session progressive-disclosure experiment
last-verified: 2026-10-08
verified-against: baseline candidate 867f6709642854721f209a15e362d79a96b3b489; after candidate 16cc740f839876b7b7581a7cbbaf9a318d4c14ac
---

# 票09：常规五类正式会话记录

本报告记录冻结队列第 1–20 行：UI、Chat、Knowledge、Permissions、Tests 五类任务，每类每个候选两次。它只报告本票采集和审计情况，不给出完整实验验收结论。票10负责同一实验的第 21–32 行，票11汇总32个逻辑槽和最终评分。

## 冻结依据与边界

- 实验ID：`pdr-2026-10-07-16cc740f`。
- 冻结记录：`dev-log/disclosure-readability-recovery/ticket08/archive/manifests/frozen-experiment-pdr-2026-10-07-16cc740f.json`，SHA-256 `0cc825816c9f134ccfbd9ea47d5f1722eb7c0ba1c0b91024b1e69f6c995570b1`。
- 队列：`dev-log/disclosure-readability-recovery/ticket08/archive/manifests/frozen-queue-pdr-2026-10-07-16cc740f.csv`，SHA-256 `54458c060c267c2272b69cd2ec5330e95d5cb83c13d200d8c746f6a1c3dba1fe`。本票只执行第1–20行；CSV保持冻结原样。
- Baseline：commit `867f6709642854721f209a15e362d79a96b3b489`，manifest SHA-256 `ea6d866455937115b99f9bcb9d688923f37bd20cac967e34f8d79030bbcb924a`。
- After：commit `16cc740f839876b7b7581a7cbbaf9a318d4c14ac`，tree `6f1c4e340758b92ec8e8d3c165185a98a832253f`，manifest SHA-256 `45e45e0e61b15f812a767978e8354b17ce49bb509c28ffbb703d79811d01303b`。
- 所有正式 attempt 使用 Codex CLI `0.160.0`、请求别名 `gpt-6.1-sol`、medium reasoning；source catalog 文件 SHA-256 `9ce669a7c68b7b64004832d0479fa78563f008d4d2b8cc4e26bfc09346d0f33d`，effective catalog canonical SHA-256 `430739c8d3b67555f5c09c7285892249c3efd922f2ebe67430478df7b8f51cf8`，正式 tool-config SHA-256 `da55cd757919611c8577414c449a548e3c3ec52b3c4f8955596e15d4ab2cd078`。
- 后端解析出的模型修订号不可用。因此这批数据不能被描述为严格可比，也不支持严格对照通过结论。
- 20个逻辑槽共启动23个正式 attempt。19个最终 attempt 提交了六字段答案；slot18 的唯一关联重试仍失败，故无可评分答案。所有原始失败和重试均保留，没有重抽错误答案或按结果改候选。
- 收集器校验每个 attempt 先完整读取候选根 `AGENTS.md`。独立复核重算了所有读事件的 UTF-8 行区间并集；逐attempt均与 collector 的 `unique_bytes_read` 相同。候选路径、manifest、prompt、source catalog、effective catalog 和正式工具配置哈希均与冻结记录吻合；未发现收集器禁读评估材料被返回、外部帮助或污染记录。这里的“禁读评估材料”指rubric、scorer、评分fixtures等收集器拒绝路径；不表示文档治理中的67条protected fingerprint正文都禁止普通读者读取。详细核验在本地 ignored archive 的 `dev-log/disclosure-readability-recovery/ticket09/archive/audits/ticket09-session-reconciliation.json`；完整队列顺序与run ID映射见 `dev-log/disclosure-readability-recovery/ticket09/archive/audits/ticket09-dispatch-reconciliation.json`。
- 原始答案、读事件、JSONL traces、配置、prompt副本、grader原评和裁决均只在本机 ignored `dev-log/disclosure-readability-recovery/ticket09/archive/` 中保存；没有配置外部持久归档，干净检出不能复算原始读数。

## 逻辑槽结果

下表使用每槽最后一次正式 attempt。slot16–18 的首次基础设施失败仍列在尝试链中，不作为额外逻辑样本。`—` 表示失败 attempt 未提交答案，因此没有可用的首读至提交时长。

| 槽 | 候选 | 任务 | Rep | 最终状态 | 秒 | 去重 UTF-8 字节 | 正式尝试与状态 |
| --- | --- | --- | --- | --- | ---: | ---: | --- |
| 01 | baseline | ui | 1 | submitted | 41.777 | 74517 | baseline-ui-20261007T102948Z-248859371129511 (submitted) |
| 02 | after | ui | 1 | submitted | 39.118 | 60083 | after-ui-20261007T103119Z-248944733199206 (submitted) |
| 03 | after | chat | 1 | submitted | 94.812 | 177533 | after-chat-20261007T103119Z-248944765066182 (submitted) |
| 04 | baseline | chat | 1 | submitted | 81.511 | 143446 | baseline-chat-20261007T103119Z-248944764256993 (submitted) |
| 05 | baseline | knowledge | 1 | submitted | 95.089 | 95279 | baseline-knowledge-20261007T103220Z-249000763184017 (submitted) |
| 06 | after | knowledge | 1 | submitted | 111.798 | 228878 | after-knowledge-20261007T103316Z-249051282691652 (submitted) |
| 07 | after | permissions | 1 | submitted | 92.327 | 211683 | after-permissions-20261007T103320Z-249055793201805 (submitted) |
| 08 | baseline | permissions | 1 | submitted | 84.893 | 226736 | baseline-permissions-20261007T103417Z-249109818888351 (submitted) |
| 09 | baseline | tests | 1 | submitted | 56.521 | 171516 | baseline-tests-20261007T103528Z-249176857096650 (submitted) |
| 10 | after | tests | 1 | submitted | 79.561 | 176759 | after-tests-20261007T103532Z-249180854936366 (submitted) |
| 11 | after | tests | 2 | submitted | 72.157 | 175432 | after-tests-20261007T103603Z-249209892181293 (submitted) |
| 12 | baseline | tests | 2 | submitted | 75.249 | 240308 | baseline-tests-20261007T103644Z-249247897216025 (submitted) |
| 13 | baseline | permissions | 2 | submitted | 65.316 | 159848 | baseline-permissions-20261007T103712Z-249273912521573 (submitted) |
| 14 | after | permissions | 2 | submitted | 105.091 | 209148 | after-permissions-20261007T103735Z-249296419369732 (submitted) |
| 15 | after | knowledge | 2 | submitted | 94.350 | 155592 | after-knowledge-20261007T103820Z-249337434338048 (submitted) |
| 16 | baseline | knowledge | 2 | submitted | 78.350 | 116863 | baseline-knowledge-20261007T103837Z-249353443814629 (failed); baseline-knowledge-20261007T104212Z-249553505895872 (submitted) |
| 17 | baseline | chat | 2 | submitted | 72.656 | 181696 | baseline-chat-20261007T103943Z-249415487438718 (failed); baseline-chat-20261007T104350Z-249644441226247 (submitted) |
| 18 | after | chat | 2 | failed | — | 36727 | after-chat-20261007T103948Z-249420485829907 (failed); after-chat-20261007T104524Z-249730893747704 (failed) |
| 19 | after | ui | 2 | submitted | 56.524 | 88186 | after-ui-20261007T104016Z-249445497660081 (submitted) |
| 20 | baseline | ui | 2 | submitted | 52.465 | 81638 | baseline-ui-20261007T104018Z-249447009346481 (submitted) |

slot16、slot17、slot18 首次 attempt 的 Codex trace 均以 `turn.failed: failed to load workspace requirements` 结束；冻结 runner 在读取 collector 正并发写入的记录时遇到瞬时截断 JSON 并退出。按冻结规则，三者各进行了一次关联基础设施重试。slot16 和slot17重试提交；slot18重试再次失败，达到每槽重试上限。重试启动前曾有一次本地catalog路径拼接错误，命令在会话初始化前退出，没有生成collector记录或访问模型；该 preflight 日志单独保存在各slot目录，没有计入正式 attempt。冻结期间没有修改runner或collector；并发写JSON的读取缺陷作为后续工具修复建议。

初始队列按冻结CSV顺序派发，最多三个会话并行；dispatch ledger覆盖第2–20行，slot01的run ID 和运行目录在 `dev-log/.../sessions/slot-01/` 留存。三条失败记录的runner PID在后续关联重试前已退出。重试在完整队列结束后顺序执行，并保留 `retry_of` lineage。所有任务使用相同提示文件哈希和候选manifest；原CSV未修改。

## 阅读成本分项

以下为20个逻辑槽最终attempt按文件区间并集计算的去重 UTF-8 字节，按路径类别拆分。“收集器禁读评估材料”计数仅指rubric、scorer和评估fixtures等拒绝路径，不指document-policy里的67条治理指纹。重复读取另行保留在逐会话审计文件；它不会再次计入以下合计。slot18失败重试的实际读取成本仍保留在after样本里。

| 候选 | 各级指引（根及后代） | 任务路由 | 当前契约 | 源码 | 历史材料 | 收集器禁读评估材料 | 其他 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline | 554388 | 0 | 611540 | 247918 | 77848 | 0 | 153 |
| after | 318752 | 173700 | 610968 | 353649 | 62952 | 0 | 0 |

| 候选 | 重复读取 UTF-8 字节 | 收集器保护材料读取次数 |
| --- | ---: | ---: |
| baseline | 119420 | 0 |
| after | 99748 | 0 |

这些成本数字是描述性证据，不计算验收门槛，也不根据字节变化单独声称效率改善。下表的重复字节按同一最终attempt读取范围内重复返回的UTF-8字节汇总；“收集器保护材料读取”沿用audit的 `protected_reads` 计数口径，区别于收集器禁读的评分材料类别及文档治理67条fingerprint正文。

## 评分进度

冻结rubric要求两名独立grader逐锚点评分，并只在真实分歧时由第三人裁决。19份已提交答案均由A、B独立评分；7个真实分歧槽（01、03、05、12、16、17、20）均由第三人按锚点裁决，其他12槽初评一致，未解决分歧为0。冻结 scorer 对19份评分逐条校验后，11份判为正确、8份至少遗漏一个必需锚点；其中baseline为3/10，after为8/9，另有slot18为after候选的失败未评分样本。这个槽级描述不是总体验收结论，也不把未提交样本从任何最终门槛分母中删除。关键裁决包括slot16的KB-05 missed、slot17的CHAT-02/03/05 met、slot20的UI-03 met且UI-01维持missed。机器可读初评、裁决、逐槽计分分别在本地ignored archive的 `grades/a/`、`grades/b/`、`grades/adjudication/`、`grades/score-derived/`；核对汇总为 `audits/ticket09-grading-reconciliation.json`。slot18没有语义评分文件。所有原评、证据摘录和裁决均保留，不以平均分抵消。

## 后续阅读者隔离

本报告在候选于2026-10-07冻结后创建，当前路径不在baseline或after冻结目录和manifest中。票10继续使用冻结的候选根、prompt、collector及source catalog；候选读取工具仅服务对应候选根，因此本报告及本地grade包不对计时读者开放。没有把报告复制进候选或修改冻结CLI、manifest、prompt、rubric。治理policy将此报告登记为 coordinator-only supplement，以标明它是本轮结果证据，不是读者指导或候选契约。复核时确认报告路径不在两份冻结manifest及各自候选根中。

## 交接

票09已为20个逻辑槽保留最终状态和全部attempt lineage，其中19个可评分、1个失败终态；**正式验收证据仍不完整，不能由本票宣布总体通过**。票10应继续执行冻结队列21–32行；票11需把两票合并，验证全部32个逻辑槽、评分与裁决完整性，并如实报告slot18缺失与模型修订号限制。
