"""Static tests for Codex-native .codex-loop scaffold validation."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parent.parent
VALIDATOR = SKILL_ROOT / "scripts" / "validate_codex_loop_scaffold.py"
EXAMPLE = SKILL_ROOT / "examples" / "codex-loop"


class CodexLoopScaffoldValidationTests(unittest.TestCase):
    def run_validator(self, path: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-B", str(VALIDATOR), str(path)],
            text=True,
            capture_output=True,
            check=False,
        )

    @contextmanager
    def scaffold(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / ".codex-loop"
            shutil.copytree(EXAMPLE, work)
            yield work

    @staticmethod
    def load(work: Path, name: str) -> dict:
        return json.loads((work / name).read_text(encoding="utf-8"))

    @staticmethod
    def save(work: Path, name: str, payload: dict) -> None:
        (work / name).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def assert_invalid(self, work: Path, message: str) -> None:
        result = self.run_validator(work)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(message, result.stdout + result.stderr)

    def test_valid_four_role_scaffold_passes_without_max_items_assumption(self) -> None:
        manifest = json.loads((EXAMPLE / "agent_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["subagents"]), 4)
        result = self.run_validator(EXAMPLE)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_rejects_runtime_engine_artifacts(self) -> None:
        with self.scaffold() as work:
            (work / "runtime").mkdir()
            self.assert_invalid(work, "forbidden runtime artifact")

    def test_rejects_parent_traversal_prompt_path(self) -> None:
        with self.scaffold() as work:
            manifest = self.load(work, "agent_manifest.json")
            manifest["subagents"][0]["prompt_path"] = ".codex-loop/subagents/../escape.md"
            self.save(work, "agent_manifest.json", manifest)
            self.assert_invalid(work, "prompt_path")

    def test_rejects_windows_device_agent_ids_case_insensitively(self) -> None:
        for unsafe_id in ("CON", "con"):
            with self.subTest(unsafe_id=unsafe_id), self.scaffold() as work:
                manifest = self.load(work, "agent_manifest.json")
                manifest["subagents"][0]["id"] = unsafe_id
                self.save(work, "agent_manifest.json", manifest)
                self.assert_invalid(work, "unsafe agent id")

    def test_rejects_case_folding_agent_id_collision(self) -> None:
        with self.scaffold() as work:
            manifest = self.load(work, "agent_manifest.json")
            manifest["subagents"][1]["id"] = manifest["subagents"][0]["id"].upper()
            self.save(work, "agent_manifest.json", manifest)
            self.assert_invalid(work, "case-folding collision")

    def test_rejects_prompt_path_that_does_not_match_agent_id(self) -> None:
        with self.scaffold() as work:
            manifest = self.load(work, "agent_manifest.json")
            manifest["subagents"][0]["prompt_path"] = manifest["subagents"][1]["prompt_path"]
            self.save(work, "agent_manifest.json", manifest)
            self.assert_invalid(work, "canonical prompt path")

    def test_rejects_undeclared_subagent_prompt_file(self) -> None:
        with self.scaffold() as work:
            (work / "subagents" / "undeclared.md").write_text("# Undeclared\n", encoding="utf-8")
            self.assert_invalid(work, "undeclared subagent prompt")

    def test_rejects_orphan_activation_node(self) -> None:
        with self.scaffold() as work:
            manifest = self.load(work, "agent_manifest.json")
            manifest["subagents"][0]["activation_nodes"] = ["missing-node"]
            self.save(work, "agent_manifest.json", manifest)
            self.assert_invalid(work, "activation node")

    def test_rejects_manifest_registry_role_mismatch(self) -> None:
        with self.scaffold() as work:
            manifest = self.load(work, "agent_manifest.json")
            manifest["subagents"][0]["governance_role"] = "implementer"
            self.save(work, "agent_manifest.json", manifest)
            self.assert_invalid(work, "governance_role")

    def test_rejects_node_agent_role_mismatch(self) -> None:
        with self.scaffold() as work:
            spec = self.load(work, "loop_spec.json")
            spec["control_flow"]["nodes"][0]["role"] = "implementer"
            self.save(work, "loop_spec.json", spec)
            self.assert_invalid(work, "governance_role")

    def test_rejects_terminal_only_evaluator_for_an_implementer(self) -> None:
        with self.scaffold() as work:
            spec = self.load(work, "loop_spec.json")
            for node in spec["control_flow"]["nodes"]:
                if node.get("role") in {"reviewer", "verifier"}:
                    node["kind"] = "terminal"
            self.save(work, "loop_spec.json", spec)
            self.assert_invalid(work, "reachable non-terminal reviewer/verifier")

    def test_rejects_subagent_tool_outside_capability_snapshot(self) -> None:
        with self.scaffold() as work:
            manifest = self.load(work, "agent_manifest.json")
            manifest["subagents"][0]["allowed_tools"].append("network_probe")
            self.save(work, "agent_manifest.json", manifest)
            self.assert_invalid(work, "undeclared tool")

    def test_rejects_node_tool_outside_capability_snapshot(self) -> None:
        with self.scaffold() as work:
            spec = self.load(work, "loop_spec.json")
            spec["control_flow"]["nodes"][0]["allowed_tools"].append("network_probe")
            self.save(work, "loop_spec.json", spec)
            self.assert_invalid(work, "undeclared tool")

    def test_rejects_manifest_loop_spec_tool_mode_disagreement(self) -> None:
        with self.scaffold() as work:
            manifest = self.load(work, "agent_manifest.json")
            binding = next(item for item in manifest["tool_bindings"] if item["name"] == "run_tests")
            binding["permission_mode"] = "workspace_write"
            self.save(work, "agent_manifest.json", manifest)
            self.assert_invalid(work, "permission mode")

    def test_rejects_status_that_is_not_an_actual_node_id(self) -> None:
        with self.scaffold() as work:
            (work / ".status").write_text("syntactically-valid-but-missing\n", encoding="utf-8")
            self.assert_invalid(work, "unknown node id")

    def test_rejects_node_assigned_to_multiple_agents(self) -> None:
        with self.scaffold() as work:
            manifest = self.load(work, "agent_manifest.json")
            manifest["subagents"][1]["activation_nodes"] = manifest["subagents"][0]["activation_nodes"][:]
            self.save(work, "agent_manifest.json", manifest)
            self.assert_invalid(work, "multiple agents")

    def test_rejects_multiline_status(self) -> None:
        with self.scaffold() as work:
            (work / ".status").write_text("requirements-analysis\nfeature-implementation\n", encoding="utf-8")
            self.assert_invalid(work, ".status must contain exactly one stage id")


if __name__ == "__main__":
    unittest.main()
