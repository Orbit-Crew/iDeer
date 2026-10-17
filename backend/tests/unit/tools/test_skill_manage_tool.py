import asyncio
import importlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import anyio
import pytest

from deerflow.skills.security_static_scanner import StaticScannerError
from deerflow.tools.skill_manage_tool import (  # noqa: E402
    _get_lock,
    _get_thread_id,
    _history_record,
    _scan_or_raise,
    _to_thread,
    skill_manage_tool,
)

skill_manage_module = importlib.import_module("deerflow.tools.skill_manage_tool")


def _skill_content(name: str, description: str = "Demo skill") -> str:
    return f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n"


async def _async_result(decision: str, reason: str):
    from deerflow.skills.security_scanner import ScanResult

    return ScanResult(decision=decision, reason=reason)


def _make_config(skills_root: Path):
    return SimpleNamespace(
        skills=SimpleNamespace(
            get_skills_path=lambda: skills_root,
            container_path="/mnt/skills",
            use="deerflow.skills.storage.local_skill_storage:LocalSkillStorage",
        ),
        skill_evolution=SimpleNamespace(enabled=True, moderation_model_name=None),
    )


def _make_runtime(*, thread_id: str = "thread-1", user_id: str = "default"):
    return SimpleNamespace(
        context={"thread_id": thread_id, "user_id": user_id},
        config={"configurable": {"thread_id": thread_id, "user_id": user_id}},
    )


def test_skill_manage_create_and_patch(monkeypatch, tmp_path):
    skills_root = tmp_path / "skills"
    config = _make_config(skills_root)
    monkeypatch.setattr("deerflow.config.get_app_config", lambda: config)
    monkeypatch.setattr("deerflow.skills.security_scanner.get_app_config", lambda: config)
    # Patch get_paths so UserScopedSkillStorage resolves user dirs under tmp_path
    from deerflow.config.paths import Paths

    monkeypatch.setattr("deerflow.config.paths.get_paths", lambda: Paths(base_dir=tmp_path))
    monkeypatch.setattr("deerflow.config.paths._paths", None)

    refresh_calls = []

    async def _refresh(user_id: str):
        refresh_calls.append(("refresh", user_id))

    monkeypatch.setattr(skill_manage_module, "refresh_user_skills_system_prompt_cache_async", _refresh)
    monkeypatch.setattr(skill_manage_module, "scan_skill_content", lambda *args, **kwargs: _async_result("allow", "ok"))

    runtime = _make_runtime(user_id="default")

    result = anyio.run(
        skill_manage_module.skill_manage_tool.coroutine,
        runtime,
        "create",
        "demo-skill",
        _skill_content("demo-skill"),
    )
    assert "Created custom skill" in result

    patch_result = anyio.run(
        skill_manage_module.skill_manage_tool.coroutine,
        runtime,
        "patch",
        "demo-skill",
        None,
        None,
        "Demo skill",
        "Patched skill",
        1,
    )
    assert "Patched custom skill" in patch_result
    # User-scoped: custom skills written under users/default/skills/custom/
    user_custom = tmp_path / "users" / "default" / "skills" / "custom"
    assert "Patched skill" in (user_custom / "demo-skill" / "SKILL.md").read_text(encoding="utf-8")
    assert refresh_calls == [("refresh", "default"), ("refresh", "default")]


def test_skill_manage_patch_replaces_single_occurrence_by_default(monkeypatch, tmp_path):
    skills_root = tmp_path / "skills"
    config = _make_config(skills_root)
    monkeypatch.setattr("deerflow.config.get_app_config", lambda: config)
    monkeypatch.setattr("deerflow.skills.security_scanner.get_app_config", lambda: config)
    from deerflow.config.paths import Paths

    monkeypatch.setattr("deerflow.config.paths.get_paths", lambda: Paths(base_dir=tmp_path))
    monkeypatch.setattr("deerflow.config.paths._paths", None)

    async def _refresh(user_id: str):
        return None

    monkeypatch.setattr(skill_manage_module, "refresh_user_skills_system_prompt_cache_async", _refresh)
    monkeypatch.setattr(skill_manage_module, "scan_skill_content", lambda *args, **kwargs: _async_result("allow", "ok"))

    runtime = _make_runtime(user_id="default")
    content = _skill_content("demo-skill", "Demo skill") + "\nRepeated: Demo skill\n"

    anyio.run(skill_manage_module.skill_manage_tool.coroutine, runtime, "create", "demo-skill", content)
    patch_result = anyio.run(
        skill_manage_module.skill_manage_tool.coroutine,
        runtime,
        "patch",
        "demo-skill",
        None,
        None,
        "Demo skill",
        "Patched skill",
    )

    user_custom = tmp_path / "users" / "default" / "skills" / "custom"
    skill_text = (user_custom / "demo-skill" / "SKILL.md").read_text(encoding="utf-8")
    assert "1 replacement(s) applied, 2 match(es) found" in patch_result
    assert skill_text.count("Patched skill") == 1
    assert skill_text.count("Demo skill") == 1


def test_skill_manage_rejects_public_skill_patch(monkeypatch, tmp_path):
    skills_root = tmp_path / "skills"
    public_dir = skills_root / "public" / "deep-research"
    public_dir.mkdir(parents=True, exist_ok=True)
    (public_dir / "SKILL.md").write_text(_skill_content("deep-research"), encoding="utf-8")
    config = _make_config(skills_root)
    monkeypatch.setattr("deerflow.config.get_app_config", lambda: config)
    from deerflow.config.paths import Paths

    monkeypatch.setattr("deerflow.config.paths.get_paths", lambda: Paths(base_dir=tmp_path))
    monkeypatch.setattr("deerflow.config.paths._paths", None)

    runtime = _make_runtime(user_id="default")

    with pytest.raises(ValueError, match="built-in skill"):
        anyio.run(
            skill_manage_module.skill_manage_tool.coroutine,
            runtime,
            "patch",
            "deep-research",
            None,
            None,
            "Demo skill",
            "Patched",
        )


def test_skill_manage_sync_wrapper_supported(monkeypatch, tmp_path):
    skills_root = tmp_path / "skills"
    config = _make_config(skills_root)
    monkeypatch.setattr("deerflow.config.get_app_config", lambda: config)
    from deerflow.config.paths import Paths

    monkeypatch.setattr("deerflow.config.paths.get_paths", lambda: Paths(base_dir=tmp_path))
    monkeypatch.setattr("deerflow.config.paths._paths", None)

    refresh_calls = []

    async def _refresh(user_id: str):
        refresh_calls.append(("refresh", user_id))

    monkeypatch.setattr(skill_manage_module, "refresh_user_skills_system_prompt_cache_async", _refresh)
    monkeypatch.setattr(skill_manage_module, "scan_skill_content", lambda *args, **kwargs: _async_result("allow", "ok"))

    runtime = _make_runtime(thread_id="thread-sync", user_id="default")
    result = skill_manage_module.skill_manage_tool.func(
        runtime=runtime,
        action="create",
        name="sync-skill",
        content=_skill_content("sync-skill"),
    )

    assert "Created custom skill" in result
    assert refresh_calls == [("refresh", "default")]


def test_skill_manage_rejects_support_path_traversal(monkeypatch, tmp_path):
    skills_root = tmp_path / "skills"
    config = _make_config(skills_root)
    monkeypatch.setattr("deerflow.config.get_app_config", lambda: config)
    monkeypatch.setattr("deerflow.skills.security_scanner.get_app_config", lambda: config)
    from deerflow.config.paths import Paths

    monkeypatch.setattr("deerflow.config.paths.get_paths", lambda: Paths(base_dir=tmp_path))
    monkeypatch.setattr("deerflow.config.paths._paths", None)

    async def _refresh(user_id: str):
        return None

    monkeypatch.setattr(skill_manage_module, "refresh_user_skills_system_prompt_cache_async", _refresh)
    monkeypatch.setattr(skill_manage_module, "scan_skill_content", lambda *args, **kwargs: _async_result("allow", "ok"))

    runtime = _make_runtime(user_id="default")
    anyio.run(skill_manage_module.skill_manage_tool.coroutine, runtime, "create", "demo-skill", _skill_content("demo-skill"))

    with pytest.raises(ValueError, match="parent-directory traversal|selected support directory"):
        anyio.run(
            skill_manage_module.skill_manage_tool.coroutine,
            runtime,
            "write_file",
            "demo-skill",
            "malicious overwrite",
            "references/../SKILL.md",
        )


def test_skill_manage_remove_file_updates_sandbox_projection_before_return(monkeypatch, tmp_path):
    skills_root = tmp_path / "skills"
    config = _make_config(skills_root)
    monkeypatch.setattr("deerflow.config.get_app_config", lambda: config)
    monkeypatch.setattr("deerflow.skills.security_scanner.get_app_config", lambda: config)
    from deerflow.config.paths import Paths

    monkeypatch.setattr("deerflow.config.paths.get_paths", lambda: Paths(base_dir=tmp_path))
    monkeypatch.setattr("deerflow.config.paths._paths", None)

    async def _refresh(user_id: str):
        return None

    monkeypatch.setattr(skill_manage_module, "refresh_user_skills_system_prompt_cache_async", _refresh)
    monkeypatch.setattr(skill_manage_module, "scan_skill_content", lambda *args, **kwargs: _async_result("allow", "ok"))

    runtime = _make_runtime(user_id="default")
    anyio.run(skill_manage_module.skill_manage_tool.coroutine, runtime, "create", "demo-skill", _skill_content("demo-skill"))
    anyio.run(
        skill_manage_module.skill_manage_tool.coroutine,
        runtime,
        "write_file",
        "demo-skill",
        "supporting content",
        "references/guide.md",
    )
    projected_file = tmp_path / "users" / "default" / "skills_view" / "custom" / "demo-skill" / "references" / "guide.md"
    assert projected_file.read_text(encoding="utf-8") == "supporting content"

    result = anyio.run(
        skill_manage_module.skill_manage_tool.coroutine,
        runtime,
        "remove_file",
        "demo-skill",
        None,
        "references/guide.md",
    )

    assert result == "Removed 'references/guide.md' from custom skill 'demo-skill'."
    assert not projected_file.exists()


def test_skill_manage_static_critical_blocks_create_before_llm(monkeypatch, tmp_path):
    skills_root = tmp_path / "skills"
    config = _make_config(skills_root)
    monkeypatch.setattr("deerflow.config.get_app_config", lambda: config)
    monkeypatch.setattr("deerflow.skills.security_scanner.get_app_config", lambda: config)
    from deerflow.config.paths import Paths

    monkeypatch.setattr("deerflow.config.paths.get_paths", lambda: Paths(base_dir=tmp_path))
    monkeypatch.setattr("deerflow.config.paths._paths", None)
    refresh_calls = []
    llm_calls = []

    async def _refresh(user_id: str):
        refresh_calls.append(("refresh", user_id))

    async def _scan(*args, **kwargs):
        llm_calls.append({"args": args, "kwargs": kwargs})
        return await _async_result("allow", "ok")

    monkeypatch.setattr(skill_manage_module, "refresh_user_skills_system_prompt_cache_async", _refresh)
    monkeypatch.setattr(skill_manage_module, "scan_skill_content", _scan)

    runtime = _make_runtime(user_id="default")
    content = _skill_content("blocked-skill") + "\n-----BEGIN RSA PRIVATE KEY-----\nabc\n-----END RSA PRIVATE KEY-----\n"

    with pytest.raises(ValueError) as excinfo:
        anyio.run(
            skill_manage_module.skill_manage_tool.coroutine,
            runtime,
            "create",
            "blocked-skill",
            content,
        )

    assert "Static security scan blocked" in str(excinfo.value)
    assert "secret-private-key" in str(excinfo.value)
    assert llm_calls == []
    assert refresh_calls == []
    assert not (tmp_path / "users" / "default" / "skills" / "custom" / "blocked-skill" / "SKILL.md").exists()


def test_skill_manage_static_scan_failure_blocks_create_before_llm(monkeypatch, tmp_path):
    skills_root = tmp_path / "skills"
    config = _make_config(skills_root)
    monkeypatch.setattr("deerflow.config.get_app_config", lambda: config)
    monkeypatch.setattr("deerflow.skills.security_scanner.get_app_config", lambda: config)
    from deerflow.config.paths import Paths

    monkeypatch.setattr("deerflow.config.paths.get_paths", lambda: Paths(base_dir=tmp_path))
    monkeypatch.setattr("deerflow.config.paths._paths", None)
    refresh_calls = []
    llm_calls = []

    async def _refresh(user_id: str):
        refresh_calls.append(("refresh", user_id))

    async def _scan(*args, **kwargs):
        llm_calls.append({"args": args, "kwargs": kwargs})
        return await _async_result("allow", "ok")

    def _broken_static_scan(skill_dir, *, skill_name=None, app_config=None):
        raise StaticScannerError("native scanner unavailable")

    monkeypatch.setattr(skill_manage_module, "refresh_user_skills_system_prompt_cache_async", _refresh)
    monkeypatch.setattr(skill_manage_module, "scan_skill_content", _scan)
    monkeypatch.setattr(skill_manage_module, "enforce_static_scan", _broken_static_scan)

    runtime = _make_runtime(user_id="default")

    with pytest.raises(ValueError, match="Static security scan failed.*native scanner unavailable"):
        anyio.run(
            skill_manage_module.skill_manage_tool.coroutine,
            runtime,
            "create",
            "scanner-failure-skill",
            _skill_content("scanner-failure-skill"),
        )

    assert llm_calls == []
    assert refresh_calls == []
    assert not (tmp_path / "users" / "default" / "skills" / "custom" / "scanner-failure-skill" / "SKILL.md").exists()


def test_skill_manage_per_user_isolation(monkeypatch, tmp_path):
    """Two different users must get separate custom skill directories."""
    skills_root = tmp_path / "skills"
    config = _make_config(skills_root)
    monkeypatch.setattr("deerflow.config.get_app_config", lambda: config)
    monkeypatch.setattr("deerflow.skills.security_scanner.get_app_config", lambda: config)
    from deerflow.config.paths import Paths

    monkeypatch.setattr("deerflow.config.paths.get_paths", lambda: Paths(base_dir=tmp_path))
    monkeypatch.setattr("deerflow.config.paths._paths", None)

    async def _refresh(user_id: str):
        return None

    monkeypatch.setattr(skill_manage_module, "refresh_user_skills_system_prompt_cache_async", _refresh)
    monkeypatch.setattr(skill_manage_module, "scan_skill_content", lambda *args, **kwargs: _async_result("allow", "ok"))

    # Alice creates a skill
    runtime_alice = _make_runtime(user_id="alice")
    result_a = anyio.run(
        skill_manage_module.skill_manage_tool.coroutine,
        runtime_alice,
        "create",
        "alice-skill",
        _skill_content("alice-skill"),
    )
    assert "Created custom skill" in result_a

    # Bob creates a different skill
    runtime_bob = _make_runtime(user_id="bob")
    result_b = anyio.run(
        skill_manage_module.skill_manage_tool.coroutine,
        runtime_bob,
        "create",
        "bob-skill",
        _skill_content("bob-skill"),
    )
    assert "Created custom skill" in result_b

    # Verify separate directories
    alice_dir = tmp_path / "users" / "alice" / "skills" / "custom" / "alice-skill"
    bob_dir = tmp_path / "users" / "bob" / "skills" / "custom" / "bob-skill"
    assert alice_dir.exists()
    assert bob_dir.exists()
    # No cross-contamination
    assert not (tmp_path / "users" / "alice" / "skills" / "custom" / "bob-skill").exists()
    assert not (tmp_path / "users" / "bob" / "skills" / "custom" / "alice-skill").exists()


# --- tracing wiring: the in-graph choke point (see the INVARIANT in
# packages/harness/deerflow/agents/lead_agent/agent.py) ---


def test_scan_or_raise_does_not_attach_model_tracing(monkeypatch, tmp_path):
    """``_scan_or_raise`` is the in-graph choke point for the skill security scan.

    The graph root already attached the tracing callbacks, so the scan model must
    not attach them again: double-attaching emits duplicate spans and blocks the
    Langfuse handler's ``propagate_attributes`` path, so session_id/user_id never
    reach the trace. Drives the real ``scan_skill_content`` rather than stubbing it,
    so the flag is pinned all the way to the model factory.
    """
    config = _make_config(tmp_path / "skills")
    monkeypatch.setattr("deerflow.skills.security_scanner.get_app_config", lambda: config)

    create_kwargs = {}

    class FakeModel:
        async def ainvoke(self, *args, **kwargs):
            return SimpleNamespace(content='{"decision":"allow","reason":"ok"}')

    def _fake_create_chat_model(**kwargs):
        create_kwargs.update(kwargs)
        return FakeModel()

    monkeypatch.setattr("deerflow.skills.security_scanner.create_chat_model", _fake_create_chat_model)

    result = anyio.run(
        lambda: skill_manage_module._scan_or_raise(
            _skill_content("demo-skill"),
            executable=False,
            location="demo-skill/SKILL.md",
        )
    )

    assert result["decision"] == "allow"
    assert create_kwargs["attach_tracing"] is False


# --- merged from test_skill_manage_tool.py (subdir-only tests; root copy is the dedup base) ---
def _make_scan_result(decision: str = "allow", reason: str = "ok"):
    return SimpleNamespace(decision=decision, reason=reason)


def _user_custom_root(tmp_path: Path) -> Path:
    """Custom-skill root for the test user inside the isolated base dir."""
    return tmp_path / "users" / "test-user" / "skills" / "custom"


@pytest.fixture()
def _patch_deps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Isolate config paths and patch the async/model dependencies.

    The storage itself stays real (UserScopedSkillStorage over tmp_path) so the
    tool's filesystem behaviour is exercised end to end; only the LLM security
    scan and the prompt-cache refresh are mocked.
    """
    from deerflow.config.paths import Paths
    from deerflow.skills.storage.user_scoped_skill_storage import UserScopedSkillStorage

    paths = Paths(base_dir=tmp_path)
    monkeypatch.setattr("deerflow.config.paths.get_paths", lambda: paths)
    storage = UserScopedSkillStorage("test-user", host_path=str(tmp_path))

    with (
        patch("deerflow.tools.skill_manage_tool.get_or_new_user_skill_storage", return_value=storage),
        patch("deerflow.tools.skill_manage_tool.scan_skill_content", new_callable=AsyncMock) as mock_scan,
        patch("deerflow.tools.skill_manage_tool.refresh_user_skills_system_prompt_cache_async", new_callable=AsyncMock) as mock_refresh,
    ):
        mock_scan.return_value = _make_scan_result()
        yield SimpleNamespace(
            storage=storage,
            scan=mock_scan,
            refresh=mock_refresh,
        )


class TestGetLock:
    @pytest.fixture(autouse=True)
    def _patch_deps_scoped(self, _patch_deps):
        pass

    def test_returns_lock_for_name(self):
        lock = _get_lock("test-user", "my-skill")
        assert isinstance(lock, asyncio.Lock)

    def test_same_lock_for_same_name(self):
        a = _get_lock("test-user", "same")
        b = _get_lock("test-user", "same")
        assert a is b

    def test_different_locks_for_different_names(self):
        a = _get_lock("test-user", "alpha")
        b = _get_lock("test-user", "beta")
        assert a is not b

    def test_different_locks_for_different_users(self):
        """Lock granularity is (user_id, skill_name) to avoid cross-user blocking."""
        a = _get_lock("user-1", "shared")
        b = _get_lock("user-2", "shared")
        assert a is not b


class TestGetThreadId:
    @pytest.fixture(autouse=True)
    def _patch_deps_scoped(self, _patch_deps):
        pass

    def test_none_runtime(self):
        assert _get_thread_id(None) is None

    def test_from_context(self):
        rt = SimpleNamespace(context={"thread_id": "ctx-1"}, config={})
        assert _get_thread_id(rt) == "ctx-1"

    def test_from_config_fallback(self):
        rt = SimpleNamespace(context={}, config={"configurable": {"thread_id": "cfg-1"}})
        assert _get_thread_id(rt) == "cfg-1"

    def test_context_missing_thread_id(self):
        rt = SimpleNamespace(context={"other": "val"}, config={"configurable": {"thread_id": "cfg-2"}})
        assert _get_thread_id(rt) == "cfg-2"

    def test_no_context_no_config(self):
        rt = SimpleNamespace(context={}, config={})
        assert _get_thread_id(rt) is None

    def test_context_is_none(self):
        rt = SimpleNamespace(context=None, config={})
        assert _get_thread_id(rt) is None


class TestHistoryRecord:
    @pytest.fixture(autouse=True)
    def _patch_deps_scoped(self, _patch_deps):
        pass

    def test_returns_expected_dict(self):
        rec = _history_record(
            action="create",
            file_path="SKILL.md",
            prev_content=None,
            new_content="# Hello",
            thread_id="t-1",
            scanner={"decision": "allow", "reason": "ok"},
        )
        assert rec["action"] == "create"
        assert rec["author"] == "agent"
        assert rec["thread_id"] == "t-1"
        assert rec["file_path"] == "SKILL.md"
        assert rec["prev_content"] is None
        assert rec["new_content"] == "# Hello"
        assert rec["scanner"] == {"decision": "allow", "reason": "ok"}


class TestScanOrRaise:
    @pytest.fixture(autouse=True)
    def _patch_deps_scoped(self, _patch_deps):
        pass

    @pytest.mark.asyncio
    async def test_allow_decision(self, _patch_deps):
        _patch_deps.scan.return_value = _make_scan_result("allow", "clean")
        result = await _scan_or_raise("content", executable=False, location="x/SKILL.md")
        assert result == {"decision": "allow", "reason": "clean"}

    @pytest.mark.asyncio
    async def test_warn_decision_non_executable(self, _patch_deps):
        _patch_deps.scan.return_value = _make_scan_result("warn", "suspicious")
        result = await _scan_or_raise("content", executable=False, location="x/SKILL.md")
        assert result == {"decision": "warn", "reason": "suspicious"}

    @pytest.mark.asyncio
    async def test_block_raises(self, _patch_deps):
        _patch_deps.scan.return_value = _make_scan_result("block", "malicious")
        with pytest.raises(ValueError, match="Security scan blocked"):
            await _scan_or_raise("content", executable=False, location="x/SKILL.md")

    @pytest.mark.asyncio
    async def test_executable_warn_raises(self, _patch_deps):
        _patch_deps.scan.return_value = _make_scan_result("warn", "untrusted")
        with pytest.raises(ValueError, match="Security scan rejected executable"):
            await _scan_or_raise("content", executable=True, location="x/scripts/run.sh")

    @pytest.mark.asyncio
    async def test_executable_allow_ok(self, _patch_deps):
        _patch_deps.scan.return_value = _make_scan_result("allow", "ok")
        result = await _scan_or_raise("content", executable=True, location="x/scripts/run.sh")
        assert result["decision"] == "allow"


class TestToThread:
    @pytest.fixture(autouse=True)
    def _patch_deps_scoped(self, _patch_deps):
        pass

    @pytest.mark.asyncio
    async def test_runs_sync_function_in_thread(self):
        result = await _to_thread(lambda: 42)
        assert result == 42

    @pytest.mark.asyncio
    async def test_passes_args(self):
        def add(a, b):
            return a + b

        result = await _to_thread(add, 3, 4)
        assert result == 7

    def test_concurrent_same_name_same_lock(self):
        lock_a = _get_lock("test-user", "concurrent-skill")
        lock_b = _get_lock("test-user", "concurrent-skill")
        assert lock_a is lock_b

    def test_weakref_allows_gc(self):
        """Locks are stored in WeakValueDictionary — unreferenced locks can be GC'd."""
        import gc

        _get_lock("test-user", "gc-test")
        gc.collect()
        # After GC, a new lock may be created (not guaranteed, but no crash)
        lock = _get_lock("test-user", "gc-test")
        assert isinstance(lock, asyncio.Lock)


class TestSkillManageFilesystem:
    @pytest.fixture(autouse=True)
    def _patch_deps_scoped(self, _patch_deps):
        pass

    @pytest.mark.asyncio
    async def test_create_publishes_skill(self, tmp_path: Path) -> None:
        result = await skill_manage_tool.coroutine(
            runtime=_make_runtime(),
            action="create",
            name="my-skill",
            content=_skill_content("my-skill"),
        )

        assert result == "Created custom skill 'my-skill'."
        published = _user_custom_root(tmp_path) / "my-skill" / "SKILL.md"
        assert published.read_text(encoding="utf-8") == _skill_content("my-skill")

    @pytest.mark.asyncio
    async def test_create_rejects_existing_skill(self) -> None:
        await skill_manage_tool.coroutine(runtime=_make_runtime(), action="create", name="my-skill", content=_skill_content("my-skill"))
        with pytest.raises(ValueError, match="already exists"):
            await skill_manage_tool.coroutine(runtime=_make_runtime(), action="create", name="my-skill", content=_skill_content("my-skill"))

    @pytest.mark.asyncio
    async def test_edit_updates_skill_and_records_history(self, _patch_deps) -> None:
        await skill_manage_tool.coroutine(runtime=_make_runtime(), action="create", name="my-skill", content=_skill_content("my-skill"))
        result = await skill_manage_tool.coroutine(
            runtime=_make_runtime(),
            action="edit",
            name="my-skill",
            content=_skill_content("my-skill", description="Edited"),
        )

        assert result == "Updated custom skill 'my-skill'."
        history = _patch_deps.storage.read_history("my-skill")
        assert [record["action"] for record in history] == ["create", "edit"], "previous version must be retained in history"
        assert history[-1]["prev_content"] == _skill_content("my-skill")

    @pytest.mark.asyncio
    async def test_patch_applies_replacement(self, tmp_path: Path) -> None:
        await skill_manage_tool.coroutine(runtime=_make_runtime(), action="create", name="my-skill", content=_skill_content("my-skill"))
        result = await skill_manage_tool.coroutine(runtime=_make_runtime(), action="patch", name="my-skill", find="Demo skill", replace="Patched skill")

        assert "1 replacement(s)" in result
        published = _user_custom_root(tmp_path) / "my-skill" / "SKILL.md"
        assert "Patched skill" in published.read_text(encoding="utf-8")

    @pytest.mark.asyncio
    async def test_write_file_and_remove_file(self, tmp_path: Path) -> None:
        await skill_manage_tool.coroutine(runtime=_make_runtime(), action="create", name="my-skill", content=_skill_content("my-skill"))
        await skill_manage_tool.coroutine(runtime=_make_runtime(), action="write_file", name="my-skill", path="templates/letter.md", content="# Letter")

        skill_dir = _user_custom_root(tmp_path) / "my-skill"
        assert (skill_dir / "templates" / "letter.md").read_text(encoding="utf-8") == "# Letter"

        await skill_manage_tool.coroutine(runtime=_make_runtime(), action="remove_file", name="my-skill", path="templates/letter.md")
        assert not (skill_dir / "templates" / "letter.md").exists()
        assert (skill_dir / "SKILL.md").exists(), "SKILL.md must survive a support-file removal"

    @pytest.mark.asyncio
    async def test_delete_removes_custom_skill(self, tmp_path: Path) -> None:
        await skill_manage_tool.coroutine(runtime=_make_runtime(), action="create", name="my-skill", content=_skill_content("my-skill"))
        result = await skill_manage_tool.coroutine(runtime=_make_runtime(), action="delete", name="my-skill")

        assert result == "Deleted custom skill 'my-skill'."
        assert not (_user_custom_root(tmp_path) / "my-skill").exists()

    @pytest.mark.asyncio
    async def test_edit_unknown_skill_raises(self) -> None:
        with pytest.raises(FileNotFoundError, match="not found"):
            await skill_manage_tool.coroutine(runtime=_make_runtime(), action="edit", name="ghost-skill", content="# Ghost")

    @pytest.mark.asyncio
    async def test_unsupported_action_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported action"):
            await skill_manage_tool.coroutine(runtime=_make_runtime(), action="frobnicate", name="my-skill")
