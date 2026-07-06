"""Codex-facing package surface checks for prompt-to-loop-engineering."""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = SKILL_ROOT.parents[1]


class SkillSurfaceTests(unittest.TestCase):
    def require_full_repository(self) -> None:
        if not (REPO_ROOT / "README.md").is_file():
            self.skipTest("repository-root assets are not present in installed-skill mode")

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
        required = [
            "templates/agents-gate/AGENTS.md",
            "schemas/loop_design_request.schema.json",
            "schemas/loop_design_result.schema.json",
            "schemas/loop_spec.schema.json",
            "schemas/agent_manifest.schema.json",
            "schemas/guardrails.schema.json",
            "scripts/validate_design_result.py",
            "scripts/validate_codex_loop_scaffold.py",
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
            "examples/codex-loop/subagents/planner.md",
            "examples/codex-loop/subagents/executor.md",
        ]
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
            "MUST generate exactly one `loop_design_result`",
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
        self.assertIn("**Skill version:** `1.6.0`", skill)
        self.assertIn("### v1.6.0 (2026-07-06)", readme)
        self.assertIn("### v1.6.0 (2026-07-06)", readme_cn)

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
            "`planner.md`",
            "`executor.md`",
            "MUST NOT merge these two roles",
        ]
        missing = [phrase for phrase in required_phrases if phrase not in content]
        self.assertEqual(missing, [], f"Missing defensive design phrases: {missing}")

    def test_readmes_describe_public_clone_install_and_codex_usage(self) -> None:
        self.require_full_repository()
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        readme_cn = (REPO_ROOT / "README-CN.md").read_text(encoding="utf-8")
        for content in (readme, readme_cn):
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
            ]:
                self.assertIn(phrase, content)

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

    def test_example_subagent_prompts_request_reasoning_alignment(self) -> None:
        for relative in [
            "examples/codex-loop/subagents/planner.md",
            "examples/codex-loop/subagents/executor.md",
        ]:
            content = (SKILL_ROOT / relative).read_text(encoding="utf-8")
            for phrase in [
                "reasoning_intensity = extended_thought",
                "5.5 ultra-high",
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


if __name__ == "__main__":
    unittest.main()
