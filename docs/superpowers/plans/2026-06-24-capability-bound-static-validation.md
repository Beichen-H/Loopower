# Capability-Bound Static Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `prompt-to-loop-engineering` produce request-bound, KB v4.0.2-compliant static designs without containing or executing a Runtime Engine.

**Architecture:** Keep the output contract separate from the input request and validate the pair deterministically. Tighten graph predicates, capability inference, orthogonal architecture, criterion bindings, and reference integrity in one pure-standard-library validator; keep examples as executable contract fixtures.

**Tech Stack:** Python 3 standard library, JSON Schema 2020-12 documents, `unittest`, Markdown, YAML metadata.

## Global Constraints

- Skill version is `1.2.0`; release label is `v1.2.0 (2026-06-24)`.
- No `runtime/` directory or Runtime Engine implementation.
- No user-task execution; `execution_performed=false` and `user_task_passed=false`.
- Missing runtime capability fields mean unavailable/false.
- All changes use RED-GREEN-REFACTOR and preserve the existing five-stage bundled Skill DAG.

---

### Task 1: Encode the missing compliance rules as failing tests

**Files:**
- Modify: `skills/prompt-to-loop-engineering/scripts/test_validate_design_result.py`
- Modify: `skills/prompt-to-loop-engineering/scripts/test_skill_surface.py`

**Interfaces:**
- Consumes: existing `validate_design_result(payload)` behavior.
- Produces: required API `validate_design_result(payload, request)` and CLI `RESULT --request REQUEST`.

- [ ] Add tests that reject non-null one-shot specs, empty mandatory evidence, missing request binding, invented tools and capabilities, invalid architecture vocabulary, free-form conditions, unresolved cycle/policy/threshold references, unreachable nodes, and incorrect terminal mapping.
- [ ] Add surface tests for version `1.2.0`, request fixtures, request-aware command text, and absence of a `runtime/` directory.
- [ ] Run `python -m unittest discover -s skills/prompt-to-loop-engineering/scripts -p "test_*.py" -v` and confirm failures identify missing validation behavior.

### Task 2: Implement request-bound deterministic validation

**Files:**
- Modify: `skills/prompt-to-loop-engineering/scripts/validate_design_result.py`
- Modify: `skills/prompt-to-loop-engineering/schemas/loop_design_request.schema.json`
- Modify: `skills/prompt-to-loop-engineering/schemas/loop_design_result.schema.json`
- Modify: `skills/prompt-to-loop-engineering/schemas/loop_spec.schema.json`

**Interfaces:**
- Consumes: `dict` request plus `dict` result.
- Produces: `validate_design_result(payload: dict[str, Any], request: dict[str, Any]) -> None`; raises `DesignValidationError` on the first deterministic violation.

- [ ] Normalize the seven capability fields, require request identity, and compare the normalized request to `runtime_binding.capabilities_snapshot`.
- [ ] Infer required capabilities from tools, state persistence, checkpoints, approvals, topology, delegation, workers, and sandbox declarations; reject overreach.
- [ ] Validate six architecture dimensions, structured predicates, reachability, criterion bindings, state scopes, transition authority, cycle controls, and all policy/threshold references.
- [ ] Require the CLI `--request` path and keep all validation side-effect free.
- [ ] Run focused tests until they pass, then run the complete suite.

### Task 3: Migrate canonical examples and the bundled design graph

**Files:**
- Create: `skills/prompt-to-loop-engineering/examples/requests/{one_shot,workflow,agent_loop,needs_input,unsupported}.json`
- Modify: `skills/prompt-to-loop-engineering/examples/{one_shot,workflow,agent_loop,needs_input,unsupported}.json`
- Modify: `skills/prompt-to-loop-engineering/loop_spec.json`

**Interfaces:**
- Consumes: paired request/result filenames.
- Produces: five request-bound examples accepted by the validator.

- [ ] Give every example an explicit real capability snapshot and policy envelope.
- [ ] Convert workflow and agent-loop edges to structured predicates and KB vocabulary.
- [ ] Make the agent loop memory-only unless durable state is declared; separate passed and stopped terminal nodes; use structured progress and exit conditions.
- [ ] Convert the bundled Skill DAG conditions to the same structured predicate form without introducing a cycle or runtime action.
- [ ] Validate every pair through the CLI and run the standalone bundled DAG test.

### Task 4: Publish the design-only v1.2.0 contract

**Files:**
- Modify: `skills/prompt-to-loop-engineering/SKILL.md`
- Modify: `skills/prompt-to-loop-engineering/agents/openai.yaml`
- Modify: `README.md`

**Interfaces:**
- Consumes: request-aware validator and paired examples.
- Produces: concise Codex instructions for static design only.

- [ ] Replace the old validator command with `RESULT --request REQUEST`; explicitly forbid task execution and Runtime Engine modules.
- [ ] State exact one-shot/workflow/agent-loop selection and capability-binding rules.
- [ ] Document `v1.2.0` changes and paired example usage without describing runtime implementation work as part of this Skill.
- [ ] Run all unit tests, parse every JSON file, run `quick_validate.py`, check for caches/runtime modules, and prepare a Static Validation Report.
