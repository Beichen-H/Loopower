#!/usr/bin/env python3
"""Post-hoc validation for evidence-locked Codex DAG execution.

This validator checks files produced by a Codex-native `.codex-loop/` scaffold
after GO-phase work has begun. It does not run the loop, call tools, spawn
agents, or emulate a Runtime Engine. It only verifies that the persisted
execution evidence required by the scaffold is present and internally
consistent.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


EXPECTED_RUNTIME_MODE = "COOPERATIVE_GOVERNANCE"
EXPECTED_SCHEDULER = "codex_loop_dag"
EXPECTED_INLINE_POLICY = "forbidden_for_subagent_nodes"
EXPECTED_ATOMIC_ROLE = "node_scoped_atomic_capability"
EXPECTED_REASONING = "extended_thought"


class EvidenceValidationError(AssertionError):
    """Raised when execution evidence violates the static governance contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceValidationError(message)


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise EvidenceValidationError(f"missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise EvidenceValidationError(f"invalid JSON in {path}: {exc}") from exc
    require(isinstance(payload, dict), f"{path} must contain a JSON object")
    return payload


def localize_codex_loop_ref(root: Path, ref: str) -> Path:
    require(isinstance(ref, str) and ref, "required evidence ref must be a non-empty string")
    require(not Path(ref).is_absolute(), f"evidence ref must be relative: {ref}")
    require(".." not in Path(ref).parts, f"evidence ref must not escape scaffold: {ref}")
    prefix = ".codex-loop/"
    require(ref.startswith(prefix), f"evidence ref must start with {prefix}: {ref}")
    return root / ref.removeprefix(prefix)


def validate_loop_governance(loop_spec: dict[str, Any]) -> None:
    governance = loop_spec.get("execution_governance")
    require(isinstance(governance, dict), "loop_spec.execution_governance must be present")
    require(
        governance.get("runtime_mode") == EXPECTED_RUNTIME_MODE,
        "execution_governance.runtime_mode must be COOPERATIVE_GOVERNANCE",
    )
    require(
        governance.get("scheduler") == EXPECTED_SCHEDULER,
        "execution_governance.scheduler must be codex_loop_dag",
    )
    require(
        governance.get("inline_execution_policy") == EXPECTED_INLINE_POLICY,
        "execution_governance.inline_execution_policy must be forbidden_for_subagent_nodes",
    )
    required_evidence = governance.get("required_evidence")
    require(isinstance(required_evidence, dict), "execution_governance.required_evidence must be an object")
    for evidence_type in ["activation", "handoff", "completion"]:
        require(
            required_evidence.get(evidence_type) is True,
            f"execution_governance.required_evidence.{evidence_type} must be true",
        )
    plugins = governance.get("linear_fulfillment_plugins")
    require(isinstance(plugins, dict), "execution_governance.linear_fulfillment_plugins must be an object")
    require(
        plugins.get("scheduler_takeover") == "forbidden",
        "linear_fulfillment_plugins.scheduler_takeover must be forbidden",
    )
    require(
        plugins.get("allowed_role") == EXPECTED_ATOMIC_ROLE,
        "linear_fulfillment_plugins.allowed_role must be node_scoped_atomic_capability",
    )


def validate_manifest_overlay(manifest: dict[str, Any]) -> list[str]:
    overlay = manifest.get("governance_overlay")
    require(isinstance(overlay, dict), "agent_manifest.governance_overlay must be present")
    require(
        overlay.get("runtime_mode") == EXPECTED_RUNTIME_MODE,
        "governance_overlay.runtime_mode must be COOPERATIVE_GOVERNANCE",
    )
    require(
        overlay.get("dag_scheduler_owner") == "prompt-to-loop-engineering",
        "governance_overlay.dag_scheduler_owner must be prompt-to-loop-engineering",
    )
    require(
        overlay.get("host_linear_fulfillment_takeover") == "forbidden",
        "governance_overlay.host_linear_fulfillment_takeover must be forbidden",
    )
    require(
        overlay.get("specialized_skills_policy") == "node_scoped_atomic_capabilities",
        "governance_overlay.specialized_skills_policy must be node_scoped_atomic_capabilities",
    )
    require(
        overlay.get("evidence_root") == ".codex-loop/evidence",
        "governance_overlay.evidence_root must be .codex-loop/evidence",
    )
    refs = overlay.get("required_evidence_refs")
    require(isinstance(refs, list) and refs, "governance_overlay.required_evidence_refs must be a non-empty array")
    require(all(isinstance(ref, str) for ref in refs), "all required_evidence_refs must be strings")
    require(len(refs) == len(set(refs)), "governance_overlay.required_evidence_refs must be unique")
    return refs


def subagent_nodes(manifest: dict[str, Any]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for subagent in manifest.get("subagents", []):
        subagent_id = subagent.get("id")
        for node_id in subagent.get("activation_nodes", []):
            require(
                node_id not in mapping,
                f"node {node_id!r} is assigned to multiple subagents",
            )
            mapping[node_id] = subagent_id
    return mapping


def validate_activation(path: Path, evidence: dict[str, Any], owned_nodes: dict[str, str]) -> None:
    require(evidence.get("evidence_type") == "activation", f"{path}: evidence_type must be activation")
    require(evidence.get("status") == "activated", f"{path}: status must be activated")
    node_id = evidence.get("node_id")
    subagent_id = evidence.get("subagent_id")
    require(isinstance(node_id, str) and node_id, f"{path}: node_id is required")
    require(isinstance(subagent_id, str) and subagent_id, f"{path}: subagent_id is required")
    require(
        owned_nodes.get(node_id) == subagent_id,
        f"{path}: subagent_id does not match manifest activation_nodes for node {node_id!r}",
    )
    model_config = evidence.get("model_config")
    require(isinstance(model_config, dict), f"{path}: model_config is required")
    require(
        model_config.get("reasoning_intensity") == EXPECTED_REASONING,
        f"{path}: reasoning_intensity must be extended_thought",
    )
    require(model_config.get("inherit_parent") is True, f"{path}: inherit_parent must be true")
    require(model_config.get("degraded") is False, f"{path}: degraded must be false")


def validate_completion(path: Path, evidence: dict[str, Any], owned_nodes: dict[str, str]) -> None:
    require(evidence.get("evidence_type") == "completion", f"{path}: evidence_type must be completion")
    require(evidence.get("status") in {"completed", "blocked", "stopped"}, f"{path}: invalid completion status")
    node_id = evidence.get("node_id")
    require(isinstance(node_id, str) and node_id, f"{path}: node_id is required")
    if node_id in owned_nodes:
        expected_subagent = owned_nodes[node_id]
        require(
            evidence.get("subagent_id") == expected_subagent,
            f"{path}: inline completion is forbidden for subagent node {node_id!r}; expected subagent_id {expected_subagent!r}",
        )
    require(
        evidence.get("inline_fulfillment") is False,
        f"{path}: inline_fulfillment must be false under forbidden_for_subagent_nodes",
    )


def validate_handoff(path: Path, evidence: dict[str, Any]) -> None:
    require(evidence.get("evidence_type") == "handoff", f"{path}: evidence_type must be handoff")
    require(evidence.get("status") == "handoff_ready", f"{path}: status must be handoff_ready")
    require(isinstance(evidence.get("from_node"), str) and evidence["from_node"], f"{path}: from_node is required")
    require(isinstance(evidence.get("to_node"), str) and evidence["to_node"], f"{path}: to_node is required")
    require(
        evidence["from_node"] != evidence["to_node"],
        f"{path}: handoff from_node and to_node must differ",
    )


def validate_evidence_file(path: Path, owned_nodes: dict[str, str]) -> None:
    require(path.is_file(), f"missing required evidence file: {path.as_posix()}")
    evidence = load_json(path)
    evidence_type = evidence.get("evidence_type")
    if evidence_type == "activation":
        validate_activation(path, evidence, owned_nodes)
    elif evidence_type == "completion":
        validate_completion(path, evidence, owned_nodes)
    elif evidence_type == "handoff":
        validate_handoff(path, evidence)
    else:
        raise EvidenceValidationError(f"{path}: unknown evidence_type {evidence_type!r}")


def validate_evidence(root: Path) -> None:
    root = root.resolve()
    require(root.is_dir(), f"scaffold directory not found: {root}")
    require(root.name in {".codex-loop", "codex-loop"}, "scaffold directory must be named .codex-loop")

    loop_spec = load_json(root / "loop_spec.json")
    manifest = load_json(root / "agent_manifest.json")
    validate_loop_governance(loop_spec)
    required_refs = validate_manifest_overlay(manifest)
    owned_nodes = subagent_nodes(manifest)
    for ref in required_refs:
        validate_evidence_file(localize_codex_loop_ref(root, ref), owned_nodes)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: validate_dag_execution_evidence.py path/to/.codex-loop", file=sys.stderr)
        return 2
    try:
        validate_evidence(Path(argv[1]))
    except EvidenceValidationError as exc:
        print(f"ERROR: DAG Evidence Error: {exc}")
        return 1
    print("OK: DAG execution evidence validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
