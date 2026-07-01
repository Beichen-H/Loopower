#!/usr/bin/env python3
"""Validate a lightweight Codex-native .codex-loop scaffold.

This is a static validator. It does not execute the loop, run sub-agents, call
tools, or emulate a Runtime Engine.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


STAGE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@-]*$")
FORBIDDEN_NAMES = {
    "runtime",
    "state.json",
    "checkpoint.json",
    "checkpoints",
    "queue",
    "queues",
    "database",
    "db",
}
REQUIRED_FILES = [
    "loop_spec.json",
    "agent_manifest.json",
    "guardrails.json",
    "subagents/planner.md",
    "subagents/executor.md",
]


class ScaffoldValidationError(AssertionError):
    """Raised when a scaffold violates the static contract."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ScaffoldValidationError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ScaffoldValidationError(f"{path} must contain a JSON object")
    return payload


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ScaffoldValidationError(message)


def validate_required_files(root: Path) -> None:
    for relative in REQUIRED_FILES:
        message = (
            f"missing subagent prompt: .codex-loop/{relative}"
            if relative.startswith("subagents/")
            else f"missing required scaffold file: {relative}"
        )
        require((root / relative).is_file(), message)


def validate_no_runtime_artifacts(root: Path) -> None:
    for path in root.rglob("*"):
        if path.name in FORBIDDEN_NAMES or path.suffix.lower() in {".sqlite", ".db"}:
            relative = path.relative_to(root).as_posix()
            raise ScaffoldValidationError(f"forbidden runtime artifact: {relative}")


def validate_status(root: Path) -> None:
    status = root / ".status"
    if not status.exists():
        return
    lines = [line.strip() for line in status.read_text(encoding="utf-8").splitlines() if line.strip()]
    require(len(lines) == 1, ".status must contain exactly one stage id")
    require(bool(STAGE_ID_RE.fullmatch(lines[0])), f"invalid .status stage id: {lines[0]!r}")


def validate_manifest(root: Path, manifest: dict[str, Any]) -> None:
    require(manifest.get("schema_version") == "1.0.0", "agent_manifest.schema_version must be 1.0.0")
    host = manifest.get("codex_host")
    require(isinstance(host, dict), "agent_manifest.codex_host must be an object")
    require(host.get("executor") == "codex", "agent_manifest.codex_host.executor must be codex")
    require(
        host.get("independent_runtime_engine") is False,
        "agent_manifest must set independent_runtime_engine=false",
    )

    loop_binding = manifest.get("loop_binding")
    require(isinstance(loop_binding, dict), "agent_manifest.loop_binding must be an object")
    require(
        loop_binding.get("loop_spec_path") == ".codex-loop/loop_spec.json",
        "loop_binding.loop_spec_path must be .codex-loop/loop_spec.json",
    )
    require(
        loop_binding.get("status_path") == ".codex-loop/.status",
        "loop_binding.status_path must be .codex-loop/.status",
    )
    require(
        manifest.get("guardrails_ref") == ".codex-loop/guardrails.json",
        "guardrails_ref must be .codex-loop/guardrails.json",
    )

    subagents = manifest.get("subagents")
    require(isinstance(subagents, list), "agent_manifest.subagents must be an array")
    require(1 <= len(subagents) <= 3, "agent_manifest.subagents must contain 1 to 3 entries")
    seen_ids: set[str] = set()
    for subagent in subagents:
        require(isinstance(subagent, dict), "subagent entry must be an object")
        subagent_id = subagent.get("id")
        prompt_path = subagent.get("prompt_path")
        require(isinstance(subagent_id, str) and subagent_id, "subagent.id is required")
        require(subagent_id not in seen_ids, f"duplicate subagent id: {subagent_id}")
        seen_ids.add(subagent_id)
        require(isinstance(prompt_path, str) and prompt_path, f"subagent {subagent_id} prompt_path is required")
        require(prompt_path.startswith(".codex-loop/subagents/"), f"subagent {subagent_id} prompt_path must stay under .codex-loop/subagents/")
        local_prompt = root / Path(prompt_path).relative_to(".codex-loop")
        require(local_prompt.is_file(), f"missing subagent prompt: {prompt_path}")

    resume_policy = manifest.get("resume_policy")
    require(isinstance(resume_policy, dict), "agent_manifest.resume_policy must be an object")
    order = resume_policy.get("context_source_order")
    require(isinstance(order, list), "resume_policy.context_source_order must be an array")
    for required_source in [
        ".codex-loop/agent_manifest.json",
        ".codex-loop/loop_spec.json",
        ".codex-loop/guardrails.json",
    ]:
        require(required_source in order, f"resume_policy missing context source: {required_source}")


def validate_guardrails(guardrails: dict[str, Any]) -> None:
    require(guardrails.get("schema_version") == "1.0.0", "guardrails.schema_version must be 1.0.0")
    for key in [
        "forbidden_commands",
        "write_boundaries",
        "approval_required_actions",
        "stop_conditions",
    ]:
        require(isinstance(guardrails.get(key), list), f"guardrails.{key} must be an array")
    require(len(guardrails["stop_conditions"]) > 0, "guardrails.stop_conditions must not be empty")


def validate_scaffold(root: Path) -> None:
    root = root.resolve()
    require(root.is_dir(), f"scaffold directory not found: {root}")
    require(root.name in {".codex-loop", "codex-loop"}, "scaffold directory must be named .codex-loop")
    validate_no_runtime_artifacts(root)
    validate_required_files(root)
    loop_spec = load_json(root / "loop_spec.json")
    manifest = load_json(root / "agent_manifest.json")
    guardrails = load_json(root / "guardrails.json")
    require(isinstance(loop_spec.get("control_flow"), dict), "loop_spec.control_flow must be present")
    validate_manifest(root, manifest)
    validate_guardrails(guardrails)
    validate_status(root)


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
