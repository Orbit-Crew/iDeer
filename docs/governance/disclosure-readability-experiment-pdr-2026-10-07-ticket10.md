---
id: disclosure-readability-ticket10-pdr-2026-10-07-16cc740f
kind: evidence
status: current
owner: repository maintainers
scope: ticket 10 formal sessions for the special-task slots in the frozen 32-session progressive-disclosure experiment
last-verified: 2026-10-07
verified-against: baseline candidate 867f6709642854721f209a15e362d79a96b3b489; after candidate 16cc740f839876b7b7581a7cbbaf9a318d4c14ac
---

# 票10：重点任务正式会话记录

本报告记录冻结队列第 21–32 行：Runtime、Upstream、History 三类任务，各候选两次。它只记录票10的采集、逐答案评分和审计，不给出整轮实验验收结论。票11负责与票09合并 32 个逻辑槽并判断完整性；此前 slot18 仍缺可评分答案。

## 冻结依据与协议

- 实验 ID：`pdr-2026-10-07-16cc740f`。
- 冻结记录：`dev-log/disclosure-readability-recovery/ticket08/archive/manifests/frozen-experiment-pdr-2026-10-07-16cc740f.json`，文件 SHA-256 `0cc825816c9f134ccfbd9ea47d5f1722eb7c0ba1c0b91024b1e69f6c995570b1`。
- 冻结队列：`dev-log/disclosure-readability-recovery/ticket08/archive/manifests/frozen-queue-pdr-2026-10-07-16cc740f.csv`，文件 SHA-256 `54458c060c267c2272b69cd2ec5330e95d5cb83c13d200d8c746f6a1c3dba1fe`。CSV 未修改；本票按队列顺序首派第 21–32 行，失败后的关联重试不改变首次派发顺序。
- Baseline：commit `867f6709642854721f209a15e362d79a96b3b489`，候选 manifest SHA-256 `ea6d866455937115b99f9bcb9d688923f37bd20cac967e34f8d79030bbcb924a`。After：commit `16cc740f839876b7b7581a7cbbaf9a318d4c14ac`，tree `6f1c4e340758b92ec8e8d3c165185a98a832253f`，候选 manifest SHA-256 `45e45e0e61b15f812a767978e8354b17ce49bb509c28ffbb703d79811d01303b`。
- 所有实际会话使用 Codex CLI `0.160.0`、请求别名 `gpt-6.1-sol`、medium reasoning。冻结 source catalog 文件 SHA-256 为 `9ce669a7c68b7b64004832d0479fa78563f008d4d2b8cc4e26bfc09346d0f33d`，effective catalog canonical SHA-256 为 `430739c8d3b67555f5c09c7285892249c3efd922f2ebe67430478df7b8f51cf8`，正式 tool-config SHA-256 为 `da55cd757919611c8577414c449a548e3c3ec52b3c4f8955596e15d4ab2cd078`。所有记录及配置均核对为同一哈希。解析出的后端模型修订号不可用，因此不能声称严格模型可比。
- 正式协议要求完整首读候选根 `AGENTS.md`，仅通过 collector 读取或搜索候选，并在最多 300 秒任务时限内提交六字段答案。16 个实际 attempt 均先完整读取根指引；日志中的模型工具仅为 `read_candidate`、`search_candidate`、`submit_answer`。无外部帮助或污染记录。

## 逻辑槽结果

每个逻辑槽只计最后状态；重试仍作为原槽的关联 attempt 保存。`—` 表示没有提交答案，因此没有正式提交耗时、提交字节指标或评分；失败前实际读取字节仍在下文单独记录。

| 槽 | 候选 | 任务 | Rep | 最终状态 | 正确 | 秒 | 去重 UTF-8 字节 | attempt 数 |
| --- | --- | --- | ---: | --- | --- | ---: | ---: | ---: |
| 21 | baseline | Runtime | 1 | submitted | 是 | 115.301 | 225497 | 1 |
| 22 | after | Runtime | 1 | submitted | 是 | 105.809 | 247914 | 1 |
| 23 | after | Upstream | 1 | submitted | 是 | 144.562 | 139912 | 2 |
| 24 | baseline | Upstream | 1 | failed；无答案 | — | — | — | 2 |
| 25 | baseline | History | 1 | submitted | 否 | 132.395 | 119892 | 1 |
| 26 | after | History | 1 | submitted | 是 | 120.056 | 142992 | 2 |
| 27 | after | History | 2 | submitted | 是 | 89.770 | 122412 | 1 |
| 28 | baseline | History | 2 | submitted | 否 | 89.981 | 112911 | 2 |
| 29 | baseline | Upstream | 2 | submitted | 是 | 63.624 | 108670 | 1 |
| 30 | after | Upstream | 2 | submitted | 是 | 130.115 | 121918 | 1 |
| 31 | after | Runtime | 2 | submitted | 是 | 82.838 | 184688 | 1 |
| 32 | baseline | Runtime | 2 | submitted | 是 | 99.044 | 268707 | 1 |

12 个逻辑槽均已首派，产生 16 个实际 attempt：11 个提交，5 个协议失败。slot23、24、26、28 各有一次合规关联重试；slot23、26、28 的重试提交，slot24 的重试再次失败并达到单槽上限。slot23 首次失败后曾有一次重试命令因原始记录尚为 `started` 被 runner 拒绝；该命令未启动模型会话、不计实际 attempt，拒绝和 prompt 副本另记在本地 dispatch ledger。runner 的并发 JSON 读取缺陷在冻结期间未修改。

五个失败 attempt 的 collector 记录均保留。用其原始 read/search 行区间重算失败前读取的唯一源字节分别为：slot23 首次 120287；slot24 首次 65034、重试 77008；slot26 首次 114686；slot28 首次 38869。对应从首个成功内容读取到协议关闭的时长依次为 148.759、99.841、154.802、40.644、24.565 秒。收集器在完整根 `AGENTS.md` 首读通过后设置 `started_monotonic`，并在支持的失败关闭中设置 `closed_monotonic`；这些差值从首个成功内容读取计到协议关闭，不能当作提交耗时或正确答案耗时。slot24 没有答案、grader 记录或历史误用判定。

## 评分与裁决

11 个已提交答案均由两名独立评分者逐 anchor 评分，并由仓库 scorer 的 single-record 模式从原评分记录派生正确性；派生输出位于本地 `dev-log/disclosure-readability-recovery/ticket10/archive/grades/score-derived/`。slot24 未评分。最终结果为 9 个正确、2 个错误、1 个未提交。六个 after 答案全部正确，after critical 错误为 0，历史权威误用为 0；四个 Runtime 与三个可评分 Upstream 答案的操作入口/冲突判断 anchors 均通过。

slot25 和 slot28 的两名初评者都判定 HIST-03（以当前项目状态说明实现状态）为 missed；它们在 HIST-04 的当前权威路由判断上各有一次实际分歧。第三评审分别裁决 HIST-04 为 met：baseline 根 `Task documentation map` 与决策索引构成等价路由，不要求 baseline 中不存在的 `task-routing.md` 文件名。原 A/B 评分、第三裁决和理由均保留。除此两项外无 A/B 分歧，也无未解决分歧；所有 11 个可评分答案的历史权威误用判断均为 false。

按候选汇总，baseline 的五个已提交答案中三项正确、两项错误，另有 slot24 失败；after 六个答案均正确。Runtime/Upstream/History 属于特殊任务，不计入常规阅读效率门槛，但这些 after 答案仍计入全部 16 个 after 正确性分母。

## 阅读成本与重试成本

下表按每个已提交逻辑槽的文件行区间并集拆分 UTF-8 字节。它只描述本票特殊任务，不是常规五类效率验收，也不以不完整的 baseline Upstream 样本作对照。

| 候选 | 各级指引 | 任务路由 | 当前契约 | 历史材料 | 源码/脚本 | 其他 | 合计 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline（5 个提交） | 213751 | 0 | 348186 | 96455 | 132699 | 44586 | 835677 |
| after（6 个提交） | 211040 | 104220 | 369601 | 73833 | 199352 | 1790 | 959836 |

16 个实际 attempt 总计读取 2211397 个唯一源字节、返回 2483937 字节；同一 attempt 内的重复读取为 272540 字节。四个重试本身共消耗 472823 个唯一源字节；五个失败 attempt 消耗 415884 个唯一源字节。提交样本中，六个 after 的描述性耗时中位数为 112.933 秒、去重字节中位数为 141452；这些数值不替代规格中的常规五类效率判定。

独立审计对每次 read/search 的实际文件哈希及行区间求并集；提交记录重算值与 collector 的 `unique_bytes_read` 一致，失败记录因未进入 submit 不含该字段，按同一算法从原事件重算。计时和字节的逐 attempt 来源类别、读取路径、重试 lineage 与哈希保存在本地 `dev-log/disclosure-readability-recovery/ticket10/archive/audits/ticket10-session-reconciliation.json`；dispatch 时间与文件完成时间证据见同目录 `dispatch-ledger.jsonl`。

审计共见 12 次被 collector 拒绝的工具请求：8 次无效行范围、2 次候选内不可读路径、1 次 Broken pipe 和 1 次一个绝对候选外路径。绝对路径请求未返回内容；rubric、scorer 或评分 fixtures 等禁读评估材料返回数为 0。这里的禁读材料仅指评估材料，不包括 `document-policy.json` 中的 67 条文档治理保护指纹；指纹保护与读者可读性是不同约束。

## 证据保留与限制

原始 session JSON、完整 JSONL trace、prompt 副本、配置、失败快照、grader 原评和裁决都保存在 ignored `dev-log/disclosure-readability-recovery/ticket10/archive/`；没有外部持久归档，干净检出无法仅凭哈希重算原始读取。dispatch ledger 保存 run ID、队列槽、candidate/task、runner exec session handle 和文件时间证据；运行接口没有暴露宿主 OS PID，因此 handle 未伪称 PID。协议失败后在重试前用 `ps` 检查任务 reader 进程，检查结果均无残留进程。

候选冻结后才创建本报告、评分包和审计输出；这些文件不在任一冻结候选根或 manifest 内。定时会话只能通过对应候选 collector 访问内容，不能读取另一候选、rubric、scorer、grades 或本报告。原始数据仍是本地 ignored 文件，不构成可公开重放的归档。

**交接：** 本票的采集与逐答案评分已交付，但 slot24 无 baseline Upstream 答案，且整轮还缺 slot18；本报告不宣布完整性或整体验收通过。票11应使用全部原始 attempt、grade 与 adjudication，报告缺失样本和后端模型修订未知的限制。
