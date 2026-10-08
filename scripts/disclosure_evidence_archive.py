#!/usr/bin/env python3
"""Pack and verify portable disclosure experiment evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath


MANIFEST_NAME = "MANIFEST.json"
PILOT_CANDIDATES = {"baseline", "after"}
PILOT_TASKS = {
    "ui",
    "chat",
    "knowledge",
    "permissions",
    "tests",
    "runtime",
    "upstream",
    "history",
}


class ArchiveError(Exception):
    """Invalid or incomplete evidence archive."""


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_files(root: Path, prefix: str) -> list[tuple[str, Path]]:
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ArchiveError(f"evidence source is not a directory: {prefix}")
    result: list[tuple[str, Path]] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ArchiveError(
                f"symlinks are not allowed in evidence: {prefix}/{path.relative_to(root)}"
            )
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        result.append((f"{prefix}/{relative}", path))
    return result


def pack_archive(
    legacy_root: Path, experiment_root: Path, output: Path
) -> dict[str, object]:
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise ArchiveError(f"archive already exists: {output}")

    entries = source_files(legacy_root, "legacy") + source_files(
        experiment_root, "experiment"
    )
    if not entries:
        raise ArchiveError("evidence inputs contain no files")
    paths = [name for name, _ in entries]
    if len(paths) != len(set(paths)):
        raise ArchiveError("evidence inputs contain duplicate archive paths")

    rows = [
        {"path": name, "size": path.stat().st_size, "sha256": sha256_file(path)}
        for name, path in entries
    ]
    body: dict[str, object] = {"format": 1, "files": rows}
    body["manifest_sha256"] = hashlib.sha256(canonical_json(body)).hexdigest()
    manifest_bytes = (
        json.dumps(body, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    )

    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
    )
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        with tarfile.open(temporary, "w:gz", compresslevel=6) as archive:
            for name, path in entries:
                archive.add(path, arcname=name, recursive=False)
            import io

            info = tarfile.TarInfo(MANIFEST_NAME)
            info.size = len(manifest_bytes)
            info.mode = 0o644
            archive.addfile(info, io.BytesIO(manifest_bytes))
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)

    return {
        "archive": str(output),
        "files": len(rows),
        "manifest_sha256": body["manifest_sha256"],
        "archive_sha256": sha256_file(output),
    }


def safe_archive_path(raw: str) -> PurePosixPath:
    path = PurePosixPath(raw)
    if (
        not raw
        or "\\" in raw
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or (path.parts and ":" in path.parts[0])
    ):
        raise ArchiveError(f"unsafe archive path: {raw!r}")
    return path


def load_archive_members(
    archive: tarfile.TarFile,
) -> tuple[dict[str, tarfile.TarInfo], dict[str, object]]:
    files: dict[str, tarfile.TarInfo] = {}
    for member in archive.getmembers():
        safe_archive_path(member.name)
        if not member.isfile():
            raise ArchiveError(
                f"non-regular archive member is not allowed: {member.name}"
            )
        if member.name in files:
            raise ArchiveError(f"duplicate archive member: {member.name}")
        files[member.name] = member

    manifest_member = files.pop(MANIFEST_NAME, None)
    if manifest_member is None:
        raise ArchiveError("archive manifest is missing")
    manifest_source = archive.extractfile(manifest_member)
    if manifest_source is None:
        raise ArchiveError("archive manifest cannot be read")
    try:
        manifest = json.load(manifest_source)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ArchiveError("archive manifest is invalid JSON") from exc
    if (
        not isinstance(manifest, dict)
        or manifest.get("format") != 1
        or not isinstance(manifest.get("files"), list)
    ):
        raise ArchiveError("archive manifest has an unsupported format")
    claimed = manifest.get("manifest_sha256")
    unsigned = {
        key: value for key, value in manifest.items() if key != "manifest_sha256"
    }
    actual_manifest_sha = hashlib.sha256(canonical_json(unsigned)).hexdigest()
    if claimed != actual_manifest_sha:
        raise ArchiveError("archive manifest digest mismatch")

    expected: dict[str, dict[str, object]] = {}
    for row in manifest["files"]:
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            raise ArchiveError("archive manifest contains an invalid file row")
        path = row["path"]
        safe_archive_path(path)
        if path == MANIFEST_NAME or path in expected:
            raise ArchiveError(
                f"archive manifest has duplicate or reserved path: {path}"
            )
        if not isinstance(row.get("size"), int) or row["size"] < 0:
            raise ArchiveError(f"archive manifest has an invalid size for {path}")
        if not isinstance(row.get("sha256"), str) or len(row["sha256"]) != 64:
            raise ArchiveError(f"archive manifest has an invalid digest for {path}")
        expected[path] = row
    if set(files) != set(expected):
        raise ArchiveError("archive file set differs from manifest")
    return files, {"manifest": manifest, "expected": expected}


def verify_archive(archive_path: Path, restore_to: Path) -> dict[str, object]:
    restore_to = restore_to.resolve()
    if restore_to.is_symlink():
        raise ArchiveError(f"restore destination cannot be a symlink: {restore_to}")
    if restore_to.exists():
        if not restore_to.is_dir() or any(restore_to.iterdir()):
            raise ArchiveError(f"restore destination must be empty: {restore_to}")
        restore_to.rmdir()
    restore_to.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(
        prefix=".disclosure-restore-", dir=restore_to.parent
    ) as temporary_dir:
        staging = Path(temporary_dir) / "restored"
        staging.mkdir()
        with tarfile.open(archive_path, "r:gz") as archive:
            members, loaded = load_archive_members(archive)
            expected = loaded["expected"]
            for name, member in members.items():
                target = staging.joinpath(*safe_archive_path(name).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    raise ArchiveError(f"archive member cannot be read: {name}")
                with source, target.open("xb") as destination:
                    while chunk := source.read(1024 * 1024):
                        destination.write(chunk)

            actual_paths = {
                path.relative_to(staging).as_posix()
                for path in staging.rglob("*")
                if path.is_file()
            }
            if actual_paths != set(expected):
                raise ArchiveError("restored file set differs from manifest")
            for name, row in expected.items():
                path = staging.joinpath(*safe_archive_path(name).parts)
                if (
                    path.stat().st_size != row["size"]
                    or sha256_file(path) != row["sha256"]
                ):
                    raise ArchiveError(f"digest mismatch for {name}")
            os.replace(staging, restore_to)

    return {
        "restore_to": str(restore_to),
        "verified_files": len(expected),
        "manifest_sha256": loaded["manifest"]["manifest_sha256"],
        "archive_sha256": sha256_file(archive_path),
    }


def recompute_pilots(experiment_root: Path, output: Path) -> dict[str, object]:
    experiment_root = experiment_root.resolve(strict=True)
    try:
        freeze = json.loads(
            (experiment_root / "freeze.json").read_text(encoding="utf-8")
        )
        frozen_model = freeze["model"]["alias"]
        frozen_reasoning = freeze["model"]["reasoning"]
        frozen_stage = freeze["stage"]
    except (OSError, KeyError, json.JSONDecodeError, TypeError) as exc:
        raise ArchiveError("pilot freeze manifest is missing or invalid") from exc
    queue = json.loads(
        (experiment_root / "pilot-queue.json").read_text(encoding="utf-8")
    )
    if not isinstance(queue, list) or not queue:
        raise ArchiveError("pilot queue must be a non-empty JSON array")

    queue_by_key: dict[tuple[str, str], list[dict[str, object]]] = {}
    queue_slots: set[int] = set()
    for row in queue:
        if not isinstance(row, dict):
            raise ArchiveError("pilot queue contains an invalid row")
        slot, candidate, task = row.get("slot"), row.get("candidate"), row.get("task")
        if not isinstance(slot, int) or slot <= 0 or slot in queue_slots:
            raise ArchiveError("pilot queue slots must be unique positive integers")
        if not isinstance(candidate, str) or not isinstance(task, str):
            raise ArchiveError(f"pilot queue slot {slot} has no candidate/task")
        if candidate not in PILOT_CANDIDATES or task not in PILOT_TASKS:
            raise ArchiveError(f"unsafe queue candidate/task in slot {slot}")
        queue_slots.add(slot)
        queue_by_key.setdefault((candidate, task), []).append(row)

    manifest_digests: dict[str, str] = {}
    prompt_digests: dict[str, str] = {}
    for candidate, task in queue_by_key:
        manifest_path = experiment_root / "candidates" / f"{candidate}.manifest.json"
        prompt_path = experiment_root / "prompts" / f"{task}.txt"
        try:
            manifest_digests[candidate] = json.loads(
                manifest_path.read_text(encoding="utf-8")
            )["manifest_sha256"]
            prompt_digests[task] = sha256_file(prompt_path)
        except (OSError, KeyError, json.JSONDecodeError) as exc:
            raise ArchiveError(
                f"frozen manifest or prompt is missing for {candidate}/{task}"
            ) from exc

    pilots_dir = experiment_root / "pilots"
    if not pilots_dir.is_dir():
        raise ArchiveError("pilot records directory is missing")
    records: list[dict[str, object]] = []
    seen_ids: dict[str, dict[str, object]] = {}
    attempts_by_key: dict[tuple[str, str], list[dict[str, object]]] = {}
    for record_path in sorted(pilots_dir.glob("*.json")):
        if record_path.name == "quota-exhausted.json" or record_path.name.endswith(
            ".config.json"
        ):
            continue
        record = json.loads(record_path.read_text(encoding="utf-8"))
        run_id = record.get("run_id")
        candidate, task = record.get("candidate"), record.get("task")
        key = (candidate, task)
        if (
            not isinstance(run_id, str)
            or not run_id
            or Path(run_id).name != run_id
            or run_id in seen_ids
        ):
            raise ArchiveError(
                f"invalid or duplicate pilot run id in {record_path.name}"
            )
        if key not in queue_by_key:
            raise ArchiveError(f"pilot attempt is absent from frozen queue: {run_id}")
        if record.get("manifest_sha256") != manifest_digests[candidate]:
            raise ArchiveError(f"candidate manifest digest drift for {run_id}")
        if record.get("task_sha256") != prompt_digests[task]:
            raise ArchiveError(f"prompt digest drift for {run_id}")
        if record.get("status") not in {
            "started",
            "submitted",
            "failed",
            "interrupted",
            "timeout",
        }:
            raise ArchiveError(f"invalid pilot status for {run_id}")

        trace_path = pilots_dir / f"{run_id}.jsonl"
        config_path = pilots_dir / f"{run_id}.config.json"
        if not trace_path.is_file():
            raise ArchiveError(f"trace is missing for {run_id}")
        if not config_path.is_file():
            raise ArchiveError(f"config sidecar is missing for {run_id}")
        config_sidecar = json.loads(config_path.read_text(encoding="utf-8"))
        config = config_sidecar.get("config")
        if not isinstance(config, dict):
            raise ArchiveError(f"config sidecar is invalid for {run_id}")
        if (
            config.get("model") != frozen_model
            or config.get("reasoning") != frozen_reasoning
            or config.get("stage") != frozen_stage
        ):
            raise ArchiveError(f"model/config drift for {run_id}")
        if (
            config_sidecar.get("prompt_sha256") != record.get("task_sha256")
            or config_sidecar.get("manifest_sha256") != record.get("manifest_sha256")
            or config_sidecar.get("tool_config_sha256")
            != record.get("tool_config_sha256")
        ):
            raise ArchiveError(f"record/config identity mismatch for {run_id}")

        attempt_no = record.get("attempt_no")
        if not isinstance(attempt_no, int) or attempt_no < 1:
            raise ArchiveError(f"invalid attempt number for {run_id}")
        previous_id = record.get("retry_of")
        if previous_id is None and attempt_no != 1:
            raise ArchiveError(f"unlinked retry for {run_id}")
        if previous_id is not None:
            previous = seen_ids.get(previous_id)
            if (
                previous is None
                or (previous.get("candidate"), previous.get("task")) != key
                or previous.get("attempt_no") != attempt_no - 1
            ):
                raise ArchiveError(f"invalid retry lineage for {run_id}")

        seen_ids[run_id] = record
        attempts_by_key.setdefault(key, []).append(record)
        artifact_digest = hashlib.sha256(
            canonical_json(
                {
                    "record": sha256_file(record_path),
                    "trace": sha256_file(trace_path),
                    "config": sha256_file(config_path),
                }
            )
        ).hexdigest()
        records.append(
            {
                "run_id": run_id,
                "candidate": candidate,
                "task": task,
                "attempt_no": attempt_no,
                "retry_of": previous_id,
                "status": record["status"],
                "failure_class": record.get("failure_class"),
                "read_event_count": len(record.get("events", [])),
                "has_submission": record.get("status") == "submitted",
                "artifacts_sha256": artifact_digest,
            }
        )

    for key, attempts in attempts_by_key.items():
        attempts.sort(key=lambda row: row["attempt_no"])
        if len(attempts) > 2:
            raise ArchiveError(f"retry limit exceeded for {key[0]}/{key[1]}")
        if [row["attempt_no"] for row in attempts] != list(range(1, len(attempts) + 1)):
            raise ArchiveError(f"attempt sequence has a gap for {key[0]}/{key[1]}")
        for left, right in zip(attempts, attempts[1:]):
            if right.get("retry_of") != left.get("run_id"):
                raise ArchiveError(f"retry lineage is not linked for {key[0]}/{key[1]}")

    terminal_by_key = {
        key: attempts[-1].get("status")
        for key, attempts in attempts_by_key.items()
        if attempts
    }
    unstarted_slots = [
        row["slot"]
        for row in queue
        if (row["candidate"], row["task"]) not in attempts_by_key
    ]
    incomplete_slots = [
        row["slot"]
        for row in queue
        if terminal_by_key.get((row["candidate"], row["task"])) != "submitted"
    ]
    summary: dict[str, object] = {
        "format": 1,
        "stage": "non-scored",
        "status": "complete" if not incomplete_slots else "incomplete",
        "queue_slot_count": len(queue),
        "attempt_count": len(records),
        "terminal_failures": sum(
            status in {"failed", "interrupted", "timeout"}
            for status in terminal_by_key.values()
        ),
        "submitted_slots": [
            slot for slot in sorted(queue_slots) if slot not in incomplete_slots
        ],
        "incomplete_slots": incomplete_slots,
        "unstarted_queue_slots": unstarted_slots,
        "read_intervals_recomputed": False,
        "answer_scoring_performed": False,
        "records": records,
    }
    if output.exists():
        raise ArchiveError(f"pilot summary output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as destination:
            json.dump(summary, destination, ensure_ascii=False, indent=2)
            destination.write("\n")
            destination.flush()
            os.fsync(destination.fileno())
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "output": str(output),
        "status": summary["status"],
        "attempt_count": len(records),
        "incomplete_slots": incomplete_slots,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    pack_parser = subparsers.add_parser(
        "pack", help="create a checksummed portable archive"
    )
    pack_parser.add_argument("--legacy-root", type=Path, required=True)
    pack_parser.add_argument("--experiment-root", type=Path, required=True)
    pack_parser.add_argument("--out", type=Path, required=True)
    verify_parser = subparsers.add_parser(
        "verify", help="restore and verify an archive"
    )
    verify_parser.add_argument("--archive", type=Path, required=True)
    verify_parser.add_argument("--restore-to", type=Path, required=True)
    recompute_parser = subparsers.add_parser(
        "recompute-pilots", help="recompute pilot completeness from raw records"
    )
    recompute_parser.add_argument("--experiment-root", type=Path, required=True)
    recompute_parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "pack":
            result = pack_archive(args.legacy_root, args.experiment_root, args.out)
        elif args.command == "verify":
            result = verify_archive(args.archive, args.restore_to)
        else:
            result = recompute_pilots(args.experiment_root, args.out)
    except (ArchiveError, OSError, tarfile.TarError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
