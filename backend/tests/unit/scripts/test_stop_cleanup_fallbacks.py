"""Regression coverage for issue #21: stop helpers must survive lsof gaps.

The fixture PATH stubs ``lsof`` with the WSL2 failure mode from the issue
(exit 1, no output) so the scripts can only reclaim listeners through their
procfs/``ss`` fallbacks. Each script runs from a sandbox copy of ``scripts/``
so its REPO_ROOT — and with it every ownership root, pid file and nginx conf
path — resolves inside tmp_path, never at the real checkout: the stop paths
must never be able to kill a developer's actually running stack.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from support.shell import require_script_bash

REPO_ROOT = Path(__file__).resolve().parents[4]


def _start_fixture_process(*, cwd: Path, marker: str | None = None, process_name: str = "fixture-service") -> subprocess.Popen[str]:
    environment = os.environ.copy()
    if marker is not None:
        environment["DEERFLOW_DAEMON_ROOT"] = marker
    return subprocess.Popen(
        ["/bin/bash", "-c", f"exec -a {process_name} /bin/sleep 120"],
        cwd=cwd,
        env=environment,
        text=True,
    )


def _fake_commands(tmp_path: Path, *, fake_nginx: bool = False) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    # Reproduce the issue's environment: lsof exits 1 silently for the
    # next-server process, so every lsof-based lookup comes back empty.
    (bin_dir / "lsof").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    # ss ignores the port filter (the scripts only probe their own ports) and
    # reports the fixture listener whenever it is alive. /proc/<pid>/stat puts
    # the state letter right after the closing parenthesis of the comm field,
    # so a reaped-pending zombie ("... ) Z ...") must not be reported.
    (bin_dir / "ss").write_text(
        "#!/bin/sh\n"
        "pid=${TEST_LISTENER_PID:-}\n"
        "state=$(sed -n 's/^[0-9]* (.*) \\([A-Za-z]\\) .*/\\1/p' \"/proc/$pid/stat\" 2>/dev/null)\n"
        'if [ -n "$pid" ] && [ -n "$state" ] && [ "$state" != "Z" ]; then\n'
        "  printf 'State Recv-Q Send-Q Local Address:Port Peer Address:Port Process\\n'\n"
        "  port=${TEST_LISTENER_PORT:-3000}\n"
        '  printf \'LISTEN 0 128 0.0.0.0:%s 0.0.0.0:* users:(("fixture",pid=%s,fd=3))\\n\' "$port" "$pid"\n'
        "fi\n",
        encoding="utf-8",
    )
    for command in ("lsof", "netstat", "pgrep"):
        (bin_dir / command).write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    (bin_dir / "nginx").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (bin_dir / "tmux").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    for command in ("lsof", "ss", "netstat", "pgrep", "nginx", "tmux"):
        (bin_dir / command).chmod(0o755)
    if fake_nginx:
        # The fixture's comm stays "sleep" (exec -a only rewrites argv[0]), so
        # answer ps ownership queries as nginx the way a real nginx master does.
        (bin_dir / "ps").write_text(
            '#!/bin/sh\ncase "$*" in\n  *"-o comm="*) printf \'nginx\\n\' ;;\n  *"-o args="*) printf \'nginx\\n\' ;;\n  *) exec /usr/bin/ps "$@" ;;\nesac\n',
            encoding="utf-8",
        )
        (bin_dir / "ps").chmod(0o755)
    return {"PATH": f"{bin_dir}:{os.environ['PATH']}"}


def _make_sandbox(script_name: str, tmp_path: Path) -> Path:
    """Copy the target script into a sandbox so its REPO_ROOT — ownership
    roots, pid file, nginx conf — resolves inside tmp_path."""
    sandbox = tmp_path / "repo"
    (sandbox / "scripts").mkdir(parents=True)
    shutil.copy2(REPO_ROOT / "scripts" / script_name, sandbox / "scripts" / script_name)
    return sandbox


def _run_stop(script_name: str, tmp_path: Path, listener: subprocess.Popen[str]) -> subprocess.CompletedProcess[str]:
    sandbox = tmp_path / "repo"
    environment = _fake_commands(tmp_path, fake_nginx=script_name == "run-local-services.sh")
    environment["TEST_LISTENER_PID"] = str(listener.pid)
    environment["TEST_LISTENER_PORT"] = "3000" if script_name == "serve.sh" else "2026"
    bash = require_script_bash()
    return subprocess.run(
        [bash, str(sandbox / "scripts" / script_name), "--stop" if script_name == "serve.sh" else "stop"],
        cwd=sandbox,
        env={**os.environ, **environment},
        text=True,
        capture_output=True,
        check=False,
        timeout=15,
    )


def _assert_alive(process: subprocess.Popen[str]) -> None:
    assert process.poll() is None, "fixture died before the stop path ran"


def _assert_stopped(process: subprocess.Popen[str]) -> None:
    process.wait(timeout=5)
    assert process.returncode is not None


def test_serve_stop_uses_proc_cwd_when_lsof_cannot_list_process(tmp_path: Path) -> None:
    sandbox = _make_sandbox("serve.sh", tmp_path)
    process = _start_fixture_process(cwd=sandbox)
    try:
        _assert_alive(process)
        result = _run_stop("serve.sh", tmp_path, process)

        assert result.returncode == 0, result.stdout + result.stderr
        _assert_stopped(process)
        assert "All services stopped" in result.stdout
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


def test_serve_stop_uses_ss_pid_fallback_and_marker_for_owned_listener(tmp_path: Path) -> None:
    sandbox = _make_sandbox("serve.sh", tmp_path)
    process = _start_fixture_process(cwd=tmp_path, marker=str(sandbox))
    try:
        _assert_alive(process)
        result = _run_stop("serve.sh", tmp_path, process)

        assert result.returncode == 0, result.stdout + result.stderr
        _assert_stopped(process)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


def test_serve_stop_reports_but_does_not_kill_external_listener(tmp_path: Path) -> None:
    _make_sandbox("serve.sh", tmp_path)
    external_root = tmp_path / "outside"
    external_root.mkdir()
    process = _start_fixture_process(cwd=external_root)
    try:
        _assert_alive(process)
        result = _run_stop("serve.sh", tmp_path, process)

        assert result.returncode != 0
        assert "Port 3000 is still listening" in result.stdout
        assert "PID" in result.stdout
        assert process.poll() is None
    finally:
        process.kill()
        process.wait()


@pytest.mark.parametrize("owned", [True, False])
def test_local_services_stop_only_kills_repo_nginx_listener(tmp_path: Path, owned: bool) -> None:
    sandbox = _make_sandbox("run-local-services.sh", tmp_path)
    cwd = sandbox if owned else tmp_path
    process = _start_fixture_process(cwd=cwd, process_name="nginx")
    try:
        _assert_alive(process)
        result = _run_stop("run-local-services.sh", tmp_path, process)

        if owned:
            assert result.returncode == 0, result.stdout + result.stderr
            _assert_stopped(process)
        else:
            assert result.returncode != 0
            assert "Port 2026 is still listening" in result.stdout
            assert process.poll() is None
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
