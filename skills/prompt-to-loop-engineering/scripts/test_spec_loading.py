"""Static topology validation for the bundled LoopSpec."""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


SPEC_PATH = Path(__file__).resolve().parent.parent / "loop_spec.json"


def load_spec(path: Path = SPEC_PATH) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        spec = json.load(handle)
    assert isinstance(spec, dict), "LoopSpec root must be a JSON object."
    return spec


def validate_topology(spec: dict[str, Any]) -> None:
    control_flow = spec.get("control_flow")
    assert isinstance(control_flow, dict), "Missing object 'control_flow'."

    nodes = control_flow.get("nodes")
    edges = control_flow.get("edges")
    terminal_nodes = control_flow.get("terminal_nodes")
    assert isinstance(nodes, list), "'control_flow.nodes' must be a list."
    assert isinstance(edges, list), "'control_flow.edges' must be a list."
    assert isinstance(terminal_nodes, dict), "'control_flow.terminal_nodes' must be an object."

    node_ids = _node_ids(nodes)
    terminal_ids = _terminal_ids(terminal_nodes, node_ids)
    outgoing = _validate_edges(edges, node_ids)
    _validate_successors(node_ids, terminal_ids, outgoing)
    _validate_dag(node_ids, outgoing)
    _validate_priorities(outgoing)


def _node_ids(nodes: list[Any]) -> set[str]:
    node_ids: set[str] = set()
    for index, node in enumerate(nodes):
        assert isinstance(node, dict), f"Node at index {index} must be an object."
        node_id = node.get("id")
        assert isinstance(node_id, str) and node_id, f"Node at index {index} has no valid 'id'."
        assert node_id not in node_ids, f"Duplicate node id '{node_id}'."
        node_ids.add(node_id)
    return node_ids


def _terminal_ids(terminal_nodes: dict[str, Any], node_ids: set[str]) -> set[str]:
    terminal_ids: set[str] = set()
    for status, ids in terminal_nodes.items():
        assert isinstance(ids, list), f"Terminal group '{status}' must be a list."
        for node_id in ids:
            assert isinstance(node_id, str) and node_id, (
                f"Terminal group '{status}' contains an invalid node id: {node_id!r}."
            )
            assert node_id in node_ids, (
                f"Terminal group '{status}' references undefined node '{node_id}'."
            )
            terminal_ids.add(node_id)
    return terminal_ids


def _validate_edges(
    edges: list[Any], node_ids: set[str]
) -> dict[str, list[dict[str, Any]]]:
    outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for index, edge in enumerate(edges):
        assert isinstance(edge, dict), f"Edge at index {index} must be an object."
        source = edge.get("from")
        target = edge.get("to")
        assert source in node_ids, (
            f"Dangling edge at index {index}: source node '{source}' is not defined."
        )
        assert target in node_ids, (
            f"Dangling edge at index {index}: target node '{target}' is not defined."
        )
        outgoing[source].append(edge)
    return outgoing


def _validate_successors(
    node_ids: set[str],
    terminal_ids: set[str],
    outgoing: dict[str, list[dict[str, Any]]],
) -> None:
    for node_id in sorted(node_ids - terminal_ids):
        assert outgoing.get(node_id), f"Node '{node_id}' has no successor edge."


def _validate_dag(
    node_ids: set[str], outgoing: dict[str, list[dict[str, Any]]]
) -> None:
    state = {node_id: 0 for node_id in node_ids}  # 0=unvisited, 1=visiting, 2=done
    stack: list[str] = []

    def visit(node_id: str) -> None:
        if state[node_id] == 1:
            cycle_start = stack.index(node_id)
            cycle = stack[cycle_start:] + [node_id]
            raise AssertionError(f"Directed cycle detected: {' -> '.join(cycle)}.")
        if state[node_id] == 2:
            return

        state[node_id] = 1
        stack.append(node_id)
        for edge in outgoing.get(node_id, []):
            visit(edge["to"])
        stack.pop()
        state[node_id] = 2

    for node_id in sorted(node_ids):
        if state[node_id] == 0:
            visit(node_id)


def _validate_priorities(outgoing: dict[str, list[dict[str, Any]]]) -> None:
    for source, source_edges in outgoing.items():
        priorities: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for edge in source_edges:
            priority = edge.get("priority")
            assert isinstance(priority, int) and not isinstance(priority, bool), (
                f"Edge '{source}' -> '{edge.get('to')}' has no explicit integer priority."
            )
            priorities[priority].append(edge)

        for priority, tied_edges in priorities.items():
            if len(tied_edges) < 2:
                continue
            tie_breakers = [edge.get("tie_breaker") for edge in tied_edges]
            targets = [edge.get("to") for edge in tied_edges]
            assert all(isinstance(value, str) and value.strip() for value in tie_breakers), (
                f"Node '{source}' has duplicate priority {priority} for targets {targets}; "
                "add an explicit deterministic tie_breaker to every tied edge."
            )
            assert len(set(tie_breakers)) == len(tie_breakers), (
                f"Node '{source}' has duplicate priority {priority} with non-unique "
                f"tie_breakers for targets {targets}."
            )


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    try:
        validate_topology(load_spec())
    except (AssertionError, json.JSONDecodeError, OSError, TypeError, ValueError) as error:
        print(f"❌ Topology Error: {error}", file=sys.stderr)
        return 1

    print("✅ LoopSpec static topology validation passed. Graph is a valid DAG.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
