#!/usr/bin/env python3
"""Recompute historical disclosure read intervals and costs from retained raw attempts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

from disclosure_reading_collector import canonical_json, candidate_files, digest
from report_disclosure_costs import InputError, build_report


PDR_ID = "pdr-2026-10-07-16cc740f"
EXPECTED_CANDIDATES = {
    "baseline": "ea6d866455937115b99f9bcb9d688923f37bd20cac967e34f8d79030bbcb924a",
    "after": "45e45e0e61b15f812a767978e8354b17ce49bb509c28ffbb703d79811d01303b",
}
EXPECTED_AUDIT_SHA256 = (
    "80f0490eb5f0f5d463f64a599e92d0d62a2799c30c849d061768e41a10875d22"
)
EXPECTED_CATEGORIES = {
    "root_guidance": "root-guidance",
    "descendant_guidance": "other-guidance",
    "route": "task-route",
    "current_documentation": "remaining-engineering-docs",
    "historical_material": "decision-upgrade-history-paths",
    "source_test_config": "source-code",
    "other": "other",
}


class RecomputeError(ValueError):
    """Historical raw evidence cannot be recomputed consistently."""


def sha256_file(path: Path) -> str:
    digest_state = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest_state.update(chunk)
    return digest_state.hexdigest()


def manifest_digest(root: Path) -> str:
    root = root.resolve(strict=True)
    rows = candidate_files(root)
    excluded = [
        {"path": row["path"], "sha256": row["sha256"], "reason": row["exclusion"]}
        for row in rows
        if row["exclusion"]
    ]
    body: dict[str, Any] = {
        "format": 2,
        "root_name": root.name,
        "files": rows,
        "exclusions": excluded,
    }
    body["exclusion_sha256"] = digest(canonical_json(excluded))
    return digest(canonical_json(body))


def role_for_path(path: str) -> str:
    """Reapply the historical ticket09 path-family rules and ticket11 guidance split."""
    parsed = PurePosixPath(path)
    if path == "AGENTS.md":
        return "root_guidance"
    if parsed.name in {"AGENTS.md", "CLAUDE.md"}:
        return "descendant_guidance"
    if path == "docs/agents/task-routing.md" or path.startswith(
        "docs/agents/task-routing/"
    ):
        return "route"
    if (
        path.startswith(
            ("docs/adr/", "docs/decisions/", "docs/upgrades/", "docs/testing/evidence/")
        )
        or "history" in parsed.name.casefold()
        or "archive" in parsed.parts
    ):
        return "historical_material"
    if path.startswith("docs/") or path in {"CONTEXT.md", "UPSTREAM_PATCH_LEDGER.md"}:
        return "current_documentation"
    if path.startswith(
        ("backend/", "frontend/", "scripts/", "resources/", "docker/", "skills/")
    ):
        return "source_test_config"
    return "other"


def _raw_path(legacy_root: Path, audit_path: str) -> Path:
    prefix = "dev-log/disclosure-readability-recovery/"
    relative = (
        audit_path[len(prefix) :] if audit_path.startswith(prefix) else audit_path
    )
    rel = PurePosixPath(relative)
    if rel.is_absolute() or any(part in {"", ".", ".."} for part in rel.parts):
        raise RecomputeError(f"unsafe historical raw path: {audit_path}")
    path = legacy_root.joinpath(*rel.parts).resolve(strict=True)
    if not path.is_relative_to(legacy_root.resolve(strict=True)):
        raise RecomputeError(
            f"historical raw path escapes legacy evidence: {audit_path}"
        )
    return path


def load_trusted_audit(audit_path: Path) -> dict[str, Any]:
    raw = audit_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != EXPECTED_AUDIT_SHA256:
        raise RecomputeError("legacy cost audit digest mismatch")
    audit = json.loads(raw)
    if not isinstance(audit, dict) or not isinstance(audit.get("slots"), list):
        raise RecomputeError("legacy cost audit has an invalid structure")
    return audit


def validate_slots(slots: list[Any]) -> None:
    if len(slots) != 32:
        raise RecomputeError("legacy cost audit must contain exactly 32 slots")
    numbers = [row.get("slot") if isinstance(row, dict) else None for row in slots]
    if set(numbers) != set(range(1, 33)) or len(set(numbers)) != 32:
        raise RecomputeError("legacy cost audit slot identities must be unique 1–32")


def validate_slot_identity(slot: dict[str, Any], record: dict[str, Any]) -> None:
    if any(
        record.get(field) != slot.get(field)
        for field in ("run_id", "candidate", "task", "status")
    ):
        raise RecomputeError(
            f"raw record identity/status mismatch for slot {slot.get('slot')}"
        )
    if record.get("status") not in {"submitted", "failed", "interrupted", "timeout"}:
        raise RecomputeError(f"raw record is not terminal for slot {slot.get('slot')}")


def load_attempt_lineage(legacy_root: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for ticket in ("ticket09", "ticket10"):
        session_root = legacy_root / ticket / "archive/sessions"
        for raw_path in session_root.rglob("*.json"):
            if raw_path.name.endswith(".config.json") or raw_path.name.endswith(
                ".started-snapshot.json"
            ):
                continue
            raw = json.loads(raw_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or not isinstance(raw.get("run_id"), str):
                continue
            run_id = raw["run_id"]
            if run_id in records:
                raise RecomputeError(f"duplicate legacy raw attempt: {run_id}")
            records[run_id] = raw
    if len(records) != 39:
        raise RecomputeError("legacy ticket09/ticket10 raw attempt count must be 39")
    for run_id, record in records.items():
        parent_id = record.get("retry_of")
        if parent_id is None:
            continue
        parent = records.get(parent_id)
        if (
            parent is None
            or parent.get("retry_run_id") != run_id
            or parent.get("candidate") != record.get("candidate")
            or parent.get("task") != record.get("task")
        ):
            raise RecomputeError(f"legacy retry lineage mismatch for {run_id}")
    return records


def _load_attempts(
    legacy_root: Path,
    audit: dict[str, Any],
    candidates: dict[str, Path],
    candidate_digests: dict[str, str],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    attempts: list[dict[str, Any]] = []
    sources: list[dict[str, str]] = []
    validate_slots(audit.get("slots", []))
    lineage = load_attempt_lineage(legacy_root)
    for slot in audit.get("slots", []):
        if not isinstance(slot, dict):
            raise RecomputeError("legacy cost audit contains an invalid slot")
        raw_path = _raw_path(legacy_root, slot.get("raw_record_path", ""))
        raw_sha = sha256_file(raw_path)
        if raw_sha != slot.get("raw_record_sha256"):
            raise RecomputeError(
                f"raw record digest mismatch for slot {slot.get('slot')}"
            )
        record = json.loads(raw_path.read_text(encoding="utf-8"))
        if not isinstance(record, dict):
            raise RecomputeError(
                f"raw record is not an object for slot {slot.get('slot')}"
            )
        validate_slot_identity(slot, record)
        candidate = record.get("candidate")
        if candidate not in candidates:
            raise RecomputeError(
                f"raw record identity mismatch for slot {slot.get('slot')}"
            )
        if record["run_id"] not in lineage or lineage[record["run_id"]].get(
            "retry_of"
        ) != record.get("retry_of"):
            raise RecomputeError(
                f"raw record is absent from retained attempt lineage for {record['run_id']}"
            )
        if any(row.get("retry_of") == record["run_id"] for row in lineage.values()):
            raise RecomputeError(
                f"audit selected a non-terminal retry for {record['run_id']}"
            )
        if record.get("manifest_sha256") != candidate_digests[candidate]:
            raise RecomputeError(f"candidate manifest drift for {record['run_id']}")
        record["candidate_root"] = str(candidates[candidate])
        # The audit selects one terminal attempt per logical slot. Retry linkage stays
        # in the immutable raw record and provenance; this derived input computes only
        # each selected terminal record's intervals and cost.
        record["retry_of"] = None
        record["retry_run_id"] = None
        record["attempt_no"] = 1
        attempts.append(record)
        sources.append({"run_id": record["run_id"], "raw_record_sha256": raw_sha})
    if len(attempts) != 32 or len({row["run_id"] for row in attempts}) != 32:
        raise RecomputeError("expected exactly 32 unique terminal logical attempts")
    return attempts, sources


def recompute(legacy_root: Path, output: Path) -> dict[str, Any]:
    legacy_root = legacy_root.resolve(strict=True)
    audit_path = legacy_root / "ticket11/archive/audits/cost-categories-32-final.json"
    frozen_path = (
        legacy_root
        / "ticket08/archive/manifests/frozen-experiment-pdr-2026-10-07-16cc740f.json"
    )
    audit = load_trusted_audit(audit_path)
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    if not isinstance(frozen, dict):
        raise RecomputeError("frozen manifest has an invalid structure")
    if audit.get("experiment_id") != PDR_ID or frozen.get("experiment_id") != PDR_ID:
        raise RecomputeError("legacy experiment identity mismatch")

    candidates = {
        "baseline": (
            legacy_root / "ticket08/archive/candidates/baseline-867f670"
        ).resolve(strict=True),
        "after": (
            legacy_root / "ticket08/archive/pilots/candidates/after-16cc740"
        ).resolve(strict=True),
    }
    candidate_digests = {
        name: manifest_digest(path) for name, path in candidates.items()
    }
    for candidate, expected in EXPECTED_CANDIDATES.items():
        if candidate_digests[candidate] != expected:
            raise RecomputeError(f"frozen {candidate} candidate digest mismatch")

    attempts, raw_sources = _load_attempts(
        legacy_root, audit, candidates, candidate_digests
    )
    role_map = {
        "format": 1,
        "candidates": candidate_digests,
        "paths": {
            row["path"]: role_for_path(row["path"])
            for candidate_root in candidates.values()
            for row in candidate_files(candidate_root)
        },
        "sections": [],
    }
    report = build_report({"role_map": role_map, "attempts": attempts})
    recomputed = {row["run_id"]: row for row in report["attempts"]}
    expected_rows = {row["run_id"]: row for row in audit["slots"]}
    if set(recomputed) != set(expected_rows):
        raise RecomputeError("recomputed logical attempt set differs from the audit")
    for run_id, expected in expected_rows.items():
        actual = recomputed[run_id]
        if actual["unique_bytes_read"] != expected["unique_utf8_bytes"]:
            raise RecomputeError(f"unique interval byte mismatch for {run_id}")
        if (
            actual["content_bytes_returned"]
            != expected["returned_utf8_bytes_including_repeats"]
        ):
            raise RecomputeError(f"returned byte mismatch for {run_id}")
        for role, label in EXPECTED_CATEGORIES.items():
            if actual["categories"][role] != expected["categories_utf8_bytes"].get(
                label, 0
            ):
                raise RecomputeError(f"cost category mismatch for {run_id}: {role}")

    payload = {
        "format": 1,
        "experiment_id": PDR_ID,
        "status": "recomputed-and-reconciled",
        "source_audit_sha256": sha256_file(audit_path),
        "source_frozen_manifest_sha256": sha256_file(frozen_path),
        "candidate_manifest_sha256": candidate_digests,
        "raw_terminal_records": raw_sources,
        "interval_and_cost_report": report,
    }
    if output.exists():
        raise RecomputeError(f"output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as destination:
            json.dump(
                payload, destination, ensure_ascii=False, indent=2, allow_nan=False
            )
            destination.write("\n")
            destination.flush()
            os.fsync(destination.fileno())
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return {"status": payload["status"], "logical_attempts": 32, "output": str(output)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = recompute(args.legacy_root, args.out)
    except (OSError, KeyError, json.JSONDecodeError, RecomputeError, InputError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
