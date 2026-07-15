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

    def required_evidence(self, root: Path) -> list[tuple[Path, dict]]:
        manifest = json.loads((root / "agent_manifest.json").read_text(encoding="utf-8"))
        result = []
        for ref in manifest["governance_overlay"]["required_evidence_refs"]:
            path = root / ref.removeprefix(".codex-loop/")
            result.append((path, json.loads(path.read_text(encoding="utf-8"))))
        return result

    def evidence_for(self, root: Path, evidence_type: str, node_id: str) -> Path:
        matches = [
            path
            for path, evidence in self.required_evidence(root)
            if evidence.get("evidence_type") == evidence_type and evidence.get("node_id") == node_id
        ]
        self.assertEqual(len(matches), 1)
        return matches[0]

    def write_evidence(self, path: Path, evidence: dict) -> None:
        path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")

    def test_valid_example_with_four_arbitrary_roles_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_scaffold(tmp)
            manifest = json.loads((root / "agent_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(
                {agent["id"] for agent in manifest["subagents"]},
                {"requirements-analyst", "feature-engineer", "test-verifier", "security-auditor"},
            )
            result = self.run_validator(root)

        self.assertEqual(
            result.returncode,
            0,
            f"validator failed\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
        )
        self.assertIn("OK: DAG execution evidence validation passed.", result.stdout)

    def test_evidence_bound_to_different_loop_spec_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_scaffold(tmp)
            path = self.evidence_for(root, "activation", "requirements-analysis")
            evidence = json.loads(path.read_text(encoding="utf-8"))
            evidence["loop_spec_digest"] = "sha256:" + "0" * 64
            self.write_evidence(path, evidence)
            result = self.run_validator(root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("LoopSpec digest mismatch", result.stdout)

    def test_activation_for_undeclared_role_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_scaffold(tmp)
            path = self.evidence_for(root, "activation", "requirements-analysis")
            evidence = json.loads(path.read_text(encoding="utf-8"))
            evidence["subagent_id"] = "ghost-agent"
            self.write_evidence(path, evidence)
            result = self.run_validator(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("subagent_id does not match", result.stdout)

    def test_completion_by_wrong_role_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_scaffold(tmp)
            path = self.evidence_for(root, "completion", "feature-implementation")
            evidence = json.loads(path.read_text(encoding="utf-8"))
            evidence["subagent_id"] = "test-verifier"
            self.write_evidence(path, evidence)
            result = self.run_validator(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("inline completion is forbidden", result.stdout)

    def test_terminal_completion_by_fake_subagent_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_scaffold(tmp)
            path = self.evidence_for(root, "completion", "terminal-export")
            evidence = json.loads(path.read_text(encoding="utf-8"))
            evidence["producer"] = "fake_verifier_subagent"
            evidence["subagent_id"] = "test-verifier"
            self.write_evidence(path, evidence)
            result = self.run_validator(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("terminal completion must be produced by the Codex host", result.stdout)

    def test_handoff_to_undefined_node_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_scaffold(tmp)
            path, evidence = next(
                (path, evidence)
                for path, evidence in self.required_evidence(root)
                if evidence.get("evidence_type") == "handoff"
            )
            evidence["to_node"] = "undefined-node"
            self.write_evidence(path, evidence)
            result = self.run_validator(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("handoff references undefined node", result.stdout)

    def test_handoff_not_represented_by_edge_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_scaffold(tmp)
            path, evidence = next(
                (path, evidence)
                for path, evidence in self.required_evidence(root)
                if evidence.get("evidence_type") == "handoff"
            )
            evidence["to_node"] = "security-review"
            self.write_evidence(path, evidence)
            result = self.run_validator(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("handoff does not match a LoopSpec edge", result.stdout)

    def test_handoff_identity_must_match_manifest_ownership(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_scaffold(tmp)
            path = root / "evidence" / "handoff" / "handoff-01.json"
            evidence = json.loads(path.read_text(encoding="utf-8"))
            evidence["from_subagent_id"] = "ghost-agent"
            self.write_evidence(path, evidence)
            result = self.run_validator(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("source identity", result.stdout)

    def test_missing_activation_coverage_for_subagent_node_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_scaffold(tmp)
            manifest_path = root / "agent_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            missing = self.evidence_for(root, "activation", "test-verification")
            ref = ".codex-loop/" + missing.relative_to(root).as_posix()
            manifest["governance_overlay"]["required_evidence_refs"].remove(ref)
            self.write_evidence(manifest_path, manifest)
            result = self.run_validator(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("exactly one activation evidence entry", result.stdout)
        self.assertIn("test-verification", result.stdout)

    def test_missing_completion_coverage_for_subagent_node_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_scaffold(tmp)
            manifest_path = root / "agent_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            missing = self.evidence_for(root, "completion", "security-review")
            ref = ".codex-loop/" + missing.relative_to(root).as_posix()
            manifest["governance_overlay"]["required_evidence_refs"].remove(ref)
            self.write_evidence(manifest_path, manifest)
            result = self.run_validator(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("exactly one completion evidence entry", result.stdout)
        self.assertIn("security-review", result.stdout)

    def test_duplicate_activation_evidence_for_node_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_scaffold(tmp)
            source = self.evidence_for(root, "activation", "feature-implementation")
            duplicate = source.with_name("unrelated-filename.json")
            shutil.copyfile(source, duplicate)
            manifest_path = root / "agent_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["governance_overlay"]["required_evidence_refs"].append(
                ".codex-loop/" + duplicate.relative_to(root).as_posix()
            )
            self.write_evidence(manifest_path, manifest)
            result = self.run_validator(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("exactly one activation evidence entry", result.stdout)
        self.assertIn("feature-implementation", result.stdout)

    def test_degraded_subagent_reasoning_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_scaffold(tmp)
            path = self.evidence_for(root, "activation", "feature-implementation")
            evidence = json.loads(path.read_text(encoding="utf-8"))
            evidence["model_config"]["reasoning_intensity"] = "low"
            self.write_evidence(path, evidence)
            result = self.run_validator(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("reasoning_intensity must be extended_thought", result.stdout)

    def test_removing_all_handoff_refs_fails_for_executed_chain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_scaffold(tmp)
            manifest_path = root / "agent_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["governance_overlay"]["required_evidence_refs"] = [
                ref for ref in manifest["governance_overlay"]["required_evidence_refs"]
                if "/handoff/" not in ref
            ]
            self.write_evidence(manifest_path, manifest)
            result = self.run_validator(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("handoff evidence", result.stdout)

    def test_missing_one_executed_transition_handoff_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_scaffold(tmp)
            manifest_path = root / "agent_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["governance_overlay"]["required_evidence_refs"].remove(
                ".codex-loop/evidence/handoff/handoff-02.json"
            )
            self.write_evidence(manifest_path, manifest)
            result = self.run_validator(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("executed transition", result.stdout)


if __name__ == "__main__":
    unittest.main()
