#!/usr/bin/env python3
"""Validate that an approved replan is exactly the preview the user approved."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from governance_contracts import SHA256_RE, canonical_json_digest


class ReplanValidationError(AssertionError):
    """Raised when a replan proposal is stale, substituted, or unapproved."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReplanValidationError(message)


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReplanValidationError(f"cannot read valid JSON from {path}: {exc}") from exc
    require(isinstance(value, dict), f"{path} must contain a JSON object")
    return value


def validate_replan(root: Path, proposed_path: Path, proposal_path: Path) -> None:
    root = root.resolve()
    current = load_json(root / "loop_spec.json")
    manifest = load_json(root / "agent_manifest.json")
    proposed = load_json(proposed_path.resolve())
    proposal = load_json(proposal_path.resolve())
    binding = manifest.get("configuration_binding")
    require(isinstance(binding, dict), "manifest configuration_binding is required")

    current_digest = canonical_json_digest(current)
    proposed_digest = canonical_json_digest(proposed)
    require(proposal.get("schema_version") == "1.0.0", "replan proposal schema_version must be 1.0.0")
    require(proposal.get("base_config_version") == binding.get("config_version"), "replan proposal base config version is stale")
    require(proposal.get("base_loop_spec_digest") == current_digest, "replan proposal base LoopSpec is stale")
    require(binding.get("loop_spec_digest") == current_digest, "manifest LoopSpec digest is stale")
    require(proposal.get("proposed_loop_spec_digest") == proposed_digest, "proposed LoopSpec differs from preview digest")
    proposal_id = proposal.get("proposal_id")
    require(isinstance(proposal_id, str) and proposal_id == f"proposal:{proposed_digest.removeprefix('sha256:')}", "proposal_id must derive from the proposed LoopSpec digest")
    approval = proposal.get("approval")
    require(isinstance(approval, dict), "explicit replan approval is required")
    require(approval.get("status") == "approved", "replan proposal is not approved")
    require(approval.get("explicit_user_go") is True, "replan approval requires explicit user GO")
    require(approval.get("approved_proposal_id") == proposal_id, "approval references a different proposal")
    require(approval.get("approved_digest") == proposed_digest, "approval references a different LoopSpec digest")
    require(SHA256_RE.fullmatch(proposed_digest) is not None, "invalid proposed LoopSpec digest")


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print("Usage: validate_replan_proposal.py path/to/.codex-loop proposed_loop_spec.json replan_proposal.json", file=sys.stderr)
        return 2
    try:
        validate_replan(Path(argv[1]), Path(argv[2]), Path(argv[3]))
    except ReplanValidationError as exc:
        print(f"ERROR: Replan Validation Error: {exc}")
        return 1
    print("OK: approved replan proposal exactly matches the previewed LoopSpec.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
