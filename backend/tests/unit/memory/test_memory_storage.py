"""Tests for memory storage providers (DI: FileMemoryStorage(config) / create_storage)."""

import threading
from unittest.mock import patch

import pytest

import app.agentplatform.legacy.memory.storage as _legacy_memory_storage
from deerflow.agents.memory.backends.deermem.deermem.config import DeerMemConfig
from deerflow.agents.memory.backends.deermem.deermem.core.paths import validate_agent_name
from deerflow.agents.memory.backends.deermem.deermem.core.storage import (
    FileMemoryStorage,
    MemoryStorage,
    create_empty_memory,
    create_storage,
)
from deerflow.config.memory_config import MemoryConfig


def _storage_at(memory_file) -> FileMemoryStorage:
    """A FileMemoryStorage whose absolute storage_path is a single shared file."""
    resolved = str(memory_file.resolve())
    return FileMemoryStorage(DeerMemConfig(storage_path=resolved))


class TestCreateEmptyMemory:
    """Test create_empty_memory function."""

    def test_returns_valid_structure(self):
        memory = create_empty_memory()
        assert isinstance(memory, dict)
        assert memory["version"] == "1.0"
        assert "lastUpdated" in memory
        assert isinstance(memory["user"], dict)
        assert isinstance(memory["history"], dict)
        assert isinstance(memory["facts"], list)


class TestMemoryStorageInterface:
    """Test MemoryStorage abstract base class."""

    def test_abstract_methods(self):
        class TestStorage(MemoryStorage):
            pass

        with pytest.raises(TypeError):
            TestStorage(DeerMemConfig())


class TestFileMemoryStorage:
    """Test FileMemoryStorage implementation (DI: constructed with a config)."""

    def test_get_memory_file_path_global(self, tmp_path, monkeypatch):
        """DEERMEM_DATA_DIR as root + empty storage_path => global legacy path."""
        monkeypatch.setenv("DEERMEM_DATA_DIR", str(tmp_path))
        storage = FileMemoryStorage(DeerMemConfig())
        assert storage._get_memory_file_path(None) == tmp_path / "memory.json"

    def test_get_memory_file_path_agent(self, tmp_path, monkeypatch):
        """Agent facts share the user's global summary JSON path."""
        monkeypatch.setenv("DEERMEM_DATA_DIR", str(tmp_path))
        storage = FileMemoryStorage(DeerMemConfig())
        path = storage._get_memory_file_path("test-agent")
        assert path == tmp_path / "memory.json"

    @pytest.mark.parametrize("invalid_name", ["", "../etc/passwd", "agent/name", "agent\\name", "agent name", "agent@123", "agent_name"])
    def test_validate_agent_name_invalid(self, invalid_name):
        """Should raise ValueError for invalid agent names."""
        with pytest.raises(ValueError, match="Invalid agent name|Agent name must be a non-empty string"):
            validate_agent_name(invalid_name)

    def test_load_creates_empty_memory(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DEERMEM_DATA_DIR", str(tmp_path))
        storage = FileMemoryStorage(DeerMemConfig())
        memory = storage.load()
        assert isinstance(memory, dict)
        assert memory["version"] == "1.0"

    def test_save_writes_to_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DEERMEM_DATA_DIR", str(tmp_path))
        memory_file = tmp_path / "memory.json"
        storage = FileMemoryStorage(DeerMemConfig())
        result = storage.save({"version": "1.0", "facts": []})
        assert result is True
        assert memory_file.exists()
        assert "facts" not in memory_file.read_text(encoding="utf-8")

    def test_save_does_not_mutate_caller_dict(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DEERMEM_DATA_DIR", str(tmp_path))
        storage = FileMemoryStorage(DeerMemConfig())
        original = {"version": "1.0", "facts": []}
        before_keys = set(original.keys())
        storage.save(original)
        assert set(original.keys()) == before_keys, "save() must not add keys to caller's dict"
        assert "lastUpdated" not in original

    def test_cache_not_corrupted_when_save_fails(self, tmp_path, monkeypatch):
        """Cache must remain clean when save() raises OSError."""
        monkeypatch.setenv("DEERMEM_DATA_DIR", str(tmp_path))
        memory_file = tmp_path / "memory.json"
        memory_file.parent.mkdir(parents=True, exist_ok=True)
        import json as _json

        memory_file.write_text(_json.dumps({"version": "2.0", "user": {"workContext": {"summary": "original"}}, "history": {}}))
        storage = FileMemoryStorage(DeerMemConfig())
        cached = storage.load()
        assert cached["user"]["workContext"]["summary"] == "original"

        with patch("builtins.open", side_effect=OSError("disk full")):
            changed = create_empty_memory()
            changed["user"]["workContext"]["summary"] = "mutated"
            result = storage.save(changed)
        assert result is False
        after = storage.load()
        assert after["user"]["workContext"]["summary"] == "original"

    def test_cache_thread_safety(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DEERMEM_DATA_DIR", str(tmp_path))
        memory_file = tmp_path / "memory.json"
        memory_file.parent.mkdir(parents=True, exist_ok=True)
        import json as _json

        memory_file.write_text(_json.dumps({"version": "1.0", "facts": []}))
        storage = FileMemoryStorage(DeerMemConfig())
        errors: list[Exception] = []

        def load_many(s: FileMemoryStorage) -> None:
            try:
                for _ in range(50):
                    s.load()
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=load_many, args=(storage,)) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors, f"Thread-safety errors: {errors}"

    def test_reload_forces_cache_invalidation(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DEERMEM_DATA_DIR", str(tmp_path))
        memory_file = tmp_path / "memory.json"
        memory_file.parent.mkdir(parents=True, exist_ok=True)
        memory_file.write_text('{"version": "2.0", "user": {"workContext": {"summary": "initial"}}, "history": {}}')
        storage = FileMemoryStorage(DeerMemConfig())
        memory1 = storage.load()
        assert memory1["user"]["workContext"]["summary"] == "initial"
        memory_file.write_text('{"version": "2.0", "user": {"workContext": {"summary": "updated"}}, "history": {}}')
        memory2 = storage.reload()
        assert memory2["user"]["workContext"]["summary"] == "updated"


class TestCreateStorage:
    """Test create_storage(config) (replaces the old get_memory_storage() singleton)."""

    def test_returns_file_memory_storage_by_default(self):
        """Empty storage_class (default) -> FileMemoryStorage directly."""
        assert isinstance(create_storage(DeerMemConfig()), FileMemoryStorage)

    def test_raises_on_unresolvable_storage_class(self):
        """An unimportable storage_class raises ValueError (fail-fast), not a silent
        FileMemoryStorage fallback -- memory is persistent state, so a wrong store
        is a data-integrity footgun. Mirrors the manager_class resolution policy."""
        with pytest.raises(ValueError, match="storage_class"):
            create_storage(DeerMemConfig(storage_class="non.existent.StorageClass"))

    def test_raises_on_non_class_storage_class(self):
        """A storage_class that resolves to a non-class (e.g. a function) raises
        ValueError, not a silent fallback to FileMemoryStorage."""
        with pytest.raises(ValueError, match="storage_class"):
            create_storage(DeerMemConfig(storage_class="os.path.join"))

    def test_raises_on_non_subclass_storage_class(self):
        """A storage_class that is not a MemoryStorage subclass raises ValueError,
        not a silent fallback to FileMemoryStorage."""
        with pytest.raises(ValueError, match="storage_class"):
            create_storage(DeerMemConfig(storage_class="builtins.dict"))

    def test_dotted_storage_class_resolves(self):
        storage = create_storage(DeerMemConfig(storage_class="deerflow.agents.memory.backends.deermem.deermem.core.storage.FileMemoryStorage"))
        assert isinstance(storage, FileMemoryStorage)


# --- merged from test_memory_storage.py (subdir-only tests; root copy is the dedup base) ---
class TestGetMemoryStorage:
    """Test get_memory_storage function."""

    @pytest.fixture(autouse=True)
    def reset_storage_instance(self):
        """Reset the global storage instance before and after each test."""
        import app.agentplatform.legacy.memory.storage as storage_mod

        storage_mod._storage_instance = None
        yield
        storage_mod._storage_instance = None

    def test_returns_file_memory_storage_by_default(self):
        """Should return FileMemoryStorage by default."""
        with patch("app.agentplatform.legacy.memory.storage.get_memory_config", return_value=MemoryConfig(backend_config={"storage_class": "app.agentplatform.legacy.memory.storage.FileMemoryStorage"})):
            storage = _legacy_memory_storage.get_memory_storage()
            assert isinstance(storage, _legacy_memory_storage.FileMemoryStorage)

    def test_falls_back_to_file_memory_storage_on_error(self):
        """Should fall back to FileMemoryStorage if configured storage fails to load."""
        with patch("app.agentplatform.legacy.memory.storage.get_memory_config", return_value=MemoryConfig(backend_config={"storage_class": "non.existent.StorageClass"})):
            storage = _legacy_memory_storage.get_memory_storage()
            assert isinstance(storage, _legacy_memory_storage.FileMemoryStorage)

    def test_returns_singleton_instance(self):
        """Should return the same instance on subsequent calls."""
        with patch("app.agentplatform.legacy.memory.storage.get_memory_config", return_value=MemoryConfig(backend_config={"storage_class": "app.agentplatform.legacy.memory.storage.FileMemoryStorage"})):
            storage1 = _legacy_memory_storage.get_memory_storage()
            storage2 = _legacy_memory_storage.get_memory_storage()
            assert storage1 is storage2

    def test_get_memory_storage_thread_safety(self):
        """Should safely initialize the singleton even with concurrent calls."""
        results = []

        def get_storage():
            # get_memory_storage is called concurrently from multiple threads while
            # get_memory_config is patched once around thread creation. This verifies
            # that the singleton initialization remains thread-safe.
            results.append(_legacy_memory_storage.get_memory_storage())

        with patch("app.agentplatform.legacy.memory.storage.get_memory_config", return_value=MemoryConfig(backend_config={"storage_class": "app.agentplatform.legacy.memory.storage.FileMemoryStorage"})):
            threads = [threading.Thread(target=get_storage) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        # All results should be the exact same instance
        assert len(results) == 10
        assert all(r is results[0] for r in results)

    def test_get_memory_storage_invalid_class_fallback(self):
        """Should fall back to FileMemoryStorage if the configured class is not actually a class."""
        # Using a built-in function instead of a class
        with patch("app.agentplatform.legacy.memory.storage.get_memory_config", return_value=MemoryConfig(backend_config={"storage_class": "os.path.join"})):
            storage = _legacy_memory_storage.get_memory_storage()
            assert isinstance(storage, _legacy_memory_storage.FileMemoryStorage)

    def test_get_memory_storage_non_subclass_fallback(self):
        """Should fall back to FileMemoryStorage if the configured class is not a subclass of MemoryStorage."""
        # Using 'dict' as a class that is not a MemoryStorage subclass
        with patch("app.agentplatform.legacy.memory.storage.get_memory_config", return_value=MemoryConfig(backend_config={"storage_class": "builtins.dict"})):
            storage = _legacy_memory_storage.get_memory_storage()
            assert isinstance(storage, _legacy_memory_storage.FileMemoryStorage)
