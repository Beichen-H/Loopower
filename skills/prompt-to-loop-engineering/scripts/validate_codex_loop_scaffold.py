#!/usr/bin/env python3
"""Validate a static Codex-native .codex-loop scaffold."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from governance_contracts import (
    SHA256_RE,
    canonical_json_digest,
    validate_core_loop_governance,
    validate_output_binding,
    validate_passed_path_evaluators,
    validate_safe_agent_id as validate_shared_safe_agent_id,
)


STAGE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@-]*$")
FORBIDDEN_NAMES = {
    "runtime", "state.json", "checkpoint.json", "checkpoints", "queue",
    "queues", "database", "db",
}
REQUIRED_FILES = ["loop_spec.json", "agent_manifest.json", "guardrails.json"]
ALIGNMENT_FIELDS = (
    "id", "display_name", "specialization", "governance_role", "rationale",
    "activation_policy", "activation_nodes", "allowed_tools",
)


class ScaffoldValidationError(AssertionError):
    """Raised when a scaffold violates the static contract."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ScaffoldValidationError(f"missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ScaffoldValidationError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ScaffoldValidationError(f"{path} must contain a JSON object")
    return payload


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ScaffoldValidationError(message)


def validate_safe_agent_id(agent_id: str) -> None:
    try:
        validate_shared_safe_agent_id(agent_id, require, "agent id")
    except ScaffoldValidationError as exc:
        raise ScaffoldValidationError(f"unsafe agent id: {agent_id!r}; {exc}") from exc


def canonical_prompt_path(agent_id: str) -> str:
    validate_safe_agent_id(agent_id)
    return f".codex-loop/subagents/{agent_id}.md"


def validate_required_files(root: Path) -> None:
    for relative in REQUIRED_FILES:
        require((root / relative).is_file(), f"missing required scaffold file: {relative}")


def validate_no_runtime_artifacts(root: Path) -> None:
    for path in root.rglob("*"):
        if path.name.casefold() in FORBIDDEN_NAMES or path.suffix.lower() in {".sqlite", ".db"}:
            raise ScaffoldValidationError(f"forbidden runtime artifact: {path.relative_to(root).as_posix()}")


def _objects(value: Any, path: str) -> list[dict[str, Any]]:
    require(isinstance(value, list), f"{path} must be an array")
    require(all(isinstance(item, dict) for item in value), f"{path} entries must be objects")
    return value


def _tool_modes(loop_spec: dict[str, Any]) -> dict[str, str]:
    runtime = loop_spec.get("runtime_binding")
    require(isinstance(runtime, dict), "loop_spec.runtime_binding must be present")
    snapshot = runtime.get("capabilities_snapshot")
    required = runtime.get("required_capabilities")
    require(isinstance(snapshot, dict), "capabilities_snapshot must be an object")
    require(isinstance(required, dict), "required_capabilities must be an object")
    tools = snapshot.get("available_tools")
    modes = snapshot.get("tool_access_modes")
    require(isinstance(tools, list), "capabilities_snapshot.available_tools must be an array")
    require(isinstance(modes, dict), "capabilities_snapshot.tool_access_modes must be an object")
    require(set(modes) == set(tools), "capabilities_snapshot tool modes must classify every available tool")
    require(all(mode in {"read_only", "workspace_write", "external_write"} for mode in modes.values()), "invalid capability permission mode")
    required_tools = required.get("available_tools", [])
    required_modes = required.get("tool_access_modes", {})
    require(set(required_tools) <= set(tools), "required tools must be available")
    require(all(modes.get(name) == mode for name, mode in required_modes.items()), "required tool permission modes must match capability snapshot")
    return modes


def _node_map(loop_spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    control_flow = loop_spec.get("control_flow")
    require(isinstance(control_flow, dict), "loop_spec.control_flow must be present")
    nodes = _objects(control_flow.get("nodes"), "loop_spec.control_flow.nodes")
    result: dict[str, dict[str, Any]] = {}
    for node in nodes:
        node_id = node.get("id")
        require(isinstance(node_id, str) and node_id, "node id is required")
        require(node_id not in result, f"duplicate node id: {node_id}")
        result[node_id] = node
    return result


def _reachable_nodes(loop_spec: dict[str, Any], nodes: dict[str, dict[str, Any]]) -> set[str]:
    control_flow = loop_spec["control_flow"]
    entry = control_flow.get("entry_node")
    require(entry in nodes, f"unknown entry node: {entry!r}")
    adjacency = {node_id: [] for node_id in nodes}
    for edge in _objects(control_flow.get("edges", []), "loop_spec.control_flow.edges"):
        source, target = edge.get("from"), edge.get("to")
        require(source in nodes and target in nodes, f"edge references unknown node: {source!r} -> {target!r}")
        adjacency[source].append(target)
    reachable, pending = set(), [entry]
    while pending:
        node_id = pending.pop()
        if node_id not in reachable:
            reachable.add(node_id)
            pending.extend(adjacency[node_id])
    return reachable


def validate_loop_spec(loop_spec: dict[str, Any]) -> None:
    governance = loop_spec.get("execution_governance")
    require(isinstance(governance, dict), "loop_spec.execution_governance must be present")
    require(governance.get("runtime_mode") == "COOPERATIVE_GOVERNANCE", "execution_governance.runtime_mode must be COOPERATIVE_GOVERNANCE")
    require(governance.get("scheduler") == "codex_loop_dag", "execution_governance.scheduler must be codex_loop_dag")
    require(governance.get("inline_execution_policy") == "forbidden_for_subagent_nodes", "execution_governance.inline_execution_policy must be forbidden_for_subagent_nodes")
    modes = _tool_modes(loop_spec)
    nodes = _node_map(loop_spec)
    for node in nodes.values():
        for tool in node.get("allowed_tools", []):
            require(tool in modes, f"node {node['id']} uses undeclared tool: {tool}")
        if node.get("role") in {"reviewer", "verifier"}:
            non_read_only = [tool for tool in node.get("allowed_tools", []) if modes[tool] != "read_only"]
            require(not non_read_only, f"reviewer/verifier node {node['id']!r} has non-read-only tools: {non_read_only}")
    snapshot = loop_spec["runtime_binding"]["capabilities_snapshot"]
    required = loop_spec["runtime_binding"]["required_capabilities"]
    require(snapshot.get("subagents") is True, "live agent registry requires subagents=true")
    require(required.get("subagents") is True, "live agent registry requires required subagents=true")
    require(snapshot.get("required_subagent_reasoning_intensity") == "extended_thought", "capabilities_snapshot.required_subagent_reasoning_intensity must be extended_thought")
    require(required.get("required_subagent_reasoning_intensity") == "extended_thought", "required_capabilities.required_subagent_reasoning_intensity must be extended_thought")


def validate_manifest_loop_alignment(manifest: dict[str, Any], loop_spec: dict[str, Any]) -> None:
    manifest_agents = _objects(manifest.get("subagents"), "agent_manifest.subagents")
    delegation = loop_spec.get("delegation")
    require(isinstance(delegation, dict), "loop_spec.delegation must be an object")
    registry_agents = _objects(delegation.get("agent_registry"), "loop_spec.delegation.agent_registry")
    nodes = _node_map(loop_spec)
    reachable = _reachable_nodes(loop_spec, nodes)
    modes = _tool_modes(loop_spec)

    folded: dict[str, str] = {}
    assignments: dict[str, str] = {}
    manifest_by_id: dict[str, dict[str, Any]] = {}
    for agent in manifest_agents:
        agent_id = agent.get("id")
        require(isinstance(agent_id, str) and agent_id, "subagent.id is required")
        folded_id = agent_id.casefold()
        if folded_id in folded:
            raise ScaffoldValidationError(
                f"case-folding collision between agent ids: {folded[folded_id]!r} and {agent_id!r}"
            )
        folded[folded_id] = agent_id
        validate_safe_agent_id(agent_id)
        require(agent_id not in manifest_by_id, f"duplicate subagent id: {agent_id}")
        manifest_by_id[agent_id] = agent
        expected_path = canonical_prompt_path(agent_id)
        require(agent.get("prompt_path") == expected_path, f"subagent {agent_id} prompt_path must equal canonical prompt path {expected_path}")
        for node_id in agent.get("activation_nodes", []):
            require(node_id not in assignments, f"activation node {node_id!r} is assigned to multiple agents")
            assignments[node_id] = agent_id
        for tool in agent.get("allowed_tools", []):
            require(tool in modes, f"subagent {agent_id} uses undeclared tool: {tool}")

        if agent.get("governance_role") in {"reviewer", "verifier"}:
            non_read_only = [
                tool for tool in agent.get("allowed_tools", [])
                if modes[tool] != "read_only"
            ]
            require(
                not non_read_only,
                f"reviewer/verifier agent {agent_id!r} has non-read-only tools: {non_read_only}",
            )

    registry_by_id: dict[str, dict[str, Any]] = {}
    registry_folded: dict[str, str] = {}
    for agent in registry_agents:
        agent_id = agent.get("id")
        require(isinstance(agent_id, str) and agent_id, "registry agent id is required")
        validate_safe_agent_id(agent_id)
        require(agent_id not in registry_by_id, f"duplicate registry agent id: {agent_id}")
        folded_id = agent_id.casefold()
        if folded_id in registry_folded:
            raise ScaffoldValidationError(
                f"case-folding collision between registry agent ids: "
                f"{registry_folded[folded_id]!r} and {agent_id!r}"
            )
        registry_folded[folded_id] = agent_id
        registry_by_id[agent_id] = agent

    require(
        len(manifest_agents) == len(registry_agents),
        "Manifest and LoopSpec agent registry cardinality mismatch",
    )
    require(set(manifest_by_id) == set(registry_by_id), "Manifest and LoopSpec agent identities disagree")
    for agent_id, manifest_agent in manifest_by_id.items():
        registry_agent = registry_by_id[agent_id]
        for field in ALIGNMENT_FIELDS:
            label = "activation node" if field == "activation_nodes" else field
            require(manifest_agent.get(field) == registry_agent.get(field), f"Manifest/LoopSpec {label} disagreement for agent {agent_id}")
        require(registry_agent.get("prompt_ref") == manifest_agent.get("prompt_path"), f"Manifest/LoopSpec prompt reference disagreement for agent {agent_id}")
        for node_id in manifest_agent.get("activation_nodes", []):
            require(node_id in nodes, f"agent {agent_id} activation node is unknown: {node_id}")
            require(node_id in reachable, f"agent {agent_id} activation node is unreachable: {node_id}")
            node = nodes[node_id]
            require(node.get("agent_ref") == agent_id, f"activation node {node_id} does not bind agent {agent_id}")
            require(node.get("role") == manifest_agent.get("governance_role"), f"node/agent governance_role disagreement for {agent_id}")
            require(set(node.get("allowed_tools", [])) <= set(manifest_agent.get("allowed_tools", [])), f"node {node_id} tools exceed agent {agent_id} tools")

    for node in nodes.values():
        agent_ref = node.get("agent_ref")
        if agent_ref is not None:
            require(agent_ref in manifest_by_id, f"node {node['id']} references undeclared agent {agent_ref}")
            require(assignments.get(node["id"]) == agent_ref, f"node {node['id']} is not an activation node for {agent_ref}")

    if any(agent.get("governance_role") == "implementer" for agent in manifest_agents):
        evaluator_agents = {
            node.get("agent_ref") for node_id, node in nodes.items()
            if node_id in reachable and node.get("kind") != "terminal" and node.get("role") in {"reviewer", "verifier"}
        }
        implementer_ids = {agent["id"] for agent in manifest_agents if agent.get("governance_role") == "implementer"}
        require(bool(evaluator_agents - implementer_ids - {None}), "implementer requires a reachable non-terminal reviewer/verifier with an independent agent_ref")


def validate_manifest(root: Path, manifest: dict[str, Any], loop_spec: dict[str, Any]) -> None:
    require(manifest.get("schema_version") == "3.0.0", "agent_manifest.schema_version must be 3.0.0")
    host = manifest.get("codex_host")
    require(isinstance(host, dict) and host.get("executor") == "codex", "agent_manifest.codex_host.executor must be codex")
    require(host.get("independent_runtime_engine") is False, "agent_manifest must set independent_runtime_engine=false")
    loop_binding = manifest.get("loop_binding")
    require(isinstance(loop_binding, dict), "agent_manifest.loop_binding must be an object")
    require(loop_binding.get("loop_spec_path") == ".codex-loop/loop_spec.json", "invalid loop_spec_path")
    require(loop_binding.get("status_path") == ".codex-loop/.status", "invalid status_path")
    require(manifest.get("guardrails_ref") == ".codex-loop/guardrails.json", "invalid guardrails_ref")
    overlay = manifest.get("governance_overlay")
    require(isinstance(overlay, dict), "agent_manifest.governance_overlay must be an object")
    require(overlay.get("host_linear_fulfillment_takeover") == "forbidden", "host linear fulfillment takeover must be forbidden")
    validate_manifest_loop_alignment(manifest, loop_spec)

    declared = {agent["prompt_path"] for agent in manifest["subagents"]}
    actual = {f".codex-loop/{path.relative_to(root).as_posix()}" for path in (root / "subagents").glob("*.md")}
    for prompt_path in declared:
        require((root / Path(prompt_path).relative_to(".codex-loop")).is_file(), f"missing subagent prompt: {prompt_path}")
    undeclared = sorted(actual - declared)
    if undeclared:
        raise ScaffoldValidationError(f"undeclared subagent prompt: {undeclared[0]}")

    manifest_modes: dict[str, str] = {}
    for binding in _objects(manifest.get("tool_bindings"), "agent_manifest.tool_bindings"):
        name, mode = binding.get("name"), binding.get("permission_mode")
        require(isinstance(name, str) and name not in manifest_modes, f"duplicate or invalid Manifest tool binding: {name!r}")
        manifest_modes[name] = mode
    loop_modes = _tool_modes(loop_spec)
    require(manifest_modes == loop_modes, "Manifest/LoopSpec tool permission mode disagreement")


def validate_configuration_binding(root: Path, manifest: dict[str, Any], loop_spec: dict[str, Any]) -> None:
    """Bind the approved scaffold and GO preflight to one immutable config version."""
    configuration = manifest.get("configuration_binding")
    require(isinstance(configuration, dict), "agent_manifest.configuration_binding must be an object")
    version = configuration.get("config_version") if isinstance(configuration, dict) else None
    digest = configuration.get("loop_spec_digest") if isinstance(configuration, dict) else None
    require(isinstance(version, int) and not isinstance(version, bool) and version >= 1, "configuration_binding.config_version must be a positive integer")
    require(isinstance(digest, str) and SHA256_RE.fullmatch(digest) is not None, "configuration_binding.loop_spec_digest must be a sha256 digest")
    require(digest == canonical_json_digest(loop_spec), "configuration_binding.loop_spec_digest does not match loop_spec.json")
    require(configuration.get("approval_source") == "explicit_user_go", "configuration_binding.approval_source must be explicit_user_go")
    require(configuration.get("capability_preflight_ref") == ".codex-loop/evidence/preflight/go-preflight.json", "configuration_binding.capability_preflight_ref is invalid")
    preflight = load_json(root / "evidence" / "preflight" / "go-preflight.json")
    require(preflight.get("schema_version") == "1.0.0", "GO preflight schema_version must be 1.0.0")
    require(preflight.get("evidence_type") == "go_capability_preflight", "invalid GO preflight evidence_type")
    require(preflight.get("config_version") == version, "GO preflight config_version mismatch")
    require(preflight.get("loop_spec_digest") == digest, "GO preflight loop_spec_digest mismatch")
    require(preflight.get("status") == "passed", "GO capability preflight must pass before activation")
    require(preflight.get("capability_drift") == [], "GO capability preflight detected capability drift")
    capabilities = loop_spec["runtime_binding"]["capabilities_snapshot"]
    require(preflight.get("observed_capabilities") == capabilities, "GO preflight observed capabilities must exactly match the approved capability snapshot")

    checked_at = preflight.get("checked_at")
    require(isinstance(checked_at, str) and bool(checked_at), "GO preflight checked_at must be a non-empty ISO 8601 timestamp")
    try:
        parsed_checked_at = datetime.fromisoformat(checked_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ScaffoldValidationError("GO preflight checked_at must be a valid ISO 8601 timestamp") from exc
    require(
        "T" in checked_at and parsed_checked_at.tzinfo is not None,
        "GO preflight checked_at must include time and UTC offset",
    )

    discovery = preflight.get("lifecycle_discovery")
    require(isinstance(discovery, dict), "GO preflight lifecycle_discovery must be an object")
    require(
        discovery.get("keywords") == ["spawn_agent", "spawn_subagent", "subagent", "multi_agent"],
        "GO preflight lifecycle discovery must use the mandatory host API keywords",
    )
    if capabilities.get("subagents") is True:
        require(
            discovery.get("result") == "host_native_lifecycle_tool_found",
            "subagents=true requires successful GO-time host lifecycle discovery",
        )
        require(
            isinstance(discovery.get("host_api"), str) and bool(discovery["host_api"].strip()),
            "subagents=true requires a non-empty discovered host lifecycle API",
        )
    else:
        require(
            discovery.get("result") == "no_host_native_lifecycle_tool_found" and discovery.get("host_api") is None,
            "subagents=false requires explicit no-host-lifecycle-tool evidence",
        )


def validate_guardrails(guardrails: dict[str, Any]) -> None:
    require(guardrails.get("schema_version") == "1.0.0", "guardrails.schema_version must be 1.0.0")
    for key in ("forbidden_commands", "write_boundaries", "approval_required_actions", "stop_conditions"):
        require(isinstance(guardrails.get(key), list), f"guardrails.{key} must be an array")
    require(bool(guardrails["stop_conditions"]), "guardrails.stop_conditions must not be empty")


def validate_status(root: Path, loop_spec: dict[str, Any]) -> None:
    status = root / ".status"
    if not status.exists():
        return
    lines = [line.strip() for line in status.read_text(encoding="utf-8").splitlines() if line.strip()]
    require(len(lines) == 1, ".status must contain exactly one stage id")
    require(bool(STAGE_ID_RE.fullmatch(lines[0])), f"invalid .status stage id: {lines[0]!r}")
    require(lines[0] in _node_map(loop_spec), f".status references unknown node id: {lines[0]}")


def validate_scaffold(root: Path) -> None:
    root = root.resolve()
    require(root.is_dir(), f"scaffold directory not found: {root}")
    require(root.name in {".codex-loop", "codex-loop"}, "scaffold directory must be named .codex-loop")
    validate_no_runtime_artifacts(root)
    validate_required_files(root)
    loop_spec = load_json(root / "loop_spec.json")
    manifest = load_json(root / "agent_manifest.json")
    guardrails = load_json(root / "guardrails.json")
    validate_loop_spec(loop_spec)
    validate_manifest(root, manifest, loop_spec)
    validate_core_loop_governance(loop_spec, require)
    validate_output_binding(loop_spec, require)
    validate_passed_path_evaluators(loop_spec, require)
    validate_guardrails(guardrails)
    validate_status(root, loop_spec)
    validate_configuration_binding(root, manifest, loop_spec)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: validate_codex_loop_scaffold.py path/to/.codex-loop", file=sys.stderr)
        return 2
    try:
        validate_scaffold(Path(argv[1]))
    except ScaffoldValidationError as exc:
        print(f"ERROR: Scaffold Error: {exc}")
        return 1
    print("OK: Codex loop scaffold validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
