"""Cross-entry regression guards for the known fault-zeroing defects (ticket 07).

Each test pins one historically observed failure mode so it cannot return:

1. 最终修订绕过       — assessment_refine must carry a fault_tree schema gate.
2. 非法验证状态       — invalid verification statuses are rejected.
3. confidence 漂移    — schema enums and the contract share one definition.
4. 缺失报告章节       — a missing report section fails the contract.
5. 错误 Workflow 路径 — the acceptance harness points at the real YAML.
6. validator 未执行   — the acceptance report records a contract evaluation.
7. 文件存在即成功     — non-empty-but-broken artifacts never complete a run.
8. 枚举漂移           — node prompts cite the unified rule source instead of
   restating the enum/grading lists owned by evidence_rules.md and the schema.
9. 契约复述漂移       — node prompts and the SKILL/SOUL texts cite the
   generated contract reference instead of restating the declarative Result
   Contract content owned by contract.py (ticket 07, spec candidate 6).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
PKG_DIR = REPO_ROOT / "backend" / "app" / "agentplatform" / "fault_zeroing"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(name, module)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def workflow_yaml() -> dict:
    import yaml

    return yaml.safe_load((REPO_ROOT / "resources" / "workflows" / "fault-zeroing.yaml").read_text(encoding="utf-8"))


def _node(workflow: dict, node_id: str) -> dict:
    return next(node for node in workflow["nodes"] if node["id"] == node_id)


def test_final_revision_cannot_bypass_schema_gate(workflow_yaml: dict) -> None:
    """Regression 1: the last write of fault_tree.json is still schema-gated."""

    refine = _node(workflow_yaml, "assessment_refine")
    gates = refine.get("schemas") or []
    assert any("fault_tree.schema.json" in (gate.get("schema_file") or "") for gate in gates), "assessment_refine must gate fault_tree.json with fault_tree.schema.json"

    # The earlier gates must still be present as well.
    for node_id in ("integrate_tree", "evidence_assessment"):
        gates = _node(workflow_yaml, node_id).get("schemas") or []
        assert any("fault_tree" in (gate.get("schema_file") or "") for gate in gates), f"{node_id} lost its schema gate"


def test_invalid_verification_status_is_rejected_by_contract(tmp_path: Path) -> None:
    """Regression 2: only pending/in_progress/passed/failed/blocked pass."""

    contract = load_module("fz_contract_regr", PKG_DIR / "contract.py")
    fixtures = load_module(
        "fz_contract_fixtures_regr",
        REPO_ROOT / "backend" / "tests" / "unit" / "fault_zeroing" / "test_contract.py",
    )
    tree = fixtures.valid_fault_tree()
    tree["verification_plan"][0]["status"] = "to_verify"
    output_dir = fixtures.write_outputs(tmp_path, tree)

    verdict = contract.evaluate_result_contract(output_dir)

    assert not verdict.ok
    assert "verification_status_invalid" in {f.code for f in verdict.findings}


def test_confidence_drift_is_structurally_impossible(tmp_path: Path) -> None:
    """Regression 3: schema gate and contract accept the same confidence set."""

    contract = load_module("fz_contract_regr2", PKG_DIR / "contract.py")
    schema = json.loads((REPO_ROOT / "resources" / "skills" / "fault-zeroing" / "templates" / "fault_tree.schema.json").read_text(encoding="utf-8"))

    assert set(schema["$defs"]["confidence"]["enum"]) == contract.CONFIDENCE_VALUES

    # A Finding Confidence value that passes the schema gate also passes the
    # contract (historically the validator rejected it).
    fixtures = load_module(
        "fz_contract_fixtures_regr2",
        REPO_ROOT / "backend" / "tests" / "unit" / "fault_zeroing" / "test_contract.py",
    )
    tree = fixtures.valid_fault_tree()
    tree["bottom_events"][0]["confidence"] = "high_risk_candidate"
    output_dir = fixtures.write_outputs(tmp_path, tree)
    assert contract.evaluate_result_contract(output_dir).ok


def test_missing_report_section_fails(tmp_path: Path) -> None:
    """Regression 4: dropping a required section fails the contract."""

    contract = load_module("fz_contract_regr3", PKG_DIR / "contract.py")
    fixtures = load_module(
        "fz_contract_fixtures_regr3",
        REPO_ROOT / "backend" / "tests" / "unit" / "fault_zeroing" / "test_contract.py",
    )
    report = fixtures.valid_report().replace(
        "## 1. 问题概述\n\n- 顶事件：热流传感器 HF-07 测值超过试验允许上限\n- 主根因：HF-07 测量链路零点漂移\n",
        "",
    )
    output_dir = fixtures.write_outputs(tmp_path, report=report)

    verdict = contract.evaluate_result_contract(output_dir)

    assert not verdict.ok
    assert any(f.code == "report_section_missing" for f in verdict.findings)


def test_acceptance_harness_points_at_real_workflow_and_runs_contract() -> None:
    """Regressions 5+6: the harness consumes the canonical bundled workflow
    (its manifest source IS resources/workflows/fault-zeroing.yaml); the
    contract evaluation is still recorded."""

    source = (REPO_ROOT / "scripts" / "run_fault_zeroing_acceptance.py").read_text(encoding="utf-8")

    workflow_path = REPO_ROOT / "resources" / "workflows" / "fault-zeroing.yaml"
    assert workflow_path.is_file()
    # The canonical seam seeds the bundled manifest and freezes the workflow
    # resource whose source is the real YAML — not a stale local copy.
    assert 'REPO_ROOT / "bundled-resources.json"' in source
    assert "seed_bundled_resources" in source
    assert 'REPO_ROOT / "workflows" / "fault-zeroing.yaml"' not in source
    manifest = json.loads((REPO_ROOT / "bundled-resources.json").read_text(encoding="utf-8"))
    workflow_entry = next(entry for entry in manifest["resources"] if entry["type"] == "workflow" and entry["slug"] == "fault-zeroing")
    assert workflow_entry["source"] == "resources/workflows/fault-zeroing.yaml"

    assert '"validator_run": True' in source
    assert "evaluate_completion" in source
    assert "FaultZeroingKernel" in source


def test_node_prompts_cite_rule_source_instead_of_inlining_enums(workflow_yaml: dict) -> None:
    """Dedup guard (ticket 05 / spec user story 7): workflow node prompts cite
    the unified rule source and the output schema instead of restating grading
    enums and grade rules, while the schema keeps enforcing them. Without this
    guard the inline lists drift again on the next edit (枚举漂移)."""

    SKILL_DIR = REPO_ROOT / "resources" / "skills" / "fault-zeroing"

    def prompt_of(node: dict) -> str:
        action = node.get("action") or {}
        params = action.get("params") or {}
        return (params.get("prompt") or "") + (params.get("system_prompt") or "")

    # The rule-consuming nodes must name the unified rule source before acting.
    for node_id in ("evidence_collection", "evidence_assessment", "assessment_review"):
        prompt = prompt_of(_node(workflow_yaml, node_id))
        assert "evidence_rules.md" in prompt, f"{node_id} must cite evidence_rules.md"
        assert "唯一来源" in prompt, f"{node_id} must present evidence_rules.md as the single source"

    # No node prompt restates the enum lists owned by fault_tree.schema.json.
    owned_enum_lists = (
        "pending / in_progress / passed / failed / blocked",
        "confirmed / rejected / to_verify / not_applicable",
    )
    for node in workflow_yaml["nodes"]:
        prompt = prompt_of(node)
        for enum_list in owned_enum_lists:
            assert enum_list not in prompt, f"{node['id']} restates the enum list owned by fault_tree.schema.json: {enum_list!r}"

    # Grade rules are not restated inside the assessment prompts either.
    for node_id in ("evidence_assessment", "assessment_review"):
        prompt = prompt_of(_node(workflow_yaml, node_id))
        assert "A/B 级" not in prompt, f"{node_id} restates the A/B grade rule owned by evidence_rules.md"
        assert "C 级" not in prompt, f"{node_id} restates the C grade rule owned by evidence_rules.md"

    # The constraints stay machine-enforced: the schema enums are intact and
    # the static-alert confidence cap lives in the unified rule source.
    schema = json.loads((SKILL_DIR / "templates" / "fault_tree.schema.json").read_text(encoding="utf-8"))
    assert set(schema["$defs"]["verification_status"]["enum"]) == {"pending", "in_progress", "passed", "failed", "blocked"}
    assert set(schema["$defs"]["conclusion_status"]["enum"]) == {"confirmed", "rejected", "to_verify", "not_applicable"}
    rules = (SKILL_DIR / "references" / "evidence_rules.md").read_text(encoding="utf-8")
    assert "high_risk_candidate" in rules, "the static-alert confidence cap must live in evidence_rules.md"


def test_file_existence_alone_never_completes_a_run(tmp_path: Path) -> None:
    """Regression 7: placeholder outputs fail the contract gate."""

    kernel_mod = load_module("fz_kernel_regr", PKG_DIR / "kernel.py")
    contract = load_module("fz_contract_regr4", PKG_DIR / "contract.py")
    load_module("fz_intake_regr", PKG_DIR / "intake.py")
    load_module("fz_policy_regr", PKG_DIR / "policy.py")

    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    for name in (
        "fault_tree.json",
        "fault_tree.svg",
        "bottom_event_assessment.md",
        "analysis_process.svg",
        "zeroing_report.md",
    ):
        (output_dir / name).write_text("占位\n", encoding="utf-8")

    verdict = contract.evaluate_result_contract(output_dir)
    assert not verdict.ok

    completion = kernel_mod.KernelCompletion(
        run_id="run-x",
        status=kernel_mod.COMPLETION_STATUS_FAILED,
        verdict=verdict,
    )
    assert completion.status == kernel_mod.COMPLETION_STATUS_FAILED


def _contract_texts(workflow_yaml: dict) -> dict[str, str]:
    """The prose surfaces that used to restate the declarative contract."""

    def prompt_of(node: dict) -> str:
        action = node.get("action") or {}
        params = action.get("params") or {}
        return (params.get("prompt") or "") + "\n" + (params.get("system_prompt") or "")

    skill = (REPO_ROOT / "resources" / "skills" / "fault-zeroing" / "SKILL.md").read_text(encoding="utf-8")
    soul = (REPO_ROOT / "resources" / "agents" / "fault-zeroing" / "SOUL.md").read_text(encoding="utf-8")
    return {
        "workflow-prompts": "\n".join(prompt_of(node) for node in workflow_yaml["nodes"]),
        "SKILL.md": skill,
        "SOUL.md": soul,
    }


def test_prose_cites_the_contract_reference_instead_of_restating_it(workflow_yaml: dict) -> None:
    """Regression 9 (ticket 07 / spec candidate 6, Q10=a): contract.py is the
    single home of the declarative Result Contract content.  The workflow
    prompts and the SKILL/SOUL texts cite the generated sandbox reference
    (``/mnt/skills/fault-zeroing/references/result_contract.md``) instead of
    restating the artifact list, report sections, coverage categories, stage
    markers, responsibility phrases or disclosure phrases — one rule change
    must stay one file edit (the generated copies excluded)."""

    contract = load_module("fz_contract_regr5", PKG_DIR / "contract.py")
    texts = _contract_texts(workflow_yaml)

    # The prose names the generated citation target.
    for name, text in texts.items():
        assert "result_contract.md" in text, f"{name} must cite references/result_contract.md"

    # The contract-consuming nodes present it as the single source, like the
    # evidence_rules citation introduced by the rule-source unification.
    for node_id in ("evidence_collection", "generate_outputs"):
        node = _node(workflow_yaml, node_id)
        action = node.get("action") or {}
        prompt = (action.get("params") or {}).get("prompt") or ""
        assert "result_contract.md" in prompt, f"{node_id} must cite result_contract.md"
        assert "唯一来源" in prompt, f"{node_id} must present result_contract.md as the single source"

    # No prose surface restates a declarative family verbatim.  Fingerprints
    # are the canonical item sequences with the separators the prose used.
    def normalize(text: str) -> str:
        return text.replace("`", "")

    families: dict[str, tuple[str, ...]] = {
        "REQUIRED_OUTPUTS": ("、".join(contract.REQUIRED_OUTPUTS),),
        "REQUIRED_REPORT_SECTIONS": ("、".join(contract.REQUIRED_REPORT_SECTIONS),),
        "REQUIRED_COVERAGE": ("、".join(contract.REQUIRED_COVERAGE),),
        "REQUIRED_REPORT_KEY_PHRASES": ("、".join(contract.REQUIRED_REPORT_KEY_PHRASES),),
        "REQUIRED_STAGE_MARKERS": (
            "、".join(contract.REQUIRED_STAGE_MARKERS),
            "→".join(contract.REQUIRED_STAGE_MARKERS),
        ),
        "REQUIRED_RESPONSIBILITY_PHRASES": (
            "；".join(contract.REQUIRED_RESPONSIBILITY_PHRASES),
            "、".join(contract.REQUIRED_RESPONSIBILITY_PHRASES),
        ),
        "disclosure-phrases": (
            *contract.EVIDENCE_SIDE_DISCLOSURE.values(),
            contract.SCANNER_UNAVAILABLE_DISCLOSURE,
        ),
    }
    for family, fingerprints in families.items():
        for name, text in texts.items():
            normalized = normalize(text)
            for fingerprint in fingerprints:
                assert fingerprint not in normalized, f"{name} restates the declarative contract family {family}: {fingerprint!r}"

    # The generated citation target actually carries every family, so the
    # citation is actionable inside the sandbox.
    reference = (REPO_ROOT / "resources" / "skills" / "fault-zeroing" / "references" / "result_contract.md").read_text(encoding="utf-8")
    for item in (
        *contract.REQUIRED_OUTPUTS,
        *contract.REQUIRED_REPORT_SECTIONS,
        *contract.REQUIRED_COVERAGE,
        *contract.REQUIRED_REPORT_KEY_PHRASES,
        *contract.REQUIRED_STAGE_MARKERS,
        *contract.REQUIRED_RESPONSIBILITY_PHRASES,
        *contract.FORBIDDEN_RESPONSIBILITY_CLAIMS,
        *contract.EVIDENCE_SIDE_DISCLOSURE.values(),
        contract.SCANNER_UNAVAILABLE_DISCLOSURE,
    ):
        assert item in reference, f"generated reference lost {item!r}"


def test_telemetry_dat_evidence_channel_is_pinned_across_prose_surfaces(workflow_yaml: dict) -> None:
    """Ticket 77: telemetry ``.dat`` is a legal evidence input of the
    fault-zeroing evidence channel.  The workflow prompts (collection, plus
    the review node's source re-check) and the SKILL.md reading rules must
    route ``.dat`` through read_dat / parse_dat, and evidence_rules.md must
    carry the pending-verification grading guidance for model-decoded
    telemetry values.  Without this guard the prompt surfaces and the rule
    doc drift apart again on the next edit."""

    SKILL_DIR = REPO_ROOT / "resources" / "skills" / "fault-zeroing"

    def prompt_of(node: dict) -> str:
        action = node.get("action") or {}
        params = action.get("params") or {}
        return (params.get("prompt") or "") + "\n" + (params.get("system_prompt") or "")

    # The evidence-collection node reads .dat through the telemetry tools and
    # defers the grading of decoded values to the unified rule source.
    collection = prompt_of(_node(workflow_yaml, "evidence_collection"))
    for marker in (".dat", "read_dat", "parse_dat", "待验证级（pending_verification）"):
        assert marker in collection, f"evidence_collection prompt lost {marker!r}"
    assert "evidence_rules" in collection, "evidence_collection must defer the pending-verification rule to evidence_rules.md"

    # The review node can re-check telemetry sources instead of reporting
    # them as unverifiable.
    review = prompt_of(_node(workflow_yaml, "assessment_review"))
    for marker in (".dat", "read_dat", "parse_dat"):
        assert marker in review, f"assessment_review prompt lost {marker!r}"

    # The SKILL.md mirror keeps the same reading rule, and the telemetry
    # tools stay granted via allowed-tools.
    skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    for marker in (".dat", "read_dat", "parse_dat", "待验证级（pending_verification）"):
        assert marker in skill, f"SKILL.md lost {marker!r}"
    assert "\n  - read_dat\n" in skill and "\n  - parse_dat\n" in skill, "SKILL.md allowed-tools must keep read_dat/parse_dat granted"

    # The unified rule source owns the grading guidance with the exact
    # Finding Confidence terminology, and keeps the coverage matrix honest
    # about telemetry evidence.
    rules = (SKILL_DIR / "references" / "evidence_rules.md").read_text(encoding="utf-8")
    for marker in (
        ".dat",
        "遥测格式文档（Telemetry Format Document）",
        "Frame Layout Spec（帧布局参数）",
        "待验证级（pending_verification）",
        "格式文档样例或用户提供的参照结果互证",
        "不新增定级流程",
        "资料覆盖矩阵",
    ):
        assert marker in rules, f"evidence_rules.md lost {marker!r}"
