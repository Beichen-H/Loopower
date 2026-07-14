# Dynamic Subagent Topology and Controller-Owned Termination Design

## Status and release boundary

This design replaces the fixed `planner` / `executor` / optional `reviewer` scaffold contract with task-derived professional roles. Because it changes the public `agent_manifest` and LoopSpec contracts, release it as `v3.0.0` under Semantic Versioning. Preserve all v2.0.0 provenance, evidence-locking, hard-budget, workflow-precedence, reasoning-inheritance, and zero-independent-Runtime guarantees.

## Goals

- Generate professional live roles such as `researcher`, `data-engineer`, `security-auditor`, or other task-derived identities.
- Remove the universal three-subagent ceiling.
- Let the validated LoopSpec topology determine the finite subagent lineup.
- Keep authority classes small and auditable even when professional identities are open-ended.
- Give LoopSpec sole policy authority over transitions and termination; make the main Codex host the policy-bound evaluator and executor.
- Keep reviewers and verifiers as evidence providers; they never own global scheduling or termination.

## Non-goals

- Do not add an independent Runtime Engine, daemon, queue, database, or role factory.
- Do not permit unvalidated subagent creation during GO-phase execution.
- Do not claim unlimited concurrency or bypass host lifecycle limits.
- Do not allow a role name to grant permissions.
- Do not weaken implementer/reviewer isolation or the four hard loop limits.

## Identity and authority model

Separate a subagent's professional identity from its governance authority:

```json
{
  "id": "security-auditor",
  "display_name": "Security Auditor",
  "specialization": "application-security",
  "governance_role": "reviewer",
  "prompt_path": ".codex-loop/subagents/security-auditor.md",
  "activation_nodes": ["security_review"],
  "allowed_tools": ["read_files", "run_security_scan"]
}
```

`id` is a unique lowercase ASCII slug and may express any task-relevant profession. Reject path traversal, case-folding collisions, Windows reserved device names, trailing dots/spaces, and identifiers that cannot map safely to one file on all supported platforms. `display_name` and `specialization` are descriptive. `governance_role` remains a closed enum: `planner`, `implementer`, `reviewer`, or `verifier`. Every governance role may have zero or more instances. A terminal control-flow node is not a subagent.

Permissions derive from the normalized capability snapshot, node bindings, tool access modes, and `governance_role`; they never derive from `id`, `display_name`, or prompt prose. Reviewer and verifier agents remain read-only.

## Manifest and prompt contract

Remove `maxItems: 3` from `agent_manifest.subagents`. The manifest is still a finite JSON array generated during design. Remove the fixed identity and prompt-path enums. Accept an arbitrary safe slug and require `prompt_path` to equal `.codex-loop/subagents/<id>.md` through deterministic validation.

Remove hard-coded `planner.md` and `executor.md` file requirements. The scaffold validator derives required prompt files from `agent_manifest.subagents`. Every declared subagent must have exactly one prompt file, and every file under `.codex-loop/subagents/` must correspond to exactly one declared subagent. Reusable but inactive templates belong outside the generated scaffold.

The design builder must justify each subagent with a distinct responsibility, at least one reachable activation node, and a task or risk boundary that cannot be represented cleanly by an existing role. Reject duplicate identities, duplicate prompt paths, orphan roles, and exact duplicate responsibility/tool/node signatures.

Every subagent uses `activation_policy=on_demand`. Declaring many roles does not authorize eager activation. Each activated role must inherit the required reasoning configuration and produce the existing activation, handoff, and completion evidence.

The ambiguous-request fallback remains defensive but no longer mandates named roles. It derives the smallest useful lineup from observable project evidence and records the rationale. A simple one-shot or fixed workflow may produce no subagents.

## LoopSpec bindings

LoopSpec is the design-stage source of truth and therefore carries a statically validated `delegation.agent_registry`. Each registry entry contains the professional identity, governance role, specialization, rationale, activation nodes, allowed tools, and prompt reference that the later scaffold must persist. `validate_design_result.py` validates node bindings against this registry without requiring a separate Manifest input. During scaffold validation, `agent_manifest.subagents` must mirror the registry exactly for all lifecycle-relevant fields; the Manifest may add only its declared host-lifecycle and output-contract metadata.

Control-flow nodes keep a closed governance classification and add an explicit professional-agent binding:

```json
{
  "id": "inspect-dependencies",
  "type": "model",
  "role": "reviewer",
  "agent_ref": "security-auditor",
  "allowed_tools": ["read_files", "run_security_scan"]
}
```

For every node with `agent_ref`:

- the referenced manifest subagent must exist;
- the node `role` must equal the subagent `governance_role`;
- the node id must appear in the subagent's `activation_nodes`;
- node tools must be a subset of the subagent tools and normalized host capabilities;
- the node must be reachable from the LoopSpec entry node.

Every manifest activation node must resolve back to a reachable node with the same `agent_ref`. Parallel activation remains legal only when `runtime_capabilities.parallel_execution=true`; declared team size does not imply concurrent execution.

## Implementer and evaluator isolation

Each implementer agent that contributes to a mandatory acceptance criterion must be covered by at least one independent reviewer or verifier agent. The evaluator must have a different `agent_ref` from every implementer whose output it evaluates. One reviewer may cover multiple low-risk implementers when the criteria bindings make that coverage explicit. Separate reviewers or verifiers are required when policy, risk domain, or tool isolation requires independent scopes.

Mandatory criteria bindings name both `subject_nodes` and an `evaluator_node`. `subject_nodes` identifies the nodes that produced the work under evaluation, making independence machine-checkable instead of inferred from prose. The evaluator node must have governance role `reviewer` or `verifier`, bind to an agent different from every subject node's agent, use read-only tools, and emit structured evidence references. An implementer cannot evaluate its own mandatory work through a second node or alias.

## Controller-owned transition and termination

Reviewer and verifier agents report structured facts; they do not select edges, update global status, or terminate the loop. Their output contract contains criterion status, evidence references, observations, and blocking facts only.

Every generated agent loop declares:

```json
{
  "termination_control": {
    "policy_authority": "loop_spec",
    "evaluation_authority": "codex_host_controller",
    "reviewer_authority": "evidence_only",
    "transition_policy": "lower_first_then_first_match",
    "hard_stop_precedence": [
      "policy_violation",
      "user_interrupt",
      "max_runtime_seconds",
      "max_iterations",
      "max_token_budget",
      "max_no_progress_loops"
    ]
  }
}
```

LoopSpec owns the permitted edges, predicates, priority policy, thresholds, hard-stop precedence, and terminal meanings. The main Codex host has no discretion to invent or bypass those rules: it evaluates controller-observable predicates over reviewer evidence, progress evidence, policy state, user interrupts, and threshold counters, then mechanically selects the first matching declared edge. It updates `.status` and records terminal or stagnation evidence. A reviewer may emit `status=passed` or `status=failed`; it may not emit a global `continue`, `terminate`, or scheduler decision.

Replace the ambiguous agent-loop `transition_policy.authority=model_proposal` wording with separate fields: `decision_authority=codex_host_controller` and `proposal_mode=model_proposal`. Model nodes may propose a target, but only the controller validates predicates and selects an edge. Reviewer and verifier nodes use `decision_rights=evidence_only`, may not write controller-owned state, and may not be listed as transition proposal sources.

Hard-stop conditions take precedence over ordinary pass/fail routing. A successful terminal requires all mandatory criteria to have independent passing evidence and no unresolved policy or capability block. Failure, blocked, stopped, and stagnation terminals remain distinct.

## Lifecycle and amendment rules

After explicit GO and scaffold validation, Codex activates only the manifest roles required by the currently authorized nodes. The number of declared roles has no universal schema maximum, but actual live concurrency is bounded by discovered host capabilities and approval policy.

If execution evidence reveals a need for a previously undeclared specialist, Codex must pause. It may propose an amended LoopSpec, manifest, guardrails, and prompt file; then it must rerun static validation and obtain any required approval before activation. It must never spawn an undeclared role and retroactively write evidence.

## Compatibility and migration

Existing `planner`, `executor`, and `reviewer` identities remain valid slugs, but v2 manifests lack the new explicit authority and node-binding guarantees. The v3 validator should report a targeted migration error rather than silently inferring permissions. Examples and installation assets move together to v3.0.0.

Set the Skill release to `3.0.0` and the breaking `agent_manifest` schema contract to `2.0.0`. Keep these version domains explicit rather than pretending the old manifest validates unchanged.

No v2 evidence or provenance rule is removed. Existing four-hard-limit thresholds, progress fingerprints, tool access modes, reasoning intensity inheritance, activation/handoff/completion evidence, and scheduler ownership remain required where currently applicable.

## Physical changes

- Update `SKILL.md` to define dynamic professional roles, controller-owned termination, and amendment gates.
- Update `schemas/agent_manifest.schema.json` to remove fixed role names and the three-agent maximum, and require professional identity metadata plus `governance_role`.
- Update `schemas/loop_spec.schema.json` with `agent_ref` bindings and `termination_control`.
- Formalize `loop_spec.delegation.agent_registry` as the design-stage role source of truth and require the scaffold Manifest to mirror it.
- Update the scaffold and design-result validators to enforce referential integrity, role/tool agreement, independent evaluator identity, prompt derivation, and controller-only termination.
- Replace fixed prompt-file requirements in `validate_codex_loop_scaffold.py` with manifest-derived requirements.
- Cross-check Manifest tool bindings against LoopSpec `tool_access_modes` and reject access-mode disagreement or undeclared subagent tools.
- Require `.status` to reference a real LoopSpec node, require handoff evidence to reference a real graph edge, and require activation/completion evidence coverage for every activated subagent node rather than trusting an incomplete hand-written evidence list.
- Reject a terminal node used as the only reviewer/verifier; an implementer requires a reachable non-terminal independent evaluator.
- Update the example scaffold with task-specific roles and corresponding prompt files.
- Update both `README.md` and `README-CN.md`, packaged `AGENTS.md` templates, release metadata, installation text, architecture comparisons, lifecycle examples, and all Skill version markers to v3.0.0. Document that role count is topology-derived and finite, while concurrency remains capability-bound.
- Preserve the repository's no-Runtime rule.

## Test strategy

Add passing tests for arbitrary professional role names, more than three declared subagents, multiple implementers, multiple reviewers, sequential activation without parallel capability, and independent reviewer coverage.

Add failing tests for orphan agents, unsafe or case-colliding ids, missing or mismatched prompt files, duplicate role signatures, node/manifest authority mismatch, undeclared activation, implementer self-evaluation through aliases, missing `subject_nodes`, reviewer write tools, reviewer-owned transition decisions, reviewer writes to controller state, terminal-only review, missing controller termination contract, Manifest/LoopSpec tool-mode disagreement, invalid `.status`, handoff to a non-edge, incomplete lifecycle evidence coverage, unvalidated mid-run role creation, and parallel activation without capability support.

Run the complete unit suite, recursive JSON parsing, scaffold validation, design-result example validation, DAG evidence validation, progress evidence validation, Skill surface validation, and local installer dry-run before release.
