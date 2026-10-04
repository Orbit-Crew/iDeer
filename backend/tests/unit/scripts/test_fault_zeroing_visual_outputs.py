from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
REQUIRED_OUTPUTS = [
    "fault_tree.json",
    "fault_tree.svg",
    "bottom_event_assessment.md",
    "analysis_process.svg",
    "zeroing_report.md",
]
STAGE_MARKERS = [
    "证据提取",
    "故障树构建",
    "底事件评估",
    "根因归因",
    "纠正措施",
    "文档生产",
]
RESPONSIBILITY_PHRASES = [
    "演绎建树阶段不依赖证据台账",
    "证据检漏只做添加不做删除",
    "文档阶段不修改分析数据",
]
# Since the contract single-home change (2026-10-03), SKILL/SOUL no longer
# restate the declarative contract content; they reference the generated
# sandbox copy by section, and that copy carries the phrases verbatim
# (parity-guarded against app.agentplatform.fault_zeroing.contract).
CONTRACT_REFERENCE_MOUNT = "/mnt/skills/fault-zeroing/references/result_contract.md"
CONTRACT_REFERENCE_TARGET = REPO_ROOT / "resources" / "skills" / "fault-zeroing" / "references" / "result_contract.md"
CONTRACT_SECTIONS_SKILL = [
    "五件产物清单",
    "资料覆盖类别",
    "报告章节",
    "报告关键短语",
    "分析阶段标记",
    "阶段职责说明",
]
CONTRACT_SECTIONS_SOUL = [
    "五件产物清单",
    "资料覆盖类别",
    "报告关键短语",
    "分析阶段标记",
    "阶段职责说明",
]
# The inline end-to-end chat mode was removed by the unified-kernel ticket 04:
# real analysis promotes into a kernel Run via start_zeroing_run instead.
REMOVED_INLINE_MODE_PHRASES = [
    "独立完成全流程",
    "端到端模式",
    "展示五份文件",
    "/mnt/user-data/outputs/fault_tree.json",
    "python scripts/validate_fault_zeroing_outputs.py",
    "ideer.fault_zeroing.kernel",
]
CLOSURE_TOOLS = [
    "start_zeroing_run",
    "confirm_zeroing_run",
    "check_zeroing_run",
]


def test_fault_zeroing_skill_promotes_real_analysis_into_kernel_runs() -> None:
    content = (REPO_ROOT / "resources" / "skills" / "fault-zeroing" / "SKILL.md").read_text(encoding="utf-8")

    # The bisection rule: chat tools drive the closed loop, the five artifacts
    # only ever come back through the Run bridge.
    for tool in CLOSURE_TOOLS:
        assert tool in content
    for phrase in [
        "ask_clarification",
        "三选一",
        "input_snapshot_hash",
        "资料覆盖矩阵",
        "证据台账",
        "probability_basis",
        "06_expected_analysis.md",
    ]:
        assert phrase in content

    # The declarative contract content is referenced, not restated: the skill
    # points at the generated reference copy by section, and that copy carries
    # the five artifacts, stage markers, and responsibility phrases verbatim.
    assert CONTRACT_REFERENCE_MOUNT in content
    for section in CONTRACT_SECTIONS_SKILL:
        assert f"「{section}」" in content
    reference_target = CONTRACT_REFERENCE_TARGET.read_text(encoding="utf-8")
    for phrase in [*REQUIRED_OUTPUTS, *STAGE_MARKERS, *RESPONSIBILITY_PHRASES]:
        assert phrase in reference_target

    assert "present_files" in content
    assert "不写脚本和外链资源" in content

    assert "read_document" in content
    for phrase in [
        ".doc` / `.docx` / `.pdf",
        "page_range",
        "疑似扫描件",
    ]:
        assert phrase in content

    # Custom sandbox.mounts directories are readable, including office docs.
    assert "sandbox.mounts" in content
    assert "read_document` 打开" in content

    # Legacy .doc is readable via read_document (LibreOffice-backed conversion);
    # the skill must advertise it as a supported format.
    assert ".doc` / `.docx` / `.pdf` / `.xls`" in content
    assert "不支持 legacy" not in content
    # Tool error responses (e.g. read_document JSON errors) must be treated
    # under the failure contract, never ingested as document content.
    assert "JSON 错误" in content

    for phrase in REMOVED_INLINE_MODE_PHRASES:
        assert phrase not in content

    # The shared-kernel reference points at the real kernel module.
    assert "app.agentplatform.fault_zeroing.kernel" in content
    # The validator pointer resolves on the skill mount path.
    assert "/mnt/skills/fault-zeroing/scripts/validate_fault_zeroing_outputs.py" in content


def test_fault_zeroing_soul_promotes_real_analysis_into_kernel_runs() -> None:
    content = (REPO_ROOT / "resources" / "agents" / "fault-zeroing" / "SOUL.md").read_text(encoding="utf-8")

    for tool in CLOSURE_TOOLS:
        assert tool in content
    for phrase in [
        "ask_clarification",
        "三选一",
        "证据台账",
        "资料覆盖矩阵",
        "probability_basis",
    ]:
        assert phrase in content

    # Same contract-reference design as the skill: sections by name, phrases
    # carried by the generated reference copy.
    assert CONTRACT_REFERENCE_MOUNT in content
    for section in CONTRACT_SECTIONS_SOUL:
        assert f"「{section}」" in content
    reference_target = CONTRACT_REFERENCE_TARGET.read_text(encoding="utf-8")
    for phrase in [*REQUIRED_OUTPUTS, *STAGE_MARKERS, *RESPONSIBILITY_PHRASES]:
        assert phrase in reference_target

    assert "SVG 不得包含脚本、外链资源或动态交互代码" in content

    # Drift guards: conclusion status enum must match fault_tree.schema.json
    # (conclusion_status), and the schema path must be the runtime mount path.
    assert "`in_progress`、`not_applicable`" not in content
    assert "skills/custom/fault-zeroing" not in content
    assert "/mnt/skills/fault-zeroing/templates/fault_tree.schema.json" in content
    assert "不得用于结论状态" in content

    for phrase in REMOVED_INLINE_MODE_PHRASES:
        assert phrase not in content

    assert "/mnt/skills/fault-zeroing/scripts/validate_fault_zeroing_outputs.py" in content


def test_fault_zeroing_sample_prompt_mentions_visual_outputs() -> None:
    content = (REPO_ROOT / "docs" / "zero_agent_eval_cases" / "README.md").read_text(encoding="utf-8")

    for output in REQUIRED_OUTPUTS:
        assert output in content
