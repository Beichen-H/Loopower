"""Tests for post-hoc loop progress evidence validation."""

from __future__ import annotations

import json
import copy
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from governance_contracts import canonical_json_digest


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

    def refresh_config_binding(self, root: Path) -> None:
        spec = json.loads((root / "loop_spec.json").read_text(encoding="utf-8"))
        digest = canonical_json_digest(spec)
        manifest_path = root / "agent_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["configuration_binding"]["loop_spec_digest"] = digest
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        for path in (root / "evidence").rglob("*.json"):
            evidence = json.loads(path.read_text(encoding="utf-8"))
            if "loop_spec_digest" in evidence:
                evidence["loop_spec_digest"] = digest
                path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")

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
                clone["cycle_iteration"] = iteration
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

    def test_exceeding_iteration_limit_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_scaffold(tmp)
            spec_path = root / "loop_spec.json"
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
            for threshold in spec["threshold_register"]:
                if threshold["id"] == "max_iterations":
                    threshold["value"] = 1
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            self.refresh_config_binding(root)
            result = self.run_validator(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("max_iterations exceeded", result.stdout)

    def test_exceeding_runtime_limit_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_scaffold(tmp)
            sample_path = root / "evidence" / "progress" / "iteration_2.json"
            sample = json.loads(sample_path.read_text(encoding="utf-8"))
            sample["elapsed_runtime_seconds"] = 901
            sample_path.write_text(json.dumps(sample), encoding="utf-8")
            result = self.run_validator(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("max_runtime_seconds exceeded", result.stdout)

    def test_exceeding_token_limit_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_scaffold(tmp)
            sample_path = root / "evidence" / "progress" / "iteration_2.json"
            sample = json.loads(sample_path.read_text(encoding="utf-8"))
            sample["cumulative_token_count"] = 45001
            sample_path.write_text(json.dumps(sample), encoding="utf-8")
            result = self.run_validator(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("max_token_budget exceeded", result.stdout)

    def test_missing_budget_observation_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_scaffold(tmp)
            sample_path = root / "evidence" / "progress" / "iteration_2.json"
            sample = json.loads(sample_path.read_text(encoding="utf-8"))
            del sample["cumulative_token_count"]
            sample_path.write_text(json.dumps(sample), encoding="utf-8")
            result = self.run_validator(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("progress fields must exactly match", result.stdout)

    def test_rejects_legacy_progress_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_scaffold(tmp)
            sample_path = root / "evidence" / "progress" / "iteration_1.json"
            sample = json.loads(sample_path.read_text(encoding="utf-8"))
            sample["schema_version"] = "1.0.0"
            sample_path.write_text(json.dumps(sample), encoding="utf-8")
            result = self.run_validator(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("schema_version must be 3.0.0", result.stdout)

    def test_rejects_undeclared_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_scaffold(tmp)
            sample_path = root / "evidence" / "progress" / "iteration_1.json"
            sample = json.loads(sample_path.read_text(encoding="utf-8"))
            sample["cycle_id"] = "invented_cycle"
            sample_path.write_text(json.dumps(sample), encoding="utf-8")
            result = self.run_validator(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("undeclared cycle", result.stdout)

    def test_rejects_non_contiguous_run_iterations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_scaffold(tmp)
            sample_path = root / "evidence" / "progress" / "iteration_2.json"
            sample = json.loads(sample_path.read_text(encoding="utf-8"))
            sample["iteration"] = 3
            sample["cycle_iteration"] = 3
            sample_path.write_text(json.dumps(sample), encoding="utf-8")
            result = self.run_validator(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("must be contiguous from 1", result.stdout)

    def test_multiple_declared_cycles_are_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_scaffold(tmp)
            spec_path = root / "loop_spec.json"
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
            second_cycle = copy.deepcopy(spec["control_flow"]["cycles"][0])
            second_cycle["id"] = "secondary_cycle"
            spec["control_flow"]["cycles"].append(second_cycle)
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            self.refresh_config_binding(root)

            progress = root / "evidence" / "progress"
            sample = json.loads((progress / "iteration_2.json").read_text(encoding="utf-8"))
            sample.update(
                {
                    "cycle_id": "secondary_cycle",
                    "iteration": 3,
                    "cycle_iteration": 1,
                    "elapsed_runtime_seconds": 300,
                    "cumulative_token_count": 20000,
                    "artifact_hash": "sha256:" + "e" * 64,
                    "diff_fingerprint": "sha256:" + "f" * 64,
                }
            )
            (progress / "iteration_3.json").write_text(json.dumps(sample), encoding="utf-8")
            result = self.run_validator(root)

        self.assertEqual(result.returncode, 0, result.stdout)


if __name__ == "__main__":
    unittest.main()
