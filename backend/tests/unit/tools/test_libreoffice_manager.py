"""Tests for the LibreOffice listener manager hardening (review 02-M5).

Covers the three defects: the resident listener started with unread PIPE
buffers (deadlocks once LibreOffice fills the 64KB pipe), the unbounded
recursive fallback after a failed/timeout conversion, and the blocking
2-second startup sleep.
"""

from __future__ import annotations

import subprocess
import time
from types import SimpleNamespace

import pytest

from app.agentplatform.utils.docx_rich import libreoffice as libreoffice_module
from app.agentplatform.utils.docx_rich.libreoffice import LibreOfficeManager


class FakeProcess:
    """A Popen stand-in whose process stays alive until terminated."""

    def __init__(self, cmd, **kwargs):
        self.pid = 4242
        self.terminated = False

    def poll(self):
        return 0 if self.terminated else None

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.terminated = True

    def wait(self, timeout=None):
        return 0


@pytest.fixture
def manager(monkeypatch: pytest.MonkeyPatch) -> LibreOfficeManager:
    """A fresh manager with a stubbed soffice path and isolated singleton state."""
    LibreOfficeManager._instance = None
    LibreOfficeManager._listener_process = None
    instance = LibreOfficeManager()
    instance.soffice_path = "/usr/bin/soffice"
    monkeypatch.setattr(libreoffice_module, "_LISTENER_STARTUP_WAIT_SECONDS", 0.05)
    yield instance
    LibreOfficeManager._instance = None
    LibreOfficeManager._listener_process = None


class TestEnsureListener:
    def test_listener_streams_go_to_devnull_never_pipes(self, manager, monkeypatch) -> None:
        """The resident listener must never hold unread PIPE buffers: a
        chatty LibreOffice would fill 64KB and block the listener forever."""
        captured: dict = {}

        def fake_popen(cmd, **kwargs):
            captured.update(kwargs)
            return FakeProcess(cmd, **kwargs)

        monkeypatch.setattr(libreoffice_module.subprocess, "Popen", fake_popen)
        assert manager.ensure_listener() is True
        assert captured["stdout"] is subprocess.DEVNULL
        assert captured["stderr"] is subprocess.DEVNULL

    def test_startup_waits_by_polling_not_one_blocking_sleep(self, manager, monkeypatch) -> None:
        """Startup detection polls the process instead of a single blocking
        sleep(2): a fast-failing start (e.g. port conflict) is detected on the
        first poll tick."""
        sleeps: list[float] = []

        def fake_sleep(seconds):
            sleeps.append(seconds)

        monkeypatch.setattr(libreoffice_module.subprocess, "Popen", lambda cmd, **kwargs: FakeProcess(cmd, **kwargs))
        monkeypatch.setattr(libreoffice_module, "time", SimpleNamespace(monotonic=time.monotonic, sleep=fake_sleep))
        assert manager.ensure_listener() is True
        assert sleeps, "startup must wait via polling"
        assert all(s <= libreoffice_module._LISTENER_STARTUP_POLL_SECONDS for s in sleeps)

    def test_fast_failing_start_is_detected_on_first_poll(self, manager, monkeypatch) -> None:
        """A process that exits immediately fails fast instead of waiting out
        the whole startup window."""
        sleeps: list[float] = []

        def fake_sleep(seconds):
            sleeps.append(seconds)

        class DyingProcess(FakeProcess):
            def poll(self):
                return 1  # already exited

        monkeypatch.setattr(libreoffice_module.subprocess, "Popen", lambda cmd, **kwargs: DyingProcess(cmd, **kwargs))
        monkeypatch.setattr(libreoffice_module, "time", SimpleNamespace(monotonic=time.monotonic, sleep=fake_sleep))
        started = manager.ensure_listener()
        assert started is False
        assert manager.is_listener_running() is False
        assert all(s <= libreoffice_module._LISTENER_STARTUP_POLL_SECONDS for s in sleeps)


class TestConversionFallback:
    @pytest.fixture
    def listener(self, manager, monkeypatch):
        monkeypatch.setattr(manager, "ensure_listener", lambda: True)
        return manager

    def _patch_run(self, monkeypatch, outcomes: list):
        """Patch subprocess.run to replay ``outcomes``; the last entry repeats."""
        calls = {"run": 0}
        outcome = iter(outcomes)

        def fake_run(cmd, **kwargs):
            calls["run"] += 1
            try:
                result = next(outcome)
            except StopIteration:
                result = outcomes[-1]
            if isinstance(result, Exception):
                raise result
            return result

        monkeypatch.setattr(libreoffice_module.subprocess, "run", fake_run)
        return calls

    def test_listener_timeout_falls_back_exactly_once(self, listener, monkeypatch, tmp_path) -> None:
        """A persistently timing-out conversion must retry plain mode once —
        not recurse without bound while the listener keeps restarting."""
        stops = {"count": 0}
        monkeypatch.setattr(listener, "stop_listener", lambda: stops.__setitem__("count", stops["count"] + 1))
        calls = self._patch_run(monkeypatch, [subprocess.TimeoutExpired(cmd="soffice", timeout=60)])

        assert listener.convert_to_pdf(str(tmp_path / "doc.docx"), str(tmp_path)) is None
        assert calls["run"] == 2, "expected one listener attempt plus one plain fallback"
        assert stops["count"] == 1

    def test_listener_failure_falls_back_and_succeeds(self, listener, monkeypatch, tmp_path) -> None:
        """A listener-mode failure is retried once in plain mode and the
        produced PDF is returned."""
        stops = {"count": 0}
        monkeypatch.setattr(listener, "stop_listener", lambda: stops.__setitem__("count", stops["count"] + 1))
        (tmp_path / "doc.pdf").write_bytes(b"%PDF-1.4")
        calls = self._patch_run(
            monkeypatch,
            [
                subprocess.CompletedProcess(args=[], returncode=1, stderr="listener boom"),
                subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
            ],
        )

        assert listener.convert_to_pdf(str(tmp_path / "doc.docx"), str(tmp_path)) == str(tmp_path / "doc.pdf")
        assert calls["run"] == 2
        assert stops["count"] == 1

    def test_modern_format_timeout_falls_back_exactly_once(self, listener, monkeypatch, tmp_path) -> None:
        stops = {"count": 0}
        monkeypatch.setattr(listener, "stop_listener", lambda: stops.__setitem__("count", stops["count"] + 1))
        (tmp_path / "legacy.docx").write_bytes(b"PK")
        calls = self._patch_run(monkeypatch, [subprocess.TimeoutExpired(cmd="soffice", timeout=60)])

        assert listener.convert_to_modern_format(str(tmp_path / "legacy.doc"), str(tmp_path)) is None
        assert calls["run"] == 2
        assert stops["count"] == 1

    def test_modern_format_failure_falls_back_and_succeeds(self, listener, monkeypatch, tmp_path) -> None:
        stops = {"count": 0}
        monkeypatch.setattr(listener, "stop_listener", lambda: stops.__setitem__("count", stops["count"] + 1))
        (tmp_path / "legacy.docx").write_bytes(b"PK")
        calls = self._patch_run(
            monkeypatch,
            [
                subprocess.CompletedProcess(args=[], returncode=1, stderr="listener boom"),
                subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
            ],
        )

        assert listener.convert_to_modern_format(str(tmp_path / "legacy.doc"), str(tmp_path)) == str(tmp_path / "legacy.docx")
        assert calls["run"] == 2
        assert stops["count"] == 1

    def test_plain_mode_without_listener_makes_a_single_attempt(self, manager, monkeypatch, tmp_path) -> None:
        """Without a listener there is exactly one plain attempt and no
        stop_listener churn."""
        stops = {"count": 0}
        monkeypatch.setattr(manager, "ensure_listener", lambda: False)
        monkeypatch.setattr(manager, "stop_listener", lambda: stops.__setitem__("count", stops["count"] + 1))
        calls = self._patch_run(monkeypatch, [subprocess.TimeoutExpired(cmd="soffice", timeout=120)])

        assert manager.convert_to_pdf(str(tmp_path / "doc.docx"), str(tmp_path)) is None
        assert calls["run"] == 1
        assert stops["count"] == 0
