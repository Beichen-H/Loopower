"""Tests for deterministic Loop_design_request normalization."""

from __future__ import annotations

import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

from normalize_design_request import (
    DEFAULT_BUDGET_ENVELOPE,
    RequestNormalizationError,
    normalize_design_request,
)


class NormalizeDesignRequestTests(unittest.TestCase):
    def base_request(self) -> dict:
        return {
            "request_id": "request-1",
            "task_prompt": "Process this project safely.",
            "known_context": [],
            "runtime_capabilities": {},
            "policy_constraints": {
                "allowed_side_effects": [],
                "forbidden_actions": [],
                "approval_rules": [],
            },
            "output_requirements": {},
        }

    def test_missing_budget_is_defaulted_without_mutating_source(self) -> None:
        raw = self.base_request()
        before = copy.deepcopy(raw)

        effective, report = normalize_design_request(raw)

        self.assertEqual(raw, before)
        self.assertEqual(effective["budget_envelope"], DEFAULT_BUDGET_ENVELOPE)
        self.assertEqual(report["defaults_applied"], DEFAULT_BUDGET_ENVELOPE)
        self.assertTrue(report["source_preserved"])
        self.assertNotEqual(report["raw_request_hash"], report["effective_request_hash"])

    def test_explicit_values_are_preserved(self) -> None:
        raw = self.base_request()
        raw["budget_envelope"] = {
            "max_runtime_seconds": 1200,
            "max_iterations": 5,
            "max_token_budget": 80000,
            "max_no_progress_loops": 2,
        }

        effective, report = normalize_design_request(raw)

        self.assertEqual(effective["budget_envelope"], raw["budget_envelope"])
        self.assertEqual(report["defaults_applied"], {})
        self.assertEqual(set(report["explicit_budget_fields"]), set(DEFAULT_BUDGET_ENVELOPE))
        self.assertNotEqual(report["raw_request_hash"], report["effective_request_hash"])
        self.assertIsNone(
            effective["runtime_capabilities"]["required_subagent_reasoning_intensity"]
        )

    def test_partial_budget_receives_only_missing_defaults(self) -> None:
        raw = self.base_request()
        raw["budget_envelope"] = {"max_iterations": 7}

        effective, report = normalize_design_request(raw)

        self.assertEqual(effective["budget_envelope"]["max_iterations"], 7)
        self.assertNotIn("max_iterations", report["defaults_applied"])
        self.assertEqual(report["explicit_budget_fields"], ["max_iterations"])

    def test_invalid_explicit_value_is_not_silently_replaced(self) -> None:
        raw = self.base_request()
        raw["budget_envelope"] = {"max_iterations": 0}

        with self.assertRaisesRegex(RequestNormalizationError, "max_iterations"):
            normalize_design_request(raw)

    def test_cli_refuses_to_overwrite_raw_request(self) -> None:
        from normalize_design_request import main

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "request.json"
            report = Path(tmp) / "report.json"
            path.write_text(json.dumps(self.base_request()), encoding="utf-8")
            with redirect_stderr(io.StringIO()):
                exit_code = main([str(path), "--output", str(path), "--report", str(report)])

        self.assertEqual(exit_code, 1)

    def test_cli_refuses_existing_outputs_without_force(self) -> None:
        from normalize_design_request import main

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "raw.json"
            output = root / "effective.json"
            report = root / "report.json"
            source.write_text(json.dumps(self.base_request()), encoding="utf-8")
            output.write_text("historical", encoding="utf-8")
            with redirect_stderr(io.StringIO()):
                exit_code = main(
                    [str(source), "--output", str(output), "--report", str(report)]
                )

        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
