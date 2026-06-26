"""Codex-facing package surface checks for prompt-to-loop-engineering."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = SKILL_ROOT.parents[1]


class SkillSurfaceTests(unittest.TestCase):
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
            "schemas/loop_design_request.schema.json",
            "schemas/loop_design_result.schema.json",
            "schemas/loop_spec.schema.json",
            "scripts/validate_design_result.py",
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
        ]
        missing = [relative for relative in required if not (SKILL_ROOT / relative).is_file()]
        self.assertEqual(missing, [], f"Missing runtime-free assets: {missing}")

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
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("**Skill version:** `1.2.0`", skill)
        self.assertIn("### v1.2.0 (2026-06-24)", readme)

    def test_skill_requires_request_bound_validation_and_no_runtime_module(self) -> None:
        content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("--request", content)
        self.assertIn("MUST NOT execute the user task", content)
        self.assertFalse((SKILL_ROOT / "runtime").exists(), "Runtime Engine must stay external")

    def test_generated_python_cache_is_not_packaged(self) -> None:
        caches = [
            path.relative_to(SKILL_ROOT).as_posix()
            for path in SKILL_ROOT.rglob("*")
            if path.name == "__pycache__" or path.suffix in {".pyc", ".pyo"}
        ]
        self.assertEqual(caches, [], f"Generated Python cache must not be packaged: {caches}")


if __name__ == "__main__":
    unittest.main()
