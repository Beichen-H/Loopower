"""Shared pure checks for LoopSpec-owned execution governance."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from typing import Any


Require = Callable[[bool, str], None]
AGENT_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
WINDOWS_DEVICE_NAMES = {
    "con", "prn", "aux", "nul", "clock$",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}
TERMINAL_STATUSES = {
    "passed", "failed", "blocked", "needs_approval", "stopped", "cancelled"
}
HARD_LIMIT_IDS = {
    "max_runtime_seconds", "max_iterations", "max_token_budget",
    "max_no_progress_loops",
}
HARD_STOP_PRECEDENCE = [
    "policy_violation", "user_interrupt", "max_runtime_seconds",
    "max_iterations", "max_token_budget", "max_no_progress_loops",
]
EDGE_SELECTION_POLICY = {
    "priority_order": "lower_first",
    "match_policy": "first_match",
    "equal_priority": "require_explicit_tie_breaker",
}
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def canonical_json_digest(value: Any) -> str:
    """Return a stable digest for one JSON-compatible contract value."""
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def validate_output_binding(loop_spec: dict[str, Any], require: Require) -> None:
    """Require a non-controller primary deliverable before a passed terminal."""
    binding = loop_spec.get("output_binding")
    require(isinstance(binding, dict), "loop_spec.output_binding must be present")
    if not isinstance(binding, dict):
        return
    required = {
        "producer_node", "state_field", "format", "language",
        "non_empty_before_passed",
    }
    require(set(binding) == required, f"output_binding must define exactly {sorted(required)}")
    producer = binding.get("producer_node")
    state_field = binding.get("state_field")
    require(isinstance(producer, str) and producer, "output_binding.producer_node is required")
    require(isinstance(state_field, str) and state_field, "output_binding.state_field is required")
    require(isinstance(binding.get("format"), str) and binding["format"], "output_binding.format is required")
    require(isinstance(binding.get("language"), str) and binding["language"], "output_binding.language is required")
    require(binding.get("non_empty_before_passed") is True, "output_binding.non_empty_before_passed must be true")

    state = loop_spec.get("state")
    require(isinstance(state, dict), "loop_spec.state must be present for output binding")
    schema = state.get("schema") if isinstance(state, dict) else None
    controller_fields = state.get("controller_owned_fields") if isinstance(state, dict) else None
    require(isinstance(schema, dict), "loop_spec.state.schema must be an object")
    require(isinstance(controller_fields, list), "loop_spec.state.controller_owned_fields must be an array")
    if isinstance(schema, dict) and isinstance(state_field, str):
        require(state_field in schema, f"output_binding.state_field {state_field!r} is undefined")
    if isinstance(controller_fields, list):
        require(state_field not in controller_fields, "output_binding cannot reference controller-owned state")

    nodes = loop_spec.get("control_flow", {}).get("nodes", [])
    node_map = {
        item.get("id"): item for item in nodes
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    require(producer in node_map, f"output_binding producer node {producer!r} is undefined")
    if producer in node_map:
        write_scope = node_map[producer].get("state_write_scope")
        if write_scope is not None:
            require(isinstance(write_scope, list), f"producer node {producer!r} state_write_scope must be an array")
            if isinstance(write_scope, list):
                require(state_field in write_scope, f"producer node {producer!r} does not write output field {state_field!r}")
    passed = loop_spec.get("control_flow", {}).get("terminal_nodes", {}).get("passed")
    require(isinstance(passed, list) and bool(passed), "output_binding requires at least one passed terminal")


def validate_passed_path_evaluators(
    loop_spec: dict[str, Any],
    require: Require,
    *,
    mandatory_criterion_ids: set[str] | None = None,
) -> None:
    """Require every mandatory evaluator to dominate all entry-to-passed paths."""
    control_flow = loop_spec.get("control_flow")
    evaluation = loop_spec.get("evaluation")
    require(isinstance(control_flow, dict), "loop_spec.control_flow must be present")
    require(isinstance(evaluation, dict), "loop_spec.evaluation must be present")
    if not isinstance(control_flow, dict) or not isinstance(evaluation, dict):
        return
    nodes = control_flow.get("nodes")
    edges = control_flow.get("edges")
    bindings = evaluation.get("criteria_bindings")
    require(isinstance(nodes, list), "control_flow.nodes must be an array")
    require(isinstance(edges, list), "control_flow.edges must be an array")
    require(isinstance(bindings, list), "evaluation.criteria_bindings must be an array")
    if not isinstance(nodes, list) or not isinstance(edges, list) or not isinstance(bindings, list):
        return
    node_ids = {item.get("id") for item in nodes if isinstance(item, dict)}
    entry = control_flow.get("entry_node")
    passed = set(control_flow.get("terminal_nodes", {}).get("passed", []))
    adjacency: dict[str, list[str]] = {}
    for edge in edges:
        if isinstance(edge, dict):
            adjacency.setdefault(edge.get("from"), []).append(edge.get("to"))
    for index, binding in enumerate(bindings):
        require(isinstance(binding, dict), f"evaluation.criteria_bindings[{index}] must be an object")
        if not isinstance(binding, dict):
            continue
        criterion_id = binding.get("criterion_id")
        if mandatory_criterion_ids is not None and criterion_id not in mandatory_criterion_ids:
            continue
        evaluator = binding.get("evaluator_node")
        require(evaluator in node_ids, f"criterion {criterion_id!r} evaluator_node is undefined")
        if evaluator not in node_ids:
            continue
        if evaluator == entry:
            continue
        seen = {entry}
        pending = [entry]
        bypassed: set[str] = set()
        while pending:
            current = pending.pop()
            for target in adjacency.get(current, []):
                if target == evaluator or target in seen:
                    continue
                if target in passed:
                    bypassed.add(target)
                    continue
                seen.add(target)
                pending.append(target)
        require(
            not bypassed,
            f"mandatory criterion {criterion_id!r} evaluator {evaluator!r} can be bypassed on passed path(s) to {sorted(bypassed)}",
        )


def validate_safe_agent_id(agent_id: str, require: Require, path: str) -> None:
    """Reject unsafe or non-portable professional agent identifiers."""
    require(
        isinstance(agent_id, str) and AGENT_ID_RE.fullmatch(agent_id) is not None,
        f"{path} must be a safe lowercase ASCII professional id",
    )
    if isinstance(agent_id, str):
        require(
            agent_id.casefold() not in WINDOWS_DEVICE_NAMES,
            f"{path} uses a Windows reserved device name: {agent_id!r}",
        )


def validate_core_loop_governance(
    loop_spec: dict[str, Any],
    require: Require,
    *,
    expected_mode: str | None = None,
) -> None:
    """Validate the policy-authority split and deterministic stop surface."""
    architecture = loop_spec.get("architecture")
    declared_mode = architecture.get("mode") if isinstance(architecture, dict) else None
    mode = expected_mode if expected_mode is not None else declared_mode
    require(
        mode in {"workflow", "agent_loop"},
        "loop_spec architecture mode must be 'workflow' or 'agent_loop'",
    )

    termination = loop_spec.get("termination_control")
    require(isinstance(termination, dict), "loop_spec.termination_control must be present")
    if not isinstance(termination, dict):
        return
    require(
        termination.get("policy_authority") == "loop_spec",
        "LoopSpec must remain the policy authority; the Codex host may only evaluate and enforce it",
    )
    require(
        termination.get("evaluation_authority") == "codex_host_controller",
        "termination evaluation authority must be codex_host_controller",
    )
    require(
        termination.get("reviewer_authority") == "evidence_only",
        "reviewer authority must be evidence_only",
    )
    require(
        termination.get("transition_policy") == "lower_first_then_first_match",
        "termination transition_policy must be lower_first_then_first_match",
    )
    require(
        termination.get("hard_stop_precedence") == HARD_STOP_PRECEDENCE,
        f"termination_control.hard_stop_precedence must equal {HARD_STOP_PRECEDENCE}",
    )

    thresholds = loop_spec.get("threshold_register")
    require(isinstance(thresholds, list), "loop_spec.threshold_register must be an array")
    threshold_ids: set[str] = set()
    if isinstance(thresholds, list):
        for item in thresholds:
            require(isinstance(item, dict), "threshold_register entries must be objects")
            if not isinstance(item, dict):
                continue
            threshold_id = item.get("id")
            require(isinstance(threshold_id, str) and threshold_id, "threshold id is required")
            if not isinstance(threshold_id, str) or not threshold_id:
                continue
            require(threshold_id not in threshold_ids, f"duplicate threshold id: {threshold_id}")
            threshold_ids.add(threshold_id)
            if threshold_id in HARD_LIMIT_IDS:
                value = item.get("value")
                require(
                    isinstance(value, int) and not isinstance(value, bool) and value > 0,
                    f"hard-limit threshold {threshold_id!r} must be a positive integer",
                )
    if mode == "agent_loop":
        missing = sorted(HARD_LIMIT_IDS - threshold_ids)
        require(not missing, f"threshold_register missing hard-limit thresholds: {missing}")

    control_flow = loop_spec.get("control_flow")
    require(isinstance(control_flow, dict), "loop_spec.control_flow must be present")
    if not isinstance(control_flow, dict):
        return
    cycles = control_flow.get("cycles")
    require(isinstance(cycles, list), "control_flow.cycles must be an array")
    if mode == "workflow":
        require(not cycles, "workflow control_flow.cycles must be empty")
    require(
        control_flow.get("edge_selection_policy") == EDGE_SELECTION_POLICY,
        "edge_selection_policy must use lower_first, first_match, and explicit tie breakers",
    )
    nodes = control_flow.get("nodes")
    require(isinstance(nodes, list), "control_flow.nodes must be an array")
    node_map: dict[str, dict[str, Any]] = {}
    if isinstance(nodes, list):
        for node in nodes:
            require(isinstance(node, dict), "control_flow.nodes entries must be objects")
            if not isinstance(node, dict):
                continue
            node_id = node.get("id")
            require(isinstance(node_id, str) and node_id, "control_flow node id is required")
            if isinstance(node_id, str) and node_id:
                require(node_id not in node_map, f"duplicate node id: {node_id}")
                node_map[node_id] = node

    terminals = control_flow.get("terminal_nodes")
    require(isinstance(terminals, dict), "control_flow.terminal_nodes must be an object")
    mapped: set[str] = set()
    stopped: list[Any] = []
    if isinstance(terminals, dict):
        require(
            set(terminals) == TERMINAL_STATUSES,
            f"terminal_nodes must define exactly {sorted(TERMINAL_STATUSES)}",
        )
        for status, node_ids in terminals.items():
            require(isinstance(node_ids, list), f"terminal_nodes.{status} must be an array")
            if not isinstance(node_ids, list):
                continue
            for node_id in node_ids:
                require(node_id in node_map, f"terminal node {node_id!r} is undefined")
                require(node_id not in mapped, f"terminal node {node_id!r} maps to more than one status")
                mapped.add(node_id)
                if node_id in node_map:
                    require(node_map[node_id].get("kind") == "terminal", f"terminal node {node_id!r} must have kind='terminal'")
        terminal_kind_ids = {
            node_id for node_id, node in node_map.items() if node.get("kind") == "terminal"
        }
        require(mapped == terminal_kind_ids, "every terminal-kind node must map to exactly one terminal status")
        stopped = terminals.get("stopped", [])
        if mode == "agent_loop":
            require(isinstance(stopped, list) and bool(stopped), "hard stops require a mapped stopped terminal node")

    policy = loop_spec.get("transition_policy")
    require(isinstance(policy, dict), "loop_spec.transition_policy must be present")
    if not isinstance(policy, dict):
        return
    require(
        policy.get("decision_authority") == "codex_host_controller",
        "transition_policy.decision_authority must be codex_host_controller",
    )
    require(
        policy.get("controller_validation") == "required",
        "transition_policy.controller_validation must be required",
    )
    expected_proposal = "none" if mode == "workflow" else "model_proposal"
    require(
        policy.get("proposal_mode") == expected_proposal,
        f"{mode or 'agent_loop'} transition proposal_mode must be {expected_proposal!r}",
    )
    allowed_targets = policy.get("allowed_targets")
    require(isinstance(allowed_targets, list) and bool(allowed_targets), "transition_policy.allowed_targets must be a non-empty array")
    if isinstance(allowed_targets, list):
        for node_id in allowed_targets:
            require(node_id in node_map, f"transition_policy allowed target {node_id!r} is undefined")
    fallback = policy.get("fallback_node")
    require(fallback in node_map, "transition_policy.fallback_node is undefined")
    if mode == "agent_loop":
        require(fallback in stopped, "transition_policy.fallback_node must map to terminal_nodes.stopped")
