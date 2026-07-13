"""Shared pure checks for LoopSpec-owned execution governance."""

from __future__ import annotations

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
    if expected_mode != "workflow":
        missing = sorted(HARD_LIMIT_IDS - threshold_ids)
        require(not missing, f"threshold_register missing hard-limit thresholds: {missing}")

    control_flow = loop_spec.get("control_flow")
    require(isinstance(control_flow, dict), "loop_spec.control_flow must be present")
    if not isinstance(control_flow, dict):
        return
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
        if expected_mode != "workflow":
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
    mode = expected_mode
    if mode is None and isinstance(loop_spec.get("architecture"), dict):
        mode = loop_spec["architecture"].get("mode")
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
    if expected_mode != "workflow":
        require(fallback in stopped, "transition_policy.fallback_node must map to terminal_nodes.stopped")
