"""Contract and semantic tests for validate_design_result.py."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from validate_design_result import DesignValidationError, validate_design_result


SKILL_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = SKILL_ROOT / "examples"
REQUESTS = EXAMPLES / "requests"


def load_example(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def load_request(name: str) -> dict:
    return json.loads((REQUESTS / name).read_text(encoding="utf-8"))


def minimal_request(**capability_overrides: object) -> dict:
    capabilities = {
        "available_tools": [],
        "durable_state": False,
        "checkpoint_resume": False,
        "sandbox": False,
        "human_interrupt": False,
        "parallel_execution": False,
        "subagents": False,
    }
    capabilities.update(capability_overrides)
    return {
        "request_id": "unit-test-request",
        "task_prompt": "Build a static design only.",
        "known_context": [],
        "runtime_capabilities": capabilities,
        "policy_constraints": {
            "allowed_side_effects": [],
            "forbidden_actions": [],
            "approval_rules": [],
        },
        "budget_envelope": {},
        "output_requirements": {},
    }


class DesignResultValidationTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
