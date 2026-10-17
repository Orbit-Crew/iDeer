"""The final runtime gate rejects a reintroduced legacy runtime import."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    ("source", "expected_status"),
    [("from deerflow.config import get_app_config\n", 0), ("from ideer.config import get_app_config\n", 1)],
)
def test_runtime_boundary_requires_zero_legacy_imports(tmp_path: Path, source: str, expected_status: int) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    gate = scripts / "check-runtime-boundary.sh"
    shutil.copyfile(Path(__file__).resolve().parents[4] / "scripts" / gate.name, gate)
    app = tmp_path / "backend" / "app"
    app.mkdir(parents=True)
    (app / "entry.py").write_text(source, encoding="utf-8")
    env = dict(os.environ)
    env.pop("RUNTIME_BOUNDARY_MAX_IMPORT_FILES", None)

    result = subprocess.run(["bash", str(gate)], capture_output=True, text=True, env=env, check=False)

    assert result.returncode == expected_status, result.stdout + result.stderr


def test_runtime_boundary_without_rg_fails_closed_with_clear_error(tmp_path: Path) -> None:
    # 08-M4: a PATH without rg used to fall back to grep and, when that tool
    # was unavailable too, `|| true` swallowed the failure and the gate
    # reported OK with zero scans. The gate must fail explicitly instead.
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    gate = scripts / "check-runtime-boundary.sh"
    shutil.copyfile(Path(__file__).resolve().parents[4] / "scripts" / gate.name, gate)
    app = tmp_path / "backend" / "app"
    app.mkdir(parents=True)
    (app / "entry.py").write_text("from ideer.config import get_app_config\n", encoding="utf-8")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    dirname = shutil.which("dirname")
    bash = shutil.which("bash")
    assert dirname and bash
    (fake_bin / "dirname").symlink_to(dirname)
    env = dict(os.environ)
    env["PATH"] = str(fake_bin)

    result = subprocess.run([bash, str(gate)], capture_output=True, text=True, env=env, check=False)

    assert result.returncode != 0, result.stdout + result.stderr
    assert "ripgrep" in result.stderr
    assert "rg" in result.stderr
