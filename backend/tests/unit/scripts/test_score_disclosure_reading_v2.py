from __future__ import annotations

import pytest
from scripts.score_disclosure_reading_v2 import normalize_review, score_reviews


def _queue() -> list[dict[str, object]]:
    return [
        {
            "slot": slot,
            "task": "ui",
            "candidate": "after" if slot <= 16 else "baseline",
        }
        for slot in range(1, 33)
    ]


def _review(reviewer: str, decision: str = "met") -> dict[str, object]:
    return {
        "reviewer": reviewer,
        "anchors": [
            {
                "id": "UI-01",
                "category": "required",
                "decision": decision,
                "excerpt": "SettingsSection owns the header action.",
                "candidate_path": "frontend/src/components/workspace/settings/settings-section.tsx",
            },
            {
                "id": "UI-C1",
                "category": "conditional",
                "decision": "not_applicable",
                "trigger": False,
                "excerpt": "No generated UI is touched.",
                "candidate_path": "frontend/AGENTS.md",
            },
            {
                "id": "UI-AUX",
                "category": "auxiliary",
                "decision": "missed",
                "excerpt": "",
                "candidate_path": "",
            },
        ],
    }


def test_fixed_denominator_keeps_missing_after_slots_and_auxiliary_is_diagnostic() -> None:
    anchors = {
        "ui": [
            {"id": "UI-01", "category": "required"},
            {"id": "UI-C1", "category": "conditional"},
            {"id": "UI-AUX", "category": "auxiliary"},
        ]
    }
    records = [
        {
            "slot": 1,
            "status": "submitted",
            "tool_valid": True,
            "reviews": [_review("A"), _review("B")],
            "adjudication": None,
            "critical_error": False,
            "historical_authority_misuse": False,
        }
    ]

    report = score_reviews(_queue(), records, anchors)

    assert report["candidates"]["after"]["denominator"] == 16
    assert report["candidates"]["after"]["scored"] == 1
    assert report["candidates"]["after"]["correct"] == 1
    assert report["candidates"]["after"]["correct_rate"] == pytest.approx(1 / 16)
    assert report["auxiliary_misses"] == 1
    assert report["status"] == "incomplete"


def test_disagreement_requires_third_adjudication_and_conditional_unknown_is_incomplete() -> None:
    anchors = {
        "ui": [
            {"id": "UI-01", "category": "required"},
            {"id": "UI-C1", "category": "conditional"},
        ]
    }
    review_a = _review("A")
    review_b = _review("B")
    review_a["anchors"] = review_a["anchors"][:2]
    review_a["anchors"][1]["trigger"] = "unknown"
    review_b["anchors"] = [
        {
            "id": "UI-01",
            "category": "required",
            "decision": "missed",
            "excerpt": "",
            "candidate_path": "frontend/src/components/workspace/settings/settings-section.tsx",
        },
        {
            "id": "UI-C1",
            "category": "conditional",
            "decision": "not_applicable",
            "trigger": "unknown",
            "excerpt": "Trigger was not resolved.",
            "candidate_path": "Frozen prompt",
        },
    ]
    record = {
        "slot": 1,
        "status": "submitted",
        "tool_valid": True,
        "reviews": [review_a, review_b],
        "adjudication": None,
        "critical_error": False,
        "historical_authority_misuse": False,
    }

    report = score_reviews(_queue(), [record], anchors)

    assert report["unresolved_disagreements"] == 1
    assert report["unresolved_conditionals"] == 1
    assert report["candidates"]["after"]["correct"] == 0
    assert report["candidates"]["after"]["unresolved"] == 1
    assert report["tasks"][0]["correct"] is None
    assert report["status"] == "incomplete"


def test_missing_adjudication_does_not_count_as_correct_and_bad_queue_is_rejected() -> None:
    with pytest.raises(ValueError, match="32 slots"):
        score_reviews(_queue()[:-1], [], {})

    anchors = {"ui": [{"id": "UI-01", "category": "required"}]}
    review_a = _review("A")
    review_b = _review("B", "missed")
    review_a["anchors"] = review_a["anchors"][:1]
    review_b["anchors"] = review_b["anchors"][:1]
    record = {
        "slot": 1,
        "status": "submitted",
        "tool_valid": True,
        "reviews": [review_a, review_b],
        "adjudication": None,
        "critical_error": False,
        "historical_authority_misuse": False,
    }
    report = score_reviews(_queue(), [record], anchors)
    assert report["unresolved_disagreements"] == 1
    assert report["candidates"]["after"]["correct"] == 0


def test_third_reviewer_resolves_only_the_disputed_conditional_anchor() -> None:
    anchors = {
        "ui": [
            {"id": "UI-01", "category": "required"},
            {"id": "UI-C1", "category": "conditional"},
        ]
    }
    review_a = _review("A")
    review_b = _review("B")
    review_a["anchors"] = review_a["anchors"][:2]
    review_b["anchors"] = review_b["anchors"][:2]
    review_a["anchors"][1].update(decision="missed", trigger=True)
    review_b["anchors"][1].update(decision="not_applicable", trigger=False)
    record = {
        "slot": 1,
        "status": "submitted",
        "tool_valid": True,
        "reviews": [review_a, review_b],
        "adjudication": {
            "reviewer": "C",
            "anchors": [
                {
                    "id": "UI-C1",
                    "decision": "not_applicable",
                    "trigger": False,
                    "excerpt": "No generated UI is modified.",
                    "candidate_path": "frontend/AGENTS.md",
                }
            ],
        },
        "critical_error": False,
        "historical_authority_misuse": False,
    }

    report = score_reviews(_queue(), [record], anchors)

    assert report["unresolved_disagreements"] == 0
    assert report["unresolved_conditionals"] == 0
    assert report["candidates"]["after"]["correct"] == 1


def test_grader_numbering_is_projected_to_frozen_v2_ids_and_summaries_are_rejected() -> None:
    normalized = normalize_review(
        "ui",
        {
            "reviewer": "A",
            "anchors": [
                {
                    "id": "UI-V2-01",
                    "decision": "met",
                    "evidence": {
                        "answer": "SettingsSection is the concrete header seam.",
                        "candidate": "frontend/src/components/workspace/settings/settings-section.tsx",
                    },
                }
            ],
        },
    )

    assert normalized["anchors"] == [
        {
            "id": "UI-01",
            "category": "required",
            "decision": "met",
            "excerpt": "SettingsSection is the concrete header seam.",
            "candidate_path": "frontend/src/components/workspace/settings/settings-section.tsx",
        }
    ]
    with pytest.raises(ValueError, match="per-anchor evidence"):
        normalize_review("ui", {"reviewer": "B", "summary": "all required anchors met"})
