# Two-stage Delegation Approval Gate

This file is an optional project-level `AGENTS.md` gate for Codex projects that use `$prompt-to-loop-engineering`.

It does not grant new permissions, install a Runtime Engine, or authorize hidden background work. It only forces Codex to pause before initializing `.codex-loop/` or using sub-agent delegation for non-trivial work.

It is a cooperative governance overlay, not an exclusive router. Codex MUST continue to use specialized host skills, plugins, connectors, and tools for their normal domains while applying this gate to non-trivial scaffold creation, lifecycle activation, and approval boundaries. Those capabilities are host-resolved atomic capabilities, not private functions owned by this gate.

When this gate is active, `$prompt-to-loop-engineering` is the primary workflow for loop design, scaffold lifecycle, and validation. External plan helpers such as `superpowers:executing-plans` may be used only as auxiliary checklists after they are reconciled with this gate; they cannot override approval gates, validation, planner/executor separation, or live sub-agent activation.

## Scope

Use this gate for Non-trivial tasks, including tasks that involve any of the following:

- multi-file implementation, refactoring, or migration;
- uncertain project structure or ambiguous user requirements;
- data processing, reporting, workflow automation, or repeated validation;
- tool use with write effects;
- any task that could benefit from planner/executor/reviewer separation;
- any request to create, update, continue, or validate `.codex-loop/`.

Trivial tasks may proceed without this gate only when the answer is a single explanation, a read-only lookup, or a one-file mechanical edit with no loop, no sub-agent split, and no scaffold.

## Stage 1 — Delegation proposal only

Before starting Non-trivial work, Codex MUST prepare a proposal and then stop.

Codex MUST NOT initialize `.codex-loop/`, spawn sub-agents, edit files, run write-capable tools, or execute the user's task during Stage 1.

The proposal MUST include:

1. `Task classification`: trivial or Non-trivial, with evidence.
2. `Lineup Recommendation`: recommended roles, usually `planner` and `executor`, with optional `reviewer` only when independent review materially reduces risk.
3. `Loop Boundary`: proposed maximum iterations, default exit signal, guardrails, write boundaries, and validation command.
4. `Capability Snapshot`: before setting `subagents=false`, call `tool_search` for `spawn_agent`, `spawn_subagent`, `subagent`, and `multi_agent`; set `subagents=true` if a host-native lifecycle tool is found, or record `no_host_native_lifecycle_tool_found` if none is available.
5. `Scaffold decision`: whether `$prompt-to-loop-engineering` should create or update `.codex-loop/`.
6. `Risks and approvals`: any external write, network, credential, destructive command, or irreversible action requiring approval.

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
4. generate at least `.codex-loop/subagents/planner.md` and `.codex-loop/subagents/executor.md`;
5. keep `.status` to a single current stage id if present;
6. run `validate_codex_loop_scaffold.py .codex-loop`;
7. report validation output before claiming the scaffold is ready.

If validation fails, Codex MUST fix the scaffold and rerun validation, or stop and report the exact blocking errors.

## Default defensive bounds

When the user did not specify bounds, Codex MUST use these defaults:

- maximum loop iterations: `3`;
- default exit signal: current-stage artifact is non-empty and passes basic schema/static validation;
- default guardrail: never overwrite an existing same-name workspace file directly; use a timestamped destination or `.tmp/` staging directory;
- default roles: separate `planner` and `executor`; do not merge them.

## Non-negotiable constraints

- MUST NOT create `runtime/`, `state.json`, queues, databases, checkpoint stores, or hidden execution engines inside `.codex-loop/`.
- MUST NOT treat this gate as user approval.
- MUST NOT claim transparent interception of every Codex action or every Skill invocation unless this file has been loaded by the active host instruction layer.
- MUST NOT override specialized skills that are better suited to concrete operations.
- MUST NOT use sub-agent delegation to bypass the user's permissions, workspace policy, or tool approval requirements.
- MUST NOT write `subagents=false` without recorded `tool_search` evidence that no host-native sub-agent lifecycle tool is available.
- MUST NOT continue past the Stage 1 stop line without explicit user approval.
