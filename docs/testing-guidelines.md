---
id: docs-testing-guidelines
kind: reference
status: current
owner: repository maintainers
scope: test-writing conventions: mock principles, fixture usage, helpers, async rules, naming, isolation, and run commands
last-verified: 2026-10-04
verified-against: worktree docs/agent-doc-disclosure @ bfb00cc49
---
# 测试规范指南

> audience: testers, developers<br>
> status: current<br>
> owner: test maintainers<br>
> last-verified: 2026-07-15<br>
> canonical-path: `docs/testing-guidelines.md`

> 本文档定义了项目的测试编写规范，确保测试质量一致、可维护。

## 一、Mock 原则

### 1. Mock 边界，不 Mock 内部
- **正确做法**：mock 外部依赖（HTTP 客户端、数据库、第三方 SDK）
- **错误做法**：mock 被测模块内部的函数调用

```python
# ✓ 正确：mock 外部 HTTP 调用
@patch("httpx.AsyncClient.get")
def test_fetch_user(mock_get):
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"id": 1})
    result = fetch_user(1)
    assert result["id"] == 1

# ✗ 错误：mock 被测模块内部函数
@patch("my_module.validate_input")
def test_process(mock_validate):
    mock_validate.return_value = True
    # 这样测试没有真正验证 validate_input 的行为
```

### 2. Mock 最小化
- 只 mock 测试所需的最小依赖集
- 不要为了"安全"而 mock 一切

### 3. 验证调用，不验证实现
- 断言 mock 被正确调用（参数、次数）
- 不要断言 mock 的内部状态

```python
# ✓ 正确：验证调用
mock_client.get.assert_called_once_with("/api/users")

# ✗ 错误：验证内部状态
assert mock_client.get.call_count == 1  # 应该用 assert_called_once_with
```

### 4. 使用真实数据结构
- mock 返回值应符合真实数据结构
- 不要用 `MagicMock()` 代替字典/对象

```python
# ✓ 正确：返回真实数据
mock_response.json.return_value = {"id": 1, "name": "test"}

# ✗ 错误：返回 MagicMock
mock_response.json.return_value = MagicMock()
```

### 5. 测试行为，不测试代码
- 测试应验证业务行为
- 不要验证代码行的执行顺序

## 二、Fixture 规范

### 公共 Fixture

公共 fixture 以 `backend/tests/conftest.py` 和各子目录 `conftest.py` 的当前定义为准（2026-10-04 核对：早期文档列出的 `mock_app_config`、`mock_http_client`、`mock_db_session`、`mock_sse_bridge`、`mock_run_manager` 等命名 fixture 已不存在，勿按旧清单引用）。路由测试的认证桩统一使用 `tests/_router_auth_helpers.py`。

### 自定义 Fixture

当公共 fixture 不满足需求时，创建模块级 fixture：

```python
@pytest.fixture
def admin_config(mock_app_config):
    """基于公共 fixture 的管理员配置"""
    mock_app_config.user.role = "admin"
    return mock_app_config
```

### Autouse Fixture

以下 fixture 自动应用于所有测试（2026-10-04 核对）：
- `_reset_skill_storage_singleton` — 重置 SkillStorage 单例
- `_restore_title_config_singleton` — 恢复 TitleConfig 默认值
- `_auto_user_context` — 注入默认用户上下文（可通过 `@pytest.mark.no_auto_user` 禁用）

当前注册的 marker 见 `backend/pyproject.toml`（`serial`、`requires_llm`、`no_auto_user`、`allow_blocking_io`、`integration`）。

## 三、测试辅助函数

### Router 测试

使用 `_router_auth_helpers.py` 中的辅助函数：

```python
from tests._router_auth_helpers import make_authed_test_app, call_unwrapped

# 创建带认证的测试 app
app = make_authed_test_app(user_role="admin")

# 调用未包装的路由函数
result = await call_unwrapped(my_endpoint, param1="value")
```

### 数据构建

使用 `backend/tests/factories/` 下的工厂模块（`auth.py`、`llm.py`、`models.py`），或 `_make_` / `_build_` 前缀的模块级辅助函数：

```python
def _make_user(role="user", department_id=None):
    """构建测试用户"""
    return SimpleNamespace(
        id="test-user-id",
        email="test@example.com",
        role=role,
        department_id=department_id or "dept-1",
    )
```

### 示例测试文件

认证与 RBAC 行为测试参考 `backend/tests/unit/gateway/test_authz.py` 与 `backend/tests/contracts/` 下的契约测试。

## 四、异步测试规范

```python
@pytest.mark.asyncio
async def test_async_operation():
    """异步测试示例"""
    mock_client = AsyncMock()
    mock_client.get.return_value = MagicMock(status_code=200)
    result = await fetch_data(mock_client)
    assert result is not None
```

### 注意事项
- 使用 `@pytest.mark.asyncio` 标记异步测试
- 使用 `AsyncMock` mock 异步函数
- 异步 fixture 使用 `@pytest_asyncio.fixture`

## 五、测试数据工厂

使用工厂模式生成测试数据：

```python
# tests/factories/rbac.py
class UserFactory:
    @staticmethod
    def build(**kwargs):
        defaults = {
            "id": str(uuid4()),
            "username": f"user_{uuid4().hex[:8]}",
            "email": f"user_{uuid4().hex[:8]}@test.com",
            "role": "user",
            "is_active": True,
        }
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)
```

## 六、断言规范

### 推荐的断言方式

```python
# 精确匹配
assert response.status_code == 200
assert user.role == "admin"

# 包含检查
assert "error" in response.json()
assert "Python" in ai_response

# 类型检查
assert isinstance(result, dict)
assert isinstance(users, list)

# 布尔值
assert result  # 不要用 assert result == True
assert not error  # 不要用 assert error == False
```

### 避免的断言方式

```python
# ✗ 不要这样
assert result == True  # 用 assert result
assert len(users) > 0  # 用 assert users

# ✗ 不要过度断言
assert mock.called  # 应该断言具体调用
```

## 七、测试命名规范

| 元素 | 格式 | 示例 |
|------|------|------|
| 测试文件 | `test_<module>.py` | `test_authz.py` |
| 测试类 | `Test<Feature>` | `TestRBACSecurity` |
| 测试方法 | `test_<behavior>_<condition>` | `test_viewer_cannot_create_agent` |

## 八、测试隔离

- 每个测试应独立运行
- 不依赖测试执行顺序
- 使用 fixture 清理状态
- 使用 `monkeypatch` 而非 `@patch` 装饰器（更好的清理保证）

## 九、依赖注入覆盖

FastAPI 路由测试使用 `dependency_overrides`：

```python
from app.gateway.authz import get_current_rbac_user

def test_admin_endpoint():
    app = FastAPI()
    app.dependency_overrides[get_current_rbac_user] = lambda: mock_admin
    client = TestClient(app)
    response = client.get("/api/admin/users")
    assert response.status_code == 200
```

## 十、运行测试

```bash
# 运行所有测试（仓库标准入口）
cd backend && make test

# 运行特定文件
cd backend && PYTHONPATH=.:tests uv run pytest tests/unit/gateway/test_authz.py -v

# 运行带覆盖率
cd backend && PYTHONPATH=.:tests uv run pytest tests/ --cov=app --cov=packages --cov-report=term-missing

# 跳过 live 测试（默认 lane 即不含 live）
cd backend && PYTHONPATH=.:tests uv run pytest -m "not live"

# 只运行 LLM 测试（需要 API key）
cd backend && PYTHONPATH=.:tests uv run pytest -m "requires_llm"
```
