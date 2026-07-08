"""Tests for post-hoc evidence-locked DAG execution validation."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parent.parent
VALIDATOR = SKILL_ROOT / "scripts" / "validate_dag_execution_evidence.py"
EXAMPLE_SCAFFOLD = SKILL_ROOT / "examples" / "codex-loop"


class DagExecutionEvidenceTests(unittest.TestCase):
    def copy_scaffold(self, tmp: str) -> Path:
        target = Path(tmp) / ".codex-loop"
        shutil.copytree(EXAMPLE_SCAFFOLD, target)
        return target

    def run_validator(self, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(VALIDATOR), str(root)],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_valid_example_scaffold_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_scaffold(tmp)
            result = self.run_validator(root)

        self.assertEqual(
            result.returncode,
            0,
            f"validator failed\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
        )
        self.assertIn("OK: DAG execution evidence validation passed.", result.stdout)

    def test_missing_activation_evidence_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_scaffold(tmp)
            (root / "evidence" / "activation" / "planner.json").unlink()
            result = self.run_validator(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("missing required evidence file", result.stdout)
        self.assertIn("activation/planner.json", result.stdout)

    def test_missing_handoff_evidence_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_scaffold(tmp)
            (root / "evidence" / "handoff" / "planner_to_executor.json").unlink()
            result = self.run_validator(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("missing required evidence file", result.stdout)
        self.assertIn("handoff/planner_to_executor.json", result.stdout)

    def test_missing_completion_evidence_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_scaffold(tmp)
            (root / "evidence" / "completion" / "executor.json").unlink()
            result = self.run_validator(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("missing required evidence file", result.stdout)
        self.assertIn("completion/executor.json", result.stdout)

    def test_degraded_subagent_reasoning_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_scaffold(tmp)
            evidence_path = root / "evidence" / "activation" / "executor.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence["model_config"]["reasoning_intensity"] = "low"
            evidence_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
            result = self.run_validator(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("reasoning_intensity must be extended_thought", result.stdout)

    def test_inline_completion_for_subagent_node_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_scaffold(tmp)
            evidence_path = root / "evidence" / "completion" / "executor.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence.pop("subagent_id", None)
            evidence["producer"] = "main_session_inline"
            evidence_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
            result = self.run_validator(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("inline completion is forbidden", result.stdout)


if __name__ == "__main__":
    unittest.main()
