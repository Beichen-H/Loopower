#!/usr/bin/env python3
"""Materialize a strict Loop_design_request without mutating its source.

This is a deterministic design-time gateway, not a validator or Runtime Engine.
It fills only missing loop-budget fields, records provenance, and rejects invalid
explicit values instead of silently replacing them.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


DEFAULT_POLICY_ID = "codex-native-safe-v1"
NORMALIZER_VERSION = "2.0.0"
DEFAULT_BUDGET_ENVELOPE: dict[str, int] = {
    "max_runtime_seconds": 900,
    "max_iterations": 3,
    "max_token_budget": 45000,
    "max_no_progress_loops": 1,
}


class RequestNormalizationError(ValueError):
    """Raised when a raw request cannot be normalized safely."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RequestNormalizationError(message)


DEFAULT_RUNTIME_CAPABILITIES: dict[str, Any] = {
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


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def normalize_design_request(raw_request: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return a deep-copied effective request and deterministic provenance."""

    _require(isinstance(raw_request, dict), "raw request must be a JSON object")
    effective = copy.deepcopy(raw_request)
    raw_capabilities = effective.get("runtime_capabilities")
    if raw_capabilities is None:
        raw_capabilities = {}
        effective["runtime_capabilities"] = raw_capabilities
    _require(isinstance(raw_capabilities, dict), "runtime_capabilities must be a JSON object when provided")
    for field, default_value in DEFAULT_RUNTIME_CAPABILITIES.items():
        if field not in raw_capabilities:
            raw_capabilities[field] = copy.deepcopy(default_value)
    _require(
        isinstance(raw_capabilities["available_tools"], list)
        and all(isinstance(item, str) and item for item in raw_capabilities["available_tools"]),
        "runtime_capabilities.available_tools must be an array of non-empty strings",
    )
    _require(isinstance(raw_capabilities["tool_access_modes"], dict), "runtime_capabilities.tool_access_modes must be an object")
    _require(
        set(raw_capabilities["tool_access_modes"]) == set(raw_capabilities["available_tools"]),
        "runtime_capabilities.tool_access_modes must classify every available tool exactly once",
    )
    for tool_id, access_mode in raw_capabilities["tool_access_modes"].items():
        _require(
            access_mode in {"read_only", "workspace_write", "external_write"},
            f"runtime_capabilities.tool_access_modes.{tool_id} has invalid access mode",
        )
    for field in [
        "durable_state",
        "checkpoint_resume",
        "sandbox",
        "human_interrupt",
        "parallel_execution",
        "subagents",
    ]:
        _require(type(raw_capabilities[field]) is bool, f"runtime_capabilities.{field} must be boolean")
    _require(
        raw_capabilities["required_subagent_reasoning_intensity"] in {None, "extended_thought"},
        "runtime_capabilities.required_subagent_reasoning_intensity must be extended_thought or null",
    )
    raw_budget = effective.get("budget_envelope")
    if raw_budget is None:
        raw_budget = {}
        effective["budget_envelope"] = raw_budget
    _require(isinstance(raw_budget, dict), "budget_envelope must be a JSON object when provided")

    defaults_applied: dict[str, int] = {}
    explicit_fields: list[str] = []
    for field, default_value in DEFAULT_BUDGET_ENVELOPE.items():
        if field not in raw_budget:
            raw_budget[field] = default_value
            defaults_applied[field] = default_value
            continue
        value = raw_budget[field]
        _require(
            isinstance(value, int) and not isinstance(value, bool) and value >= 1,
            f"budget_envelope.{field} must be a positive integer when explicitly provided",
        )
        explicit_fields.append(field)

    report = {
        "schema_version": "2.0.0",
        "normalizer_version": NORMALIZER_VERSION,
        "default_policy_id": DEFAULT_POLICY_ID,
        "raw_request_hash": canonical_hash(raw_request),
        "effective_request_hash": canonical_hash(effective),
        "defaults_applied": defaults_applied,
        "explicit_budget_fields": explicit_fields,
        "source_preserved": True,
    }
    return effective, report


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RequestNormalizationError(f"input file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RequestNormalizationError(f"invalid JSON in {path}: {exc}") from exc
    _require(isinstance(value, dict), "raw request must contain a JSON object")
    return value


def _stage_json(path: Path, value: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return temporary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Normalize a raw request into a strict effective Loop_design_request."
    )
    parser.add_argument("request", type=Path, help="Raw request JSON; never modified")
    parser.add_argument("--output", required=True, type=Path, help="Effective request output JSON")
    parser.add_argument("--report", required=True, type=Path, help="Normalization provenance JSON")
    parser.add_argument("--force", action="store_true", help="Replace existing output/report files")
    args = parser.parse_args(argv)

    try:
        source = args.request.resolve()
        output = args.output.resolve()
        _require(source != output, "--output must differ from the raw request path")
        report_path = args.report.resolve()
        _require(report_path not in {source, output}, "--report must use a distinct path")
        _require(args.force or not output.exists(), f"output already exists: {output}; use --force to replace")
        _require(args.force or not report_path.exists(), f"report already exists: {report_path}; use --force to replace")
        raw = _load_json(source)
        effective, report = normalize_design_request(raw)
        output_stage = _stage_json(output, effective)
        report_stage = _stage_json(report_path, report)
        output_stage.replace(output)
        report_stage.replace(report_path)
    except (OSError, RequestNormalizationError) as exc:
        print(f"ERROR: Loop request normalization failed: {exc}", file=sys.stderr)
        return 1

    print(f"OK: effective Loop_design_request written to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
