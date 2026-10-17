"""Tests for per-user memory storage isolation (DI: FileMemoryStorage(DeerMemConfig))."""

from pathlib import Path

import pytest

from deerflow.agents.memory.backends.deermem.deermem.config import DeerMemConfig
from deerflow.agents.memory.backends.deermem.deermem.core.storage import FileMemoryStorage


@pytest.fixture
def base_dir(tmp_path: Path, monkeypatch) -> Path:
    """DeerMem data root = tmp_path (via $DEERMEM_DATA_DIR)."""
    monkeypatch.setenv("DEERMEM_DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def storage() -> FileMemoryStorage:
    return FileMemoryStorage(DeerMemConfig())
