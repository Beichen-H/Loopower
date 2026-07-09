#!/usr/bin/env python3
"""Validate post-hoc loop progress fingerprints for a `.codex-loop/` scaffold.

This script is a post-hoc runtime-trace judge, not a Runtime Engine. It reads
persisted progress evidence and rejects stalled loops whose consecutive
no-progress count exceeds the LoopSpec's `max_no_progress_loops` threshold.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


class ProgressValidationError(AssertionError):
    """Raised when loop progress evidence violates stagnation limits."""


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


def load_max_no_progress_loops(loop_spec: dict[str, Any]) -> int:
    for raw in loop_spec.get("threshold_register", []):
        if isinstance(raw, dict) and raw.get("id") == "max_no_progress_loops":
            value = raw.get("value")
            require(
                isinstance(value, int) and not isinstance(value, bool) and value >= 0,
                "threshold_register.max_no_progress_loops must be a non-negative integer",
            )
            return value
    raise ProgressValidationError("missing threshold_register entry: max_no_progress_loops")


def progress_files(root: Path) -> list[Path]:
    progress_root = root / "evidence" / "progress"
    require(progress_root.is_dir(), f"progress evidence directory not found: {progress_root}")
    files = sorted(progress_root.glob("*.json"))
    require(files, "progress evidence directory must contain at least one JSON file")
    return files


def normalize_sample(path: Path) -> dict[str, Any]:
    sample = load_json(path)
    for key in ["artifact_hash", "diff_fingerprint"]:
        require(isinstance(sample.get(key), str) and sample[key], f"{path}: {key} must be a non-empty string")
    for key in ["iteration", "test_count", "new_evidence_count"]:
        value = sample.get(key)
        require(
            isinstance(value, int) and not isinstance(value, bool) and value >= 0,
            f"{path}: {key} must be a non-negative integer",
        )
    return sample


def is_no_progress(previous: dict[str, Any], current: dict[str, Any]) -> bool:
    return (
        previous["artifact_hash"] == current["artifact_hash"]
        and previous["diff_fingerprint"] == current["diff_fingerprint"]
        and previous["test_count"] == current["test_count"]
        and current["new_evidence_count"] == 0
    )


def validate_progress(root: Path) -> None:
    root = root.resolve()
    require(root.is_dir(), f"scaffold directory not found: {root}")
    require(root.name in {".codex-loop", "codex-loop"}, "scaffold directory must be named .codex-loop")
    max_no_progress_loops = load_max_no_progress_loops(load_json(root / "loop_spec.json"))
    samples = [normalize_sample(path) for path in progress_files(root)]
    samples.sort(key=lambda item: item["iteration"])

    consecutive_no_progress = 0
    previous: dict[str, Any] | None = None
    for sample in samples:
        if previous is not None and is_no_progress(previous, sample):
            consecutive_no_progress += 1
        else:
            consecutive_no_progress = 0
        require(
            consecutive_no_progress <= max_no_progress_loops,
            f"max_no_progress_loops exceeded: {consecutive_no_progress} > {max_no_progress_loops}",
        )
        previous = sample


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
