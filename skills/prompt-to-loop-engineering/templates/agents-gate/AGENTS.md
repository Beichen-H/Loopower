# Two-stage Delegation Approval Gate

This file is an optional project-level `AGENTS.md` gate for Codex projects that use `$prompt-to-loop-engineering`.

It does not grant new permissions, install a Runtime Engine, or authorize hidden background work. It only forces Codex to pause before initializing `.codex-loop/` or using sub-agent delegation for non-trivial work.

It is a cooperative governance overlay, not an exclusive router. Codex MUST continue to use specialized host skills, plugins, connectors, and tools for their normal domains while applying this gate to non-trivial scaffold creation, lifecycle activation, and approval boundaries. Those capabilities are host-resolved atomic capabilities, not private functions owned by this gate.

## Workflow Precedence Rule

When `$prompt-to-loop-engineering` or this `AGENTS.md` gate is active, its mandatory execution protocol has precedence over external linear planning or fulfillment helpers for governed scaffold operations.

External helpers such as `superpowers:executing-plans`, planning skills, checklist skills, or generic inline execution flows may be used only as an auxiliary checklist inside the currently authorized node. They MUST NOT override approval gates, MUST NOT override validation flow, MUST NOT override role splitting, and MUST NOT override sub-agent lifecycle activation.

This precedence is scoped to LoopSpec design, two-stage approval, scaffold persistence, guardrail validation, evidence validation, role prompts, and lifecycle activation. It does not seize ownership of unrelated domain-specific tool behavior, and it does not create a hidden runtime.

## Scope

Use this gate for Non-trivial tasks, including tasks that involve any of the following:

- multi-file implementation, refactoring, or migration;
- uncertain project structure or ambiguous user requirements;
- data processing, reporting, workflow automation, or repeated validation;
- tool use with write effects;
- any task that could benefit from dynamically specialized professional instances;
- any request to create, update, continue, or validate `.codex-loop/`.

Trivial tasks may proceed without this gate only when the answer is a single explanation, a read-only lookup, or a one-file mechanical edit with no loop, no sub-agent split, and no scaffold.

## Stage 1 — Delegation proposal only

Before starting Non-trivial work, Codex MUST prepare a proposal and then stop.

Codex MUST NOT initialize `.codex-loop/`, spawn sub-agents, edit files, run write-capable tools, or execute the user's task during Stage 1.

The proposal MUST include:

1. `Task classification`: trivial or Non-trivial, with evidence.
2. `Lineup Recommendation`: the smallest evidence-justified finite lineup. For every proposed instance list its professional id, specialization, governance role, activation nodes, tools, and rationale. Governance roles may repeat across multiple differently specialized professional instances; there is no fixed planner/executor pair and no universal subagent count limit.
3. `Loop Boundary`: proposed maximum iterations, default exit signal, guardrails, write boundaries, and validation command.
4. `Scaffold decision`: whether `$prompt-to-loop-engineering` should create or update `.codex-loop/`.
5. `Risks and approvals`: any external write, network, credential, destructive command, or irreversible action requiring approval.

End Stage 1 with exactly this visible gate:

```text
STOP — Waiting for user approval
```

## Stage 2 — Approved initialization and validation

Codex may proceed only after explicit user approval, such as:

- "approved";
- "go ahead";
- "create the scaffold";
- "use the recommended lineup";
- another clear instruction authorizing the proposed delegation/scaffold.

After explicit user approval, Codex MUST:

1. invoke or follow `$prompt-to-loop-engineering`;
2. create or update the minimal `.codex-loop/` scaffold;
3. preserve the no-independent-Runtime-Engine boundary;
4. generate one `.codex-loop/subagents/<agent-id>.md` prompt for every approved registry entry and no undeclared prompt;
5. keep `.status` to a single current stage id if present;
6. run `validate_codex_loop_scaffold.py .codex-loop`;
7. report validation output before claiming the scaffold is ready.

Live activation is on demand and remains bounded by observed host capabilities; the absence of a universal registry-size limit is not a concurrency claim. The LoopSpec owns every permitted transition, predicate, threshold, and terminal meaning. The main Codex host is only its policy-bound evaluator and enforcer. Reviewer and verifier instances emit evidence only and never select edges, override thresholds, update `.status`, or decide termination.

If GO-phase evidence reveals that a new professional instance is necessary, Codex MUST pause, amend, revalidate, and obtain fresh user approval before creating its prompt or activating it. Existing GO approval covers only the validated registry.

If validation fails, Codex MUST fix the scaffold and rerun validation, or stop and report the exact blocking errors.

## Default defensive bounds

When the user did not specify bounds, Codex MUST use these defaults:

- maximum loop iterations: `3`;
- default exit signal: current-stage artifact is non-empty and passes basic schema/static validation;
- default guardrail: never overwrite an existing same-name workspace file directly; use a timestamped destination or `.tmp/` staging directory;
- default lineup: the smallest evidence-justified set of request-specific professional instances; do not invent fixed filenames or universal role defaults.

## Non-negotiable constraints

- MUST NOT create `runtime/`, `state.json`, queues, databases, checkpoint stores, or hidden execution engines inside `.codex-loop/`.
- MUST NOT treat this gate as user approval.
- MUST NOT claim transparent interception of every Codex action or every Skill invocation unless this file has been loaded by the active host instruction layer.
- MUST NOT override specialized skills that are better suited to concrete operations.
- MUST NOT use sub-agent delegation to bypass the user's permissions, workspace policy, or tool approval requirements.
- MUST NOT continue past the Stage 1 stop line without explicit user approval.
