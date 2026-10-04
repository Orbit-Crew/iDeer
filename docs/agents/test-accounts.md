# Local Test Accounts

> audience: developers verifying role behavior locally
> status: current
> canonical-path: `docs/agents/test-accounts.md`

数据库位置：`backend/.ideer/data/ideer.db`（运行时生成，未初始化的 worktree 不包含该文件）。

密码 = 邮箱名。

| 角色 | 邮箱 | 密码 |
|------|------|------|
| 超级管理员 | `super_admin@test.com` | `super_admin@test.com` |
| 部门管理员 | `department_admin@test.com` | `department_admin@test.com` |
| 普通用户 | `user@test.com` | `user@test.com` |
| 只读用户 | `viewer@test.com` | `viewer@test.com` |
| 管理员 | `admin@test.com` | `admin@test.com` |

**注意：** 这些账号仅适用于已初始化或已 seed 的本地数据库；进行角色测试前请确认实际角色值。若 `department_admin@test.com` 仍为 `user`，需先通过 admin 页面修改为 `department_admin`。
