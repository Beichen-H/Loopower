"""Static tests for Codex-native .codex-loop scaffold validation."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
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

    def test_valid_example_scaffold_passes(self) -> None:
        result = self.run_validator(EXAMPLE)
        self.assertEqual(
            result.returncode,
            0,
            f"Expected valid scaffold.\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
        )
        self.assertIn("Codex loop scaffold validation passed", result.stdout)

    def test_rejects_runtime_engine_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / ".codex-loop"
            shutil.copytree(EXAMPLE, work)
            (work / "runtime").mkdir()

            result = self.run_validator(work)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("forbidden runtime artifact", result.stdout + result.stderr)

    def test_rejects_multiline_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / ".codex-loop"
            shutil.copytree(EXAMPLE, work)
            (work / ".status").write_text("planning\nexecuting\n", encoding="utf-8")

            result = self.run_validator(work)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(".status must contain exactly one stage id", result.stdout + result.stderr)

    def test_rejects_manifest_subagent_without_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / ".codex-loop"
            shutil.copytree(EXAMPLE, work)
            (work / "subagents" / "executor.md").unlink()

            result = self.run_validator(work)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("missing subagent prompt", result.stdout + result.stderr)

    def test_rejects_subagent_scaffold_without_reasoning_intensity_marker(self) -> None:
        import json

        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / ".codex-loop"
            shutil.copytree(EXAMPLE, work)
            spec_path = work / "loop_spec.json"
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
            spec["runtime_binding"]["capabilities_snapshot"].pop(
                "required_subagent_reasoning_intensity", None
            )
            spec_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")

            result = self.run_validator(work)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "required_subagent_reasoning_intensity",
                result.stdout + result.stderr,
            )

    def test_rejects_scaffold_without_evidence_governance(self) -> None:
        import json

        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / ".codex-loop"
            shutil.copytree(EXAMPLE, work)

            spec_path = work / "loop_spec.json"
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
            spec.pop("execution_governance", None)
            spec_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")

            result = self.run_validator(work)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("execution_governance", result.stdout + result.stderr)

    def test_rejects_manifest_without_governance_overlay(self) -> None:
        import json

        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / ".codex-loop"
            shutil.copytree(EXAMPLE, work)

            manifest_path = work / "agent_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest.pop("governance_overlay", None)
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

            result = self.run_validator(work)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("governance_overlay", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
