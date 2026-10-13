"""Tests for per-user memory storage isolation (DI: FileMemoryStorage(DeerMemConfig))."""

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from app.agentplatform.legacy.memory.storage import FileMemoryStorage as _legacy_FileMemoryStorage
from deerflow.agents.memory.backends.deermem.deermem.config import DeerMemConfig
from deerflow.agents.memory.backends.deermem.deermem.core.paths import fact_file_path
from deerflow.agents.memory.backends.deermem.deermem.core.storage import FileMemoryStorage, create_empty_memory


@pytest.fixture
def base_dir(tmp_path: Path, monkeypatch) -> Path:
    """DeerMem data root = tmp_path (via $DEERMEM_DATA_DIR)."""
    monkeypatch.setenv("DEERMEM_DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def storage() -> FileMemoryStorage:
    return FileMemoryStorage(DeerMemConfig())


class TestUserIsolatedStorage:
    def test_save_and_load_per_user(self, storage: FileMemoryStorage, base_dir: Path):
        memory_a = create_empty_memory()
        memory_a["user"]["workContext"]["summary"] = "User A context"
        storage.save(memory_a, user_id="alice")

        memory_b = create_empty_memory()
        memory_b["user"]["workContext"]["summary"] = "User B context"
        storage.save(memory_b, user_id="bob")

        loaded_a = storage.load(user_id="alice")
        loaded_b = storage.load(user_id="bob")

        assert loaded_a["user"]["workContext"]["summary"] == "User A context"
        assert loaded_b["user"]["workContext"]["summary"] == "User B context"

    def test_user_memory_file_location(self, base_dir: Path):
        s = FileMemoryStorage(DeerMemConfig())
        s.save(create_empty_memory(), user_id="alice")
        assert (base_dir / "users" / "alice" / "memory.json").exists()

    def test_cache_isolated_per_user(self, base_dir: Path):
        s = FileMemoryStorage(DeerMemConfig())
        memory_a = create_empty_memory()
        memory_a["user"]["workContext"]["summary"] = "A"
        s.save(memory_a, user_id="alice")

        memory_b = create_empty_memory()
        memory_b["user"]["workContext"]["summary"] = "B"
        s.save(memory_b, user_id="bob")

        loaded_a = s.load(user_id="alice")
        assert loaded_a["user"]["workContext"]["summary"] == "A"

    def test_no_user_id_uses_legacy_path(self, base_dir: Path):
        s = FileMemoryStorage(DeerMemConfig())
        s.save(create_empty_memory(), user_id=None)
        assert (base_dir / "memory.json").exists()

    def test_user_and_legacy_do_not_interfere(self, base_dir: Path):
        """user_id=None (legacy) and user_id='alice' must use different files and caches."""
        s = FileMemoryStorage(DeerMemConfig())

        legacy_mem = create_empty_memory()
        legacy_mem["user"]["workContext"]["summary"] = "legacy"
        s.save(legacy_mem, user_id=None)

        user_mem = create_empty_memory()
        user_mem["user"]["workContext"]["summary"] = "alice"
        s.save(user_mem, user_id="alice")

        assert s.load(user_id=None)["user"]["workContext"]["summary"] == "legacy"
        assert s.load(user_id="alice")["user"]["workContext"]["summary"] == "alice"

    def test_user_agent_memory_file_location(self, base_dir: Path):
        """One user JSON stores summaries; agent facts live below the agent directory."""
        s = FileMemoryStorage(DeerMemConfig())
        memory = create_empty_memory()
        memory["facts"] = [{"id": "fact_agent", "content": "agent scoped"}]
        s.save(memory, "test-agent", user_id="alice")
        memory_path = base_dir / "users" / "alice" / "memory.json"
        assert memory_path.exists()
        assert not (base_dir / "users" / "alice" / "agents" / "test-agent" / "memory.json").exists()
        assert fact_file_path(memory_path, "fact_agent", agent_name="test-agent").exists()

    def test_cache_key_is_user_agent_tuple(self, base_dir: Path):
        """Cache keys must be (user_id, agent_name) tuples."""
        s = FileMemoryStorage(DeerMemConfig())
        s.save(create_empty_memory(), user_id="alice")
        assert ("alice", None) in s._memory_cache

    def test_reload_with_user_id(self, base_dir: Path):
        """reload() with user_id should force re-read from the user-scoped file."""
        s = FileMemoryStorage(DeerMemConfig())
        memory = create_empty_memory()
        memory["user"]["workContext"]["summary"] = "initial"
        s.save(memory, user_id="alice")

        s.load(user_id="alice")  # prime cache

        user_file = base_dir / "users" / "alice" / "memory.json"
        import json

        updated = create_empty_memory()
        updated["user"]["workContext"]["summary"] = "updated"
        user_file.write_text(json.dumps(updated))

        reloaded = s.reload(user_id="alice")
        assert reloaded["user"]["workContext"]["summary"] == "updated"

    def test_saving_memory_does_not_shadow_shared_agent_config(self, base_dir: Path):
        """Memory writes for a shared agent name must not create a per-user agent config dir."""
        from deerflow.config.paths import Paths

        paths = Paths(base_dir)
        shared_dir = base_dir / "agents" / "fault-zeroing"
        shared_dir.mkdir(parents=True)
        (shared_dir / "config.yaml").write_text(yaml.safe_dump({"name": "fault-zeroing", "description": "shared"}), encoding="utf-8")
        (shared_dir / "SOUL.md").write_text("shared soul", encoding="utf-8")

        with patch("app.agentplatform.legacy.memory.storage.get_paths", return_value=paths):
            s = _legacy_FileMemoryStorage()
            assert s.save(create_empty_memory(), "fault-zeroing", user_id="alice") is True

        # The memory file lives in the per-user agent directory, but no agent
        # definition (config.yaml) is created there and the shared global
        # agent config stays untouched.
        assert (base_dir / "users" / "alice" / "agents" / "fault-zeroing" / "memory.json").exists()
        assert not (base_dir / "users" / "alice" / "agents" / "fault-zeroing" / "config.yaml").exists()
        assert (shared_dir / "config.yaml").read_text(encoding="utf-8") == yaml.safe_dump({"name": "fault-zeroing", "description": "shared"})
