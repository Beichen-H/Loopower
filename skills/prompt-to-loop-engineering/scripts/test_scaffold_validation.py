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


if __name__ == "__main__":
    unittest.main()
