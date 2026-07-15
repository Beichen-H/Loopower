"""Tests for atomic, exact-preview LoopSpec replan approval."""

from __future__ import annotations

import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from governance_contracts import canonical_json_digest
from validate_replan_proposal import ReplanValidationError, validate_replan


SKILL_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = SKILL_ROOT / "examples" / "codex-loop"


class ReplanProposalTests(unittest.TestCase):
    def fixture(self, tmp: str) -> tuple[Path, Path, Path, dict]:
        root = Path(tmp) / ".codex-loop"
        shutil.copytree(EXAMPLE, root)
        current = json.loads((root / "loop_spec.json").read_text(encoding="utf-8"))
        proposed = copy.deepcopy(current)
        proposed["output_binding"]["language"] = "zh-CN"
        proposed_path = Path(tmp) / "proposed_loop_spec.json"
        proposed_path.write_text(json.dumps(proposed, indent=2) + "\n", encoding="utf-8")
        proposed_digest = canonical_json_digest(proposed)
        manifest = json.loads((root / "agent_manifest.json").read_text(encoding="utf-8"))
        proposal = {
            "schema_version": "1.0.0",
            "proposal_id": "proposal:" + proposed_digest.removeprefix("sha256:"),
            "base_config_version": manifest["configuration_binding"]["config_version"],
            "base_loop_spec_digest": canonical_json_digest(current),
            "proposed_loop_spec_digest": proposed_digest,
            "approval": {
                "status": "approved",
                "approved_proposal_id": "proposal:" + proposed_digest.removeprefix("sha256:"),
                "approved_digest": proposed_digest,
                "explicit_user_go": True,
            },
        }
        proposal_path = Path(tmp) / "replan_proposal.json"
        proposal_path.write_text(json.dumps(proposal, indent=2) + "\n", encoding="utf-8")
        return root, proposed_path, proposal_path, proposal

    def test_exact_approved_preview_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root, proposed, proposal, _ = self.fixture(tmp)
            validate_replan(root, proposed, proposal)

    def test_substituted_proposed_spec_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root, proposed_path, proposal_path, _ = self.fixture(tmp)
            proposed = json.loads(proposed_path.read_text(encoding="utf-8"))
            proposed["output_binding"]["language"] = "fr"
            proposed_path.write_text(json.dumps(proposed), encoding="utf-8")
            with self.assertRaisesRegex(ReplanValidationError, "differs from preview"):
                validate_replan(root, proposed_path, proposal_path)

    def test_stale_base_version_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root, proposed_path, proposal_path, proposal = self.fixture(tmp)
            proposal["base_config_version"] += 1
            proposal_path.write_text(json.dumps(proposal), encoding="utf-8")
            with self.assertRaisesRegex(ReplanValidationError, "base config version is stale"):
                validate_replan(root, proposed_path, proposal_path)

    def test_approval_for_different_digest_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root, proposed_path, proposal_path, proposal = self.fixture(tmp)
            proposal["approval"]["approved_digest"] = "sha256:" + "0" * 64
            proposal_path.write_text(json.dumps(proposal), encoding="utf-8")
            with self.assertRaisesRegex(ReplanValidationError, "different LoopSpec digest"):
                validate_replan(root, proposed_path, proposal_path)


if __name__ == "__main__":
    unittest.main()
