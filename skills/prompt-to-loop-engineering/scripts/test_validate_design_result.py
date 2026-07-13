"""Contract and semantic tests for validate_design_result.py."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from normalize_design_request import normalize_design_request
from validate_design_result import DesignValidationError, validate_design_result as _validate_design_result


SKILL_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = SKILL_ROOT / "examples"
REQUESTS = EXAMPLES / "requests"


def load_example(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def load_request(name: str) -> dict:
    return json.loads((REQUESTS / name).read_text(encoding="utf-8"))


def validate_design_result(payload: dict, raw_request: dict) -> None:
    effective_request, report = normalize_design_request(raw_request)
    _validate_design_result(
        payload,
        effective_request,
        raw_request=raw_request,
        normalization_report=report,
    )


def minimal_request(**capability_overrides: object) -> dict:
    capabilities = {
        "available_tools": [],
        "tool_access_modes": {},
        "durable_state": False,
        "checkpoint_resume": False,
        "sandbox": False,
        "human_interrupt": False,
        "parallel_execution": False,
        "subagents": False,
        "required_subagent_reasoning_intensity": None,
    }
    capabilities.update(capability_overrides)
    return {
        "request_id": "unit-test-request",
        "task_prompt": "Build a static design only.",
        "known_context": [
            {
                "source": "tool_search",
                "query": "spawn_agent spawn_subagent subagent multi_agent",
                "result": "no_host_native_lifecycle_tool_found",
            }
        ],
        "runtime_capabilities": capabilities,
        "policy_constraints": {
            "allowed_side_effects": [],
            "forbidden_actions": [],
            "approval_rules": [],
        },
        "budget_envelope": {
            "max_runtime_seconds": 900,
            "max_iterations": 3,
            "max_token_budget": 45000,
            "max_no_progress_loops": 1,
        },
        "output_requirements": {},
    }


def affirmative_subagent_discovery() -> dict:
    return {
        "source": "tool_search",
        "query": "spawn_agent spawn_subagent subagent multi_agent",
        "result": {
            "status": "host_native_lifecycle_tool_found",
            "callable": "multi_agent_v1.spawn_agent",
        },
    }


def add_agent(spec, *, agent_id, governance_role, node_id, tools):
    spec["delegation"]["agent_registry"].append({
        "id": agent_id,
        "display_name": agent_id.replace("-", " ").title(),
        "specialization": agent_id,
        "governance_role": governance_role,
        "rationale": f"Node {node_id} requires an isolated specialist.",
        "prompt_ref": f".codex-loop/subagents/{agent_id}.md",
        "activation_policy": "on_demand",
        "activation_nodes": [node_id],
        "allowed_tools": tools,
    })


def four_agent_payload() -> dict:
    payload = load_example("agent_loop.json")
    spec = payload["loop_spec"]
    spec["delegation"]["agent_registry"] = []
    spec["transition_policy"] = {
        "decision_authority": "codex_host_controller",
        "proposal_mode": "model_proposal",
        "proposal_source_nodes": ["choose_next_action"],
        "allowed_targets": ["observe_evidence", "export_passed", "export_stopped"],
        "proposal_schema": {
            "next_node": "string",
            "reason_summary": "string",
            "expected_state_change": "array",
            "requested_tools": "array",
        },
        "controller_validation": "required",
        "fallback_node": "export_stopped",
    }
    spec["termination_control"] = {
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

    nodes = spec["control_flow"]["nodes"]
    for node in nodes:
        node.pop("agent_ref", None)
        if node["id"] == "observe_evidence":
            node["agent_ref"] = "evidence-collector"
            node["state_write_scope"] = ["observations"]
        elif node["id"] == "choose_next_action":
            node["agent_ref"] = "diagnostic-strategist"
    nodes.extend([
        {
            "id": "remediation_plan",
            "kind": "model",
            "role": "implementer",
            "agent_ref": "remediation-architect",
            "objective": "Produce a criterion-scoped remediation plan from the diagnosis.",
            "supports_acceptance_criteria": ["AC-1"],
            "input_schema": {},
            "output_schema": {},
            "allowed_tools": [],
            "state_read_scope": ["observations", "diagnosis"],
            "state_write_scope": ["diagnosis"],
            "evaluator_refs": [],
            "retry_policy_ref": "model_schema_retry",
            "timeout_policy_ref": "model_timeout",
            "checkpoint_before": False,
            "checkpoint_after": False,
        },
        {
            "id": "quality_review",
            "kind": "model",
            "role": "reviewer",
            "agent_ref": "quality-auditor",
            "objective": "Independently evaluate the remediation plan and report evidence.",
            "supports_acceptance_criteria": ["AC-1"],
            "input_schema": {},
            "output_schema": {},
            "allowed_tools": [],
            "state_read_scope": ["observations", "diagnosis"],
            "state_write_scope": [],
            "evaluator_refs": ["observation_coverage_check"],
            "retry_policy_ref": "model_schema_retry",
            "timeout_policy_ref": "model_timeout",
            "checkpoint_before": False,
            "checkpoint_after": False,
        },
    ])
    edges = spec["control_flow"]["edges"]
    edges.insert(3, {
        "from": "choose_next_action",
        "to": "remediation_plan",
        "condition": {"all": [{"fact": "state.progress_detected", "operator": "eq", "value": True}]},
        "priority": 25,
    })
    edges.extend([
        {
            "from": "remediation_plan",
            "to": "quality_review",
            "condition": {"all": [{"fact": "state.progress_detected", "operator": "eq", "value": True}]},
            "priority": 10,
        },
        {
            "from": "quality_review",
            "to": "observe_evidence",
            "condition": {"all": [{"fact": "state.acceptance_passed", "operator": "eq", "value": False}]},
            "priority": 10,
        },
    ])
    spec["control_flow"]["cycles"][0]["node_ids"].extend(
        ["remediation_plan", "quality_review"]
    )
    binding = spec["evaluation"]["criteria_bindings"][0]
    binding["evaluator_node"] = "quality_review"
    binding["subject_nodes"] = ["remediation_plan"]
    add_agent(spec, agent_id="evidence-collector", governance_role="verifier", node_id="observe_evidence", tools=["read_observation"])
    add_agent(spec, agent_id="diagnostic-strategist", governance_role="planner", node_id="choose_next_action", tools=[])
    add_agent(spec, agent_id="remediation-architect", governance_role="implementer", node_id="remediation_plan", tools=[])
    add_agent(spec, agent_id="quality-auditor", governance_role="reviewer", node_id="quality_review", tools=[])
    return payload


class DesignResultValidationTests(unittest.TestCase):
    def test_accepts_arbitrary_professional_ids_and_more_than_three_agents(self) -> None:
        payload = four_agent_payload()

        validate_design_result(payload, load_request("agent_loop.json"))

        self.assertEqual(len(payload["loop_spec"]["delegation"]["agent_registry"]), 4)

    def test_bound_agent_roles_require_subagent_capability_and_reasoning_contract(self) -> None:
        payload = load_example("agent_loop.json")
        request = load_request("agent_loop.json")
        request["runtime_capabilities"]["subagents"] = True
        request["runtime_capabilities"][
            "required_subagent_reasoning_intensity"
        ] = "extended_thought"
        payload["loop_spec"]["runtime_binding"]["capabilities_snapshot"] = copy.deepcopy(
            request["runtime_capabilities"]
        )
        requirements = payload["loop_spec"]["runtime_binding"]["required_capabilities"]
        requirements["subagents"] = True
        requirements["required_subagent_reasoning_intensity"] = "extended_thought"

        cases = {
            "runtime capability": ("subagents capability", lambda result, raw: (
                raw["runtime_capabilities"].update({
                    "subagents": False,
                    "required_subagent_reasoning_intensity": None,
                }),
                raw.update({"known_context": [{
                    "source": "tool_search",
                    "query": "spawn_agent spawn_subagent subagent multi_agent",
                    "result": "no_host_native_lifecycle_tool_found",
                }]}),
                result["loop_spec"]["runtime_binding"].update({
                    "capabilities_snapshot": copy.deepcopy(raw["runtime_capabilities"])
                }),
                result["loop_spec"]["runtime_binding"]["required_capabilities"].pop("subagents"),
                result["loop_spec"]["runtime_binding"]["required_capabilities"].pop(
                    "required_subagent_reasoning_intensity"
                ),
            )),
            "required capability": ("require subagents explicitly", lambda result, raw: (
                result["loop_spec"]["runtime_binding"]["required_capabilities"].pop("subagents"),
            )),
            "snapshot reasoning": ("reasoning intensity is unavailable", lambda result, raw: (
                raw["runtime_capabilities"].update({
                    "required_subagent_reasoning_intensity": None
                }),
                result["loop_spec"]["runtime_binding"].update({
                    "capabilities_snapshot": copy.deepcopy(raw["runtime_capabilities"])
                }),
            )),
            "required reasoning": ("extended_thought", lambda result, raw: (
                result["loop_spec"]["runtime_binding"]["required_capabilities"].pop(
                    "required_subagent_reasoning_intensity"
                ),
            )),
        }
        for name, (message, mutate) in cases.items():
            with self.subTest(name=name):
                invalid_payload = copy.deepcopy(payload)
                invalid_request = copy.deepcopy(request)
                mutate(invalid_payload, invalid_request)
                with self.assertRaisesRegex(DesignValidationError, message):
                    validate_design_result(invalid_payload, invalid_request)

    def test_rejects_subagents_true_with_negative_discovery_evidence(self) -> None:
        payload = load_example("agent_loop.json")
        request = load_request("agent_loop.json")
        request["known_context"] = [{
            "source": "tool_search",
            "query": "spawn_agent spawn_subagent subagent multi_agent",
            "result": "no_host_native_lifecycle_tool_found",
        }]

        with self.assertRaisesRegex(DesignValidationError, "contradicts.*subagents=true"):
            validate_design_result(payload, request)

    def test_rejects_subagents_true_without_affirmative_discovery_evidence(self) -> None:
        payload = load_example("agent_loop.json")
        request = load_request("agent_loop.json")
        request["known_context"] = []

        with self.assertRaisesRegex(DesignValidationError, "host_native_lifecycle_tool_found"):
            validate_design_result(payload, request)

    def test_accepts_subagents_true_with_affirmative_discovery_evidence(self) -> None:
        payload = load_example("agent_loop.json")
        request = load_request("agent_loop.json")
        request["known_context"] = [affirmative_subagent_discovery()]

        validate_design_result(payload, request)

    def test_rejects_unknown_agent_ref(self) -> None:
        payload = four_agent_payload()
        payload["loop_spec"]["control_flow"]["nodes"][0]["agent_ref"] = "missing-specialist"

        with self.assertRaisesRegex(DesignValidationError, "unknown agent_ref"):
            validate_design_result(payload, load_request("agent_loop.json"))

    def test_rejects_agent_governance_role_mismatch(self) -> None:
        payload = four_agent_payload()
        payload["loop_spec"]["delegation"]["agent_registry"][0]["governance_role"] = "planner"

        with self.assertRaisesRegex(DesignValidationError, "governance role"):
            validate_design_result(payload, load_request("agent_loop.json"))

    def test_rejects_orphan_registry_entry(self) -> None:
        payload = four_agent_payload()
        add_agent(
            payload["loop_spec"],
            agent_id="orphan-specialist",
            governance_role="planner",
            node_id="observe_evidence",
            tools=[],
        )

        with self.assertRaisesRegex(DesignValidationError, "bound back"):
            validate_design_result(payload, load_request("agent_loop.json"))

    def test_rejects_duplicate_role_signature(self) -> None:
        payload = four_agent_payload()
        duplicate = copy.deepcopy(payload["loop_spec"]["delegation"]["agent_registry"][1])
        duplicate["id"] = "alternate-strategist"
        duplicate["display_name"] = "Alternate Strategist"
        duplicate["prompt_ref"] = ".codex-loop/subagents/alternate-strategist.md"
        payload["loop_spec"]["delegation"]["agent_registry"].append(duplicate)

        with self.assertRaisesRegex(DesignValidationError, "duplicate role signature"):
            validate_design_result(payload, load_request("agent_loop.json"))

    def test_rejects_missing_subject_nodes(self) -> None:
        payload = four_agent_payload()
        payload["loop_spec"]["evaluation"]["criteria_bindings"][0].pop("subject_nodes")

        with self.assertRaisesRegex(DesignValidationError, "subject_nodes"):
            validate_design_result(payload, load_request("agent_loop.json"))

    def test_rejects_implementer_self_evaluation_through_second_node(self) -> None:
        payload = four_agent_payload()
        spec = payload["loop_spec"]
        for node in spec["control_flow"]["nodes"]:
            if node["id"] == "quality_review":
                node["agent_ref"] = "remediation-architect"
                node["role"] = "implementer"
        spec["delegation"]["agent_registry"][2]["activation_nodes"].append("quality_review")
        spec["delegation"]["agent_registry"] = [
            agent for agent in spec["delegation"]["agent_registry"]
            if agent["id"] != "quality-auditor"
        ]

        with self.assertRaisesRegex(DesignValidationError, "independent agent"):
            validate_design_result(payload, load_request("agent_loop.json"))

    def test_rejects_reviewer_transition_proposals(self) -> None:
        payload = four_agent_payload()
        payload["loop_spec"]["transition_policy"]["proposal_source_nodes"] = ["quality_review"]

        with self.assertRaisesRegex(DesignValidationError, "evidence-only"):
            validate_design_result(payload, load_request("agent_loop.json"))

    def test_rejects_reviewer_writes_to_controller_owned_state(self) -> None:
        payload = four_agent_payload()
        for node in payload["loop_spec"]["control_flow"]["nodes"]:
            if node["id"] == "quality_review":
                node["state_write_scope"] = ["acceptance_passed"]

        with self.assertRaisesRegex(DesignValidationError, "controller-owned"):
            validate_design_result(payload, load_request("agent_loop.json"))

    def test_rejects_missing_termination_control(self) -> None:
        payload = four_agent_payload()
        payload["loop_spec"].pop("termination_control")

        with self.assertRaisesRegex(DesignValidationError, "termination_control"):
            validate_design_result(payload, load_request("agent_loop.json"))

    def test_rejects_tampered_effective_request(self) -> None:
        request = minimal_request()
        effective, report = normalize_design_request(request)
        effective["budget_envelope"] = {}
        with self.assertRaisesRegex(DesignValidationError, "does not match deterministic normalization"):
            _validate_design_result(
                load_example("one_shot.json"),
                effective,
                raw_request=request,
                normalization_report=report,
            )

    def test_rejects_tampered_normalization_report(self) -> None:
        raw_request = load_request("one_shot.json")
        effective, report = normalize_design_request(raw_request)
        report["raw_request_hash"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(DesignValidationError, "normalization report does not match"):
            _validate_design_result(
                load_example("one_shot.json"),
                effective,
                raw_request=raw_request,
                normalization_report=report,
            )

    def test_all_published_examples_are_valid_against_matching_requests(self) -> None:
        expected = {
            "one_shot.json": "one_shot",
            "workflow.json": "workflow",
            "agent_loop.json": "agent_loop",
            "needs_input.json": "needs_input",
            "unsupported.json": "unsupported",
        }
        for filename, disposition in expected.items():
            with self.subTest(filename=filename):
                payload = load_example(filename)
                validate_design_result(payload, load_request(filename))
                self.assertEqual(payload["disposition"], disposition)

    def test_rejects_non_null_loop_spec_for_one_shot(self) -> None:
        payload = load_example("one_shot.json")
        payload["loop_spec"] = copy.deepcopy(load_example("workflow.json")["loop_spec"])
        with self.assertRaisesRegex(DesignValidationError, "one_shot.*null"):
            validate_design_result(payload, minimal_request())

    def test_rejects_mandatory_criterion_without_evidence(self) -> None:
        payload = load_example("one_shot.json")
        payload["task_contract"]["acceptance_criteria"][0]["evidence_requirements"] = []
        with self.assertRaisesRegex(DesignValidationError, "evidence"):
            validate_design_result(payload, minimal_request())

    def test_rejects_one_shot_plan_that_does_not_cover_every_mandatory_criterion(self) -> None:
        payload = load_example("one_shot.json")
        payload["one_shot_validation_plan"]["checks"][1]["verifies"] = ["AC-1"]
        with self.assertRaisesRegex(DesignValidationError, "mandatory criterion"):
            validate_design_result(payload, minimal_request())

    def test_rejects_disposition_and_build_status_mismatch(self) -> None:
        payload = load_example("one_shot.json")
        payload["build_report"]["status"] = "spec_ready"
        with self.assertRaisesRegex(DesignValidationError, "build status"):
            validate_design_result(payload, minimal_request())

    def test_rejects_spec_ready_without_valid_static_report(self) -> None:
        payload = load_example("workflow.json")
        payload["validation_report"]["valid"] = False
        payload["validation_report"]["errors"] = ["broken graph"]
        with self.assertRaisesRegex(DesignValidationError, "spec_ready"):
            validate_design_result(payload, load_request("workflow.json"))

    def test_rejects_executable_spec_for_unsupported(self) -> None:
        payload = load_example("unsupported.json")
        payload["loop_spec"] = copy.deepcopy(load_example("workflow.json")["loop_spec"])
        with self.assertRaisesRegex(DesignValidationError, "must be null"):
            validate_design_result(payload, load_request("unsupported.json"))

    def test_rejects_runtime_snapshot_that_differs_from_request(self) -> None:
        payload = load_example("workflow.json")
        payload["loop_spec"]["runtime_binding"]["capabilities_snapshot"][
            "available_tools"
        ] = ["invented_tool"]
        with self.assertRaisesRegex(DesignValidationError, "capabilities_snapshot"):
            validate_design_result(payload, minimal_request())

    def test_rejects_unavailable_runtime_capabilities(self) -> None:
        mutations = {
            "durable_state": lambda spec: spec["state"].update({"persistence": "durable"}),
            "checkpoint_resume": lambda spec: spec["control_flow"]["nodes"][0].update(
                {"checkpoint_before": True}
            ),
            "human_interrupt": lambda spec: spec["architecture"]["control_gates"].append(
                "human_approval"
            ),
            "parallel_execution": lambda spec: spec["architecture"]["topology"].update(
                {"type": "parallel", "parallel_mode": "sectioning"}
            ),
            "subagents": lambda spec: spec["delegation"].update({"enabled": True}),
            "sandbox": lambda spec: spec["runtime_binding"]["required_capabilities"].update(
                {"sandbox": True}
            ),
        }
        for capability, mutate in mutations.items():
            with self.subTest(capability=capability):
                payload = load_example("workflow.json")
                mutate(payload["loop_spec"])
                with self.assertRaisesRegex(DesignValidationError, capability):
                    validate_design_result(payload, minimal_request())

    def test_rejects_unregistered_tool_binding(self) -> None:
        payload = load_example("workflow.json")
        node = payload["loop_spec"]["control_flow"]["nodes"][0]
        node["kind"] = "tool"
        node["allowed_tools"] = ["missing_tool"]
        with self.assertRaisesRegex(DesignValidationError, "missing_tool"):
            validate_design_result(payload, minimal_request())

    def test_rejects_invalid_orthogonal_architecture_value(self) -> None:
        payload = load_example("workflow.json")
        payload["loop_spec"]["architecture"]["execution_patterns"] = [
            "orchestrator_workers"
        ]
        with self.assertRaisesRegex(DesignValidationError, "execution_patterns"):
            validate_design_result(payload, minimal_request())

    def test_rejects_free_form_edge_condition(self) -> None:
        payload = load_example("workflow.json")
        payload["loop_spec"]["control_flow"]["edges"][0]["condition"] = (
            "decide whether it is good enough"
        )
        with self.assertRaisesRegex(DesignValidationError, "structured condition"):
            validate_design_result(payload, minimal_request())

    def test_rejects_structured_condition_with_non_observable_fact(self) -> None:
        payload = load_example("workflow.json")
        payload["loop_spec"]["control_flow"]["edges"][0]["condition"] = {
            "all": [{"fact": "model.feels_good", "operator": "eq", "value": True}]
        }
        with self.assertRaisesRegex(DesignValidationError, "controller-observable"):
            validate_design_result(payload, minimal_request())

    def test_checkpoint_design_requires_durable_state_as_well_as_resume(self) -> None:
        payload = load_example("workflow.json")
        payload["loop_spec"]["control_flow"]["nodes"][0]["checkpoint_before"] = True
        request = minimal_request(checkpoint_resume=True, durable_state=False)
        payload["loop_spec"]["runtime_binding"]["capabilities_snapshot"] = copy.deepcopy(
            request["runtime_capabilities"]
        )
        with self.assertRaisesRegex(DesignValidationError, "durable_state"):
            validate_design_result(payload, request)

    def test_rejects_out_of_order_edge_priorities(self) -> None:
        payload = load_example("agent_loop.json")
        edges = payload["loop_spec"]["control_flow"]["edges"]
        source_indexes = [index for index, edge in enumerate(edges) if edge["from"] == "choose_next_action"]
        edges[source_indexes[0]], edges[source_indexes[-1]] = (
            edges[source_indexes[-1]],
            edges[source_indexes[0]],
        )
        with self.assertRaisesRegex(DesignValidationError, "priority order"):
            validate_design_result(payload, load_request("agent_loop.json"))

    def test_rejects_missing_acceptance_binding(self) -> None:
        payload = load_example("workflow.json")
        payload["loop_spec"]["evaluation"]["criteria_bindings"] = []
        with self.assertRaisesRegex(DesignValidationError, "mandatory criterion"):
            validate_design_result(payload, minimal_request())

    def test_rejects_unresolved_policy_or_threshold_reference(self) -> None:
        payload = load_example("agent_loop.json")
        payload["loop_spec"]["control_flow"]["cycles"][0]["budget_policy_ref"] = (
            "missing_budget"
        )
        with self.assertRaisesRegex(DesignValidationError, "missing_budget"):
            validate_design_result(payload, load_request("agent_loop.json"))

    def test_rejects_unreachable_node(self) -> None:
        payload = load_example("workflow.json")
        orphan = copy.deepcopy(payload["loop_spec"]["control_flow"]["nodes"][-1])
        orphan["id"] = "orphan_terminal"
        payload["loop_spec"]["control_flow"]["nodes"].append(orphan)
        payload["loop_spec"]["control_flow"]["terminal_nodes"]["stopped"].append(
            "orphan_terminal"
        )
        with self.assertRaisesRegex(DesignValidationError, "unreachable"):
            validate_design_result(payload, minimal_request())

    def test_rejects_dangling_edge(self) -> None:
        payload = load_example("workflow.json")
        payload["loop_spec"]["control_flow"]["edges"][0]["to"] = "missing_node"
        with self.assertRaisesRegex(DesignValidationError, "undefined node"):
            validate_design_result(payload, minimal_request())

    def test_allows_declared_controlled_agent_loop_cycle(self) -> None:
        validate_design_result(load_example("agent_loop.json"), load_request("agent_loop.json"))

    def test_rejects_undeclared_agent_loop_cycle(self) -> None:
        payload = load_example("agent_loop.json")
        payload["loop_spec"]["control_flow"]["cycles"] = []
        with self.assertRaisesRegex(DesignValidationError, "undeclared directed cycle"):
            validate_design_result(payload, load_request("agent_loop.json"))

    def test_rejects_subagents_false_without_tool_search_discovery_evidence(self) -> None:
        payload = load_example("one_shot.json")
        request = minimal_request()
        request["known_context"] = []
        payload["assumptions"] = []
        payload["validation_report"]["assumptions"] = []

        with self.assertRaisesRegex(
            DesignValidationError,
            "no_host_native_lifecycle_tool_found",
        ):
            validate_design_result(payload, request)

    def test_accepts_subagents_false_when_tool_search_evidence_is_in_result_assumptions(self) -> None:
        payload = load_example("one_shot.json")
        request = minimal_request()
        request["known_context"] = []
        payload["assumptions"] = [
            "tool_search queried spawn_agent, spawn_subagent, subagent, and multi_agent; result=no_host_native_lifecycle_tool_found"
        ]

        validate_design_result(payload, request)

    def test_rejects_agent_loop_without_four_hard_limits(self) -> None:
        payload = load_example("agent_loop.json")
        request = load_request("agent_loop.json")
        request["budget_envelope"].pop("max_no_progress_loops", None)

        with self.assertRaisesRegex(DesignValidationError, "max_no_progress_loops"):
            validate_design_result(payload, request)

    def test_rejects_agent_loop_without_deterministic_progress_fact(self) -> None:
        payload = load_example("agent_loop.json")
        payload["loop_spec"]["control_flow"]["cycles"][0]["progress_signals"] = [
            {
                "fact": "state.semantic_confidence",
                "operator": "changes",
                "evidence_ref": "model_self_report",
            }
        ]

        with self.assertRaisesRegex(DesignValidationError, "deterministic progress"):
            validate_design_result(payload, load_request("agent_loop.json"))

    def test_rejects_implementer_without_reviewer_or_verifier(self) -> None:
        payload = load_example("agent_loop.json")
        nodes = payload["loop_spec"]["control_flow"]["nodes"]
        for node in nodes:
            if node["id"] == "observe_evidence":
                node["role"] = "planner"
            elif node["id"] == "choose_next_action":
                node["role"] = "implementer"
        registry = payload["loop_spec"]["delegation"]["agent_registry"]
        registry[0]["governance_role"] = "planner"
        registry[1]["governance_role"] = "implementer"
        with self.assertRaisesRegex(DesignValidationError, "reviewer or verifier"):
            validate_design_result(payload, load_request("agent_loop.json"))

    def test_rejects_reviewer_with_write_tools(self) -> None:
        payload = load_example("agent_loop.json")
        for node in payload["loop_spec"]["control_flow"]["nodes"]:
            if node["id"] == "observe_evidence":
                node["role"] = "reviewer"
                node["allowed_tools"] = ["edit_files"]
        agent = payload["loop_spec"]["delegation"]["agent_registry"][0]
        agent["governance_role"] = "reviewer"
        agent["allowed_tools"] = ["edit_files"]
        payload["loop_spec"]["tools"]["contracts"].append(
            {
                "id": "edit_files",
                "side_effect": "workspace_write",
                "access_mode": "workspace_write",
                "controller_executes": True,
            }
        )
        request = load_request("agent_loop.json")
        request["runtime_capabilities"]["available_tools"].append("edit_files")
        request["runtime_capabilities"]["tool_access_modes"]["edit_files"] = "workspace_write"
        request["policy_constraints"]["allowed_side_effects"].append("workspace_write")
        payload["loop_spec"]["runtime_binding"]["capabilities_snapshot"] = copy.deepcopy(
            request["runtime_capabilities"]
        )

        with self.assertRaisesRegex(DesignValidationError, "read-only"):
            validate_design_result(payload, request)

    def test_rejects_reviewer_with_indirect_shell_write_capability(self) -> None:
        payload = load_example("agent_loop.json")
        for node in payload["loop_spec"]["control_flow"]["nodes"]:
            if node["id"] == "observe_evidence":
                node["role"] = "reviewer"
                node["allowed_tools"] = ["shell_command"]
        agent = payload["loop_spec"]["delegation"]["agent_registry"][0]
        agent["governance_role"] = "reviewer"
        agent["allowed_tools"] = ["shell_command"]
        payload["loop_spec"]["tools"]["contracts"].append(
            {
                "id": "shell_command",
                "side_effect": "workspace_write",
                "access_mode": "workspace_write",
                "controller_executes": True,
            }
        )
        request = load_request("agent_loop.json")
        request["runtime_capabilities"]["available_tools"].append("shell_command")
        request["runtime_capabilities"]["tool_access_modes"]["shell_command"] = "workspace_write"
        request["policy_constraints"]["allowed_side_effects"].append("workspace_write")
        payload["loop_spec"]["runtime_binding"]["capabilities_snapshot"] = copy.deepcopy(
            request["runtime_capabilities"]
        )

        with self.assertRaisesRegex(DesignValidationError, "non-read-only tools"):
            validate_design_result(payload, request)

    def test_defaulted_budget_threshold_sources_are_enforced(self) -> None:
        raw_request = load_request("agent_loop.json")
        for field in [
            "max_runtime_seconds",
            "max_iterations",
            "max_token_budget",
            "max_no_progress_loops",
        ]:
            del raw_request["budget_envelope"][field]
        effective, report = normalize_design_request(raw_request)
        payload = load_example("agent_loop.json")
        for threshold in payload["loop_spec"]["threshold_register"]:
            if threshold["id"] in report["defaults_applied"]:
                threshold["value"] = effective["budget_envelope"][threshold["id"]]
                threshold["source"] = "default_policy:codex-native-safe-v1"
        _validate_design_result(
            payload,
            effective,
            raw_request=raw_request,
            normalization_report=report,
        )

        for threshold in payload["loop_spec"]["threshold_register"]:
            if threshold["id"] == "max_iterations":
                threshold["source"] = "user_explicit"
        with self.assertRaisesRegex(DesignValidationError, "source must be"):
            _validate_design_result(
                payload,
                effective,
                raw_request=raw_request,
                normalization_report=report,
            )

    def test_subagent_requirement_needs_extended_reasoning(self) -> None:
        payload = load_example("agent_loop.json")
        request = load_request("agent_loop.json")
        request["runtime_capabilities"][
            "required_subagent_reasoning_intensity"
        ] = None
        payload["loop_spec"]["runtime_binding"]["capabilities_snapshot"] = copy.deepcopy(
            request["runtime_capabilities"]
        )
        payload["loop_spec"]["runtime_binding"]["required_capabilities"][
            "required_subagent_reasoning_intensity"
        ] = None

        with self.assertRaisesRegex(DesignValidationError, "extended_thought"):
            validate_design_result(payload, request)

    def test_rejects_implementer_as_mandatory_evaluator(self) -> None:
        payload = load_example("agent_loop.json")
        for node in payload["loop_spec"]["control_flow"]["nodes"]:
            if node["id"] == "observe_evidence":
                node["role"] = "reviewer"
            elif node["id"] == "choose_next_action":
                node["role"] = "implementer"
        registry = payload["loop_spec"]["delegation"]["agent_registry"]
        registry[0]["governance_role"] = "reviewer"
        registry[1]["governance_role"] = "implementer"
        payload["loop_spec"]["evaluation"]["criteria_bindings"][0][
            "evaluator_node"
        ] = "choose_next_action"
        payload["loop_spec"]["evaluation"]["criteria_bindings"][0][
            "subject_nodes"
        ] = ["observe_evidence"]

        with self.assertRaisesRegex(DesignValidationError, "reviewer or verifier"):
            validate_design_result(payload, load_request("agent_loop.json"))


if __name__ == "__main__":
    unittest.main()
