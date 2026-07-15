#!/usr/bin/env python3
"""Validate authoritative v3 loop-progress evidence for a `.codex-loop/` scaffold.

This is a post-hoc trace judge, not a Runtime Engine. It groups samples by run
and cycle, verifies sequence completeness, and rejects all four hard-limit
violations using the thresholds persisted in the LoopSpec.
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from governance_contracts import canonical_json_digest


PROGRESS_SCHEMA_VERSION = "3.0.0"
HARD_LIMITS = {
    "max_runtime_seconds",
    "max_iterations",
    "max_token_budget",
    "max_no_progress_loops",
}
REQUIRED_SAMPLE_FIELDS = {
    "schema_version",
    "evidence_type",
    "config_version",
    "loop_spec_digest",
    "run_id",
    "cycle_id",
    "iteration",
    "cycle_iteration",
    "observed_at",
    "measurement_source",
    "token_count_quality",
    "elapsed_runtime_seconds",
    "cumulative_token_count",
    "artifact_hash",
    "diff_fingerprint",
    "test_count",
    "new_evidence_count",
}
SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


class ProgressValidationError(AssertionError):
    """Raised when loop progress evidence violates its static contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ProgressValidationError(message)


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProgressValidationError(f"missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ProgressValidationError(f"invalid JSON in {path}: {exc}") from exc
    require(isinstance(payload, dict), f"{path} must contain a JSON object")
    return payload


def load_hard_limits(loop_spec: dict[str, Any]) -> dict[str, int]:
    limits: dict[str, int] = {}
    for raw in loop_spec.get("threshold_register", []):
        if not isinstance(raw, dict) or raw.get("id") not in HARD_LIMITS:
            continue
        threshold_id = raw["id"]
        require(threshold_id not in limits, f"duplicate threshold_register entry: {threshold_id}")
        value = raw.get("value")
        require(
            isinstance(value, int) and not isinstance(value, bool) and value >= 1,
            f"threshold_register.{threshold_id} must be a positive integer",
        )
        limits[threshold_id] = value
    missing = sorted(HARD_LIMITS - set(limits))
    require(not missing, f"missing hard limit threshold(s): {missing}")
    return limits


def declared_cycle_ids(loop_spec: dict[str, Any]) -> set[str]:
    cycles = loop_spec.get("control_flow", {}).get("cycles", [])
    cycle_ids = {
        item.get("id")
        for item in cycles
        if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"]
    }
    require(cycle_ids, "LoopSpec must declare at least one cycle for progress evidence")
    return cycle_ids


def progress_files(root: Path) -> list[Path]:
    progress_root = root / "evidence" / "progress"
    require(progress_root.is_dir(), f"progress evidence directory not found: {progress_root}")
    files = sorted(progress_root.glob("*.json"))
    require(files, "progress evidence directory must contain at least one JSON file")
    return files


def _positive_integer(value: Any, path: str) -> int:
    require(isinstance(value, int) and not isinstance(value, bool) and value >= 1, f"{path} must be a positive integer")
    return value


def _non_negative_integer(value: Any, path: str) -> int:
    require(isinstance(value, int) and not isinstance(value, bool) and value >= 0, f"{path} must be a non-negative integer")
    return value


def normalize_sample(path: Path) -> dict[str, Any]:
    sample = load_json(path)
    require(set(sample) == REQUIRED_SAMPLE_FIELDS, f"{path}: progress fields must exactly match v2 contract; missing={sorted(REQUIRED_SAMPLE_FIELDS - set(sample))}, extra={sorted(set(sample) - REQUIRED_SAMPLE_FIELDS)}")
    require(sample["schema_version"] == PROGRESS_SCHEMA_VERSION, f"{path}: schema_version must be {PROGRESS_SCHEMA_VERSION}")
    require(sample["evidence_type"] == "progress_sample", f"{path}: evidence_type must be progress_sample")
    for key in ["run_id", "cycle_id"]:
        require(isinstance(sample[key], str) and sample[key], f"{path}: {key} must be a non-empty string")
    _positive_integer(sample["iteration"], f"{path}: iteration")
    _positive_integer(sample["cycle_iteration"], f"{path}: cycle_iteration")
    _positive_integer(sample["config_version"], f"{path}: config_version")
    for key in ["elapsed_runtime_seconds", "cumulative_token_count", "test_count", "new_evidence_count"]:
        _non_negative_integer(sample[key], f"{path}: {key}")
    for key in ["artifact_hash", "diff_fingerprint"]:
        require(isinstance(sample[key], str) and SHA256_PATTERN.fullmatch(sample[key]) is not None, f"{path}: {key} must be a lowercase sha256 digest")
    require(sample["measurement_source"] in {"host_api", "controller_counter"}, f"{path}: measurement_source must be host_api or controller_counter")
    require(sample["token_count_quality"] == "authoritative", f"{path}: token_count_quality must be authoritative")
    try:
        datetime.fromisoformat(sample["observed_at"].replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ProgressValidationError(f"{path}: observed_at must be an ISO-8601 timestamp") from exc
    return sample


def is_no_progress(previous: dict[str, Any], current: dict[str, Any]) -> bool:
    return (
        previous["artifact_hash"] == current["artifact_hash"]
        and previous["diff_fingerprint"] == current["diff_fingerprint"]
        and previous["test_count"] == current["test_count"]
        and current["new_evidence_count"] == 0
    )


def _require_contiguous(values: list[int], label: str) -> None:
    expected = list(range(1, len(values) + 1))
    require(values == expected, f"{label} must be contiguous from 1; observed={values}")


def validate_progress(root: Path) -> None:
    root = root.resolve()
    require(root.is_dir(), f"scaffold directory not found: {root}")
    require(root.name in {".codex-loop", "codex-loop"}, "scaffold directory must be named .codex-loop")
    loop_spec = load_json(root / "loop_spec.json")
    manifest = load_json(root / "agent_manifest.json")
    binding = manifest.get("configuration_binding")
    require(isinstance(binding, dict), "agent_manifest.configuration_binding must be present")
    expected_version = binding.get("config_version")
    expected_digest = canonical_json_digest(loop_spec)
    require(binding.get("loop_spec_digest") == expected_digest, "manifest LoopSpec digest is stale")
    limits = load_hard_limits(loop_spec)
    cycle_ids = declared_cycle_ids(loop_spec)
    samples = [normalize_sample(path) for path in progress_files(root)]

    runs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for sample in samples:
        require(sample["cycle_id"] in cycle_ids, f"progress sample references undeclared cycle: {sample['cycle_id']}")
        require(sample["config_version"] == expected_version, "progress evidence config_version mismatch")
        require(sample["loop_spec_digest"] == expected_digest, "progress evidence LoopSpec digest mismatch")
        runs[sample["run_id"]].append(sample)

    for run_id, run_samples in runs.items():
        run_samples.sort(key=lambda item: item["iteration"])
        _require_contiguous([item["iteration"] for item in run_samples], f"run {run_id!r} iteration")
        require(len(run_samples) <= limits["max_iterations"], f"max_iterations exceeded: {len(run_samples)} > {limits['max_iterations']}")

        cycle_iterations: dict[str, list[int]] = defaultdict(list)
        previous_global: dict[str, Any] | None = None
        previous_by_cycle: dict[str, dict[str, Any]] = {}
        stalled_by_cycle: dict[str, int] = defaultdict(int)
        for sample in run_samples:
            cycle_id = sample["cycle_id"]
            cycle_iterations[cycle_id].append(sample["cycle_iteration"])
            require(sample["elapsed_runtime_seconds"] <= limits["max_runtime_seconds"], f"max_runtime_seconds exceeded: {sample['elapsed_runtime_seconds']} > {limits['max_runtime_seconds']}")
            require(sample["cumulative_token_count"] <= limits["max_token_budget"], f"max_token_budget exceeded: {sample['cumulative_token_count']} > {limits['max_token_budget']}")
            if previous_global is not None:
                require(sample["elapsed_runtime_seconds"] >= previous_global["elapsed_runtime_seconds"], "elapsed_runtime_seconds must be monotonic within a run")
                require(sample["cumulative_token_count"] >= previous_global["cumulative_token_count"], "cumulative_token_count must be monotonic within a run")
            previous_cycle = previous_by_cycle.get(cycle_id)
            if previous_cycle is not None and is_no_progress(previous_cycle, sample):
                stalled_by_cycle[cycle_id] += 1
            else:
                stalled_by_cycle[cycle_id] = 0
            require(stalled_by_cycle[cycle_id] <= limits["max_no_progress_loops"], f"max_no_progress_loops exceeded for cycle {cycle_id!r}: {stalled_by_cycle[cycle_id]} > {limits['max_no_progress_loops']}")
            previous_by_cycle[cycle_id] = sample
            previous_global = sample

        for cycle_id, values in cycle_iterations.items():
            _require_contiguous(values, f"run {run_id!r} cycle {cycle_id!r} cycle_iteration")


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: validate_loop_progress_evidence.py path/to/.codex-loop", file=sys.stderr)
        return 2
    try:
        validate_progress(Path(argv[1]))
    except ProgressValidationError as exc:
        print(f"ERROR: Progress Evidence Error: {exc}")
        return 1
    print("OK: loop progress evidence validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
