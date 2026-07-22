"""Codex-facing package surface checks for prompt-to-loop-engineering."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = SKILL_ROOT.parents[1]


class SkillSurfaceTests(unittest.TestCase):
    def test_agent_id_schema_patterns_reject_windows_device_names(self) -> None:
        loop_schema = json.loads(
            (SKILL_ROOT / "schemas" / "loop_spec.schema.json").read_text(encoding="utf-8")
        )
        manifest_schema = json.loads(
            (SKILL_ROOT / "schemas" / "agent_manifest.schema.json").read_text(encoding="utf-8")
        )
        patterns = [
            loop_schema["$defs"]["agent_registry_entry"]["properties"]["id"]["pattern"],
            loop_schema["$defs"]["node"]["properties"]["agent_ref"]["pattern"],
            manifest_schema["$defs"]["subagent"]["properties"]["id"]["pattern"],
        ]
        for pattern in patterns:
            for unsafe in ("con", "prn", "aux", "nul", "com1", "com9", "lpt1", "lpt9"):
                self.assertIsNone(re.fullmatch(pattern, unsafe), (pattern, unsafe))
            self.assertIsNotNone(re.fullmatch(pattern, "security-auditor"))

    def require_full_repository(self) -> None:
        if not (REPO_ROOT / "README.md").is_file():
            self.skipTest("repository-root assets are not present in installed-skill mode")

    def test_v3_manifest_accepts_dynamic_professional_roles_without_fixed_max(self):
        manifest = json.loads(
            (SKILL_ROOT / "schemas/agent_manifest.schema.json").read_text(
                encoding="utf-8"
            )
        )
        subagents = manifest["properties"]["subagents"]
        self.assertNotIn("maxItems", subagents)
        role = manifest["$defs"]["subagent"]["properties"]["governance_role"]
        self.assertEqual(
            role["enum"], ["planner", "implementer", "reviewer", "verifier"]
        )
        self.assertIn("specialization", manifest["$defs"]["subagent"]["required"])

    def test_v3_loop_schema_has_registry_identity_and_controller_termination(self):
        schema = json.loads(
            (SKILL_ROOT / "schemas/loop_spec.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertIn("agent_ref", schema["$defs"]["node"]["properties"])
        self.assertIn(
            "subject_nodes", schema["$defs"]["criteria_binding"]["required"]
        )
        self.assertIn("termination_control", schema["required"])

    def test_skill_frontmatter_matches_folder(self) -> None:
        content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        match = re.match(r"^---\n(?P<body>.*?)\n---", content, re.DOTALL)
        self.assertIsNotNone(match, "SKILL.md is missing YAML frontmatter")
        body = match.group("body") if match else ""
        self.assertIn("name: prompt-to-loop-engineering", body)
        self.assertRegex(body, r"(?m)^description:\s*Use when ")

    def test_codex_metadata_is_complete(self) -> None:
        path = SKILL_ROOT / "agents" / "openai.yaml"
        self.assertTrue(path.is_file(), "agents/openai.yaml is missing")
        content = path.read_text(encoding="utf-8")
        self.assertRegex(content, r'(?m)^\s{2}display_name:\s*".+"$')
        description = re.search(
            r'(?m)^\s{2}short_description:\s*"(?P<value>.+)"$', content
        )
        self.assertIsNotNone(description, "short_description is missing")
        if description:
            self.assertGreaterEqual(len(description.group("value")), 25)
            self.assertLessEqual(len(description.group("value")), 64)
        self.assertRegex(
            content,
            r'(?m)^\s{2}default_prompt:\s*".*\$prompt-to-loop-engineering.*"$',
        )

    def test_runtime_free_contract_assets_exist(self) -> None:
        manifest = json.loads(
            (SKILL_ROOT / "examples/codex-loop/agent_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        required = [
            "templates/agents-gate/AGENTS.md",
            "schemas/loop_design_request.schema.json",
            "schemas/loop_design_result.schema.json",
            "schemas/loop_spec.schema.json",
            "schemas/agent_manifest.schema.json",
            "schemas/guardrails.schema.json",
            "schemas/progress_evidence.schema.json",
            "schemas/normalization_report.schema.json",
            "schemas/go_capability_preflight.schema.json",
            "schemas/replan_proposal.schema.json",
            "scripts/validate_design_result.py",
            "scripts/validate_codex_loop_scaffold.py",
            "scripts/validate_dag_execution_evidence.py",
            "scripts/validate_loop_progress_evidence.py",
            "scripts/normalize_design_request.py",
            "scripts/validate_replan_proposal.py",
            "examples/one_shot.json",
            "examples/workflow.json",
            "examples/agent_loop.json",
            "examples/needs_input.json",
            "examples/unsupported.json",
            "examples/requests/one_shot.json",
            "examples/requests/workflow.json",
            "examples/requests/agent_loop.json",
            "examples/requests/needs_input.json",
            "examples/requests/unsupported.json",
            "examples/codex-loop/loop_spec.json",
            "examples/codex-loop/agent_manifest.json",
            "examples/codex-loop/guardrails.json",
            "examples/codex-loop/evidence/progress/iteration_1.json",
            "examples/codex-loop/evidence/progress/iteration_2.json",
            "examples/codex-loop/evidence/preflight/go-preflight.json",
        ]
        required.extend(
            f"examples/codex-loop/subagents/{agent['id']}.md"
            for agent in manifest["subagents"]
        )
        required.extend(
            f"examples/codex-loop/{ref.removeprefix('.codex-loop/')}"
            for ref in manifest["governance_overlay"]["required_evidence_refs"]
        )
        if (REPO_ROOT / "README.md").is_file():
            required.append("../../examples/agents-gate/AGENTS.md")
        missing = [relative for relative in required if not (SKILL_ROOT / relative).is_file()]
        self.assertEqual(missing, [], f"Missing runtime-free assets: {missing}")

    def test_repository_license_is_mit_for_beichen_hu(self) -> None:
        self.require_full_repository()
        license_path = REPO_ROOT / "LICENSE"
        self.assertTrue(license_path.is_file(), "LICENSE is missing")
        content = license_path.read_text(encoding="utf-8")
        self.assertIn("MIT License", content)
        self.assertIn("Copyright (c) 2026 Beichen Hu", content)
        self.assertIn("Permission is hereby granted, free of charge", content)

    def test_skill_instructions_enforce_validation_gate(self) -> None:
        content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        required_phrases = [
            "MUST read `loop_spec.json`",
            "generate exactly one `loop_design_result`",
            "MUST run `scripts/validate_design_result.py`",
            "MUST NOT emit `spec_ready` when validation fails",
        ]
        missing = [phrase for phrase in required_phrases if phrase not in content]
        self.assertEqual(missing, [], f"Missing mandatory instructions: {missing}")

    def test_release_version_is_consistent(self) -> None:
        self.require_full_repository()
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        readme_cn_path = REPO_ROOT / "README-CN.md"
        self.assertTrue(readme_cn_path.is_file(), "README-CN.md is missing")
        readme_cn = readme_cn_path.read_text(encoding="utf-8")
        self.assertIn("**Skill version:** `3.1.0`", skill)
        self.assertIn("### v3.1.0 (2026-07-15)", readme)
        self.assertIn("### v3.1.0 (2026-07-15)", readme_cn)
        self.assertIn("### v3.0.0 (2026-07-13)", readme)
        self.assertIn("### v3.0.0 (2026-07-13)", readme_cn)
        self.assertIn("### v2.0.0 (2026-07-10)", readme)
        self.assertIn("### v2.0.0 (2026-07-10)", readme_cn)
        self_design = json.loads(
            (SKILL_ROOT / "loop_spec.json").read_text(encoding="utf-8")
        )
        self.assertEqual(self_design["skill_version"], "3.1.0")
        self.assertEqual(self_design["spec_id"], "prompt-to-loop-engineering@3.1.0")
        manifest = json.loads(
            (SKILL_ROOT / "examples" / "codex-loop" / "agent_manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["created_by_skill"]["version"], "3.1.0")
        self.assertEqual(manifest["schema_version"], "3.0.0")

    def test_skill_requires_request_bound_validation_and_no_runtime_module(self) -> None:
        content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("--request", content)
        self.assertIn("MUST NOT execute the user task", content)
        self.assertFalse((SKILL_ROOT / "runtime").exists(), "Runtime Engine must stay external")

    def test_codex_native_agent_config_scaffold_contract_is_documented(self) -> None:
        content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        required_phrases = [
            "Codex-native Agent Config Scaffold",
            ".codex-loop/",
            "agent_manifest.json",
            "guardrails.json",
            "subagents/",
            "MUST NOT create or require an independent Runtime Engine",
            "Codex is the host executor",
            "schemas/agent_manifest.schema.json",
            "scripts/validate_codex_loop_scaffold.py",
        ]
        missing = [phrase for phrase in required_phrases if phrase not in content]
        self.assertEqual(missing, [], f"Missing scaffold contract phrases: {missing}")

    def test_agent_lifecycle_activation_contract_is_documented(self) -> None:
        content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        required_phrases = [
            "Agent Lifecycle Activation Contract",
            "Host Instantiation Command",
            "Live Subagents Panel",
            "MUST NOT treat the scaffold as passive text only",
            "host-native `spawn_subagent`",
            "equivalent native sub-agent creation API",
            "Context Alignment",
            "sole authoritative System Prompt baseline",
            "Status Binding",
            "MUST update `.codex-loop/.status`",
            "No independent Runtime Engine is introduced",
        ]
        missing = [phrase for phrase in required_phrases if phrase not in content]
        self.assertEqual(missing, [], f"Missing lifecycle activation phrases: {missing}")

    def test_cooperative_governance_overlay_contract_is_documented(self) -> None:
        content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        required_phrases = [
            "Cooperative Governance Overlay",
            "Non-exclusive Routing Contract",
            "MUST NOT claim exclusive routing ownership",
            "Specialized host skills remain primary capability providers",
            "AGENTS-scoped Middleware Semantics",
            "not a background daemon, global hook, scheduler, or hidden runtime",
            "Host-resolved Atomic Capability Contract",
            "MUST NOT be modeled as directly callable functions",
            "Cooperative Skill Dispatch Rule",
            "Five Governance Variables",
            "`task_classification`",
            "`capability_snapshot`",
            "`lineup_recommendation`",
            "`loop_boundary`",
            "`approval_state`",
            "No Transparent Interception Claim",
            "MUST NOT claim that it can transparently intercept every Codex action",
            "Subagent Capability Boundary",
        ]
        missing = [phrase for phrase in required_phrases if phrase not in content]
        self.assertEqual(missing, [], f"Missing cooperative overlay phrases: {missing}")

    def test_model_configuration_inheritance_contract_is_documented(self) -> None:
        content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        required_phrases = [
            "Model Configuration Inheritance Contract",
            "Enforce Intensity Realignment",
            "`reasoning_intensity: \"extended_thought\"`",
            "`model_config: inherit_parent`",
            "required_subagent_reasoning_intensity",
            "`extended_thought`",
            "5.5 ultra-high",
            "Model Configuration Fallback Prompt",
            "Scaffold Logging",
            "capability_snapshot",
            "MUST treat lifecycle activation as degraded",
        ]
        missing = [phrase for phrase in required_phrases if phrase not in content]
        self.assertEqual(missing, [], f"Missing model inheritance phrases: {missing}")

    def test_evidence_locked_dag_execution_governance_contract_is_documented(self) -> None:
        content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        required_phrases = [
            "v1.7.0 — Evidence-Locked DAG Execution Governance",
            "GO-phase Scheduler Ownership Contract",
            "Inline Fulfillment Prohibition",
            "Execution Evidence Contract",
            "Post-hoc Hard Validation",
            "Node-scoped Atomic Capability Policy",
            "`runtime_mode`",
            "`COOPERATIVE_GOVERNANCE`",
            "`codex_loop_dag`",
            "`forbidden_for_subagent_nodes`",
            "`required_evidence`",
            "`linear_fulfillment_plugins`",
            "`scheduler_takeover`",
            "`node_scoped_atomic_capability`",
            "MUST NOT inline-fulfill",
            "MUST run `scripts/validate_dag_execution_evidence.py`",
        ]
        missing = [phrase for phrase in required_phrases if phrase not in content]
        self.assertEqual(missing, [], f"Missing evidence governance phrases: {missing}")

    def test_workflow_precedence_and_subagent_discovery_contracts_are_documented(self) -> None:
        content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        required_phrases = [
            "Workflow Precedence Rule",
            "mandatory execution protocol",
            "superpowers:executing-plans",
            "auxiliary checklist",
            "MUST NOT override approval gates",
            "MUST NOT override validation flow",
            "MUST NOT override role splitting",
            "MUST NOT override sub-agent lifecycle activation",
            "Subagent Capability Discovery Guard",
            "MUST call `tool_search`",
            "`spawn_agent`",
            "`spawn_subagent`",
            "`subagent`",
            "`multi_agent`",
            "`no_host_native_lifecycle_tool_found`",
        ]
        missing = [phrase for phrase in required_phrases if phrase not in content]
        self.assertEqual(missing, [], f"Missing precedence/discovery phrases: {missing}")

    def test_role_isolated_governance_contract_is_documented(self) -> None:
        content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        required_phrases = [
            "v1.8.0 — Evidence-Locked & Role-Isolated Governance",
            "Four Hard Limits",
            "`max_runtime_seconds`",
            "`max_iterations`",
            "`max_token_budget`",
            "`max_no_progress_loops`",
            "No-Progress Deterministic Contract",
            "`state.diff_fingerprint`",
            "`state.test_count`",
            "`state.artifact_hash`",
            "`state.new_evidence_count`",
            "Implementer/Reviewer Isolation",
            "implementer MUST NOT verify mandatory acceptance criteria",
            "reviewer or verifier",
            "MUST remain read-only",
            "validate_loop_progress_evidence.py",
        ]
        missing = [phrase for phrase in required_phrases if phrase not in content]
        self.assertEqual(missing, [], f"Missing v1.8 governance phrases: {missing}")

    def test_request_normalization_and_budget_provenance_are_documented(self) -> None:
        content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        required_phrases = [
            "v2.0.0 — Release-Hardened Contract Alignment",
            "scripts/normalize_design_request.py",
            "codex-native-safe-v1",
            "raw_request_hash",
            "effective_request_hash",
            "elapsed_runtime_seconds",
            "cumulative_token_count",
        ]
        missing = [phrase for phrase in required_phrases if phrase not in content]
        self.assertEqual(missing, [], f"Missing v2 normalization phrases: {missing}")

    def test_defensive_designing_fallback_contract_is_documented(self) -> None:
        content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        required_phrases = [
            "Defensive Designing Principle",
            "Ambiguous Prompt Fallback Contract",
            "MUST NOT produce a shallow scaffold",
            "MUST NOT reject solely because the prompt is vague",
            "derive a reasonable scaffold from observable project evidence",
            "Default maximum loop iterations: 3",
            "non-empty artifact check and basic schema/static validation",
            "MUST NOT overwrite an existing same-name workspace file directly",
            "timestamped destination or a `.tmp/` staging directory",
            "smallest evidence-justified lineup",
            "no universal subagent count limit",
        ]
        missing = [phrase for phrase in required_phrases if phrase not in content]
        self.assertEqual(missing, [], f"Missing defensive design phrases: {missing}")

    def test_dynamic_professional_role_contract_is_documented(self) -> None:
        content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        required_phrases = [
            "Dynamic Professional Role Contract",
            "delegation.agent_registry",
            "termination_control",
            "codex_host_controller",
            "reviewer_authority=evidence_only",
            "no universal subagent count limit",
            "multiple planners, implementers, reviewers, or verifiers",
            "pause, amend, revalidate, and obtain fresh user approval",
            "<agent-id>.md",
        ]
        missing = [phrase for phrase in required_phrases if phrase not in content]
        self.assertEqual(missing, [], f"Missing dynamic role phrases: {missing}")

    def test_agents_gate_uses_dynamic_lineup_and_copies_are_identical(self) -> None:
        packaged = (SKILL_ROOT / "templates" / "agents-gate" / "AGENTS.md").read_bytes()
        example = (REPO_ROOT / "examples" / "agents-gate" / "AGENTS.md").read_bytes()
        self.assertEqual(packaged, example)
        content = packaged.decode("utf-8")
        for stale_path in ("planner.md", "executor.md"):
            self.assertNotIn(stale_path, content)
        for field in (
            "professional id",
            "specialization",
            "governance role",
            "activation nodes",
            "tools",
            "rationale",
        ):
            self.assertIn(field, content)
        self.assertIn("pause, amend, revalidate, and obtain fresh user approval", content)

    def test_active_contracts_reject_stale_fixed_cast_language(self) -> None:
        active_contracts = {
            "SKILL.md": (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8"),
            "packaged AGENTS.md": (
                SKILL_ROOT / "templates" / "agents-gate" / "AGENTS.md"
            ).read_text(encoding="utf-8"),
            "example AGENTS.md": (
                REPO_ROOT / "examples" / "agents-gate" / "AGENTS.md"
            ).read_text(encoding="utf-8"),
        }
        forbidden = [
            "`lineup_recommendation`: proposed roles such as `planner`, `executor`, and optional `reviewer`",
            "`subagents/` MUST include both `planner.md` and `executor.md`",
            "generate at least `.codex-loop/subagents/planner.md` and `.codex-loop/subagents/executor.md`",
            "Default sub-agent split: `subagents/` MUST include both",
        ]
        violations = [
            f"{name}: {phrase}"
            for name, content in active_contracts.items()
            for phrase in forbidden
            if phrase in content
        ]
        self.assertEqual(violations, [], f"Stale fixed-cast contract language: {violations}")

    def test_readmes_describe_public_clone_install_and_codex_usage(self) -> None:
        self.require_full_repository()
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        readme_cn = (REPO_ROOT / "README-CN.md").read_text(encoding="utf-8")
        for content in (readme, readme_cn):
            self.assertIn("git clone https://github.com/Beichen-H/Loopower.git", content)
            self.assertNotIn("Beichen-H/meta-skills", content)
            for phrase in [
                "git clone",
                "install_local.py --verify",
                "$prompt-to-loop-engineering",
                "validate_codex_loop_scaffold.py",
                ".codex-loop/",
                "MIT License",
                "examples/agents-gate/AGENTS.md",
                "templates/agents-gate/AGENTS.md",
                "Two-stage Delegation Approval Gate",
                "Live Subagent Bridge",
                "installed-mode",
                "Cooperative Governance Overlay",
                "non-exclusive",
                "host-resolved atomic capabilities",
                "Model Configuration Inheritance Contract",
                "required_subagent_reasoning_intensity",
                "extended_thought",
                "Evidence-Locked DAG Execution Governance",
                "validate_dag_execution_evidence.py",
                "validate_loop_progress_evidence.py",
                "inline execution",
            ]:
                self.assertIn(phrase, content)

    def test_readmes_publish_dynamic_topology_and_authority_boundaries(self) -> None:
        self.require_full_repository()
        readmes = {
            "README.md": (REPO_ROOT / "README.md").read_text(encoding="utf-8"),
            "README-CN.md": (REPO_ROOT / "README-CN.md").read_text(
                encoding="utf-8"
            ),
        }
        required = [
            "topology-derived professional roles",
            "requirements-analyst",
            "feature-engineer",
            "test-verifier",
            "security-auditor",
            "not reserved roles",
            "no universal declared-role ceiling",
            "finite, statically validated",
            "capability-bound concurrency",
            "LoopSpec owns transition and termination policy",
            "Codex host controller mechanically evaluates",
            "reviewers and verifiers produce evidence only",
            "v2-to-v3 migration",
            "Manifest schema `2.0.0`",
            "regenerate v2 scaffolds",
        ]
        forbidden = [
            ".codex-loop/subagents/planner.md  -> planner live process",
            ".codex-loop/subagents/executor.md -> executor live process",
            "|   |-- planner.md",
            "|   `-- executor.md",
        ]
        for name, content in readmes.items():
            missing = [phrase for phrase in required if phrase not in content]
            self.assertEqual(missing, [], f"{name} missing v3 guidance: {missing}")
            stale = [phrase for phrase in forbidden if phrase in content]
            self.assertEqual(stale, [], f"{name} has fixed-cast mappings: {stale}")

    def test_readmes_explain_cross_preset_subagent_activation_boundary(self) -> None:
        self.require_full_repository()
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        readme_cn = (REPO_ROOT / "README-CN.md").read_text(encoding="utf-8")
        for phrase in (
            "Turn a short Codex task into an approved, bounded sub-agent workflow",
            "Making sub-agent delegation explicit across model presets",
            "standard models and normal reasoning presets",
            "does not create a missing host API",
            "The lineup is topology-derived rather than fixed",
        ):
            self.assertIn(phrase, readme)
        for phrase in (
            "把一句普通 Codex 任务转换为经过审批",
            "让不同模型预设显式启用 Sub-agent 委派",
            "标准模型和正常推理强度预设",
            "不会凭空创建宿主 API",
            "阵容由拓扑决定，而不是固定模板",
        ):
            self.assertIn(phrase, readme_cn)

    def test_readmes_embed_three_progressively_disclosed_mermaid_diagrams(self) -> None:
        self.require_full_repository()
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        readme_cn = (REPO_ROOT / "README-CN.md").read_text(encoding="utf-8")
        for content in (readme, readme_cn):
            self.assertIn("docs/assets/loopower-overview.gif", content)
        self.assertTrue((REPO_ROOT / "docs" / "assets" / "loopower-overview.gif").is_file())
        self.assertTrue((REPO_ROOT / "docs" / "assets" / "loopower-social-preview.png").is_file())
        self.assertEqual(readme.count("```mermaid"), 3)
        self.assertEqual(readme_cn.count("```mermaid"), 3)
        self.assertLess(readme.index("## Architecture at a glance"), readme.index("## What it gives Codex"))
        self.assertLess(readme.index("## Evidence-Locked DAG Execution Governance"), readme.index("### Evidence hash chain"))
        self.assertLess(readme.index("### Evidence hash chain"), readme.index("## Dynamic Professional Topology"))
        self.assertLess(readme.index("## Dynamic Professional Topology"), readme.index("### Evaluator path dominance"))
        self.assertLess(readme.index("### Evaluator path dominance"), readme.index("## Architectural Efficacy"))
        self.assertLess(readme_cn.index("## 架构总览"), readme_cn.index("## 它让 Codex 获得什么能力"))
        self.assertLess(readme_cn.index("## Evidence-Locked DAG Execution Governance"), readme_cn.index("### 证据哈希链"))
        self.assertLess(readme_cn.index("### 证据哈希链"), readme_cn.index("## 动态专业角色拓扑"))
        self.assertLess(readme_cn.index("## 动态专业角色拓扑"), readme_cn.index("### 评估器路径支配性"))
        self.assertLess(readme_cn.index("### 评估器路径支配性"), readme_cn.index("## 架构效能与边界评估"))
        self.assertIn("validators remain the normative source of truth", readme)
        self.assertIn("JSON Schema 与验证器仍是规范事实来源", readme_cn)

    def test_loop_spec_schema_and_example_log_subagent_reasoning_intensity(self) -> None:
        import json

        request_schema = json.loads(
            (SKILL_ROOT / "schemas" / "loop_design_request.schema.json").read_text(
                encoding="utf-8"
            )
        )
        runtime_props = request_schema["properties"]["runtime_capabilities"]["properties"]
        self.assertIn("required_subagent_reasoning_intensity", runtime_props)
        self.assertIn("extended_thought", runtime_props["required_subagent_reasoning_intensity"]["enum"])

        loop_spec = json.loads(
            (SKILL_ROOT / "examples" / "codex-loop" / "loop_spec.json").read_text(
                encoding="utf-8"
            )
        )
        snapshot = loop_spec["runtime_binding"]["capabilities_snapshot"]
        required = loop_spec["runtime_binding"]["required_capabilities"]
        self.assertEqual(
            snapshot.get("required_subagent_reasoning_intensity"), "extended_thought"
        )
        self.assertEqual(
            required.get("required_subagent_reasoning_intensity"), "extended_thought"
        )

    def test_codex_loop_example_declares_evidence_locked_governance(self) -> None:
        import json

        loop_spec = json.loads(
            (SKILL_ROOT / "examples" / "codex-loop" / "loop_spec.json").read_text(
                encoding="utf-8"
            )
        )
        manifest = json.loads(
            (SKILL_ROOT / "examples" / "codex-loop" / "agent_manifest.json").read_text(
                encoding="utf-8"
            )
        )

        execution_governance = loop_spec["execution_governance"]
        self.assertEqual(execution_governance["runtime_mode"], "COOPERATIVE_GOVERNANCE")
        self.assertEqual(execution_governance["scheduler"], "codex_loop_dag")
        self.assertEqual(
            execution_governance["inline_execution_policy"],
            "forbidden_for_subagent_nodes",
        )
        self.assertEqual(
            execution_governance["linear_fulfillment_plugins"]["scheduler_takeover"],
            "forbidden",
        )
        self.assertEqual(
            execution_governance["linear_fulfillment_plugins"]["allowed_role"],
            "node_scoped_atomic_capability",
        )

        overlay = manifest["governance_overlay"]
        self.assertEqual(overlay["runtime_mode"], "COOPERATIVE_GOVERNANCE")
        self.assertEqual(overlay["dag_scheduler_owner"], "prompt-to-loop-engineering")
        self.assertEqual(overlay["host_linear_fulfillment_takeover"], "forbidden")
        self.assertEqual(
            overlay["specialized_skills_policy"],
            "node_scoped_atomic_capabilities",
        )
        for agent in manifest["subagents"]:
            self.assertIn(
                f".codex-loop/evidence/activation/{agent['id']}.json",
                overlay["required_evidence_refs"],
            )

    def test_example_subagent_prompts_request_reasoning_alignment(self) -> None:
        manifest = json.loads(
            (SKILL_ROOT / "examples/codex-loop/agent_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        for agent in manifest["subagents"]:
            relative = f"examples/codex-loop/subagents/{agent['id']}.md"
            content = (SKILL_ROOT / relative).read_text(encoding="utf-8")
            for phrase in [
                "reasoning_intensity = extended_thought",
                "model_configuration_degraded",
            ]:
                self.assertIn(phrase, content, f"{relative} missing {phrase}")

    def test_agents_gate_requires_two_stage_delegation_approval(self) -> None:
        gate_paths = [SKILL_ROOT / "templates" / "agents-gate" / "AGENTS.md"]
        if (REPO_ROOT / "examples" / "agents-gate" / "AGENTS.md").is_file():
            gate_paths.append(REPO_ROOT / "examples" / "agents-gate" / "AGENTS.md")
        for gate_path in gate_paths:
            self.assertTrue(gate_path.is_file(), f"{gate_path} is missing")
        contents = [path.read_text(encoding="utf-8") for path in gate_paths]
        required_phrases = [
            "Two-stage Delegation Approval Gate",
            "Workflow Precedence Rule",
            "mandatory execution protocol",
            "superpowers:executing-plans",
            "auxiliary checklist",
            "MUST NOT override approval gates",
            "MUST NOT override validation flow",
            "MUST NOT override role splitting",
            "MUST NOT override sub-agent lifecycle activation",
            "Non-trivial",
            "Lineup Recommendation",
            "Loop Boundary",
            "STOP — Waiting for user approval",
            "explicit user approval",
            "$prompt-to-loop-engineering",
            "MUST NOT initialize `.codex-loop/`",
            "validate_codex_loop_scaffold.py",
        ]
        for content in contents:
            missing = [phrase for phrase in required_phrases if phrase not in content]
            self.assertEqual(missing, [], f"Missing AGENTS gate phrases: {missing}")
        if len(contents) == 2:
            self.assertEqual(contents[0], contents[1], "repo and packaged gate templates diverged")

    def test_agent_manifest_schema_contract_has_core_scaffold_fields(self) -> None:
        import json

        schema_path = SKILL_ROOT / "schemas" / "agent_manifest.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertEqual(schema["title"], "Codex Agent Manifest")
        required = set(schema["required"])
        self.assertGreaterEqual(
            required,
            {
                "schema_version",
                "manifest_id",
                "codex_host",
                "loop_binding",
                "guardrails_ref",
                "subagents",
                "tool_bindings",
                "knowledge_bindings",
                "resume_policy",
            },
        )
        self.assertFalse(
            schema["properties"]["codex_host"]["properties"]["independent_runtime_engine"][
                "const"
            ]
        )

    def test_generated_python_cache_is_not_packaged(self) -> None:
        self.require_full_repository()
        installer = (REPO_ROOT / "install_local.py").read_text(encoding="utf-8")
        for token in ['"__pycache__"', '".pyc"', '".pyo"']:
            self.assertIn(token, installer)
        self.assertIn('encoding="utf-8"', installer)
        self.assertIn('errors="replace"', installer)

    def test_local_install_scripts_are_packaged_and_documented(self) -> None:
        self.require_full_repository()
        required = ["install_local.py", "install_local.ps1"]
        missing = [relative for relative in required if not (REPO_ROOT / relative).is_file()]
        self.assertEqual(missing, [], f"Missing local install scripts: {missing}")

        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        for phrase in [
            "## Local Installation",
            "install_local.py",
            "install_local.ps1",
            "--dry-run",
            "prompt-to-loop-engineering",
        ]:
            self.assertIn(phrase, readme)

    def test_github_actions_ci_is_packaged(self) -> None:
        self.require_full_repository()
        workflow = REPO_ROOT / ".github" / "workflows" / "ci.yml"
        self.assertTrue(workflow.is_file(), ".github/workflows/ci.yml is missing")
        content = workflow.read_text(encoding="utf-8")
        for phrase in [
            "python -B -m unittest discover",
            "validate_codex_loop_scaffold.py",
            "validate_dag_execution_evidence.py",
            "test_spec_loading.py",
            "validate_design_result.py",
        ]:
            self.assertIn(phrase, content)

    def test_python_installer_copies_skill_and_runs_verify_command(self) -> None:
        self.require_full_repository()
        installer = REPO_ROOT / "install_local.py"
        with tempfile.TemporaryDirectory() as tmp:
            target_root = Path(tmp) / "skills-home"
            result = subprocess.run(
                [
                    sys.executable,
                    str(installer),
                    "--target",
                    str(target_root),
                    "--verify",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(
                result.returncode,
                0,
                f"Installer failed.\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )
            installed = target_root / "prompt-to-loop-engineering"
            self.assertTrue((installed / "SKILL.md").is_file())
            self.assertTrue((installed / "loop_spec.json").is_file())
            self.assertTrue((installed / "scripts" / "validate_design_result.py").is_file())
            self.assertTrue((installed / "templates" / "agents-gate" / "AGENTS.md").is_file())
            self.assertFalse((installed / "runtime").exists(), "Installer must not create runtime/")
            installed_cache = [
                path.relative_to(installed).as_posix()
                for path in installed.rglob("*")
                if path.name == "__pycache__" or path.suffix in {".pyc", ".pyo"}
            ]
            self.assertEqual(installed_cache, [], f"Installer copied generated cache: {installed_cache}")

            replacement = subprocess.run(
                [
                    sys.executable,
                    str(installer),
                    "--target",
                    str(target_root),
                    "--force",
                    "--verify",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(
                replacement.returncode,
                0,
                "Forced reinstall must replace copied read-only directories.\n"
                f"STDOUT:\n{replacement.stdout}\nSTDERR:\n{replacement.stderr}",
            )

    def test_python_installer_verifies_a_relative_target(self) -> None:
        self.require_full_repository()
        installer = REPO_ROOT / "install_local.py"
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tmp:
            target_root = Path(tmp)
            relative_target = target_root.relative_to(REPO_ROOT)
            result = subprocess.run(
                [
                    sys.executable,
                    str(installer),
                    "--target",
                    str(relative_target),
                    "--verify",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(
                result.returncode,
                0,
                "Relative install targets must resolve before verification.\n"
                f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )

    def test_python_installer_dry_run_does_not_write_target(self) -> None:
        self.require_full_repository()
        installer = REPO_ROOT / "install_local.py"
        with tempfile.TemporaryDirectory() as tmp:
            target_root = Path(tmp) / "dry-run-skills"
            result = subprocess.run(
                [
                    sys.executable,
                    str(installer),
                    "--target",
                    str(target_root),
                    "--dry-run",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(
                result.returncode,
                0,
                f"Dry run failed.\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )
            self.assertIn("DRY RUN", result.stdout)
            self.assertFalse(target_root.exists(), "Dry run must not create target directory")

    def test_published_loop_specs_cover_schema_root_requirements(self) -> None:
        schema = json.loads((SKILL_ROOT / "schemas" / "loop_spec.schema.json").read_text(encoding="utf-8"))
        required = set(schema["required"])
        # Task 2 migrates the published v2 examples to the v3 controller contract.
        legacy_required = required - {"termination_control"}
        node_required = set(schema["$defs"]["node"]["required"])
        self.assertNotIn("execution_governance", required)
        documents = {
            "self": json.loads((SKILL_ROOT / "loop_spec.json").read_text(encoding="utf-8")),
            "workflow": json.loads((SKILL_ROOT / "examples" / "workflow.json").read_text(encoding="utf-8"))["loop_spec"],
            "agent_loop": json.loads((SKILL_ROOT / "examples" / "agent_loop.json").read_text(encoding="utf-8"))["loop_spec"],
        }
        for name, spec in documents.items():
            missing = legacy_required - set(spec)
            self.assertEqual(missing, set(), f"{name} misses LoopSpec schema fields: {sorted(missing)}")
            for node in spec["control_flow"]["nodes"]:
                node_missing = node_required - set(node)
                self.assertEqual(node_missing, set(), f"{name}/{node.get('id')} misses node fields: {sorted(node_missing)}")

    def test_effective_request_capabilities_match_schema_requirements(self) -> None:
        schema = json.loads((SKILL_ROOT / "schemas" / "loop_design_request.schema.json").read_text(encoding="utf-8"))
        required = set(schema["properties"]["runtime_capabilities"]["required"])
        for path in (SKILL_ROOT / "examples" / "requests").glob("*.json"):
            request = json.loads(path.read_text(encoding="utf-8"))
            missing = required - set(request["runtime_capabilities"])
            self.assertEqual(missing, set(), f"{path.name} misses capability fields: {sorted(missing)}")

    def test_progress_examples_match_v3_schema_surface(self) -> None:
        schema = json.loads((SKILL_ROOT / "schemas" / "progress_evidence.schema.json").read_text(encoding="utf-8"))
        required = set(schema["required"])
        for path in (SKILL_ROOT / "examples" / "codex-loop" / "evidence" / "progress").glob("*.json"):
            sample = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(set(sample), required, f"{path.name} does not match progress schema surface")
            self.assertEqual(sample["schema_version"], "3.0.0")


if __name__ == "__main__":
    unittest.main()
