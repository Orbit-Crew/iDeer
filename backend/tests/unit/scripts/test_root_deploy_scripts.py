"""Regression tests for the root deploy/docker/cleanup/check script cluster (08-L4..L10).

Covers the batch-7 #70 pool items:
- 08-L4: cleanup-containers.sh anchored docker name filter and argv-passed prefix
- 08-L5: check-intranet.sh ambiguous image tar error and real template hint
- 08-L6: docker.sh array COMPOSE_CMD and pinned sandbox image default
- 08-L7: deploy.sh seeds frontend/.env from its example
- 08-L9: deploy.sh down does not print a config.yaml success check
- 08-L10: config-upgrade.sh prints the upgrade banner only when upgrading
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import stat
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
CLEANUP_SCRIPT = REPO_ROOT / "scripts" / "cleanup-containers.sh"
CHECK_INTRANET_SCRIPT = REPO_ROOT / "scripts" / "check-intranet.sh"
DOCKER_SH = REPO_ROOT / "scripts" / "docker.sh"
DEPLOY_SH = REPO_ROOT / "scripts" / "deploy.sh"
CONFIG_UPGRADE_SH = REPO_ROOT / "scripts" / "config-upgrade.sh"


def _write_executable(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def test_cleanup_containers_uses_anchored_filter_and_argv_prefix(tmp_path: Path) -> None:
    """08-L4: docker name filters must be anchored and PREFIX must reach python via argv."""
    bin_dir = tmp_path / "bin"
    docker_log = tmp_path / "docker-calls.log"
    _write_executable(
        bin_dir / "docker",
        f"""#!/usr/bin/env sh
printf '%s\\n' "$*" >> {shlex.quote(str(docker_log))}
exit 0
""",
    )
    container_log = tmp_path / "container-calls.log"
    # A container id that actually contains the quote-carrying prefix: with the
    # old source interpolation the embedded double quote turned the inline
    # python into a syntax error that the bare except swallowed, so nothing
    # was stopped; with argv passing the match still happens.
    container_log_json = json.dumps([{"configuration": {"id": 'de"er-sandbox-1'}}])
    _write_executable(
        bin_dir / "container",
        f"""#!/usr/bin/env sh
if [ "$1" = "list" ]; then
  printf '%s\\n' {shlex.quote(container_log_json)}
  exit 0
fi
printf '%s\\n' "$*" >> {shlex.quote(str(container_log))}
exit 0
""",
    )
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"

    proc = subprocess.run(
        ["bash", str(CLEANUP_SCRIPT), 'de"er'],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    docker_calls = docker_log.read_text(encoding="utf-8")
    assert 'name=^de"er' in docker_calls, "the docker name filter must be regex-anchored (^prefix); a bare name= filter is a substring match that can stop unrelated containers (08-L4)"
    stops = container_log.read_text(encoding="utf-8")
    assert 'de"er-sandbox-1' in stops, "the Apple Container branch must still match and stop containers when the prefix contains shell/python metacharacters; the prefix travels as argv now (08-L4)"


def test_check_intranet_reports_ambiguous_image_tar_and_real_template_hint(tmp_path: Path) -> None:
    """08-L5: multiple image tars are an error (deploy requires uniqueness) and the hint names a real template."""
    (tmp_path / "ideer-images-a.tar").write_text("a", encoding="utf-8")
    (tmp_path / "ideer-images-b.tar").write_text("b", encoding="utf-8")

    proc = subprocess.run(
        ["bash", str(CHECK_INTRANET_SCRIPT)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    output = proc.stdout + proc.stderr
    assert "AMBIGUOUS" in output and "exactly one" in output, output
    assert "copy config.intranet.yaml from the repository" in output, "the config hint must reference the template that actually exists in the repository (config.intranet.yaml), not config.intranet.yaml.example (08-L5)"


def test_docker_sh_uses_array_compose_cmd_and_pinned_sandbox_image() -> None:
    """08-L6: COMPOSE_CMD stays an array and the sandbox default is pinned like setup-sandbox.sh."""
    script = DOCKER_SH.read_text(encoding="utf-8")

    assert 'COMPOSE_CMD=("${COMPOSE_BIN[@]}" -p deer-flow-dev -f "$COMPOSE_FILE")' in script, "COMPOSE_CMD must be an array so repo paths with spaces and the two-word 'docker compose' survive quoting (08-L6)"
    assert '"${COMPOSE_CMD[@]}"' in script, "COMPOSE_CMD call sites must expand the array"
    assert "all-in-one-sandbox:latest" not in script, "the sandbox default must stay pinned: the mirror's :latest tag is frozen on an old pre-1.9.3 digest (see setup-sandbox.sh / #3921) (08-L6)"
    assert "all-in-one-sandbox:1.11.0" in script


def test_deploy_sh_seeds_frontend_env_from_example() -> None:
    """08-L7: deploy.sh must ensure frontend/.env exists (compose declares it required)."""
    script = DEPLOY_SH.read_text(encoding="utf-8")

    assert '[ "$CMD" != "down" ] && [ ! -f "$REPO_ROOT/frontend/.env" ]' in script
    assert 'cp "$REPO_ROOT/frontend/.env.example" "$REPO_ROOT/frontend/.env"' in script, (
        "deploy.sh must seed frontend/.env from frontend/.env.example like docker.sh's ensure_env_files, instead of failing compose parsing on a fresh checkout (08-L7)"
    )


def test_deploy_sh_down_does_not_claim_config_check(tmp_path: Path) -> None:
    """08-L9: 'down' with no config.yaml must not print a green config check that never ran."""
    bin_dir = tmp_path / "bin"
    docker_log = tmp_path / "docker-calls.log"
    _write_executable(
        bin_dir / "docker",
        f"""#!/usr/bin/env sh
printf '%s\\n' "$*" >> {shlex.quote(str(docker_log))}
exit 0
""",
    )
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["IDEER_HOME"] = str(tmp_path / "home")
    (tmp_path / "home").mkdir()
    env["BETTER_AUTH_SECRET"] = "test-secret"
    env["IDEER_INTERNAL_AUTH_TOKEN"] = "test-token"
    (tmp_path / "config.yaml").write_text("models: []\n", encoding="utf-8")
    env["IDEER_CONFIG_PATH"] = str(tmp_path / "config.yaml")

    proc = subprocess.run(
        ["bash", str(DEPLOY_SH), "down"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert "✓ config.yaml" not in proc.stdout, "down never verifies config.yaml; printing the green check implies a check that did not happen (08-L9)"
    docker_calls = docker_log.read_text(encoding="utf-8")
    assert "down" in docker_calls


def test_pre_commit_validation_script_does_not_reference_archived_validators() -> None:
    """08-L12: the script header must not claim to call the archived validator skills.

    AGENTS.md: frontend-validator / backend-validator are historical proposals
    and not callable skills; the script actually runs pnpm typecheck/lint/format
    and ruff.
    """
    script = (REPO_ROOT / "scripts" / "pre-commit-validation.sh").read_text(encoding="utf-8")
    assert "frontend-validator" not in script
    assert "backend-validator" not in script
    assert "pnpm typecheck" in script
    assert "ruff check" in script


def test_config_upgrade_current_version_prints_no_upgrade_banner(tmp_path: Path) -> None:
    """08-L10: an already-current config must not also print 'version X -> X'."""
    config = tmp_path / "config.yaml"
    example = REPO_ROOT / "config.example.yaml"
    shutil.copy2(example, config)
    env = os.environ.copy()
    env["CONFIG_WIN"] = str(config)
    env["EXAMPLE_WIN"] = str(example)

    env["IDEER_CONFIG_PATH"] = str(config)

    proc = subprocess.run(
        ["bash", str(CONFIG_UPGRADE_SH)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert "is current" in proc.stdout
    assert "Upgrading config.yaml: version" not in proc.stdout, "the upgrade banner is mutually exclusive with the already-current notice; printing both produced a nonsensical 'version X -> X' line (08-L10)"
