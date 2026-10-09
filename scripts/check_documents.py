#!/usr/bin/env python3
"""Read-only checker for engineering document governance contracts.

Validates a candidate (the working tree by default, or a selected Git
revision with ``--revision``) against the durable policy in
``docs/governance/document-policy.json``. The checker never mutates files,
installs dependencies, or probes the network; external URLs receive syntax
checks only.

Exit codes:
  0  clean candidate (no findings)
  1  contract findings reported
  2  operational error (bad repo root, unresolvable revision, unreadable
     policy, git failure)

Rule IDs (stable):
  inventory-coverage            path-set coverage and classification counts
  metadata-shape                frontmatter presence, required keys, values
  duplicate-id                  document id uniqueness
  authority-conflict            topic authority uniqueness
  broken-link                   local links/images and external URL syntax
  broken-anchor                 heading anchors of local Markdown targets
  route-incomplete              task-route reachability and validation pointers
  supersession-invalid          replacement naming, back-references, cycles
  evidence-missing              current-state verification evidence
  stale-package-path            old ideer package paths in current documents
  blockquote-metadata-residue   legacy bold blockquote metadata beside frontmatter
  protected-fingerprint-mismatch  protected file content fingerprints
  gitnexus-exemption-missing    AGENTS.md GitNexus block keeps the doc-only exemption line

Required ``task_domains`` names the task domains; ``task_routes`` contains one
``{"domain": name, "route": path, "targets": [path, ...], "validation": path}``
entry per domain. Targets and validation are mandatory, and every named path
must exist in the candidate. Missing configuration is a route-incomplete finding.

Optional ``supplements`` registers paths outside the frozen seed. These paths
participate in body checks with the same classification rules as inventory.
Their recorded sha256/lines remain point-in-time registration records, not
protected fingerprints.

Path conventions: Markdown link/image targets resolve relative to the
containing document (leading ``/`` resolves from the repository root);
frontmatter path fields (``superseded-by``, ``supersedes``) and policy
authority/route paths are repository-root-relative.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import re
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_OPERATIONAL = 2

POLICY_RELATIVE = "docs/governance/document-policy.json"

RULE_INVENTORY_COVERAGE = "inventory-coverage"
RULE_METADATA_SHAPE = "metadata-shape"
RULE_DUPLICATE_ID = "duplicate-id"
RULE_AUTHORITY_CONFLICT = "authority-conflict"
RULE_BROKEN_LINK = "broken-link"
RULE_BROKEN_ANCHOR = "broken-anchor"
RULE_ROUTE_INCOMPLETE = "route-incomplete"
RULE_SUPERSESSION_INVALID = "supersession-invalid"
RULE_EVIDENCE_MISSING = "evidence-missing"
RULE_STALE_PACKAGE_PATH = "stale-package-path"
RULE_BLOCKQUOTE_METADATA_RESIDUE = "blockquote-metadata-residue"
RULE_PROTECTED_FINGERPRINT = "protected-fingerprint-mismatch"
RULE_GITNEXUS_EXEMPTION = "gitnexus-exemption-missing"

FRONTMATTER_REQUIRED_KEYS = ("id", "kind", "status", "owner", "scope")
VALID_STATUS = frozenset({"current", "draft", "superseded", "archived"})
VALID_KIND = frozenset(
    {"index", "reference", "policy", "decision", "plan", "snapshot", "evidence"}
)
FRONTMATTER_EXEMPT_BASENAMES = frozenset({"AGENTS.md", "CLAUDE.md"})
FRONTMATTER_REQUIRED_CLASSIFICATIONS = frozenset(
    {"engineering-body-review", "agent-guidance"}
)


class OperationalError(RuntimeError):
    """Checker cannot run: configuration, git, or policy failure."""


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: str
    file: str
    location: str
    reason: str


@dataclass(frozen=True)
class Candidate:
    mode: str  # "worktree" or "revision"
    revision: str | None
    head: str | None


def _git(root: Path, *args: str) -> bytes:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, check=False)
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise OperationalError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout


def _git_success(root: Path, *args: str) -> bool:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, check=False)
    return result.returncode == 0


def _git_paths(root: Path, *args: str) -> set[PurePosixPath]:
    output = _git(root, *args)
    paths: set[PurePosixPath] = set()
    for raw in output.split(b"\0"):
        if not raw:
            continue
        path = PurePosixPath(raw.decode("utf-8", errors="strict"))
        if path.is_absolute() or ".." in path.parts:
            raise OperationalError(f"unsafe git path: {path}")
        paths.add(path)
    return paths


class WorktreeSource:
    """Reads tracked paths and working-tree content (staged files included)."""

    mode = "worktree"

    def __init__(self, root: Path) -> None:
        self._root = root
        self._tracked = _git_paths(
            root, "ls-files", "--cached", "--others", "--exclude-standard", "-z"
        )

    def tracked_paths(self) -> set[PurePosixPath]:
        return set(self._tracked)

    def read(self, path: PurePosixPath) -> bytes:
        target = self._root / Path(path.as_posix())
        try:
            return target.read_bytes()
        except OSError as exc:
            raise KeyError(path.as_posix()) from exc

    def close(self) -> None:
        return None


class RevisionSource:
    """Reads path sets and blob content strictly from one Git revision.

    Content comes from ``git cat-file --batch``; the working tree and the
    index are never consulted, so uncommitted changes cannot mask a candidate
    failure.
    """

    mode = "revision"

    def __init__(self, root: Path, revision: str) -> None:
        self._root = root
        self._revision = revision
        resolved = _git(
            root, "rev-parse", "--verify", "--quiet", f"{revision}^{{commit}}"
        )
        self.commit = resolved.decode("ascii").strip()
        self._tracked = _git_paths(
            root, "ls-tree", "-r", "--name-only", "-z", self.commit
        )
        self._proc: subprocess.Popen[bytes] | None = None

    def tracked_paths(self) -> set[PurePosixPath]:
        return set(self._tracked)

    def read(self, path: PurePosixPath) -> bytes:
        if self._proc is None:
            self._proc = subprocess.Popen(
                ["git", "cat-file", "--batch"],
                cwd=self._root,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
            )
        assert self._proc.stdin is not None and self._proc.stdout is not None
        request = f"{self._revision}:{path.as_posix()}\n".encode("utf-8")
        self._proc.stdin.write(request)
        self._proc.stdin.flush()
        header = self._proc.stdout.readline()
        if header.endswith(b"missing\n") or b"ambiguous" in header:
            raise KeyError(path.as_posix())
        try:
            size = int(header.rsplit(b" ", 1)[1].strip())
        except (IndexError, ValueError) as exc:
            raise OperationalError(
                f"unexpected git cat-file header for {path}: {header!r}"
            ) from exc
        data = self._proc.stdout.read(size)
        if len(data) != size:
            raise OperationalError(f"short read from git cat-file for {path}")
        self._proc.stdout.read(1)  # trailing newline after the blob
        return data

    def close(self) -> None:
        if self._proc is not None:
            self._proc.stdin.close()
            self._proc.terminate()
            self._proc.wait()
            self._proc = None


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


DocumentSource = WorktreeSource | RevisionSource


def _load_policy(source: DocumentSource) -> dict:
    try:
        raw = source.read(PurePosixPath(POLICY_RELATIVE))
    except KeyError as exc:
        raise OperationalError(
            f"policy file missing from candidate: {POLICY_RELATIVE}"
        ) from exc
    try:
        policy = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OperationalError(f"policy file is not valid JSON: {exc}") from exc
    if not isinstance(policy, dict):
        raise OperationalError("policy file must contain a JSON object")
    inventory = policy.get("inventory")
    if not isinstance(inventory, dict) or not isinstance(inventory.get("files"), list):
        raise OperationalError("policy file is missing inventory.files")
    return policy


def _inventory_paths(policy: dict) -> list[PurePosixPath]:
    return [PurePosixPath(str(row["path"])) for row in policy["inventory"]["files"]]


def _exclusion_roots(policy: dict) -> tuple[set[PurePosixPath], list[str]]:
    exact: set[PurePosixPath] = set()
    prefixes: list[str] = []
    categories = policy.get("exclusions", {}).get("categories", [])
    if not isinstance(categories, list):
        raise OperationalError("policy exclusions.categories must be a list")
    for category in categories:
        for path in category.get("paths", []) or []:
            exact.add(PurePosixPath(str(path)))
        prefixes.extend(
            str(prefix) for prefix in category.get("path_prefixes", []) or []
        )
    return exact, prefixes


def _supplement_paths(policy: dict) -> set[PurePosixPath]:
    """Paths registered under ``supplements``: covered like inventory, must exist."""
    supplements = policy.get("supplements")
    if supplements is None:
        return set()
    if not isinstance(supplements, dict) or not isinstance(
        supplements.get("files"), list
    ):
        raise OperationalError("policy supplements.files must be a list")
    return {PurePosixPath(str(row["path"])) for row in supplements["files"]}


def check_inventory_coverage(policy: dict, source: DocumentSource) -> list[Finding]:
    findings: list[Finding] = []
    tracked = source.tracked_paths()
    tracked_md = {path for path in tracked if path.name.lower().endswith(".md")}
    inventory = _inventory_paths(policy)
    inventory_set = set(inventory)
    exact, prefixes = _exclusion_roots(policy)
    supplements = _supplement_paths(policy)

    def covered(path: PurePosixPath) -> bool:
        if path in inventory_set or path in exact or path in supplements:
            return True
        posix = path.as_posix()
        return any(posix.startswith(prefix) for prefix in prefixes)

    for path in sorted(inventory_set):
        try:
            source.read(path)
        except KeyError:
            findings.append(
                Finding(
                    RULE_INVENTORY_COVERAGE,
                    "error",
                    path.as_posix(),
                    "",
                    "inventory path missing from candidate",
                )
            )

    for path in sorted(supplements - inventory_set):
        try:
            source.read(path)
        except KeyError:
            findings.append(
                Finding(
                    RULE_INVENTORY_COVERAGE,
                    "error",
                    path.as_posix(),
                    "",
                    "supplement path missing from candidate",
                )
            )

    uncovered = sorted(path for path in tracked_md if not covered(path))
    for path in uncovered:
        findings.append(
            Finding(
                RULE_INVENTORY_COVERAGE,
                "error",
                path.as_posix(),
                "",
                "tracked markdown path not covered by inventory or exclusions",
            )
        )

    rows = policy["inventory"]["files"]
    computed: dict[str, int] = {}
    for row in rows:
        classification = str(row.get("classification", ""))
        computed[classification] = computed.get(classification, 0) + 1
    declared_counts = policy["inventory"].get("classification_counts")
    if (
        isinstance(declared_counts, dict)
        and {k: int(v) for k, v in declared_counts.items()} != computed
    ):
        findings.append(
            Finding(
                RULE_INVENTORY_COVERAGE,
                "error",
                POLICY_RELATIVE,
                "",
                f"classification_counts {declared_counts} do not match inventory rows {computed}",
            )
        )
    declared_total = policy["inventory"].get("count")
    if isinstance(declared_total, int) and declared_total != len(rows):
        findings.append(
            Finding(
                RULE_INVENTORY_COVERAGE,
                "error",
                POLICY_RELATIVE,
                "",
                f"inventory count {declared_total} does not match {len(rows)} rows",
            )
        )
    return findings


def check_protected_fingerprints(policy: dict, source: DocumentSource) -> list[Finding]:
    findings: list[Finding] = []
    protected = policy.get("protected_files", {})
    fingerprints = protected.get("fingerprints")
    if not isinstance(fingerprints, list):
        raise OperationalError("policy protected_files.fingerprints must be a list")
    for entry in fingerprints:
        path = PurePosixPath(str(entry["path"]))
        try:
            data = source.read(path)
        except KeyError:
            findings.append(
                Finding(
                    RULE_PROTECTED_FINGERPRINT,
                    "error",
                    path.as_posix(),
                    "",
                    "protected file missing from candidate",
                )
            )
            continue
        actual = _sha256_hex(data)
        if actual != str(entry.get("sha256", "")):
            findings.append(
                Finding(
                    RULE_PROTECTED_FINGERPRINT,
                    "error",
                    path.as_posix(),
                    "",
                    f"protected fingerprint mismatch: expected {entry.get('sha256')}, got {actual}",
                )
            )
    return findings


def _parse_frontmatter(text: str) -> dict[str, object]:
    """Parse a simple ``key: value`` YAML frontmatter block.

    Returns an empty dict when the document has no frontmatter block. Values
    are scalars or simple inline lists (``[a, b]``); nested structures are not
    supported and left unparsed.
    """
    if not text.startswith("---"):
        return {}
    lines = text.splitlines()
    if len(lines) < 2 or lines[0].strip() != "---":
        return {}
    fields: dict[str, object] = {}
    for index in range(1, len(lines)):
        line = lines[index]
        if line.strip() == "---":
            return fields
        match = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if not match:
            return fields
        key, value = match.group(1), match.group(2).strip()
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            fields[key] = [item.strip() for item in inner.split(",")] if inner else []
        else:
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]
            fields[key] = value
    return fields


def _frontmatter_line_count(text: str) -> int:
    """Number of lines occupied by the frontmatter block; 0 when absent."""
    if not text.startswith("---"):
        return 0
    lines = text.splitlines()
    if len(lines) < 2 or lines[0].strip() != "---":
        return 0
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return index + 1
    return 0


def _document_texts(
    policy: dict, source: DocumentSource, tracked: set[PurePosixPath]
) -> dict[PurePosixPath, str]:
    texts: dict[PurePosixPath, str] = {}
    for path in _inventory_paths(policy):
        if path not in tracked:
            continue
        try:
            data = source.read(path)
        except KeyError:
            continue
        texts[path] = data.decode("utf-8", errors="replace")
    return texts


def check_metadata(policy: dict, texts: dict[PurePosixPath, str]) -> list[Finding]:
    findings: list[Finding] = []
    for row in policy["inventory"]["files"]:
        path = PurePosixPath(str(row["path"]))
        if (
            str(row.get("classification", ""))
            not in FRONTMATTER_REQUIRED_CLASSIFICATIONS
        ):
            continue
        if path.name in FRONTMATTER_EXEMPT_BASENAMES:
            continue
        text = texts.get(path)
        if text is None:
            continue
        fields = _parse_frontmatter(text)
        if not fields:
            findings.append(
                Finding(
                    RULE_METADATA_SHAPE,
                    "error",
                    path.as_posix(),
                    "1",
                    "required frontmatter block is missing",
                )
            )
            continue
        missing = [key for key in FRONTMATTER_REQUIRED_KEYS if key not in fields]
        if missing:
            findings.append(
                Finding(
                    RULE_METADATA_SHAPE,
                    "error",
                    path.as_posix(),
                    "1",
                    f"frontmatter is missing required keys: {', '.join(missing)}",
                )
            )
        status = fields.get("status")
        if status is not None and status not in VALID_STATUS:
            findings.append(
                Finding(
                    RULE_METADATA_SHAPE,
                    "error",
                    path.as_posix(),
                    "1",
                    f"frontmatter status {status!r} is not one of {sorted(VALID_STATUS)}",
                )
            )
        kind = fields.get("kind")
        if kind is not None and kind not in VALID_KIND:
            findings.append(
                Finding(
                    RULE_METADATA_SHAPE,
                    "error",
                    path.as_posix(),
                    "1",
                    f"frontmatter kind {kind!r} is not one of {sorted(VALID_KIND)}",
                )
            )
    return findings


def check_duplicate_ids(policy: dict, texts: dict[PurePosixPath, str]) -> list[Finding]:
    findings: list[Finding] = []
    seen: dict[str, PurePosixPath] = {}
    for row in policy["inventory"]["files"]:
        path = PurePosixPath(str(row["path"]))
        text = texts.get(path)
        if text is None:
            continue
        doc_id = _parse_frontmatter(text).get("id")
        if not isinstance(doc_id, str) or not doc_id:
            continue
        first = seen.get(doc_id)
        if first is None:
            seen[doc_id] = path
        else:
            findings.append(
                Finding(
                    RULE_DUPLICATE_ID,
                    "error",
                    path.as_posix(),
                    "1",
                    f"document id {doc_id!r} duplicates {first.as_posix()}",
                )
            )
    return findings


def check_authority_uniqueness(policy: dict) -> list[Finding]:
    findings: list[Finding] = []
    topics = policy.get("authority_topics", [])
    if not isinstance(topics, list):
        raise OperationalError("policy authority_topics must be a list")
    seen_pairs: dict[tuple[str, str], str] = {}
    scope_paths: dict[tuple[str, str], str] = {}
    for topic in topics:
        if not isinstance(topic, dict):
            raise OperationalError("policy authority_topics entries must be objects")
        name = str(topic.get("topic", ""))
        scope = str(topic.get("scope", ""))
        authorities = topic.get("authorities")
        if not isinstance(authorities, list):
            raise OperationalError(
                f"policy authority topic {name!r} is missing an authorities list"
            )
        pair = (name, scope)
        if pair in seen_pairs:
            findings.append(
                Finding(
                    RULE_AUTHORITY_CONFLICT,
                    "error",
                    POLICY_RELATIVE,
                    "",
                    f"authority topic {name!r} with scope {scope!r} is declared twice "
                    f"(first declared with authorities {seen_pairs[pair]!r})",
                )
            )
        else:
            seen_pairs[pair] = str(authorities)
        claimed: set[str] = set()
        for authority in authorities:
            path = str(authority)
            if path in claimed:
                findings.append(
                    Finding(
                        RULE_AUTHORITY_CONFLICT,
                        "error",
                        POLICY_RELATIVE,
                        "",
                        f"authority topic {name!r} lists {path} more than once",
                    )
                )
            claimed.add(path)
            scope_key = (scope, path)
            if scope_key in scope_paths and scope_paths[scope_key] != name:
                findings.append(
                    Finding(
                        RULE_AUTHORITY_CONFLICT,
                        "error",
                        POLICY_RELATIVE,
                        "",
                        f"{path} is declared an authority for scope {scope!r} by both "
                        f"topic {scope_paths[scope_key]!r} and topic {name!r}",
                    )
                )
            else:
                scope_paths[scope_key] = name
    return findings


_INLINE_LINK_RE = re.compile(
    r"!?\[(?P<text>[^\]\n]*)\]\(\s*(?:<(?P<angle>[^>]*)>|(?P<target>[^)\s]+))(?:\s+\"[^\"]*\")?\s*\)"
)
_REFERENCE_USE_RE = re.compile(r"!?\[(?P<text>[^\]\n]+)\]\[(?P<label>[^\]\n]*)\]")
_REFERENCE_DEF_RE = re.compile(r"^\s*\[([^\]\n]+)\]:\s+(\S+)\s*$")
_EXTERNAL_SCHEME_RE = re.compile(
    r"^(?P<scheme>https?|mailto):(?P<rest>.*)$", re.IGNORECASE
)


def _iter_outside_fences(text: str) -> list[tuple[int, str]]:
    """Return (line_number, line) pairs for lines outside fenced code blocks.

    Lines are returned unmodified; inline code spans are still present.
    """
    entries: list[tuple[int, str]] = []
    fence = ""
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if fence:
            if stripped.startswith(fence):
                fence = ""
            continue
        opening = re.match(r"^(`{3,}|~{3,})", stripped)
        if opening:
            fence = opening.group(1)
            continue
        entries.append((number, line))
    return entries


def _visible_lines(text: str) -> list[tuple[int, str]]:
    """Return (line_number, line) outside fenced code blocks, inline code spans removed."""
    return [
        (number, re.sub(r"`[^`]*`", "", line))
        for number, line in _iter_outside_fences(text)
    ]


def _heading_anchors(text: str) -> set[str]:
    """GitHub-style heading slug approximation.

    Slugs are lowercased; characters outside Unicode word characters, spaces,
    and hyphens are removed and spaces become hyphens. Repeated slugs gain
    ``-N`` suffixes. Emoji and other symbol punctuation are not preserved
    (unlike GitHub's exact renderer), which can produce anchor findings for
    symbol-led headings; those documents are corrected in the body-audit
    batches.
    """
    slugs: dict[str, int] = {}
    for number, line in _visible_lines(text):
        match = re.match(r"^\s{0,3}(#{1,6})\s+(.*)$", line)
        if not match:
            continue
        heading = re.sub(r"[*_`]", "", match.group(2)).strip()
        slug = re.sub(r"[^\w\- ]", "", heading.lower()).strip().replace(" ", "-")
        if not slug:
            continue
        slugs[slug] = slugs.get(slug, 0) + 1
    anchors: set[str] = set()
    for slug, count in slugs.items():
        anchors.add(slug)
        for occurrence in range(1, count):
            anchors.add(f"{slug}-{occurrence}")
    return anchors


def _link_targets(text: str) -> list[tuple[int, str]]:
    definitions: dict[str, str] = {}
    for _, line in _visible_lines(text):
        definition = _REFERENCE_DEF_RE.match(line)
        if definition:
            definitions[definition.group(1).strip().casefold()] = definition.group(2)
    targets: list[tuple[int, str]] = []
    for number, line in _visible_lines(text):
        if _REFERENCE_DEF_RE.match(line):
            continue
        for match in _INLINE_LINK_RE.finditer(line):
            target = (
                match.group("angle")
                if match.group("angle") is not None
                else match.group("target")
            )
            if target is not None:
                targets.append((number, target))
        for match in _REFERENCE_USE_RE.finditer(line):
            label = (
                match.group("label").strip().casefold()
                or match.group("text").strip().casefold()
            )
            if label in definitions:
                targets.append((number, definitions[label]))
    return targets


def _classify_target(target: str) -> tuple[str, str, str]:
    """Return (kind, path, fragment) where kind is external|anchor|internal|skip."""
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    if target.startswith("#"):
        return "anchor", "", target[1:]
    match = _EXTERNAL_SCHEME_RE.match(target)
    if match:
        return "external", target, ""
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target):
        return "skip", target, ""
    path, _, fragment = target.partition("#")
    return "internal", path, fragment


def _resolve_internal(doc_path: PurePosixPath, relative: str) -> PurePosixPath | None:
    if relative.startswith("/"):
        candidate = PurePosixPath(relative.lstrip("/"))
    else:
        joined = PurePosixPath(doc_path.parent.as_posix() or ".") / relative
        candidate = PurePosixPath(joined.as_posix())
    posix = posixpath.normpath(candidate.as_posix())
    if posix.startswith("../") or posix == ".." or posix == ".":
        return None
    return PurePosixPath(posix)


def _resolve_repo_path(value: str) -> PurePosixPath | None:
    """Normalize a repository-root-relative path reference."""
    candidate = PurePosixPath(value.lstrip("/"))
    posix = posixpath.normpath(candidate.as_posix())
    if posix.startswith("../") or posix == ".." or posix == ".":
        return None
    return PurePosixPath(posix)


def check_links(
    policy: dict, texts: dict[PurePosixPath, str], tracked: set[PurePosixPath]
) -> list[Finding]:
    findings: list[Finding] = []
    anchor_cache: dict[PurePosixPath, set[str]] = {}
    for row in policy["inventory"]["files"]:
        doc_path = PurePosixPath(str(row["path"]))
        text = texts.get(doc_path)
        if text is None:
            continue
        for number, target in _link_targets(text):
            kind, path_part, fragment = _classify_target(target)
            if kind == "skip":
                continue
            if kind == "external":
                match = _EXTERNAL_SCHEME_RE.match(target)
                body = match.group("rest").lstrip("/") if match else ""
                if not body or any(char.isspace() for char in body):
                    findings.append(
                        Finding(
                            RULE_BROKEN_LINK,
                            "error",
                            doc_path.as_posix(),
                            str(number),
                            f"external URL {target!r} is syntactically invalid",
                        )
                    )
                continue
            if kind == "anchor":
                anchors = anchor_cache.setdefault(doc_path, _heading_anchors(text))
                if fragment and fragment not in anchors:
                    findings.append(
                        Finding(
                            RULE_BROKEN_ANCHOR,
                            "error",
                            doc_path.as_posix(),
                            str(number),
                            f"anchor #{fragment} does not match any heading in {doc_path.as_posix()}",
                        )
                    )
                continue
            resolved = _resolve_internal(doc_path, path_part)
            exists = resolved is not None and (
                resolved in tracked
                # Trailing-slash targets reference directories; they exist when
                # any tracked file lives underneath them.
                or (
                    resolved.as_posix() != ""
                    and any(
                        path.as_posix().startswith(f"{resolved.as_posix()}/")
                        for path in tracked
                    )
                )
            )
            if not exists:
                findings.append(
                    Finding(
                        RULE_BROKEN_LINK,
                        "error",
                        doc_path.as_posix(),
                        str(number),
                        f"local target {path_part!r} does not exist in the candidate",
                    )
                )
                continue
            if fragment and resolved.name.lower().endswith(".md"):
                target_text = texts.get(resolved)
                if target_text is None:
                    continue
                anchors = anchor_cache.setdefault(
                    resolved, _heading_anchors(target_text)
                )
                if fragment not in anchors:
                    findings.append(
                        Finding(
                            RULE_BROKEN_ANCHOR,
                            "error",
                            doc_path.as_posix(),
                            str(number),
                            f"anchor #{fragment} does not match any heading in {resolved.as_posix()}",
                        )
                    )
    return findings


def check_task_routes(policy: dict, tracked: set[PurePosixPath]) -> list[Finding]:
    findings: list[Finding] = []
    routes = policy.get("task_routes", [])
    if not isinstance(routes, list):
        raise OperationalError("policy task_routes must be a list")
    if not routes:
        findings.append(
            Finding(
                RULE_ROUTE_INCOMPLETE,
                "error",
                POLICY_RELATIVE,
                "",
                "task_routes must contain the task routing configuration",
            )
        )
    domains = policy.get("task_domains", [])
    if (
        not isinstance(domains, list)
        or not domains
        or any(not isinstance(domain, str) or not domain.strip() for domain in domains)
    ):
        findings.append(
            Finding(
                RULE_ROUTE_INCOMPLETE,
                "error",
                POLICY_RELATIVE,
                "",
                "task_domains must declare the required task domains",
            )
        )
        domains = []
    if len(domains) != len(set(domains)):
        findings.append(
            Finding(
                RULE_ROUTE_INCOMPLETE,
                "error",
                POLICY_RELATIVE,
                "",
                "task_domains must contain unique domain names",
            )
        )
    seen_domains: set[str] = set()
    for entry in routes:
        if not isinstance(entry, dict) or "route" not in entry:
            findings.append(
                Finding(
                    RULE_ROUTE_INCOMPLETE,
                    "error",
                    POLICY_RELATIVE,
                    "",
                    "task_routes entry must be an object with a route path",
                )
            )
            continue
        domain = entry.get("domain")
        if (
            not isinstance(domain, str)
            or domain not in domains
            or domain in seen_domains
        ):
            findings.append(
                Finding(
                    RULE_ROUTE_INCOMPLETE,
                    "error",
                    POLICY_RELATIVE,
                    "",
                    f"route domain {domain!r} must be declared and unique",
                )
            )
        else:
            seen_domains.add(domain)
        targets = entry.get("targets")
        if (
            not isinstance(targets, list)
            or not targets
            or any(
                not isinstance(target, str) or not target.strip() for target in targets
            )
        ):
            findings.append(
                Finding(
                    RULE_ROUTE_INCOMPLETE,
                    "error",
                    POLICY_RELATIVE,
                    "",
                    f"route {domain!r} requires nonempty targets",
                )
            )
            targets = []
        if (
            not isinstance(entry.get("validation"), str)
            or not entry["validation"].strip()
        ):
            findings.append(
                Finding(
                    RULE_ROUTE_INCOMPLETE,
                    "error",
                    POLICY_RELATIVE,
                    "",
                    f"route {domain!r} requires a validation pointer",
                )
            )
        route = PurePosixPath(str(entry["route"]))
        if route not in tracked:
            findings.append(
                Finding(
                    RULE_ROUTE_INCOMPLETE,
                    "error",
                    route.as_posix(),
                    "",
                    "route document does not exist in the candidate",
                )
            )
        for target in targets:
            target_path = PurePosixPath(str(target))
            if target_path not in tracked:
                findings.append(
                    Finding(
                        RULE_ROUTE_INCOMPLETE,
                        "error",
                        route.as_posix(),
                        "",
                        f"route target {target_path.as_posix()} does not exist in the candidate",
                    )
                )
        validation = entry.get("validation")
        if isinstance(validation, str) and validation.strip():
            validation_path = PurePosixPath(str(validation))
            if validation_path not in tracked:
                findings.append(
                    Finding(
                        RULE_ROUTE_INCOMPLETE,
                        "error",
                        route.as_posix(),
                        "",
                        f"route validation pointer {validation_path.as_posix()} does not exist in the candidate",
                    )
                )
    for domain in sorted(set(domains) - seen_domains):
        findings.append(
            Finding(
                RULE_ROUTE_INCOMPLETE,
                "error",
                POLICY_RELATIVE,
                "",
                f"missing route for task domain {domain!r}",
            )
        )
    return findings


def _frontmatter_by_path(
    policy: dict, texts: dict[PurePosixPath, str]
) -> dict[PurePosixPath, dict[str, object]]:
    return {path: _parse_frontmatter(text) for path, text in texts.items()}


def check_supersession(
    policy: dict, texts: dict[PurePosixPath, str], tracked: set[PurePosixPath]
) -> list[Finding]:
    findings: list[Finding] = []
    frontmatter = _frontmatter_by_path(policy, texts)
    replacements: dict[PurePosixPath, PurePosixPath] = {}
    for path, fields in frontmatter.items():
        status = fields.get("status")
        declared = fields.get("superseded-by")
        if declared is not None and status != "superseded":
            findings.append(
                Finding(
                    RULE_SUPERSESSION_INVALID,
                    "error",
                    path.as_posix(),
                    "1",
                    f"superseded-by is declared but status is {status!r}, not 'superseded'",
                )
            )
        if status != "superseded":
            continue
        if not isinstance(declared, str) or not declared:
            findings.append(
                Finding(
                    RULE_SUPERSESSION_INVALID,
                    "error",
                    path.as_posix(),
                    "1",
                    "superseded documents must name their replacement with superseded-by",
                )
            )
            continue
        resolved = _resolve_repo_path(declared)
        if resolved is None or resolved not in tracked:
            findings.append(
                Finding(
                    RULE_SUPERSESSION_INVALID,
                    "error",
                    path.as_posix(),
                    "1",
                    f"superseded-by target {declared!r} does not exist in the candidate",
                )
            )
            continue
        replacements[path] = resolved
        target_fields = frontmatter.get(resolved)
        if target_fields:
            back = target_fields.get("supersedes")
            back_list = (
                back
                if isinstance(back, list)
                else [back]
                if isinstance(back, str)
                else []
            )
            if path.as_posix() not in back_list and path.name not in back_list:
                findings.append(
                    Finding(
                        RULE_SUPERSESSION_INVALID,
                        "error",
                        resolved.as_posix(),
                        "1",
                        f"replacement does not declare supersedes back-reference to {path.as_posix()}",
                    )
                )
    for origin, replacement in replacements.items():
        seen = {origin}
        current = replacement
        while True:
            if current in seen:
                for path in seen:
                    findings.append(
                        Finding(
                            RULE_SUPERSESSION_INVALID,
                            "error",
                            path.as_posix(),
                            "1",
                            "supersession chain contains a cycle",
                        )
                    )
                break
            seen.add(current)
            if current not in replacements:
                break
            current = replacements[current]
    return findings


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def check_evidence(policy: dict, texts: dict[PurePosixPath, str]) -> list[Finding]:
    findings: list[Finding] = []
    for row in policy["inventory"]["files"]:
        path = PurePosixPath(str(row["path"]))
        text = texts.get(path)
        if text is None:
            continue
        fields = _parse_frontmatter(text)
        if not fields:
            continue
        last_verified = fields.get("last-verified")
        if (
            isinstance(last_verified, str)
            and last_verified
            and not _DATE_RE.match(last_verified)
        ):
            findings.append(
                Finding(
                    RULE_EVIDENCE_MISSING,
                    "error",
                    path.as_posix(),
                    "1",
                    f"last-verified {last_verified!r} is not a YYYY-MM-DD date",
                )
            )
        if fields.get("status") != "current" or fields.get("kind") != "reference":
            continue
        if not isinstance(last_verified, str) or not last_verified:
            findings.append(
                Finding(
                    RULE_EVIDENCE_MISSING,
                    "error",
                    path.as_posix(),
                    "1",
                    "current reference requires a last-verified date",
                )
            )
        verified_against = fields.get("verified-against")
        if not isinstance(verified_against, str) or not verified_against:
            findings.append(
                Finding(
                    RULE_EVIDENCE_MISSING,
                    "error",
                    path.as_posix(),
                    "1",
                    "current reference requires a verified-against candidate reference",
                )
            )
    return findings


_STALE_PACKAGE_RE = re.compile(
    # ``ideer.`` as a Python package/module prefix. The lookbehind keeps URL
    # contexts out (``https://ideer.tech``, ``.../bytedance/ideer.git``): a
    # domain or repository name is not a package path. The brand name "iDeer"
    # in prose never matches (the pattern is lowercase and case-sensitive).
    r"(?<![\w./])ideer\.[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*"
    # Old harness directory prefix; the current home is harness/deerflow/.
    r"|harness/ideer(?![\w-])"
)


def check_stale_package_paths(
    policy: dict, texts: dict[PurePosixPath, str]
) -> list[Finding]:
    """Report old ``ideer`` package paths in documents whose status is current.

    Historical and frozen documents (any other status, or no frontmatter) are
    exempt. Fenced code blocks are skipped: they quote verbatim commands that
    may deliberately document old-version tooling. Inline code is scanned: a
    package path inside backticks is still the document's own claim about the
    current system.
    """
    findings: list[Finding] = []
    for row in policy["inventory"]["files"]:
        path = PurePosixPath(str(row["path"]))
        text = texts.get(path)
        if text is None:
            continue
        if _parse_frontmatter(text).get("status") != "current":
            continue
        frontmatter_lines = _frontmatter_line_count(text)
        for number, line in _iter_outside_fences(text):
            if number <= frontmatter_lines:
                continue
            match = _STALE_PACKAGE_RE.search(line)
            if match:
                findings.append(
                    Finding(
                        RULE_STALE_PACKAGE_PATH,
                        "error",
                        path.as_posix(),
                        str(number),
                        f"current document references legacy package path {match.group(0)!r}",
                    )
                )
    return findings


# Legacy header format used before the frontmatter migration: a bold
# Chinese-key status/date blockquote line. The sanctioned header that replaced
# it uses lowercase keys ("> audience:", "> status:", "> canonical-path:") and
# never matches. Documents without frontmatter are exempt: the blockquote is
# then their only metadata carrier.
_BLOCKQUOTE_RESIDUE_KEYS = (
    "状态",
    "当前状态",
    "日期",
    "制定日期",
    "创建日期",
    "生成日期",
)
_BLOCKQUOTE_RESIDUE_RE = re.compile(
    r"^[ \t]*>[ \t]*\*\*(" + "|".join(_BLOCKQUOTE_RESIDUE_KEYS) + r")\*\*[ \t]*[:：]"
)
_BLOCKQUOTE_RESIDUE_WINDOW = 15  # body lines considered "start of the body"


def check_blockquote_metadata_residue(
    policy: dict, texts: dict[PurePosixPath, str]
) -> list[Finding]:
    """Report legacy bold blockquote metadata lines at the start of the body.

    When a document carries YAML frontmatter, the frontmatter is the
    authoritative metadata carrier and the bold blockquote equivalent is
    migration residue.
    """
    findings: list[Finding] = []
    for row in policy["inventory"]["files"]:
        path = PurePosixPath(str(row["path"]))
        text = texts.get(path)
        if text is None:
            continue
        frontmatter_lines = _frontmatter_line_count(text)
        if frontmatter_lines == 0:
            continue
        lines = text.splitlines()
        window_end = min(
            frontmatter_lines + 1 + _BLOCKQUOTE_RESIDUE_WINDOW, len(lines) + 1
        )
        for number in range(frontmatter_lines + 1, window_end):
            match = _BLOCKQUOTE_RESIDUE_RE.match(lines[number - 1])
            if match:
                findings.append(
                    Finding(
                        RULE_BLOCKQUOTE_METADATA_RESIDUE,
                        "error",
                        path.as_posix(),
                        str(number),
                        f"legacy blockquote metadata {match.group(1)!r} at body start; "
                        "frontmatter is already authoritative",
                    )
                )
    return findings


# The doc-only detect-changes exemption is a hand-added line inside the
# tool-managed GitNexus block of AGENTS.md (authoritative semantics:
# docs/governance/document-governance.md). GitNexus re-indexing regenerates
# the block between the markers and can silently drop the line, so presence
# is asserted mechanically. Only the bold lead phrase is matched: the
# explanatory wording after it may legitimately evolve. A candidate without
# the managed block reports nothing — removing the block wholesale is a
# deliberate governance decision, not the silent-drop failure mode.
_GITNEXUS_START_MARKER = "<!-- gitnexus:start -->"
_GITNEXUS_END_MARKER = "<!-- gitnexus:end -->"
_GITNEXUS_EXEMPTION_LEAD = "**Doc-only commits are exempt from re-indexing.**"
_AGENTS_GUIDANCE_PATH = PurePosixPath("AGENTS.md")


def check_gitnexus_exemption(
    policy: dict, texts: dict[PurePosixPath, str]
) -> list[Finding]:
    """Report a missing doc-only exemption line in the AGENTS.md GitNexus block.

    The line is hand-added inside the tool-managed block (``gitnexus:start``
    to ``gitnexus:end``); re-indexing regenerates that block and can silently
    drop the line. Only the bold lead phrase is matched because the rest of
    the sentence may legitimately evolve. A candidate without the managed
    block reports nothing.
    """
    findings: list[Finding] = []
    for row in policy["inventory"]["files"]:
        path = PurePosixPath(str(row["path"]))
        if path != _AGENTS_GUIDANCE_PATH:
            continue
        text = texts.get(path)
        if text is None:
            continue
        lines = text.splitlines()
        start = next(
            (
                index
                for index, line in enumerate(lines)
                if _GITNEXUS_START_MARKER in line
            ),
            None,
        )
        if start is None:
            continue
        end = next(
            (
                index
                for index in range(start + 1, len(lines))
                if _GITNEXUS_END_MARKER in lines[index]
            ),
            len(lines),
        )
        if any(
            _GITNEXUS_EXEMPTION_LEAD in lines[index] for index in range(start + 1, end)
        ):
            continue
        findings.append(
            Finding(
                RULE_GITNEXUS_EXEMPTION,
                "error",
                path.as_posix(),
                str(start + 1),
                "GitNexus block is missing the doc-only detect-changes exemption "
                "line; restore it after regenerating the managed block",
            )
        )
    return findings


def _collect_findings(policy: dict, source: DocumentSource) -> list[Finding]:
    findings: list[Finding] = []
    findings.extend(check_inventory_coverage(policy, source))
    findings.extend(check_protected_fingerprints(policy, source))
    # Baseline registration stays immutable; all registered bodies share the
    # same validation rules, including documents added after the baseline.
    policy = {
        **policy,
        "inventory": {
            **policy["inventory"],
            "files": policy["inventory"]["files"]
            + (policy.get("supplements") or {}).get("files", []),
        },
    }
    tracked = source.tracked_paths()
    texts = _document_texts(policy, source, tracked)
    findings.extend(check_metadata(policy, texts))
    findings.extend(check_duplicate_ids(policy, texts))
    findings.extend(check_authority_uniqueness(policy))
    findings.extend(check_links(policy, texts, tracked))
    findings.extend(check_task_routes(policy, tracked))
    findings.extend(check_supersession(policy, texts, tracked))
    findings.extend(check_evidence(policy, texts))
    findings.extend(check_stale_package_paths(policy, texts))
    findings.extend(check_blockquote_metadata_residue(policy, texts))
    findings.extend(check_gitnexus_exemption(policy, texts))
    return findings


def _serialize_json(
    candidate: Candidate, findings: list[Finding], error: str | None
) -> str:
    by_rule: dict[str, int] = {}
    errors = 0
    warnings = 0
    for finding in findings:
        by_rule[finding.rule] = by_rule.get(finding.rule, 0) + 1
        if finding.severity == "warning":
            warnings += 1
        else:
            errors += 1
    payload: dict = {
        "schema_version": 1,
        "candidate": {
            "mode": candidate.mode,
            "revision": candidate.revision,
            "head": candidate.head,
        },
        "counts": {
            "findings": len(findings),
            "errors": errors,
            "warnings": warnings,
            "by_rule": by_rule,
        },
        "findings": [
            {
                "rule": finding.rule,
                "severity": finding.severity,
                "file": finding.file,
                "location": finding.location,
                "reason": finding.reason,
            }
            for finding in findings
        ],
    }
    if error is not None:
        payload["error"] = {"message": error}
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _print_text(candidate: Candidate, findings: list[Finding]) -> None:
    for finding in findings:
        location = finding.location or "-"
        print(
            f"{finding.rule} {finding.severity} {finding.file}:{location} {finding.reason}"
        )
    by_rule: dict[str, int] = {}
    for finding in findings:
        by_rule[finding.rule] = by_rule.get(finding.rule, 0) + 1
    summary = " ".join(f"{rule}={count}" for rule, count in sorted(by_rule.items()))
    where = candidate.revision if candidate.mode == "revision" else "worktree"
    if findings:
        print(f"candidate={where} findings={len(findings)} {summary}".rstrip())
    else:
        print(f"document checks passed (candidate={where}; no findings)")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--repo-root", type=Path, default=Path("."), help="repository root to check"
    )
    parser.add_argument(
        "--revision", help="check files from this Git revision instead of the worktree"
    )
    parser.add_argument(
        "--json", action="store_true", help="emit a JSON report instead of text"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    root = args.repo_root.resolve()
    json_mode = bool(args.json)

    def fail(message: str) -> int:
        mode = "revision" if args.revision else "worktree"
        if json_mode:
            print(_serialize_json(Candidate(mode, args.revision, None), [], message))
        else:
            print(f"ERROR: {message}", file=sys.stderr)
        return EXIT_OPERATIONAL

    if not root.is_dir():
        return fail(f"repo root is not a directory: {root}")

    candidate = Candidate("worktree", None, None)
    try:
        if args.revision:
            source: DocumentSource = RevisionSource(root, args.revision)
            candidate = Candidate("revision", args.revision, source.commit)
        else:
            source = WorktreeSource(root)
            head = (
                _git(root, "rev-parse", "HEAD").decode("ascii").strip()
                if _git_success(root, "rev-parse", "HEAD")
                else None
            )
            candidate = Candidate("worktree", None, head or None)
        try:
            policy = _load_policy(source)
            findings = _collect_findings(policy, source)
        finally:
            source.close()
    except OperationalError as exc:
        return fail(str(exc))

    findings.sort(
        key=lambda finding: (
            finding.rule,
            finding.file,
            finding.location,
            finding.reason,
        )
    )
    if json_mode:
        print(_serialize_json(candidate, findings, None))
    else:
        _print_text(candidate, findings)
    return EXIT_FINDINGS if findings else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
