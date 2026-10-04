"""The workflow worker is a package whose import surface never changed.

Architecture-deepening candidate 5: the single-file worker became a same-named
package. The facade must keep every name the scripts and tests import today,
and expose the two run-session entries (``execute`` / ``resume``) the queue
loop and the acceptance harness call instead of the fused task function.
"""

from __future__ import annotations

import inspect

import app.workflow_worker


def test_facade_keeps_every_name_the_original_module_exported() -> None:
    worker = app.workflow_worker
    for name in (
        "main",
        "run_worker",
        "execute_workflow_task",
        "build_canonical_registry",
        "load_workflow_definition_for_run",
        "_workflow_run_evidence_context",
        "get_app_config",
    ):
        assert hasattr(worker, name), f"app.workflow_worker.{name} must stay importable"


def test_facade_exposes_the_execute_and_resume_entries() -> None:
    from app.workflow_worker.run_session import execute, resume

    assert app.workflow_worker.execute is execute
    assert app.workflow_worker.resume is resume
    assert inspect.iscoroutinefunction(execute)
    assert inspect.iscoroutinefunction(resume)


def test_legacy_task_name_stays_a_callable_task_entry() -> None:
    assert inspect.iscoroutinefunction(app.workflow_worker.execute_workflow_task)
