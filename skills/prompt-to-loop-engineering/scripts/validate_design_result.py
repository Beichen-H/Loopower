"""Statically validate a request-bound loop_design_result.

This module performs design-time checks only. It never executes a LoopSpec,
invokes a declared tool, mutates runtime state, or reports user-task success.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from normalize_design_request import normalize_design_request
from governance_contracts import (
    validate_core_loop_governance,
    validate_output_binding,
    validate_passed_path_evaluators,
    validate_safe_agent_id,
)


DISPOSITION_TO_BUILD_STATUS = {
    "one_shot": "no_loop_needed",
    "workflow": "spec_ready",
    "agent_loop": "spec_ready",
    "needs_input": "needs_input",
    "unsupported": "unsupported",
    "rejected": "rejected",
}
CAPABILITY_FLAGS = (
    "durable_state",
    "checkpoint_resume",
    "sandbox",
    "human_interrupt",
    "parallel_execution",
    "subagents",
)
CAPABILITY_KEYS = {
    "available_tools",
    "tool_access_modes",
    *CAPABILITY_FLAGS,
    "required_subagent_reasoning_intensity",
}
REQUIRED_LOOP_BUDGET_THRESHOLDS = {
    "max_runtime_seconds",
    "max_iterations",
    "max_token_budget",
    "max_no_progress_loops",
}
DETERMINISTIC_PROGRESS_FACTS = {
    "state.diff_fingerprint",
    "state.test_count",
    "state.artifact_hash",
    "state.new_evidence_count",
}
NODE_ROLES = {"planner", "implementer", "reviewer", "verifier", "terminal"}
AGENT_GOVERNANCE_ROLES = {"planner", "implementer", "reviewer", "verifier"}
TOOL_ACCESS_MODES = {"read_only", "workspace_write", "external_write"}
NODE_KINDS = {
    "deterministic",
    "model",
    "tool",
    "worker",
    "approval",
    "merge",
    "terminal",
}
VERIFICATION_METHODS = {
    "deterministic_check",
    "test",
    "schema",
    "source_check",
    "model_evaluator",
    "human_review",
}
EXECUTION_PATTERNS = {
    "prompt_chain",
    "tool_use",
    "plan_execute_replan",
    "evaluator_optimizer",
}
TOPOLOGIES = {
    "linear",
    "routed",
    "parallel",
    "orchestrator_workers",
    "graph_state_machine",
}
CONTROL_GATES = {"human_approval", "independent_review", "policy_check"}
CROSS_CUTTING_POLICIES = {
    "recovery",
    "checkpointing",
    "observability",
    "budget_control",
    "scope_control",
}
PREDICATE_OPERATORS = {
    "eq",
    "ne",
    "gt",
    "gte",
    "lt",
    "lte",
    "in",
    "not_in",
    "contains",
    "is_true",
    "is_false",
    "is_empty",
    "is_not_empty",
}
PROGRESS_OPERATORS = {"increases", "decreases", "changes", "new_unique_item"}
TERMINAL_STATUSES = {
    "passed",
    "failed",
    "blocked",
    "needs_approval",
    "stopped",
    "cancelled",
}
REQUIRED_STATIC_CHECKS = {
    "acceptance_bindings",
    "graph_reachability",
    "edge_condition_observability",
    "edge_priority_determinism",
    "state_initialization",
    "cycle_controls",
    "tool_capability_binding",
    "status_mapping",
    "threshold_sources",
    "reference_resolution",
    "output_binding",
    "passed_path_dominance",
}
SUBAGENT_DISCOVERY_TOKENS = (
    "tool_search",
    "spawn_agent",
    "spawn_subagent",
    "subagent",
    "multi_agent",
)
NEGATIVE_SUBAGENT_DISCOVERY_MARKER = "no_host_native_lifecycle_tool_found"
AFFIRMATIVE_SUBAGENT_DISCOVERY_MARKER = "host_native_lifecycle_tool_found"


class DesignValidationError(AssertionError):
    """Raised when a design violates the portable build contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise DesignValidationError(message)


def _object(value: Any, path: str) -> dict[str, Any]:
    _require(isinstance(value, dict), f"{path} must be an object")
    return value


def _list(value: Any, path: str) -> list[Any]:
    _require(isinstance(value, list), f"{path} must be an array")
    return value


def _non_empty_string(value: Any, path: str) -> str:
    _require(isinstance(value, str) and bool(value.strip()), f"{path} must be a non-empty string")
    return value


def _require_keys(value: dict[str, Any], keys: set[str], path: str) -> None:
    missing = sorted(keys - value.keys())
    _require(not missing, f"{path} is missing required fields: {missing}")


def _string_list(value: Any, path: str, *, non_empty: bool = False) -> list[str]:
    values = _list(value, path)
    if non_empty:
        _require(bool(values), f"{path} must not be empty")
    for index, item in enumerate(values):
        _non_empty_string(item, f"{path}[{index}]")
    _require(len(values) == len(set(values)), f"{path} must contain unique values")
    return values


def _flatten_for_evidence(value: Any) -> str:
    if isinstance(value, str):
        return value.lower()
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True).lower()
    except TypeError:
        return repr(value).lower()


def _contains_exact_evidence_marker(record: str, marker: str) -> bool:
    return re.search(
        rf"(?<![a-z0-9_]){re.escape(marker)}(?![a-z0-9_])",
        record,
    ) is not None


def _has_subagent_discovery_evidence(records: list[str], marker: str) -> bool:
    return any(
        _contains_exact_evidence_marker(record, marker)
        and all(token in record for token in SUBAGENT_DISCOVERY_TOKENS)
        for record in records
    )


def _validate_subagent_capability_discovery(
    *,
    capabilities: dict[str, Any],
    request: dict[str, Any],
    result_assumptions: list[Any],
    validation_assumptions: list[Any],
) -> None:
    evidence_sources: list[Any] = []
    evidence_sources.extend(_list(request.get("known_context", []), "Loop_design_request.known_context"))
    evidence_sources.extend(result_assumptions)
    evidence_sources.extend(validation_assumptions)
    records = [_flatten_for_evidence(value) for value in evidence_sources]
    negative_evidence_present = any(
        _contains_exact_evidence_marker(
            record, NEGATIVE_SUBAGENT_DISCOVERY_MARKER
        )
        for record in records
    )
    if capabilities["subagents"]:
        _require(
            not negative_evidence_present,
            "no_host_native_lifecycle_tool_found evidence contradicts runtime_capabilities.subagents=true",
        )
        _require(
            _has_subagent_discovery_evidence(
                records, AFFIRMATIVE_SUBAGENT_DISCOVERY_MARKER
            ),
            "runtime_capabilities.subagents=true requires affirmative tool_search evidence for spawn_agent, spawn_subagent, subagent, and multi_agent returning host_native_lifecycle_tool_found",
        )
        return
    _require(
        _has_subagent_discovery_evidence(
            records, NEGATIVE_SUBAGENT_DISCOVERY_MARKER
        ),
        "runtime_capabilities.subagents=false requires tool_search evidence for spawn_agent, spawn_subagent, subagent, and multi_agent returning no_host_native_lifecycle_tool_found",
    )


def _validate_request(request: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    value = _object(request, "Loop_design_request")
    _require_keys(
        value,
        {
            "request_id",
            "task_prompt",
            "known_context",
            "runtime_capabilities",
            "policy_constraints",
            "budget_envelope",
            "output_requirements",
        },
        "Loop_design_request",
    )
    _non_empty_string(value["request_id"], "Loop_design_request.request_id")
    _non_empty_string(value["task_prompt"], "Loop_design_request.task_prompt")
    _list(value["known_context"], "Loop_design_request.known_context")
    budget = _object(value["budget_envelope"], "Loop_design_request.budget_envelope")
    missing_budget = sorted(REQUIRED_LOOP_BUDGET_THRESHOLDS - set(budget))
    _require(
        not missing_budget,
        "effective Loop_design_request budget_envelope missing hard limits: "
        f"{missing_budget}; run normalize_design_request.py first",
    )
    for key in REQUIRED_LOOP_BUDGET_THRESHOLDS:
        _require(
            isinstance(budget[key], int) and not isinstance(budget[key], bool) and budget[key] >= 1,
            f"budget_envelope.{key} must be a positive integer",
        )
    _object(value["output_requirements"], "Loop_design_request.output_requirements")

    raw = _object(value["runtime_capabilities"], "Loop_design_request.runtime_capabilities")
    unknown = sorted(set(raw) - CAPABILITY_KEYS)
    _require(not unknown, f"runtime_capabilities contains unknown fields: {unknown}")
    tools = _string_list(raw.get("available_tools", []), "runtime_capabilities.available_tools")
    tool_access_modes = _object(raw.get("tool_access_modes"), "runtime_capabilities.tool_access_modes")
    _require(set(tool_access_modes) == set(tools), "runtime_capabilities.tool_access_modes must classify every available tool exactly once")
    for tool_id, access_mode in tool_access_modes.items():
        _require(access_mode in TOOL_ACCESS_MODES, f"runtime_capabilities.tool_access_modes.{tool_id} has invalid access mode")
    capabilities: dict[str, Any] = {"available_tools": tools, "tool_access_modes": tool_access_modes}
    for flag in CAPABILITY_FLAGS:
        flag_value = raw.get(flag, False)
        _require(type(flag_value) is bool, f"runtime_capabilities.{flag} must be boolean")
        capabilities[flag] = flag_value
    reasoning = raw.get("required_subagent_reasoning_intensity")
    _require(
        reasoning in {None, "extended_thought"},
        "runtime_capabilities.required_subagent_reasoning_intensity must be extended_thought or null",
    )
    capabilities["required_subagent_reasoning_intensity"] = reasoning

    policy = _object(value["policy_constraints"], "Loop_design_request.policy_constraints")
    _require_keys(policy, {"allowed_side_effects", "forbidden_actions", "approval_rules"}, "policy_constraints")
    for key in ("allowed_side_effects", "forbidden_actions", "approval_rules"):
        _list(policy[key], f"policy_constraints.{key}")
    return capabilities, policy, budget


def _validate_normalization_chain(
    raw_request: dict[str, Any],
    effective_request: dict[str, Any],
    normalization_report: dict[str, Any],
) -> dict[str, Any]:
    expected_request, expected_report = normalize_design_request(raw_request)
    _require(
        effective_request == expected_request,
        "effective Loop_design_request does not match deterministic normalization of raw request",
    )
    _require(
        normalization_report == expected_report,
        "normalization report does not match raw/effective request hashes or default provenance",
    )
    return expected_report


def validate_design_result(
    payload: dict[str, Any],
    request: dict[str, Any],
    *,
    raw_request: dict[str, Any],
    normalization_report: dict[str, Any],
) -> None:
    """Validate one static build result against its declared runtime request."""

    provenance = _validate_normalization_chain(raw_request, request, normalization_report)
    capabilities, policy, budget = _validate_request(request)
    result = _object(payload, "loop_design_result")
    _require_keys(
        result,
        {
            "disposition",
            "task_contract",
            "loop_spec",
            "one_shot_validation_plan",
            "assumptions",
            "missing_inputs",
            "validation_report",
            "rejected_alternatives",
            "build_report",
        },
        "loop_design_result",
    )

    disposition = result["disposition"]
    _require(disposition in DISPOSITION_TO_BUILD_STATUS, f"unsupported disposition {disposition!r}")
    criterion_ids, mandatory_ids = _validate_task_contract(
        _object(result["task_contract"], "task_contract")
    )
    result_assumptions = _list(result["assumptions"], "assumptions")
    missing_inputs = _list(result["missing_inputs"], "missing_inputs")
    _list(result["rejected_alternatives"], "rejected_alternatives")

    validation_report = _object(result["validation_report"], "validation_report")
    _require_keys(validation_report, {"valid", "errors", "warnings", "assumptions"}, "validation_report")
    _require(type(validation_report["valid"]) is bool, "validation_report.valid must be boolean")
    errors = _list(validation_report["errors"], "validation_report.errors")
    _list(validation_report["warnings"], "validation_report.warnings")
    validation_assumptions = _list(validation_report["assumptions"], "validation_report.assumptions")
    _validate_subagent_capability_discovery(
        capabilities=capabilities,
        request=request,
        result_assumptions=result_assumptions,
        validation_assumptions=validation_assumptions,
    )

    build_report = _object(result["build_report"], "build_report")
    _require_keys(
        build_report,
        {
            "status",
            "reason",
            "execution_performed",
            "user_task_passed",
            "generated_spec_ref",
            "validation_report_ref",
            "missing_inputs",
            "unsupported_capabilities",
            "policy_rejections",
        },
        "build_report",
    )
    expected_status = DISPOSITION_TO_BUILD_STATUS[disposition]
    _require(
        build_report["status"] == expected_status,
        f"build status {build_report['status']!r} does not match disposition {disposition!r}; expected {expected_status!r}",
    )
    _non_empty_string(build_report["reason"], "build_report.reason")
    _require(build_report["execution_performed"] is False, "build_report.execution_performed must be false")
    _require(build_report["user_task_passed"] is False, "build_report.user_task_passed must be false")
    build_missing = _list(build_report["missing_inputs"], "build_report.missing_inputs")
    unsupported = _list(build_report["unsupported_capabilities"], "build_report.unsupported_capabilities")
    rejections = _list(build_report["policy_rejections"], "build_report.policy_rejections")

    loop_spec = result["loop_spec"]
    if disposition in {"workflow", "agent_loop"}:
        _require(isinstance(loop_spec, dict), f"{disposition} requires a non-null loop_spec")
        _validate_loop_spec(
            loop_spec,
            expected_mode=disposition,
            capabilities=capabilities,
            policy=policy,
            budget=budget,
            budget_defaults=set(provenance["defaults_applied"]),
            criterion_ids=criterion_ids,
            mandatory_ids=mandatory_ids,
        )
    else:
        _require(loop_spec is None, f"{disposition}: loop_spec must be null")

    if disposition == "one_shot":
        plan = result["one_shot_validation_plan"]
        _require(isinstance(plan, dict), "one_shot requires one_shot_validation_plan")
        checks = _list(plan.get("checks"), "one_shot_validation_plan.checks")
        _require(bool(checks), "one_shot_validation_plan.checks must not be empty")
        verified_criteria: set[str] = set()
        for index, check in enumerate(checks):
            item = _object(check, f"one_shot_validation_plan.checks[{index}]")
            _non_empty_string(item.get("id"), f"one_shot_validation_plan.checks[{index}].id")
            _require(item.get("type") == "deterministic", f"one_shot_validation_plan.checks[{index}].type must be 'deterministic'")
            verifies = _string_list(item.get("verifies"), f"one_shot_validation_plan.checks[{index}].verifies", non_empty=True)
            unknown = set(verifies) - criterion_ids
            _require(not unknown, f"one_shot validation check references unknown criteria {sorted(unknown)}")
            verified_criteria.update(verifies)
        missing_criteria = sorted(mandatory_ids - verified_criteria)
        _require(not missing_criteria, f"one_shot plan does not verify mandatory criterion IDs {missing_criteria}")
    else:
        _require(result["one_shot_validation_plan"] is None, f"{disposition} requires one_shot_validation_plan=null")

    if disposition == "needs_input":
        _require(bool(missing_inputs or build_missing), "needs_input requires at least one missing input")
    if disposition == "unsupported":
        _require(bool(unsupported), "unsupported requires unsupported_capabilities")
    if disposition == "rejected":
        _require(bool(rejections), "rejected requires policy_rejections")
    if build_report["status"] == "spec_ready":
        _require(validation_report["valid"] is True and not errors, "spec_ready requires validation_report.valid=true and errors=[]")


def _validate_task_contract(contract: dict[str, Any]) -> tuple[set[str], set[str]]:
    _require_keys(
        contract,
        {
            "id",
            "version",
            "goal",
            "deliverables",
            "acceptance_criteria",
            "constraints",
            "non_goals",
            "assumptions",
            "missing_inputs",
            "risk",
            "scope_change_policy",
        },
        "task_contract",
    )
    _non_empty_string(contract["id"], "task_contract.id")
    _require(isinstance(contract["version"], int) and not isinstance(contract["version"], bool) and contract["version"] >= 1, "task_contract.version must be a positive integer")
    _non_empty_string(contract["goal"], "task_contract.goal")
    deliverables = _list(contract["deliverables"], "task_contract.deliverables")
    _require(bool(deliverables), "task_contract.deliverables must not be empty")
    for index, deliverable in enumerate(deliverables):
        item = _object(deliverable, f"task_contract.deliverables[{index}]")
        _require_keys(item, {"id", "name", "format", "destination"}, f"task_contract.deliverables[{index}]")
        for key in ("id", "name", "format", "destination"):
            _non_empty_string(item[key], f"task_contract.deliverables[{index}].{key}")

    criteria = _list(contract["acceptance_criteria"], "task_contract.acceptance_criteria")
    _require(bool(criteria), "task_contract.acceptance_criteria must not be empty")
    criterion_ids: set[str] = set()
    mandatory_ids: set[str] = set()
    for index, criterion in enumerate(criteria):
        item = _object(criterion, f"task_contract.acceptance_criteria[{index}]")
        _require_keys(item, {"id", "requirement", "mandatory", "verification_method", "evidence_requirements"}, f"task_contract.acceptance_criteria[{index}]")
        criterion_id = _non_empty_string(item["id"], f"task_contract.acceptance_criteria[{index}].id")
        _require(criterion_id not in criterion_ids, f"duplicate acceptance criterion id {criterion_id!r}")
        criterion_ids.add(criterion_id)
        _non_empty_string(item["requirement"], f"acceptance criterion {criterion_id!r}.requirement")
        _require(type(item["mandatory"]) is bool, f"acceptance criterion {criterion_id!r} mandatory must be boolean")
        _require(item["verification_method"] in VERIFICATION_METHODS, f"acceptance criterion {criterion_id!r} has invalid verification_method")
        evidence = _string_list(item["evidence_requirements"], f"acceptance criterion {criterion_id!r}.evidence_requirements")
        if item["mandatory"]:
            mandatory_ids.add(criterion_id)
            _require(bool(evidence), f"mandatory acceptance criterion {criterion_id!r} requires evidence")

    for key in ("constraints", "non_goals", "assumptions", "missing_inputs"):
        _list(contract[key], f"task_contract.{key}")
    risk = _object(contract["risk"], "task_contract.risk")
    _require_keys(risk, {"level", "side_effects", "sensitive_data", "irreversible_actions"}, "task_contract.risk")
    _require(risk["level"] in {"low", "medium", "high", "critical"}, "task_contract.risk.level is invalid")
    for key in ("side_effects", "sensitive_data", "irreversible_actions"):
        _list(risk[key], f"task_contract.risk.{key}")
    _object(contract["scope_change_policy"], "task_contract.scope_change_policy")
    return criterion_ids, mandatory_ids


def _validate_loop_spec(
    spec: dict[str, Any],
    *,
    expected_mode: str,
    capabilities: dict[str, Any],
    policy: dict[str, Any],
    budget: dict[str, Any],
    budget_defaults: set[str],
    criterion_ids: set[str],
    mandatory_ids: set[str],
) -> None:
    required = {
        "spec_id", "version", "created_from_request", "task_contract_ref", "architecture",
        "runtime_binding", "state", "context", "control_flow", "transition_policy", "tools",
        "evaluation", "termination", "termination_control", "policy_registry", "policies",
        "delegation", "artifacts", "output_binding", "threshold_register", "validation",
    }
    _require_keys(spec, required, "loop_spec")
    _non_empty_string(spec["spec_id"], "loop_spec.spec_id")
    _non_empty_string(spec["created_from_request"], "loop_spec.created_from_request")
    _non_empty_string(spec["task_contract_ref"], "loop_spec.task_contract_ref")
    for forbidden in ("role", "persona", "caller_identity", "global_permissions", "mission"):
        _require(forbidden not in spec, f"loop_spec must not define {forbidden!r}")

    architecture = _validate_architecture(_object(spec["architecture"], "loop_spec.architecture"), expected_mode)
    binding = _object(spec["runtime_binding"], "loop_spec.runtime_binding")
    snapshot = _object(binding.get("capabilities_snapshot"), "loop_spec.runtime_binding.capabilities_snapshot")
    _require(snapshot == capabilities, "loop_spec.runtime_binding.capabilities_snapshot must exactly match the normalized request")
    required_capabilities = _object(binding.get("required_capabilities"), "loop_spec.runtime_binding.required_capabilities")
    unknown_requirements = sorted(set(required_capabilities) - CAPABILITY_KEYS)
    _require(not unknown_requirements, f"required_capabilities contains unknown fields: {unknown_requirements}")
    required_tools = _string_list(required_capabilities.get("available_tools", []), "required_capabilities.available_tools")
    _require(set(required_tools) <= set(capabilities["available_tools"]), f"required tools are unavailable: {sorted(set(required_tools) - set(capabilities['available_tools']))}")
    required_access_modes = _object(required_capabilities.get("tool_access_modes", {}), "required_capabilities.tool_access_modes")
    _require(set(required_access_modes) <= set(required_tools), "required_capabilities.tool_access_modes may classify only required tools")
    for tool_id, access_mode in required_access_modes.items():
        _require(access_mode == capabilities["tool_access_modes"][tool_id], f"required tool access mode for {tool_id!r} does not match runtime capability")
    for flag in CAPABILITY_FLAGS:
        requested = required_capabilities.get(flag, False)
        _require(type(requested) is bool, f"required_capabilities.{flag} must be boolean")
        _require(not requested or capabilities[flag], f"required capability {flag} is unavailable")
    required_reasoning = required_capabilities.get("required_subagent_reasoning_intensity")
    _require(
        required_reasoning in {None, "extended_thought"},
        "required_capabilities.required_subagent_reasoning_intensity must be extended_thought or null",
    )
    _require(
        required_reasoning is None or capabilities["required_subagent_reasoning_intensity"] == required_reasoning,
        "required subagent reasoning intensity is unavailable",
    )
    if required_capabilities.get("subagents") is True:
        _require(
            required_reasoning == "extended_thought",
            "subagent designs require required_subagent_reasoning_intensity='extended_thought'",
        )
    mismatches = _list(binding.get("capability_mismatches"), "runtime_binding.capability_mismatches")
    _require(not mismatches, "spec_ready loop_spec cannot contain capability_mismatches")

    state = _validate_state(_object(spec["state"], "loop_spec.state"))
    thresholds = _validate_thresholds(_list(spec["threshold_register"], "loop_spec.threshold_register"))
    policy_registry = _validate_policy_registry(_object(spec["policy_registry"], "loop_spec.policy_registry"), thresholds)
    tools = _validate_tools(_object(spec["tools"], "loop_spec.tools"), capabilities, policy)
    declared_nodes = _list(
        _object(spec["control_flow"], "loop_spec.control_flow").get("nodes"),
        "loop_spec.control_flow.nodes",
    )
    declared_node_ids = {
        _non_empty_string(
            _object(node, f"control_flow.nodes[{index}]").get("id"),
            f"control_flow.nodes[{index}].id",
        )
        for index, node in enumerate(declared_nodes)
    }
    agent_registry = _validate_agent_registry(
        _object(spec["delegation"], "loop_spec.delegation"),
        declared_node_ids,
        tools,
    )
    flow_info = _validate_control_flow(
        _object(spec["control_flow"], "loop_spec.control_flow"),
        expected_mode=expected_mode,
        criterion_ids=criterion_ids,
        state_fields=set(state["schema"]),
        evaluator_registry=set(_list(_object(spec["evaluation"], "loop_spec.evaluation").get("evaluator_registry"), "evaluation.evaluator_registry")),
        policy_registry=policy_registry,
        tool_access_modes=tools,
        agent_registry=agent_registry,
        controller_owned_fields=set(state["controller_owned_fields"]),
    )
    evaluation = _object(spec["evaluation"], "loop_spec.evaluation")
    _validate_evaluation(evaluation, criterion_ids, mandatory_ids, flow_info, agent_registry)
    validate_output_binding(spec, _require)
    validate_passed_path_evaluators(
        spec, _require, mandatory_criterion_ids=mandatory_ids
    )
    _validate_transition_policy(_object(spec["transition_policy"], "loop_spec.transition_policy"), expected_mode, flow_info)
    _validate_termination_control(
        _object(spec["termination_control"], "loop_spec.termination_control")
    )
    validate_core_loop_governance(spec, _require, expected_mode=expected_mode)
    _validate_policy_refs(_object(spec["policies"], "loop_spec.policies"), policy_registry)
    _validate_capability_usage(spec, architecture, flow_info, tools, capabilities)
    if expected_mode == "agent_loop":
        _validate_agent_loop_hard_limits(budget, budget_defaults, thresholds)

    validation = _object(spec["validation"], "loop_spec.validation")
    _require(validation.get("schema_version") == "loop-spec-v4", "loop_spec.validation.schema_version must be 'loop-spec-v4'")
    checks = set(_string_list(validation.get("required_checks"), "loop_spec.validation.required_checks", non_empty=True))
    missing_checks = sorted(REQUIRED_STATIC_CHECKS - checks)
    _require(not missing_checks, f"loop_spec.validation.required_checks is missing {missing_checks}")


def _validate_architecture(architecture: dict[str, Any], expected_mode: str) -> dict[str, Any]:
    _require_keys(architecture, {"mode", "execution_patterns", "topology", "control_gates", "domain_compositions", "cross_cutting_policies", "rationale"}, "loop_spec.architecture")
    _require(architecture["mode"] == expected_mode, f"loop_spec architecture mode must be {expected_mode!r}")
    patterns = _string_list(architecture["execution_patterns"], "architecture.execution_patterns", non_empty=True)
    _require(set(patterns) <= EXECUTION_PATTERNS, f"architecture.execution_patterns contains invalid values: {sorted(set(patterns) - EXECUTION_PATTERNS)}")
    topology = _object(architecture["topology"], "architecture.topology")
    _require(topology.get("type") in TOPOLOGIES, f"architecture.topology.type must be one of {sorted(TOPOLOGIES)}")
    gates = _string_list(architecture["control_gates"], "architecture.control_gates")
    _require(set(gates) <= CONTROL_GATES, f"architecture.control_gates contains invalid values: {sorted(set(gates) - CONTROL_GATES)}")
    _string_list(architecture["domain_compositions"], "architecture.domain_compositions", non_empty=True)
    cross = _string_list(architecture["cross_cutting_policies"], "architecture.cross_cutting_policies", non_empty=True)
    _require(set(cross) <= CROSS_CUTTING_POLICIES, f"architecture.cross_cutting_policies contains invalid values: {sorted(set(cross) - CROSS_CUTTING_POLICIES)}")
    _non_empty_string(architecture["rationale"], "architecture.rationale")
    return architecture


def _validate_state(state: dict[str, Any]) -> dict[str, Any]:
    _require_keys(state, {"schema", "initial_state", "persistence", "state_version", "reducers", "controller_owned_fields", "write_conflict_policy"}, "loop_spec.state")
    schema = _object(state["schema"], "loop_spec.state.schema")
    initial = _object(state["initial_state"], "loop_spec.state.initial_state")
    _require(set(schema) == set(initial), "loop_spec.state.initial_state fields must exactly match state.schema")
    _non_empty_string(state["persistence"], "loop_spec.state.persistence")
    _list(state["reducers"], "loop_spec.state.reducers")
    _string_list(state["controller_owned_fields"], "loop_spec.state.controller_owned_fields")
    _non_empty_string(state["write_conflict_policy"], "loop_spec.state.write_conflict_policy")
    return state


def _validate_thresholds(thresholds: list[Any]) -> dict[str, dict[str, Any]]:
    threshold_ids: dict[str, dict[str, Any]] = {}
    for index, threshold in enumerate(thresholds):
        item = _object(threshold, f"loop_spec.threshold_register[{index}]")
        _require_keys(item, {"id", "value", "unit", "source", "rationale", "calibration_scope", "review_trigger"}, f"loop_spec.threshold_register[{index}]")
        threshold_id = _non_empty_string(item["id"], f"loop_spec.threshold_register[{index}].id")
        _require(threshold_id not in threshold_ids, f"duplicate threshold id {threshold_id!r}")
        threshold_ids[threshold_id] = item
        _require(isinstance(item["value"], (int, float)) and not isinstance(item["value"], bool), f"threshold {threshold_id!r}.value must be numeric")
        for key in ("unit", "source", "rationale", "calibration_scope", "review_trigger"):
            _non_empty_string(item[key], f"threshold {threshold_id!r}.{key}")
    return threshold_ids


def _validate_policy_registry(registry: dict[str, Any], threshold_ids: dict[str, dict[str, Any]]) -> dict[str, set[str]]:
    required_groups = {"retry", "timeout", "stagnation", "recovery", "checkpoint", "budget", "scope", "observability"}
    _require_keys(registry, required_groups, "loop_spec.policy_registry")
    ids: dict[str, set[str]] = {}
    for group in required_groups:
        ids[group] = set()
        for index, raw in enumerate(_list(registry[group], f"policy_registry.{group}")):
            item = _object(raw, f"policy_registry.{group}[{index}]")
            policy_id = _non_empty_string(item.get("id"), f"policy_registry.{group}[{index}].id")
            _require(policy_id not in ids[group], f"duplicate {group} policy id {policy_id!r}")
            ids[group].add(policy_id)
            for key in ("limit_ref", "threshold_ref", "window_ref"):
                if item.get(key) is not None:
                    ref = _non_empty_string(item[key], f"{group} policy {policy_id!r}.{key}")
                    _require(ref in threshold_ids, f"{group} policy {policy_id!r} references missing threshold {ref!r}")
            if "threshold_refs" in item:
                for ref in _string_list(item["threshold_refs"], f"{group} policy {policy_id!r}.threshold_refs", non_empty=True):
                    _require(ref in threshold_ids, f"{group} policy {policy_id!r} references missing threshold {ref!r}")
    return ids


def _validate_agent_loop_hard_limits(
    budget: dict[str, Any],
    budget_defaults: set[str],
    thresholds: dict[str, dict[str, Any]],
) -> None:
    missing_budget = sorted(REQUIRED_LOOP_BUDGET_THRESHOLDS - set(budget))
    _require(
        not missing_budget,
        f"agent_loop budget_envelope missing hard limits: {missing_budget}",
    )
    missing_thresholds = sorted(REQUIRED_LOOP_BUDGET_THRESHOLDS - set(thresholds))
    _require(
        not missing_thresholds,
        f"agent_loop threshold_register missing hard limit thresholds: {missing_thresholds}",
    )
    mismatched: list[str] = []
    for threshold_id in sorted(REQUIRED_LOOP_BUDGET_THRESHOLDS):
        if thresholds[threshold_id]["value"] != budget[threshold_id]:
            mismatched.append(threshold_id)
        expected_source = (
            "default_policy:codex-native-safe-v1"
            if threshold_id in budget_defaults
            else "request_budget_envelope"
        )
        _require(
            thresholds[threshold_id]["source"] == expected_source,
            f"agent_loop threshold {threshold_id!r} source must be {expected_source!r}",
        )
    _require(
        not mismatched,
        f"agent_loop hard limit thresholds do not align with budget_envelope: {mismatched}",
    )


def _validate_tools(tools: dict[str, Any], capabilities: dict[str, Any], policy: dict[str, Any]) -> dict[str, str]:
    _require_keys(tools, {"contracts", "rollback_procedures", "permission_bindings", "side_effect_policies"}, "loop_spec.tools")
    contract_access_modes: dict[str, str] = {}
    allowed_tools = set(capabilities["available_tools"])
    allowed_side_effects = set(policy["allowed_side_effects"])
    for index, raw in enumerate(_list(tools["contracts"], "loop_spec.tools.contracts")):
        item = _object(raw, f"loop_spec.tools.contracts[{index}]")
        tool_id = _non_empty_string(item.get("id"), f"loop_spec.tools.contracts[{index}].id")
        _require(tool_id not in contract_access_modes, f"duplicate tool contract {tool_id!r}")
        _require(tool_id in allowed_tools, f"tool {tool_id!r} is not present in runtime_capabilities.available_tools")
        _require(item.get("controller_executes") is True, f"tool {tool_id!r} must declare controller_executes=true")
        access_mode = item.get("access_mode")
        _require(access_mode in TOOL_ACCESS_MODES, f"tool {tool_id!r}.access_mode must be one of {sorted(TOOL_ACCESS_MODES)}")
        _require(access_mode == capabilities["tool_access_modes"][tool_id], f"tool {tool_id!r}.access_mode does not match runtime capability snapshot")
        contract_access_modes[tool_id] = access_mode
        side_effect = item.get("side_effect", "none")
        _require(side_effect == "none" or side_effect in allowed_side_effects, f"tool {tool_id!r} side effect {side_effect!r} is not allowed by policy")
    _list(tools["rollback_procedures"], "loop_spec.tools.rollback_procedures")
    _list(tools["permission_bindings"], "loop_spec.tools.permission_bindings")
    _list(tools["side_effect_policies"], "loop_spec.tools.side_effect_policies")
    return contract_access_modes


def _validate_agent_registry(
    delegation: dict[str, Any],
    node_ids: set[str],
    tool_access_modes: dict[str, str],
) -> dict[str, dict[str, Any]]:
    _require_keys(delegation, {"agent_registry"}, "loop_spec.delegation")
    registry: dict[str, dict[str, Any]] = {}
    signatures: dict[tuple[Any, ...], str] = {}
    for index, raw in enumerate(
        _list(delegation["agent_registry"], "loop_spec.delegation.agent_registry")
    ):
        path = f"loop_spec.delegation.agent_registry[{index}]"
        item = _object(raw, path)
        _require_keys(
            item,
            {
                "id",
                "display_name",
                "specialization",
                "governance_role",
                "rationale",
                "prompt_ref",
                "activation_policy",
                "activation_nodes",
                "allowed_tools",
            },
            path,
        )
        agent_id = _non_empty_string(item["id"], f"{path}.id")
        validate_safe_agent_id(agent_id, _require, f"{path}.id")
        _require(agent_id not in registry, f"duplicate agent registry id {agent_id!r}")
        for field in ("display_name", "specialization", "rationale"):
            _non_empty_string(item[field], f"{path}.{field}")
        role = item["governance_role"]
        _require(
            role in AGENT_GOVERNANCE_ROLES,
            f"agent {agent_id!r} has invalid governance role",
        )
        _require(
            item["prompt_ref"] == f".codex-loop/subagents/{agent_id}.md",
            f"agent {agent_id!r} prompt_ref must be derived from its id",
        )
        _require(
            item["activation_policy"] == "on_demand",
            f"agent {agent_id!r} activation_policy must be 'on_demand'",
        )
        activation_nodes = _string_list(
            item["activation_nodes"], f"agent {agent_id!r}.activation_nodes", non_empty=True
        )
        unknown_nodes = sorted(set(activation_nodes) - node_ids)
        _require(
            not unknown_nodes,
            f"agent {agent_id!r} activation_nodes reference undefined nodes {unknown_nodes}",
        )
        allowed_tools = _string_list(
            item["allowed_tools"], f"agent {agent_id!r}.allowed_tools"
        )
        unknown_tools = sorted(set(allowed_tools) - set(tool_access_modes))
        _require(
            not unknown_tools,
            f"agent {agent_id!r} references tools without matching capability access modes: {unknown_tools}",
        )
        if role in {"reviewer", "verifier"}:
            writable = sorted(
                tool_id
                for tool_id in allowed_tools
                if tool_access_modes[tool_id] != "read_only"
            )
            _require(
                not writable,
                f"reviewer or verifier agent {agent_id!r} must remain read-only; non-read-only tools: {writable}",
            )
        signature = (
            item["specialization"],
            role,
            tuple(sorted(activation_nodes)),
            tuple(sorted(allowed_tools)),
        )
        _require(
            signature not in signatures,
            f"agent {agent_id!r} has duplicate role signature with {signatures.get(signature)!r}",
        )
        signatures[signature] = agent_id
        registry[agent_id] = item
    return registry


def _validate_condition(value: Any, path: str) -> None:
    _require(isinstance(value, dict), f"{path} must be a structured condition object")
    condition = _object(value, path)
    keys = set(condition)
    _require(keys in ({"all"}, {"any"}), f"{path} must be a structured condition with exactly one of 'all' or 'any'")
    group = next(iter(keys))
    predicates = _list(condition[group], f"{path}.{group}")
    _require(bool(predicates), f"{path}.{group} must not be empty")
    for index, raw in enumerate(predicates):
        predicate = _object(raw, f"{path}.{group}[{index}]")
        _require_keys(predicate, {"fact", "operator"}, f"{path}.{group}[{index}]")
        _validate_observable_fact(predicate["fact"], f"{path}.{group}[{index}].fact")
        _require(predicate["operator"] in PREDICATE_OPERATORS, f"{path}.{group}[{index}].operator is invalid")


def _validate_observable_fact(value: Any, path: str) -> str:
    fact = _non_empty_string(value, path)
    _require(
        fact.startswith("state.") or fact.startswith("controller."),
        f"{path} must reference a controller-observable 'state.' or 'controller.' fact",
    )
    return fact


def _validate_control_flow(
    control_flow: dict[str, Any],
    *,
    expected_mode: str,
    criterion_ids: set[str],
    state_fields: set[str],
    evaluator_registry: set[str],
    policy_registry: dict[str, set[str]],
    tool_access_modes: dict[str, str],
    agent_registry: dict[str, dict[str, Any]],
    controller_owned_fields: set[str],
) -> dict[str, Any]:
    _require_keys(control_flow, {"entry_node", "edge_selection_policy", "nodes", "edges", "cycles", "terminal_nodes"}, "loop_spec.control_flow")
    selection = _object(control_flow["edge_selection_policy"], "control_flow.edge_selection_policy")
    _require(selection == {"priority_order": "lower_first", "match_policy": "first_match", "equal_priority": "require_explicit_tie_breaker"}, "edge_selection_policy must use lower_first, first_match, and explicit tie breakers")
    nodes = _list(control_flow["nodes"], "loop_spec.control_flow.nodes")
    edges = _list(control_flow["edges"], "loop_spec.control_flow.edges")
    cycles = _list(control_flow["cycles"], "loop_spec.control_flow.cycles")
    terminals = _object(control_flow["terminal_nodes"], "loop_spec.control_flow.terminal_nodes")
    _require(set(terminals) == TERMINAL_STATUSES, f"terminal_nodes must define exactly {sorted(TERMINAL_STATUSES)}")

    node_ids: set[str] = set()
    node_kinds: dict[str, str] = {}
    node_roles: dict[str, str] = {}
    nodes_by_id: dict[str, dict[str, Any]] = {}
    for index, node in enumerate(nodes):
        item = _object(node, f"control_flow.nodes[{index}]")
        _require_keys(item, {"id", "kind", "role", "objective", "input_schema", "output_schema", "allowed_tools", "state_read_scope", "state_write_scope"}, f"control_flow.nodes[{index}]")
        node_id = _non_empty_string(item["id"], f"control_flow.nodes[{index}].id")
        _require(node_id not in node_ids, f"duplicate loop_spec node id {node_id!r}")
        _require(item["kind"] in NODE_KINDS, f"node {node_id!r} has invalid kind")
        _require(item["role"] in NODE_ROLES, f"node {node_id!r} has invalid role")
        _non_empty_string(item["objective"], f"node {node_id!r}.objective")
        node_ids.add(node_id)
        node_kinds[node_id] = item["kind"]
        node_roles[node_id] = item["role"]
        nodes_by_id[node_id] = item
        node_tools = set(
            _string_list(item.get("allowed_tools", []), f"node {node_id!r}.allowed_tools")
        )
        agent_ref = item.get("agent_ref")
        if agent_ref is not None:
            _non_empty_string(agent_ref, f"node {node_id!r}.agent_ref")
            _require(
                agent_ref in agent_registry,
                f"node {node_id!r} references unknown agent_ref {agent_ref!r}",
            )
            agent = agent_registry[agent_ref]
            _require(
                item["role"] == agent["governance_role"],
                f"node {node_id!r} role does not match agent {agent_ref!r} governance role",
            )
            _require(
                node_id in agent["activation_nodes"],
                f"node {node_id!r} is not declared in agent {agent_ref!r} activation_nodes",
            )
            excess_tools = sorted(node_tools - set(agent["allowed_tools"]))
            _require(
                not excess_tools,
                f"node {node_id!r} tools exceed agent {agent_ref!r} allowed_tools: {excess_tools}",
            )
        for key in ("state_read_scope", "state_write_scope"):
            scope = set(_string_list(item[key], f"node {node_id!r}.{key}"))
            _require(scope <= state_fields, f"node {node_id!r}.{key} references undefined state fields {sorted(scope - state_fields)}")
        if item["role"] in {"reviewer", "verifier"}:
            forbidden = sorted(tool_id for tool_id in node_tools if tool_access_modes.get(tool_id) != "read_only")
            _require(
                not forbidden,
                f"reviewer or verifier node {node_id!r} must remain read-only; non-read-only tools: {forbidden}",
            )
            if agent_ref is not None:
                controller_writes = sorted(
                    set(item["state_write_scope"]) & controller_owned_fields
                )
                _require(
                    not controller_writes,
                    f"reviewer or verifier agent node {node_id!r} cannot write controller-owned state: {controller_writes}",
                )
        for criterion_id in _string_list(item.get("supports_acceptance_criteria", []), f"node {node_id!r}.supports_acceptance_criteria"):
            _require(criterion_id in criterion_ids, f"node {node_id!r} references unknown criterion {criterion_id!r}")
        for evaluator in _string_list(item.get("evaluator_refs", []), f"node {node_id!r}.evaluator_refs"):
            _require(evaluator in evaluator_registry, f"node {node_id!r} references unregistered evaluator {evaluator!r}")
        retry_ref = item.get("retry_policy_ref")
        if retry_ref is not None:
            _require(retry_ref in policy_registry["retry"], f"node {node_id!r} references missing retry policy {retry_ref!r}")
        timeout_ref = item.get("timeout_policy_ref")
        if timeout_ref is not None:
            _require(timeout_ref in policy_registry["timeout"], f"node {node_id!r} references missing timeout policy {timeout_ref!r}")

    entry = control_flow["entry_node"]
    _require(entry in node_ids, f"entry node {entry!r} is undefined")
    terminal_ids: set[str] = set()
    terminal_status_by_node: dict[str, str] = {}
    for status in sorted(TERMINAL_STATUSES):
        for node_id in _string_list(terminals[status], f"terminal_nodes.{status}"):
            _require(node_id in node_ids, f"terminal node {node_id!r} is undefined")
            _require(node_id not in terminal_ids, f"terminal node {node_id!r} maps to more than one status")
            terminal_ids.add(node_id)
            terminal_status_by_node[node_id] = status
            _require(node_kinds[node_id] == "terminal", f"terminal node {node_id!r} must have kind='terminal'")

    outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)
    adjacency: dict[str, list[str]] = defaultdict(list)
    source_priorities: dict[str, list[int]] = defaultdict(list)
    for index, edge in enumerate(edges):
        item = _object(edge, f"control_flow.edges[{index}]")
        source, target = item.get("from"), item.get("to")
        _require(source in node_ids, f"edge source references undefined node {source!r}")
        _require(target in node_ids, f"edge target references undefined node {target!r}")
        priority = item.get("priority")
        _require(isinstance(priority, int) and not isinstance(priority, bool), f"edge {source!r}->{target!r} requires an integer priority")
        _validate_condition(item.get("condition"), f"edge {source!r}->{target!r}.condition")
        outgoing[source].append(item)
        adjacency[source].append(target)
        source_priorities[source].append(priority)
    for node_id in sorted(node_ids - terminal_ids):
        _require(bool(outgoing[node_id]), f"non-terminal node {node_id!r} has no successor edge")
    for source, priorities in source_priorities.items():
        _require(priorities == sorted(priorities), f"node {source!r} edges are not in lower-first priority order")
        grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for edge in outgoing[source]:
            grouped[edge["priority"]].append(edge)
        for priority, tied in grouped.items():
            if len(tied) > 1:
                tie_breakers = [edge.get("tie_breaker") for edge in tied]
                _require(all(isinstance(value, str) and value.strip() for value in tie_breakers), f"node {source!r} has duplicate priority {priority} without explicit tie_breakers")
                _require(len(set(tie_breakers)) == len(tie_breakers), f"node {source!r} has duplicate priority {priority} with non-unique tie_breakers")

    reachable: set[str] = set()
    queue: deque[str] = deque([entry])
    while queue:
        node_id = queue.popleft()
        if node_id in reachable:
            continue
        reachable.add(node_id)
        queue.extend(adjacency.get(node_id, []))
    _require(reachable == node_ids, f"control_flow has unreachable nodes: {sorted(node_ids - reachable)}")
    for agent_id, agent in agent_registry.items():
        for activation_node in agent["activation_nodes"]:
            _require(
                activation_node in reachable
                and nodes_by_id[activation_node].get("agent_ref") == agent_id,
                f"agent {agent_id!r} activation node {activation_node!r} must be reachable and bound back through the same agent_ref",
            )

    declared_cycles: list[set[str]] = []
    if expected_mode == "workflow":
        _require(not cycles, "workflow must not declare cycles; use agent_loop for adaptive cycles")
    for index, cycle in enumerate(cycles):
        item = _object(cycle, f"control_flow.cycles[{index}]")
        _require_keys(item, {"id", "node_ids", "progress_signals", "stagnation_policy_ref", "budget_policy_ref", "exit_conditions"}, f"control_flow.cycles[{index}]")
        cycle_id = _non_empty_string(item["id"], f"control_flow.cycles[{index}].id")
        cycle_nodes = set(_string_list(item["node_ids"], f"cycle {cycle_id!r}.node_ids", non_empty=True))
        _require(cycle_nodes <= node_ids, f"cycle {cycle_id!r} references undefined nodes")
        progress = _list(item["progress_signals"], f"cycle {cycle_id!r}.progress_signals")
        _require(bool(progress), f"cycle {cycle_id!r} has no progress signal")
        for signal_index, raw in enumerate(progress):
            signal = _object(raw, f"cycle {cycle_id!r}.progress_signals[{signal_index}]")
            _require_keys(signal, {"fact", "operator", "evidence_ref"}, f"cycle {cycle_id!r}.progress_signals[{signal_index}]")
            _validate_observable_fact(signal["fact"], f"cycle {cycle_id!r}.progress_signals[{signal_index}].fact")
            _require(signal["operator"] in PROGRESS_OPERATORS, f"cycle {cycle_id!r} progress operator is invalid")
            _non_empty_string(signal["evidence_ref"], f"cycle {cycle_id!r}.progress_signals[{signal_index}].evidence_ref")
        progress_facts = {signal["fact"] for signal in progress if isinstance(signal, dict)}
        _require(
            bool(progress_facts & DETERMINISTIC_PROGRESS_FACTS),
            f"cycle {cycle_id!r} requires at least one deterministic progress fact from {sorted(DETERMINISTIC_PROGRESS_FACTS)}",
        )
        stagnation_ref = _non_empty_string(item["stagnation_policy_ref"], f"cycle {cycle_id!r}.stagnation_policy_ref")
        budget_ref = _non_empty_string(item["budget_policy_ref"], f"cycle {cycle_id!r}.budget_policy_ref")
        _require(stagnation_ref in policy_registry["stagnation"], f"cycle {cycle_id!r} references missing stagnation policy {stagnation_ref!r}")
        _require(budget_ref in policy_registry["budget"], f"cycle {cycle_id!r} references missing budget policy {budget_ref!r}")
        exits = _list(item["exit_conditions"], f"cycle {cycle_id!r}.exit_conditions")
        _require(bool(exits), f"cycle {cycle_id!r} has no exit conditions")
        for exit_index, condition in enumerate(exits):
            _validate_condition(condition, f"cycle {cycle_id!r}.exit_conditions[{exit_index}]")
        _require(any(edge["from"] in cycle_nodes and edge["to"] not in cycle_nodes for edge in edges), f"cycle {cycle_id!r} has no graph exit edge")
        declared_cycles.append(cycle_nodes)
    detected_cycles = _find_directed_cycles(node_ids, adjacency)
    if expected_mode == "agent_loop":
        _require(bool(detected_cycles), "agent_loop requires at least one directed cycle; otherwise use workflow")
    for detected in detected_cycles:
        _require(any(detected <= declared for declared in declared_cycles), f"undeclared directed cycle detected: {sorted(detected)}")

    if "implementer" in node_roles.values():
        _require(
            any(
                role in {"reviewer", "verifier"} and node_kinds[node_id] != "terminal"
                for node_id, role in node_roles.items()
            ),
            "an implementer node requires at least one non-terminal reviewer or verifier node",
        )

    return {
        "node_ids": node_ids,
        "node_kinds": node_kinds,
        "node_roles": node_roles,
        "nodes_by_id": nodes_by_id,
        "node_agent_refs": {
            node_id: node.get("agent_ref") for node_id, node in nodes_by_id.items()
        },
        "terminal_ids": terminal_ids,
        "terminal_status_by_node": terminal_status_by_node,
        "edges": edges,
    }


def _validate_evaluation(
    evaluation: dict[str, Any],
    criterion_ids: set[str],
    mandatory_ids: set[str],
    flow: dict[str, Any],
    agent_registry: dict[str, dict[str, Any]],
) -> None:
    _require_keys(evaluation, {"criteria_bindings", "evaluator_registry", "result_state_path", "controller_writes_results", "deterministic_checks", "independent_review_policy"}, "loop_spec.evaluation")
    registry = set(_string_list(evaluation["evaluator_registry"], "evaluation.evaluator_registry", non_empty=True))
    bindings = _list(evaluation["criteria_bindings"], "evaluation.criteria_bindings")
    bound: set[str] = set()
    for index, raw in enumerate(bindings):
        item = _object(raw, f"evaluation.criteria_bindings[{index}]")
        criterion_id = _non_empty_string(item.get("criterion_id"), f"evaluation.criteria_bindings[{index}].criterion_id")
        evaluator_ref = _non_empty_string(item.get("evaluator_ref"), f"evaluation.criteria_bindings[{index}].evaluator_ref")
        _require(criterion_id in criterion_ids, f"evaluation binding references unknown criterion {criterion_id!r}")
        _require(evaluator_ref in registry, f"evaluation binding references unregistered evaluator {evaluator_ref!r}")
        evaluator_node = item.get("evaluator_node")
        if evaluator_node is not None:
            _non_empty_string(evaluator_node, f"evaluation.criteria_bindings[{index}].evaluator_node")
            _require(evaluator_node in flow["node_ids"], f"evaluation binding references undefined evaluator_node {evaluator_node!r}")
        if criterion_id in mandatory_ids:
            subject_nodes = _string_list(
                item.get("subject_nodes"),
                f"mandatory criterion {criterion_id!r}.subject_nodes",
                non_empty=True,
            )
            for subject_node in subject_nodes:
                _require(
                    subject_node in flow["node_ids"],
                    f"mandatory criterion {criterion_id!r} references undefined subject node {subject_node!r}",
                )
            _require(
                evaluator_node is not None,
                f"mandatory criterion {criterion_id!r} requires evaluator_node for role isolation",
            )
            evaluator_agent = flow["node_agent_refs"].get(evaluator_node)
            subject_agents = {
                flow["node_agent_refs"].get(subject_node)
                for subject_node in subject_nodes
                if flow["node_agent_refs"].get(subject_node) is not None
            }
            if subject_agents:
                _require(
                    evaluator_agent is not None and evaluator_agent not in subject_agents,
                    f"mandatory criterion {criterion_id!r} requires an independent agent distinct from every subject node agent",
                )
            _require(
                flow["node_roles"].get(evaluator_node) in {"reviewer", "verifier"},
                f"mandatory criterion {criterion_id!r} evaluator_node {evaluator_node!r} must be a reviewer or verifier",
            )
        bound.add(criterion_id)
    missing = sorted(mandatory_ids - bound)
    _require(not missing, f"mandatory criterion bindings are missing for {missing}")
    _require(evaluation["controller_writes_results"] is True, "evaluation.controller_writes_results must be true")
    _string_list(evaluation["deterministic_checks"], "evaluation.deterministic_checks")


def _validate_transition_policy(policy: dict[str, Any], expected_mode: str, flow: dict[str, Any]) -> None:
    _require_keys(policy, {"decision_authority", "proposal_mode", "proposal_source_nodes", "allowed_targets", "proposal_schema", "controller_validation", "fallback_node"}, "loop_spec.transition_policy")
    _require(
        policy["decision_authority"] == "codex_host_controller",
        "transition_policy.decision_authority must be 'codex_host_controller'",
    )
    expected_proposal_mode = "none" if expected_mode == "workflow" else "model_proposal"
    _require(
        policy["proposal_mode"] == expected_proposal_mode,
        f"{expected_mode} transition proposal_mode must be {expected_proposal_mode!r}",
    )
    _require(policy["controller_validation"] == "required", "transition_policy.controller_validation must be 'required'")
    node_ids = flow["node_ids"]
    for target in _string_list(policy["allowed_targets"], "transition_policy.allowed_targets", non_empty=True):
        _require(target in node_ids, f"transition_policy allowed target {target!r} is undefined")
    sources = _string_list(policy["proposal_source_nodes"], "transition_policy.proposal_source_nodes")
    if expected_mode == "workflow":
        _require(not sources, "workflow must not have model proposal source nodes")
    else:
        _require(bool(sources), "agent_loop requires model proposal source nodes")
        for source in sources:
            _require(flow["node_kinds"].get(source) == "model", f"proposal source {source!r} must be a model node")
            _require(
                flow["node_roles"].get(source) not in {"reviewer", "verifier"},
                f"reviewer or verifier proposal source {source!r} violates evidence-only authority",
            )
    _require(policy["fallback_node"] in node_ids, "transition_policy.fallback_node is undefined")


def _validate_termination_control(control: dict[str, Any]) -> None:
    expected = {
        "policy_authority": "loop_spec",
        "evaluation_authority": "codex_host_controller",
        "reviewer_authority": "evidence_only",
        "transition_policy": "lower_first_then_first_match",
        "hard_stop_precedence": [
            "policy_violation",
            "user_interrupt",
            "max_runtime_seconds",
            "max_iterations",
            "max_token_budget",
            "max_no_progress_loops",
        ],
    }
    _require(
        control == expected,
        "LoopSpec must remain the policy authority; the codex_host_controller only evaluates declared transitions and hard stops",
    )


def _validate_policy_refs(policies: dict[str, Any], registry: dict[str, set[str]]) -> None:
    mapping = {
        "recovery_policy_ref": "recovery",
        "checkpoint_policy_ref": "checkpoint",
        "budget_policy_ref": "budget",
        "scope_policy_ref": "scope",
        "observability_policy_ref": "observability",
    }
    _require_keys(policies, set(mapping), "loop_spec.policies")
    for field, group in mapping.items():
        ref = policies[field]
        if ref is not None:
            _require(ref in registry[group], f"loop_spec.policies.{field} references missing policy {ref!r}")


def _validate_capability_usage(
    spec: dict[str, Any],
    architecture: dict[str, Any],
    flow: dict[str, Any],
    tool_contracts: dict[str, str],
    capabilities: dict[str, Any],
) -> None:
    used_tools: set[str] = set()
    checkpoint_used = False
    for node_id, node in flow["nodes_by_id"].items():
        node_tools = set(_string_list(node.get("allowed_tools", []), f"node {node_id!r}.allowed_tools"))
        used_tools |= node_tools
        registered_tools = set(tool_contracts)
        _require(node_tools <= registered_tools, f"node {node_id!r} references unregistered tool(s) {sorted(node_tools - registered_tools)}")
        if node["kind"] == "tool":
            _require(bool(node_tools), f"tool node {node_id!r} must declare at least one allowed tool")
        checkpoint_used = checkpoint_used or node.get("checkpoint_before") is True or node.get("checkpoint_after") is True
    _require(used_tools <= set(capabilities["available_tools"]), f"tool bindings exceed runtime capabilities: {sorted(used_tools - set(capabilities['available_tools']))}")

    persistence = spec["state"]["persistence"]
    durable_used = persistence not in {"none", "memory", "ephemeral", "request"}
    _require(not durable_used or capabilities["durable_state"], "durable_state is required by state.persistence")

    checkpoint_used = checkpoint_used or bool(spec["policy_registry"]["checkpoint"]) or spec["policies"]["checkpoint_policy_ref"] is not None
    _require(not checkpoint_used or capabilities["checkpoint_resume"], "checkpoint_resume is required by checkpoint declarations")
    _require(not checkpoint_used or capabilities["durable_state"], "durable_state is required by checkpoint declarations")

    approval_used = (
        "human_approval" in architecture["control_gates"]
        or "approval" in flow["node_kinds"].values()
        or bool(spec["control_flow"]["terminal_nodes"]["needs_approval"])
    )
    _require(not approval_used or capabilities["human_interrupt"], "human_interrupt is required by approval design")
    if spec["control_flow"]["terminal_nodes"]["needs_approval"]:
        _require(capabilities["checkpoint_resume"], "checkpoint_resume is required for needs_approval paths")
        _require(capabilities["durable_state"], "durable_state is required for needs_approval paths")

    topology = architecture["topology"]
    parallel_used = topology["type"] == "parallel" or topology.get("parallel_mode") is not None
    _require(not parallel_used or capabilities["parallel_execution"], "parallel_execution is required by parallel topology")
    subagent_used = (
        topology["type"] == "orchestrator_workers"
        or "worker" in flow["node_kinds"].values()
        or spec["delegation"].get("enabled") is True
        or bool(spec["delegation"].get("worker_profiles"))
        or bool(spec["delegation"].get("agent_registry"))
        or any(agent_ref is not None for agent_ref in flow["node_agent_refs"].values())
    )
    _require(not subagent_used or capabilities["subagents"], "subagents capability is required by agent/worker/delegation design")
    if subagent_used:
        requirements = spec["runtime_binding"]["required_capabilities"]
        _require(requirements.get("subagents") is True, "agent/worker/delegation design must require subagents explicitly")
        _require(
            capabilities["required_subagent_reasoning_intensity"] == "extended_thought",
            "agent/worker/delegation design requires extended_thought in the capability snapshot",
        )
        _require(
            requirements.get("required_subagent_reasoning_intensity") == "extended_thought",
            "agent/worker/delegation design must require extended_thought explicitly",
        )
    sandbox_used = spec["runtime_binding"]["required_capabilities"].get("sandbox", False)
    _require(not sandbox_used or capabilities["sandbox"], "sandbox capability is required by the design")


def _find_directed_cycles(node_ids: set[str], adjacency: dict[str, list[str]]) -> set[frozenset[str]]:
    state = {node_id: 0 for node_id in node_ids}
    stack: list[str] = []
    found: set[frozenset[str]] = set()

    def visit(node_id: str) -> None:
        state[node_id] = 1
        stack.append(node_id)
        for target in adjacency.get(node_id, []):
            if state[target] == 0:
                visit(target)
            elif state[target] == 1:
                start = stack.index(target)
                found.add(frozenset(stack[start:]))
        stack.pop()
        state[node_id] = 2

    for node_id in sorted(node_ids):
        if state[node_id] == 0:
            visit(node_id)
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Statically validate a request-bound loop_design_result JSON file.")
    parser.add_argument("result", type=Path, help="Path to loop_design_result JSON")
    parser.add_argument("--request", required=True, type=Path, help="Path to the effective Loop_design_request JSON")
    parser.add_argument("--raw-request", required=True, type=Path, help="Path to the preserved raw request JSON")
    parser.add_argument("--normalization-report", required=True, type=Path, help="Path to normalization provenance JSON")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    try:
        payload = json.loads(args.result.read_text(encoding="utf-8"))
        request = json.loads(args.request.read_text(encoding="utf-8"))
        raw_request = json.loads(args.raw_request.read_text(encoding="utf-8"))
        normalization_report = json.loads(args.normalization_report.read_text(encoding="utf-8"))
        validate_design_result(
            payload,
            request,
            raw_request=raw_request,
            normalization_report=normalization_report,
        )
    except (OSError, json.JSONDecodeError, DesignValidationError, TypeError, ValueError) as error:
        print(f"❌ Loop design validation failed: {error}", file=sys.stderr)
        return 1
    print(f"✅ loop_design_result static validation passed: {args.result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
