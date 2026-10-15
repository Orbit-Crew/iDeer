---
id: docs-decisions-2026-10-15-product-semantics-decision-package
kind: decision
status: current
owner: engineering maintainers
scope: 2026-10-07 全仓审查批次 6 四项"待产品确认"语义的统一决策(票 67)——archived 资源的快照加载边界、知识数据集部署层 veto 的缺省语义、list_devices 管理员全局可见、NetworkPolicy 私网判定口径
last-verified: 2026-10-15
verified-against: worktree fix/issue-67-84 @ 8fca6d510
---

# 批次 6 产品语义确认包(02-L6/L7、03-L9、04-M1)

> audience: developers, security reviewers, maintainers
> status: accepted
> owner: engineering maintainers
> last-verified: 2026-10-15
> canonical-path: `docs/decisions/2026-10-15-product-semantics-decision-package.md`

## 决策摘要

四项审查"待确认"统一裁决:两项**记录确认**(archived 快照加载为刻意契约;list_devices 管理员全局可见为显式设计),一项**部分改代码**(知识部署层 veto 在工具未配置时改为 fail-closed;属性缺省语义维持),一项**改代码**(NetworkPolicy 私网判定补齐,并记录接线前收口条件)。出处均为 `dev-log/code-review-2026-10-07/` 对应分区报告的复核勘误。

## 背景

2026-10-07 全仓审查产出四条"待产品确认"发现(02-L6、02-L7、03-L9、04-M1),复核确证现象但产品语义未成文。票 67(规格 #46 批次 6)要求逐项给出"改代码 / 记录确认 / 条件收口"结论并留痕。备选与裁决逐项如下。

## 决策

### 1. 02-L6:archived 资源的快照加载——记录确认(维持现状)

**结论:archived 表示"不可被新 Run 选用",但不打断持有冻结快照的在途 Run;这是刻意契约,不改代码。**

依据:

- 新 Run 侧已经 fail-closed:闭包解析走 `ResourceService._get_visible`,默认只取
  `lifecycle_status == "active"`(`resources/service.py`),归档资源进不了新 Run 的
  依赖闭包(报 ResourceNotFound)。
- 在途 Run 侧是既立约行为:`CanonicalResourceLoader._frozen_version` 只拒绝
  `suspended`;单测
  `test_loader_uses_frozen_version_after_archive_but_denies_suspend_and_tamper`
  以名称固化该契约。归档版本的被快照引用内容同时受 retention 冻结集保护
  (`resources/retention.py`),哈希校验贯穿加载。
- 非对称的理由:suspended 是可逆的管理动作(有 resume 路径),必须即时停用在途
  Run;archived 是终态(无恢复路径),语义是"停止新增使用",不追溯终止已在途的
  冻结快照执行。

留痕:`resources/runtime.py` `_frozen_version` 处已加注释说明该非对称;本节即勘误记录。

### 2. 02-L7:知识数据集部署层 veto 的缺省语义——部分改代码

**结论:双层语义,拆开裁决——**

- **工具未配置(`get_tool_config("knowledge_search")` 返回 `None`)→ 拒绝(fail-closed)。**
  Run 带着 KB 绑定而部署层从未声明检索工具,属于配置错装,不得静默失去部署层
  veto——与 run preparation 既有注释"cannot be read must deny"同口径。
- **工具已配置但无 `datasets` 属性 → 该层不设限(维持)。** `datasets` 是可选的
  运营方允许列表(`config.example.yaml` 明示 "Optional operator-controlled
  allowlist";LightRAG 变体单工作区、不表达 per-dataset 允许列表),一刀切
  fail-closed 会破坏已文档化部署;调用方/工作流/运行时三层 veto 与资源治理绑定
  审批仍然生效。

实现:`knowledge/scope.py` 新增 `deployment_allowed_datasets()`,统一两处调用方
(`workflows/v2/store.py` `_frozen_knowledge_scope` 与
`gateway/canonical_agent_run_preparation.py`——后者为审查正文未列出的相邻同病,
一并收口)。回归:`test_frozen_scope_denies_when_knowledge_search_is_unconfigured`。

### 3. 03-L9:list_devices 管理员全局可见——记录确认(显式设计)

**结论:服务层 `list_devices(owner_id=None)` 返回全部设备是仓储参数缺省,不是授权边界;授权边界在路由层。** `gateway/routers/devices.py` 的 `list_devices` 经 `get_current_rbac_user` 依赖强制:仅 `SUPER_ADMIN`/`DEPARTMENT_ADMIN` 以 `owner_id=None` 调用,其余角色一律 `owner_id=当前用户`。管理员全局可见属设备控制面的显式设计,实际越权风险与审查正文措辞不符(复核勘误已记录)。不改代码,不收窄;若未来引入更细的设备治理角色,再回到本节复议。

### 4. 04-M1:NetworkPolicy 私网判定——改代码 + 接线前收口条件

**结论:`_is_private_or_local` 改为 `ipaddress` 判定,对齐 harness 代理
`network_proxy.address_is_public` 的公网口径(global 且非 multicast 且非
site_local);判定测试覆盖私网变体与云元数据端点。**

- 收口范围:RFC1918 全段(含 `172.16.0.0/12`)、链路本地/云元数据
  `169.254.0.0/16`、环回(含 IPv6 `::1`)、ULA `fc00::/7`、链路本地 `fe80::/10`、
  CGNAT `100.64/10`、benchmarking `198.18/15`,以及 IPv4-mapped IPv6 的私网形态,
  在 `allow_public=True` 下一律仍视为私网拒绝;显式允许列表始终优先。
- **接线前收口条件(条件收口)**:当前 `NetworkPolicy` 无生产消费方;任何把它接
  入出网管控的改动,必须同时补 DNS 解析级校验(内部域名解析到私网地址的绕过),
  否则不得上线。该条件同时作为上游化该判定的前提。

## 备选(已否决)

- 02-L6 改为拒绝 archived 加载:否决——会打断属主删除级联(归档)下的在途 Run,
  且推翻已立约测试,无对应治理诉求。
- 02-L7 全面 fail-closed(缺属性即拒绝):否决——与 `config.example.yaml` 已文档
  化的可选允许列表语义冲突,LightRAG 单工作区部署无法表达等价允许列表。
- 03-L9 收窄服务层缺省:否决——授权边界在路由层是网关统一形态,服务层收窄不提
  供额外保障反而诱导调用方绕过。

## 验证

- `backend/tests/unit/workflows/test_v2_knowledge_freeze.py`(部署层 veto 回归)、
  `backend/tests/test_agentplatform_extension_boundary.py`(私网判定回归)、
  `backend/tests/unit/resources/test_resource_runtime.py`(archived 契约,既有)。
- 决策被接受只回答"定了什么";实现与验证的候选级状态见[项目状态页](../project-state.md)。
