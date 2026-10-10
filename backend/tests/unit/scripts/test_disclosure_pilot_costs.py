from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "scripts" / "recompute_disclosure_pilot_costs.py"
sys.path.insert(0, str(ROOT))

from scripts.disclosure_reading_collector import (  # noqa: E402
    candidate_files,
    canonical_json,
    digest,
)


def make_experiment(root: Path) -> tuple[Path, Path, Path, str, str]:
    experiment = root / "experiment"
    freeze_root = experiment / "freeze-v2"
    candidate_root = experiment / "candidates" / "after"
    pilots = freeze_root / "pilots"
    prompts = freeze_root / "prompts"
    candidate_root.mkdir(parents=True)
    pilots.mkdir(parents=True)
    prompts.mkdir()

    source = "alpha\nbeta\n"
    (candidate_root / "README.md").write_text(source, encoding="utf-8")
    rows = candidate_files(candidate_root)
    exclusions = [{"path": row["path"], "sha256": row["sha256"], "reason": row["exclusion"]} for row in rows if row["exclusion"]]
    manifest_body = {
        "format": 2,
        "root_name": candidate_root.name,
        "files": rows,
        "exclusions": exclusions,
    }
    manifest_body["exclusion_sha256"] = digest(canonical_json(exclusions))
    candidate_digest = digest(canonical_json(manifest_body))
    prompt = "Read one file and explain its section.\n"
    (prompts / "ui.txt").write_text(prompt, encoding="utf-8")
    (freeze_root / "candidates").mkdir()
    (freeze_root / "candidates" / "after.manifest.json").write_text(json.dumps({"manifest_sha256": candidate_digest}), encoding="utf-8")
    (freeze_root / "role-map.json").write_text(
        json.dumps(
            {
                "format": 1,
                "candidates": {"after": candidate_digest},
                "paths": {"README.md": "current_documentation"},
                "sections": [],
            }
        ),
        encoding="utf-8",
    )
    queue = [
        {
            "slot": 1,
            "candidate": "after",
            "task": "ui",
            "replicate": 1,
            "stage": "non-scored",
            "freeze": "freeze-v2",
        }
    ]
    queue_bytes = (json.dumps(queue) + "\n").encode()
    (freeze_root / "pilot-queue.json").write_bytes(queue_bytes)
    frozen = {
        "stage": "non-scored",
        "protocol_id": "disclosure-reading-v2",
        "role_map_sha256": hashlib.sha256((freeze_root / "role-map.json").read_bytes()).hexdigest(),
        "candidates": {"after": {"manifest_sha256": candidate_digest}},
        "queue_sha256": hashlib.sha256(queue_bytes).hexdigest(),
        "prompts": {"ui": hashlib.sha256(prompt.encode()).hexdigest()},
    }
    (freeze_root / "freeze.json").write_text(json.dumps(frozen), encoding="utf-8")
    run_id = "after-ui-test-run"
    record = {
        "run_id": run_id,
        "candidate": "after",
        "candidate_root": "/stale/path/ignored-by-recompute",
        "manifest_sha256": candidate_digest,
        "task": "ui",
        "task_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "status": "submitted",
        "started_monotonic": 1.0,
        "submitted_monotonic": 3.0,
        "elapsed_seconds": 2.0,
        "events": [
            {
                "kind": "read",
                "ranges": [{"path": "README.md", "start": 1, "end": 2}],
                "content_bytes": len(source.encode("utf-8")),
            }
        ],
    }
    (pilots / f"{run_id}.json").write_text(json.dumps(record), encoding="utf-8")
    (pilots / f"{run_id}.jsonl").write_text(
        '{"type":"item.completed","item":{"type":"mcp_tool_call","tool":"submit_answer"}}\n',
        encoding="utf-8",
    )
    return experiment, freeze_root, candidate_root, source, candidate_digest


def run_recompute(experiment: Path, out: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--experiment-root", str(experiment), "--out", str(out)],
        check=False,
        text=True,
        capture_output=True,
    )


def test_pilot_cost_cli_recomputes_raw_read_intervals_and_categories(
    tmp_path: Path,
) -> None:
    experiment, freeze_root, _, source, _ = make_experiment(tmp_path)
    output = freeze_root / "pilot-read-cost-report.json"

    result = run_recompute(experiment, output)

    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["read_intervals_recomputed"] is True
    assert report["answer_scoring_performed"] is False
    physical = report["all_physical_attempts"]
    assert physical["count"] == 1
    assert physical["content_bytes_returned"] == len(source.encode("utf-8"))
    assert physical["unique_bytes_read"] == len(source.encode("utf-8"))
    assert physical["categories"]["current_documentation"] == len(source.encode("utf-8"))


def test_pilot_cost_cli_rejects_queue_drift(tmp_path: Path) -> None:
    experiment, freeze_root, _, _, _ = make_experiment(tmp_path)
    queue_path = freeze_root / "pilot-queue.json"
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    queue[0]["task"] = "chat"
    queue_path.write_text(json.dumps(queue), encoding="utf-8")

    result = run_recompute(experiment, freeze_root / "costs.json")

    assert result.returncode != 0
    assert "queue digest mismatch" in result.stderr
    assert not (freeze_root / "costs.json").exists()


def test_pilot_cost_cli_rejects_prompt_drift_even_when_record_is_updated(
    tmp_path: Path,
) -> None:
    experiment, freeze_root, _, _, _ = make_experiment(tmp_path)
    prompt_path = freeze_root / "prompts" / "ui.txt"
    prompt_path.write_text("changed prompt\n", encoding="utf-8")
    record_path = next((freeze_root / "pilots").glob("*.json"))
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["task_sha256"] = hashlib.sha256(prompt_path.read_bytes()).hexdigest()
    record_path.write_text(json.dumps(record), encoding="utf-8")

    result = run_recompute(experiment, freeze_root / "costs.json")

    assert result.returncode != 0
    assert "prompt digest mismatch" in result.stderr
    assert not (freeze_root / "costs.json").exists()


def test_pilot_cost_cli_rejects_record_candidate_manifest_drift(
    tmp_path: Path,
) -> None:
    experiment, freeze_root, _, _, _ = make_experiment(tmp_path)
    record_path = next((freeze_root / "pilots").glob("*.json"))
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["manifest_sha256"] = "0" * 64
    record_path.write_text(json.dumps(record), encoding="utf-8")

    result = run_recompute(experiment, freeze_root / "costs.json")

    assert result.returncode != 0
    assert "candidate manifest digest mismatch" in result.stderr
    assert not (freeze_root / "costs.json").exists()


def test_pilot_cost_cli_rejects_candidate_symlink_escape(tmp_path: Path) -> None:
    experiment, freeze_root, candidate_root, _, _ = make_experiment(tmp_path)
    external = tmp_path / "outside-candidate"
    candidate_root.rename(external)
    candidate_root.symlink_to(external, target_is_directory=True)

    result = run_recompute(experiment, freeze_root / "costs.json")

    assert result.returncode != 0
    assert "candidate snapshot escapes experiment root" in result.stderr
    assert not (freeze_root / "costs.json").exists()


def test_pilot_cost_cli_reports_invalid_manifest_shape_without_traceback(
    tmp_path: Path,
) -> None:
    experiment, freeze_root, _, _, _ = make_experiment(tmp_path)
    (freeze_root / "role-map.json").write_text("[]", encoding="utf-8")

    result = run_recompute(experiment, freeze_root / "costs.json")

    assert result.returncode != 0
    assert "role map must be a JSON object" in result.stderr
    assert "Traceback" not in result.stderr


def test_pilot_cost_cli_rejects_pilots_directory_symlink_escape(tmp_path: Path) -> None:
    experiment, freeze_root, _, _, _ = make_experiment(tmp_path)
    pilots = freeze_root / "pilots"
    external = tmp_path / "outside-pilots"
    pilots.rename(external)
    pilots.symlink_to(external, target_is_directory=True)

    result = run_recompute(experiment, freeze_root / "costs.json")

    assert result.returncode != 0
    assert "records directory escapes experiment root" in result.stderr
    assert "Traceback" not in result.stderr


def test_pilot_cost_cli_rejects_record_symlink_escape(tmp_path: Path) -> None:
    experiment, freeze_root, _, _, _ = make_experiment(tmp_path)
    pilots = freeze_root / "pilots"
    record = next(pilots.glob("*.json"))
    external = tmp_path / "outside-record.json"
    record.rename(external)
    record.symlink_to(external)

    result = run_recompute(experiment, freeze_root / "costs.json")

    assert result.returncode != 0
    assert "pilot record escapes records directory" in result.stderr
    assert "Traceback" not in result.stderr


def test_pilot_cost_cli_rejects_non_object_record_without_traceback(
    tmp_path: Path,
) -> None:
    experiment, freeze_root, _, _, _ = make_experiment(tmp_path)
    record_path = next((freeze_root / "pilots").glob("*.json"))
    record_path.write_text("[]", encoding="utf-8")

    result = run_recompute(experiment, freeze_root / "costs.json")

    assert result.returncode != 0
    assert "pilot record must be a JSON object" in result.stderr
    assert "Traceback" not in result.stderr


def test_pilot_cost_cli_rejects_non_object_candidate_manifest_without_traceback(
    tmp_path: Path,
) -> None:
    experiment, freeze_root, _, _, _ = make_experiment(tmp_path)
    manifest_path = freeze_root / "candidates" / "after.manifest.json"
    manifest_path.write_text("[]", encoding="utf-8")

    result = run_recompute(experiment, freeze_root / "costs.json")

    assert result.returncode != 0
    assert "candidate manifest is invalid" in result.stderr
    assert "Traceback" not in result.stderr
