# Capability-Bound Static Validation Design

## Scope

Upgrade `prompt-to-loop-engineering` from a shape-oriented validator to a KB v4.0.2 design-time contract builder. The Skill ends after emitting and statically validating `loop_design_result`; it never executes the user task and contains no Runtime Engine.

## Contracts

- Input: one `Loop_design_request` JSON document.
- Output: one `loop_design_result` JSON document.
- Validation command: `python scripts/validate_design_result.py RESULT --request REQUEST`.
- `one_shot` always has `loop_spec=null`.
- `workflow` and `agent_loop` require a complete `loop_spec` and may return `spec_ready` only after request-bound static validation.
- Build reports always set `execution_performed=false` and `user_task_passed=false`.

## Capability binding

Normalize missing capability booleans to `false` and missing tools to an empty set. Require `loop_spec.runtime_binding.capabilities_snapshot` to equal the normalized request snapshot. Reject any required tool, durable persistence, checkpoint, approval, parallel branch, worker/sub-agent, or sandbox claim that the request does not provide.

Capability awareness is design input only. Generated specifications describe what an external controller would need; the Skill does not perform those operations.

## Static graph contract

- Represent edge conditions as structured controller-observable predicates, not free-form prose.
- Use `lower_first` and `first_match`; list each source node's edges in nondecreasing priority order. Duplicate priorities require unique deterministic tie-breakers.
- Require all nodes and terminals to be reachable from the entry node.
- Require every non-terminal node to have an outgoing edge.
- Require terminal outcomes to distinguish passed, failed, blocked, stopped, and other runtime statuses.
- Permit cycles only in `agent_loop`; each detected cycle must be declared with structured progress signals, a resolvable stagnation policy, a resolvable budget policy, structured exit conditions, and a graph exit.

## Orthogonal architecture

Require all six dimensions: architecture mode, execution patterns, orchestration topology, control gates, domain compositions, and cross-cutting policies. Validate standard KB values where the KB defines a closed vocabulary; require non-empty strings for domain-specific compositions.

## Acceptance and references

Every mandatory acceptance criterion requires a supported verification method, at least one non-empty evidence requirement, and a binding to a registered evaluator or deterministic check. Validate node criterion references, state read/write scopes, retry/timeout/policy references, threshold references, and transition authority.

## Assets

Update the three JSON Schemas, validator, five output examples, five matching request fixtures, tests, `SKILL.md`, `loop_spec.json`, `openai.yaml`, and repository README. Release as `v1.2.0`. Do not add `runtime/` or any execution module.

## Testing

Add failing tests for one-shot nullability, missing evidence, six-dimensional architecture, capability snapshot equality, tool/durable/checkpoint/approval/parallel/worker/sandbox overreach, structured predicates, cycle references, reachability, terminal outcome separation, and reference resolution. Then update implementation and examples until the complete standard-library suite, standalone topology test, example CLI validation, JSON parsing, and Codex Skill validator all pass.
