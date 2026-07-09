"""Tests for post-hoc loop progress evidence validation."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parent.parent
VALIDATOR = SKILL_ROOT / "scripts" / "validate_loop_progress_evidence.py"
EXAMPLE_SCAFFOLD = SKILL_ROOT / "examples" / "codex-loop"


class LoopProgressEvidenceTests(unittest.TestCase):
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

    def test_valid_progress_samples_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_scaffold(tmp)
            result = self.run_validator(root)

        self.assertEqual(
            result.returncode,
            0,
            f"validator failed\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
        )
        self.assertIn("OK: loop progress evidence validation passed.", result.stdout)

    def test_exceeding_max_no_progress_loops_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_scaffold(tmp)
            progress = root / "evidence" / "progress"
            first = json.loads((progress / "iteration_1.json").read_text(encoding="utf-8"))
            for iteration in [2, 3]:
                clone = dict(first)
                clone["iteration"] = iteration
                clone["new_evidence_count"] = 0
                (progress / f"iteration_{iteration}.json").write_text(
                    json.dumps(clone, indent=2),
                    encoding="utf-8",
                )
            result = self.run_validator(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("max_no_progress_loops exceeded", result.stdout)

    def test_empty_progress_directory_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_scaffold(tmp)
            for path in (root / "evidence" / "progress").glob("*.json"):
                path.unlink()
            result = self.run_validator(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("progress evidence directory must contain", result.stdout)


if __name__ == "__main__":
    unittest.main()
