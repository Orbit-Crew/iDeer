---
id: docs-agents-test-accounts
kind: reference
status: current
owner: repository maintainers
scope: local test accounts for role verification (email/password convention, role values, database location)
last-verified: 2026-10-04
verified-against: worktree docs/agent-doc-disclosure @ 71ae798fb
---

# Local Test Accounts

> audience: developers verifying role behavior locally
> status: current
> canonical-path: `docs/agents/test-accounts.md`

数据库位置：`backend/.deer-flow/data/deerflow.db`（SQLite，运行时生成，未初始化的 worktree 不包含该文件；`database.backend: sqlite` 时文件名固定为 `{sqlite_dir}/deerflow.db`，`sqlite_dir` 默认 `.deer-flow/data`）。

密码 = 邮箱名。

| 角色 | 邮箱 | 密码 |
|------|------|------|
| 超级管理员 | `super_admin@test.com` | `super_admin@test.com` |
| 部门管理员 | `department_admin@test.com` | `department_admin@test.com` |
| 普通用户 | `user@test.com` | `user@test.com` |
| 只读用户 | `viewer@test.com` | `viewer@test.com` |
| 管理员 | `admin@test.com` | `admin@test.com` |

**注意：** 这些账号仅适用于已初始化或已 seed 的本地数据库。角色合法值为 `viewer` / `user` / `department_admin` / `super_admin`（`backend/app/agentplatform/rbac_models.py` 的 `UserRole`，无 `admin` 值）；仓库自带 seed 脚本 `backend/scripts/seed-real-e2e.sh` 只创建 `super_admin@test.com` 与 `user@test.com`，其余账号依赖本地手工初始化，存在性与实际角色值未核验。进行角色测试前请确认实际角色值；若 `department_admin@test.com` 仍为 `user`，需先通过 admin 页面修改为 `department_admin`。
