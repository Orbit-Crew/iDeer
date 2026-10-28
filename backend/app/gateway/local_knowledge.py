"""Frozen local-knowledge dispatch for canonical Runs (#113).

A device-local KnowledgeBase revision never has provider content. When its
frozen manifest enters the Effective Knowledge Scope, retrieval is scheduled
to the one importing device: the payload carries frozen identity fields only,
the device's unique Runtime re-validates every document hash, and results are
filtered back into the frozen manifest before anything reaches the model or a
receipt.
"""

from __future__ import annotations

from typing import Any

from agentplatform_extension.knowledge.scope import LOCAL_DATASET_PREFIX

# The device operation re-validating the frozen revision. It is announced by
# paired Desktops and dispatched through the device broker like every other
# local capability, so the task record and its receipt stay tied to the Run.
LOCAL_KNOWLEDGE_OPERATION = "local.knowledge.search"

# Mirrors the retrieval receipt budget: chunks beyond the receipt's item cap
# could never be cited, so they are not delivered either.
MAX_DELIVERED_CHUNKS = 20


def local_dataset_token(revision_id: str) -> str:
    """The stable dataset token for one frozen device-local revision."""

    return f"{LOCAL_DATASET_PREFIX}{revision_id}"


def build_local_knowledge_specs(revision_metadata: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Project frozen revision metadata into device dispatch specs.

    A spec exists only for a device-local revision whose manifest names
    exactly one importing device; anything ambiguous stays out of the scope
    and therefore invisible to the model.
    """

    specs: dict[str, dict[str, Any]] = {}
    for dataset, metadata in (revision_metadata or {}).items():
        if not isinstance(metadata, dict) or metadata.get("origin") != "local_import":
            continue
        device_id = metadata.get("device_id")
        documents = metadata.get("documents")
        if not isinstance(device_id, str) or not device_id or not isinstance(documents, dict) or not documents:
            continue
        frozen = []
        for document_id, entry in sorted(documents.items()):
            if not isinstance(entry, dict):
                continue
            filename, content_hash = entry.get("display_name"), entry.get("content_hash")
            if not isinstance(filename, str) or not filename or not isinstance(content_hash, str) or not content_hash:
                continue
            frozen.append({
                "document_id": str(document_id),
                "filename": filename,
                "content_hash": content_hash,
            })
        if not frozen:
            continue
        specs[str(dataset)] = {
            "device_id": device_id,
            "revision_id": str(metadata.get("revision_id") or ""),
            "manifest_hash": str(metadata.get("manifest_hash") or ""),
            "documents": frozen,
        }
    return specs


def search_task_payload(query: str, spec: dict[str, Any]) -> dict[str, Any]:
    """The device task arguments: frozen identity fields plus the query.

    No device path, provider ID, or manifest-unrelated metadata is included;
    the device re-derives everything else from its own registry.
    """

    return {
        "query": query,
        "revision_id": spec["revision_id"],
        "manifest_hash": spec["manifest_hash"],
        "documents": [dict(document) for document in spec["documents"]],
    }


def validate_local_search_result(result: object, spec: dict[str, Any]) -> dict[str, Any]:
    """Keep only frozen-manifest chunks, bounded like the receipt budget.

    A compromised or buggy device cannot inject document identities outside
    the frozen revision: unknown chunks are dropped, never forwarded, and the
    revision's own missing documents are reported back as a structured list.
    """

    frozen_ids = {document["document_id"] for document in spec["documents"]}
    chunks: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    seen: set[str] = set()
    if isinstance(result, dict):
        raw_chunks = result.get("chunks")
        for chunk in raw_chunks if isinstance(raw_chunks, list) else []:
            if not isinstance(chunk, dict):
                continue
            document_id = str(chunk.get("document_id") or "")
            if document_id not in frozen_ids:
                continue
            seen.add(document_id)
            if len(chunks) >= MAX_DELIVERED_CHUNKS:
                break
            chunks.append(dict(chunk))
        raw_missing = result.get("missing")
        if isinstance(raw_missing, list):
            for entry in raw_missing:
                if not isinstance(entry, dict):
                    continue
                document_id = str(entry.get("document_id") or "")
                if document_id in frozen_ids:
                    missing.append({"document_id": document_id, "reason": str(entry.get("reason") or "unavailable")})
    for document in spec["documents"]:
        if document["document_id"] not in seen and all(row["document_id"] != document["document_id"] for row in missing):
            missing.append({"document_id": document["document_id"], "reason": "no_match"})
    return {"chunks": chunks, "missing": missing[:MAX_DELIVERED_CHUNKS], "truncated": bool(isinstance(result, dict) and result.get("truncated"))}
