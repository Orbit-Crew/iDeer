"""The ``telemetry`` toolgroup loads ``read_dat``/``parse_dat`` from config.example.yaml.

Ticket 73: ``read_dat`` is declared through the config ``tools[]`` mechanism
under the new independent ``telemetry`` group (decision: do not reuse
``code``), so agents that declare the group get the tool without any
hard-coded tool list.  The consistency pin follows the
``test_bundled_agent_and_example_config_declare_the_fault_zeroing_group``
pattern and also nails the SKILL.md allowed-tools backfill: the
fault-zeroing skill previously omitted ``read_binary_hex`` and
``code_interpreter`` even though the agent was granted them — both are
pinned here so the omission cannot regress.

Ticket 75: the same group also carries ``parse_dat`` (deterministic frame
decoding from a closed-vocabulary Frame Layout Spec); the group/wiring/
surface/chain pins below cover it next to ``read_dat``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from deerflow.config.app_config import AppConfig
from deerflow.tools.tools import get_available_tools

REPO_ROOT = Path(__file__).resolve().parents[4]


@pytest.fixture(scope="module")
def config_example() -> AppConfig:
    config_example_path = REPO_ROOT / "config.example.yaml"
    return AppConfig.model_validate(yaml.safe_load(config_example_path.read_text(encoding="utf-8")))


def test_telemetry_group_declares_read_dat(config_example: AppConfig) -> None:
    assert any(group.name == "telemetry" for group in config_example.tool_groups)

    tools = get_available_tools(groups=["telemetry"], include_mcp=False, app_config=config_example)
    names = {tool.name for tool in tools}

    assert "read_dat" in names


def test_read_dat_is_wired_to_the_telemetry_group(config_example: AppConfig) -> None:
    tools = get_available_tools(groups=["telemetry"], include_mcp=False, app_config=config_example)

    read_dat = next(tool for tool in tools if tool.name == "read_dat")
    assert read_dat.name == "read_dat"
    wired = {tool.name: tool for tool in config_example.tools if tool.name == "read_dat"}
    assert wired["read_dat"].group == "telemetry"


def test_telemetry_group_declares_parse_dat(config_example: AppConfig) -> None:
    tools = get_available_tools(groups=["telemetry"], include_mcp=False, app_config=config_example)
    names = {tool.name for tool in tools}

    assert "parse_dat" in names


def test_parse_dat_is_wired_to_the_telemetry_group(config_example: AppConfig) -> None:
    wired = {tool.name: tool for tool in config_example.tools if tool.name == "parse_dat"}
    assert wired["parse_dat"].group == "telemetry"
    assert wired["parse_dat"].use == "app.agentplatform.tools.parse_dat_tool:parse_dat_tool"


def test_parse_dat_exposes_layout_and_frame_window_parameters(config_example: AppConfig) -> None:
    tools = get_available_tools(groups=["telemetry"], include_mcp=False, app_config=config_example)
    parse_dat = next(tool for tool in tools if tool.name == "parse_dat")

    # Ticket 76: the surface grows by exactly one optional `mode` switch
    # (frames/scan) next to read_dat's own mode switch.
    assert set(parse_dat.args) == {"file_path", "layout", "start_frame", "frame_count", "fields_filter", "mode"}
    assert parse_dat.args["start_frame"].get("default") == 0
    assert parse_dat.args["frame_count"].get("default") == 25
    assert parse_dat.args["fields_filter"].get("default") == ""
    assert parse_dat.args["mode"].get("default") == "frames"
    assert "default" not in parse_dat.args["layout"]  # 布局是必填参数


def test_read_dat_exposes_only_file_path_and_paging_parameters(config_example: AppConfig) -> None:
    tools = get_available_tools(groups=["telemetry"], include_mcp=False, app_config=config_example)
    read_dat = next(tool for tool in tools if tool.name == "read_dat")

    # Ticket 74: the surface grows by exactly one optional `mode` switch
    # (view/structure); paging stays view-only.
    assert set(read_dat.args) == {"file_path", "offset", "length", "mode"}
    assert read_dat.args["mode"].get("default") == "view"


def test_bundled_agent_example_config_and_skill_allowed_tools_declare_the_telemetry_chain() -> None:
    agent_config = yaml.safe_load((REPO_ROOT / "resources" / "agents" / "fault-zeroing" / "config.yaml").read_text(encoding="utf-8"))
    assert "telemetry" in (agent_config.get("tool_groups") or [])

    example = yaml.safe_load((REPO_ROOT / "config.example.yaml").read_text(encoding="utf-8"))
    group_names = {group["name"] for group in example.get("tool_groups") or []}
    assert "telemetry" in group_names
    wired = {tool["name"]: tool for tool in example.get("tools") or []}
    assert wired["read_dat"]["group"] == "telemetry"
    assert wired["read_dat"]["use"].startswith("app.agentplatform.tools.read_dat_tool:")
    # Ticket 75: parse_dat rides the same telemetry group end to end.
    assert wired["parse_dat"]["group"] == "telemetry"
    assert wired["parse_dat"]["use"].startswith("app.agentplatform.tools.parse_dat_tool:")

    skill_text = (REPO_ROOT / "resources" / "skills" / "fault-zeroing" / "SKILL.md").read_text(encoding="utf-8")
    for name in ("read_dat", "parse_dat", "read_binary_hex", "code_interpreter"):
        assert f"  - {name}" in skill_text, name
