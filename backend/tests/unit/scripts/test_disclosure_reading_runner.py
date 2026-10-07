import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
RUNNER = ROOT / "scripts" / "run_disclosure_reading_session.py"
SPEC = importlib.util.spec_from_file_location("disclosure_reading_runner", RUNNER)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def test_isolation_catalog_removes_native_patch_without_changing_model_metadata():
    model = {
        "slug": "gpt-6.1-sol",
        "tool_mode": "code_mode_only",
        "shell_type": "unified_exec",
        "apply_patch_tool_type": "freeform",
        "experimental_supported_tools": ["clock"],
        "model_messages": {"code_mode": {"description": "retained"}},
    }

    isolated = runner.isolation_model_catalog({"models": [model]}, "gpt-6.1-sol")

    assert isolated == {"models": [{**model, "apply_patch_tool_type": None}]}
    assert model["apply_patch_tool_type"] == "freeform"
