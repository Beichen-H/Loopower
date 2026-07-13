# Dynamic Subagent Topology Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Release `prompt-to-loop-engineering` v3.0.0 with topology-derived professional subagents, no universal role-count ceiling, independent evaluator identity, LoopSpec-owned transition policy, and policy-bound Codex-host enforcement.

**Architecture:** LoopSpec becomes the design-stage source of truth through `delegation.agent_registry`; the scaffold Manifest mirrors that registry and adds host-lifecycle metadata. Nodes bind to professional agents through `agent_ref` while retaining a closed governance `role`. Reviewers emit evidence only, and the Codex host evaluates edge predicates and hard-stop conditions.

**Tech Stack:** Python 3.11 standard library, JSON Schema draft 2020-12, Markdown contracts, `unittest`, Codex-native `.codex-loop/` files.

## Global Constraints

- Skill release version is `3.0.0`; breaking `agent_manifest` schema version is `2.0.0`.
- Preserve v2.0.0 request provenance, four hard limits, progress evidence, evidence locking, workflow precedence, reasoning inheritance, and role/tool isolation.
- Do not add an independent Runtime Engine, daemon, queue, database, checkpoint service, or dynamic role factory.
- Do not place a universal `maxItems` on subagents; each emitted Manifest remains a finite static array.
- Professional ids are open-ended safe slugs; governance roles remain `planner`, `implementer`, `reviewer`, or `verifier`.
- LoopSpec is the sole transition/termination policy authority; `codex_host_controller` only evaluates and enforces declared rules, writes controller-owned state, and must not invent edges or override thresholds.
- README.md and README-CN.md must describe the same v3 behavior and boundaries.

---

### Task 1: Publish the v3 role and termination schemas

**Files:**
- Modify: `skills/prompt-to-loop-engineering/schemas/agent_manifest.schema.json`
- Modify: `skills/prompt-to-loop-engineering/schemas/loop_spec.schema.json`
- Modify: `skills/prompt-to-loop-engineering/scripts/test_skill_surface.py`

**Interfaces:**
- Produces: `agent_manifest` schema `2.0.0` with dynamic subagent entries.
- Produces: `loop_spec.delegation.agent_registry`, node `agent_ref`, criteria `subject_nodes`, `termination_control`, and explicit transition decision/proposal fields.

- [ ] **Step 1: Add failing schema-surface tests**

Add tests that load both schemas and assert the following exact contract:

```python
def test_v3_manifest_accepts_dynamic_professional_roles_without_fixed_max(self):
    manifest = json.loads((SKILL_ROOT / "schemas/agent_manifest.schema.json").read_text(encoding="utf-8"))
    subagents = manifest["properties"]["subagents"]
    self.assertNotIn("maxItems", subagents)
    role = manifest["$defs"]["subagent"]["properties"]["governance_role"]
    self.assertEqual(role["enum"], ["planner", "implementer", "reviewer", "verifier"])
    self.assertIn("specialization", manifest["$defs"]["subagent"]["required"])

def test_v3_loop_schema_has_registry_identity_and_controller_termination(self):
    schema = json.loads((SKILL_ROOT / "schemas/loop_spec.schema.json").read_text(encoding="utf-8"))
    self.assertIn("agent_ref", schema["$defs"]["node"]["properties"])
    self.assertIn("subject_nodes", schema["$defs"]["criteria_binding"]["required"])
    self.assertIn("termination_control", schema["required"])
```

- [ ] **Step 2: Run the targeted surface tests and confirm failure**

Run:

```powershell
python -B -m unittest discover -s skills/prompt-to-loop-engineering/scripts -p "test_skill_surface.py" -v
```

Expected: FAIL because v2 fixes `maxItems=3`, role ids, and prompt paths.

- [ ] **Step 3: Implement the JSON Schema contracts**

Define each subagent with these required fields:

```json
{
  "id": "security-auditor",
  "display_name": "Security Auditor",
  "specialization": "application-security",
  "governance_role": "reviewer",
  "rationale": "Independent security acceptance is mandatory.",
  "prompt_path": ".codex-loop/subagents/security-auditor.md",
  "activation_policy": "on_demand",
  "activation_nodes": ["security-review"],
  "responsibilities": ["Evaluate the security acceptance criteria."],
  "allowed_tools": ["read_files", "run_security_scan"],
  "output_contract": {"format": "json", "required_fields": ["criteria", "evidence_refs"]}
}
```

Use lowercase ASCII slug pattern `^[a-z0-9]+(?:-[a-z0-9]+)*$`. Do not encode the path/id equality solely in JSON Schema; the Python validator owns that relational check.

Define `termination_control` with constants `policy_authority=loop_spec`, `evaluation_authority=codex_host_controller`, `reviewer_authority=evidence_only`, and `transition_policy=lower_first_then_first_match`. Replace transition `authority` with `decision_authority` and `proposal_mode`.

- [ ] **Step 4: Run the targeted tests and parse both schemas**

Run the surface test command plus:

```powershell
python -m json.tool skills/prompt-to-loop-engineering/schemas/agent_manifest.schema.json > $null
python -m json.tool skills/prompt-to-loop-engineering/schemas/loop_spec.schema.json > $null
```

Expected: PASS.

- [ ] **Step 5: Commit the schema contract**

```bash
git add skills/prompt-to-loop-engineering/schemas/agent_manifest.schema.json skills/prompt-to-loop-engineering/schemas/loop_spec.schema.json skills/prompt-to-loop-engineering/scripts/test_skill_surface.py
git commit -m "feat: define dynamic subagent contracts"
```

### Task 2: Enforce dynamic role bindings during design validation

**Files:**
- Modify: `skills/prompt-to-loop-engineering/scripts/validate_design_result.py`
- Modify: `skills/prompt-to-loop-engineering/scripts/test_validate_design_result.py`
- Modify: `skills/prompt-to-loop-engineering/examples/agent_loop.json`
- Modify: `skills/prompt-to-loop-engineering/examples/workflow.json`
- Modify: `skills/prompt-to-loop-engineering/loop_spec.json`

**Interfaces:**
- Produces: `_validate_agent_registry(delegation, node_ids, tool_access_modes) -> dict[str, dict[str, Any]]`.
- Consumes: `control_flow.nodes[*].agent_ref`, `evaluation.criteria_bindings[*].subject_nodes`, and `termination_control`.

- [ ] **Step 1: Add failing validator tests**

Cover arbitrary ids and more than three agents, then add rejection tests for an unknown `agent_ref`, governance-role mismatch, orphan registry entry, duplicate role signature, missing `subject_nodes`, implementer self-evaluation through a second node, reviewer transition proposals, reviewer writes to controller-owned state, and missing termination control.

Use a helper that appends valid registry entries:

```python
def add_agent(spec, *, agent_id, governance_role, node_id, tools):
    spec["delegation"]["agent_registry"].append({
        "id": agent_id,
        "display_name": agent_id.replace("-", " ").title(),
        "specialization": agent_id,
        "governance_role": governance_role,
        "rationale": f"Node {node_id} requires an isolated specialist.",
        "prompt_ref": f".codex-loop/subagents/{agent_id}.md",
        "activation_policy": "on_demand",
        "activation_nodes": [node_id],
        "allowed_tools": tools,
    })
```

- [ ] **Step 2: Run design-result tests and confirm failure**

Run:

```powershell
python -B -m unittest discover -s skills/prompt-to-loop-engineering/scripts -p "test_validate_design_result.py" -v
```

Expected: FAIL on the new registry and controller-termination assertions.

- [ ] **Step 3: Implement registry, node, evaluator, and termination validation**

Add these validations in order:

```python
agent_registry = _validate_agent_registry(spec["delegation"], tool_access_modes)
flow = _validate_control_flow(..., agent_registry=agent_registry)
_validate_evaluation(..., flow=flow, agent_registry=agent_registry)
_validate_transition_policy(spec["transition_policy"], expected_mode, flow)
_validate_termination_control(spec["termination_control"])
```

Require each registry activation node to be reachable and bound back through the same `agent_ref`. Require every subagent tool to exist with a matching capability access mode. Require evaluator agents to differ from all agents bound to `subject_nodes`. Reject reviewer/verifier proposal sources and writes to `state.controller_owned_fields`.

- [ ] **Step 4: Migrate published LoopSpec examples**

Add empty registries to designs without subagents. Give the agent-loop example task-specific registry entries and node bindings. Use terminal node role `terminal`, not `verifier`. Make every mandatory criteria binding declare exact producer `subject_nodes`.

- [ ] **Step 5: Run all design-result tests**

Expected: all tests in `test_validate_design_result.py` pass, including every published request/result pair.

- [ ] **Step 6: Commit design validation**

```bash
git add skills/prompt-to-loop-engineering/scripts/validate_design_result.py skills/prompt-to-loop-engineering/scripts/test_validate_design_result.py skills/prompt-to-loop-engineering/examples skills/prompt-to-loop-engineering/loop_spec.json
git commit -m "feat: validate professional agent topology"
```

### Task 3: Make scaffold validation manifest-derived and cross-file strict

**Files:**
- Modify: `skills/prompt-to-loop-engineering/scripts/validate_codex_loop_scaffold.py`
- Modify: `skills/prompt-to-loop-engineering/scripts/test_scaffold_validation.py`
- Modify: `skills/prompt-to-loop-engineering/examples/codex-loop/agent_manifest.json`
- Modify: `skills/prompt-to-loop-engineering/examples/codex-loop/loop_spec.json`
- Delete: `skills/prompt-to-loop-engineering/examples/codex-loop/subagents/planner.md`
- Delete: `skills/prompt-to-loop-engineering/examples/codex-loop/subagents/executor.md`
- Create: `skills/prompt-to-loop-engineering/examples/codex-loop/subagents/requirements-analyst.md`
- Create: `skills/prompt-to-loop-engineering/examples/codex-loop/subagents/feature-engineer.md`
- Create: `skills/prompt-to-loop-engineering/examples/codex-loop/subagents/test-verifier.md`
- Create: `skills/prompt-to-loop-engineering/examples/codex-loop/subagents/security-auditor.md`

**Interfaces:**
- Produces: `validate_manifest_loop_alignment(manifest, loop_spec) -> None`.
- Produces: `canonical_prompt_path(agent_id: str) -> str` and `validate_safe_agent_id(agent_id: str) -> None`.

- [ ] **Step 1: Add failing scaffold tests**

Add tests proving four custom agents pass and failures occur for: `maxItems` assumptions, `../` paths, `CON`/`con` Windows device names, case-folding collisions, prompt/id mismatch, undeclared prompt file, orphan activation node, role mismatch, terminal-only evaluator, subagent tool outside capability snapshot, Manifest/LoopSpec tool-mode disagreement, invalid `.status`, and node assigned to multiple agents.

- [ ] **Step 2: Run scaffold tests and confirm failure**

Expected: existing validator rejects four agents and misses the cross-file defects.

- [ ] **Step 3: Replace fixed file requirements with derived requirements**

Keep only these fixed scaffold files:

```python
REQUIRED_FILES = ["loop_spec.json", "agent_manifest.json", "guardrails.json"]
```

Derive prompt files from the Manifest. Reject undeclared `*.md` files under `subagents/`. Compare registry and Manifest entries by identity, governance role, specialization, rationale, activation policy, activation nodes, allowed tools, and prompt reference/path.

- [ ] **Step 4: Add cross-file tool, status, and evaluator validation**

Require Manifest tool-binding permission modes to equal LoopSpec capability modes. Require all subagent and node tools to be declared. Resolve `.status` against actual node ids. Require a reachable non-terminal reviewer/verifier with an independent `agent_ref` whenever an implementer exists.

- [ ] **Step 5: Replace the example scaffold with a four-role sequential loop**

Use `requirements-analyst`, `feature-engineer`, `test-verifier`, and `security-auditor`. Keep `parallel_execution=false`; the graph activates roles on demand in sequence. Give `run_tests` the same `read_only` access mode in both Manifest and LoopSpec.

- [ ] **Step 6: Run scaffold tests and validator**

Run:

```powershell
python -B -m unittest discover -s skills/prompt-to-loop-engineering/scripts -p "test_scaffold_validation.py" -v
python -B skills/prompt-to-loop-engineering/scripts/validate_codex_loop_scaffold.py skills/prompt-to-loop-engineering/examples/codex-loop
```

Expected: PASS.

- [ ] **Step 7: Commit scaffold validation**

```bash
git add skills/prompt-to-loop-engineering/scripts/validate_codex_loop_scaffold.py skills/prompt-to-loop-engineering/scripts/test_scaffold_validation.py skills/prompt-to-loop-engineering/examples/codex-loop
git commit -m "feat: validate manifest-derived live roles"
```

### Task 4: Generalize lifecycle evidence to arbitrary topology

**Files:**
- Modify: `skills/prompt-to-loop-engineering/scripts/validate_dag_execution_evidence.py`
- Modify: `skills/prompt-to-loop-engineering/scripts/test_dag_execution_evidence.py`
- Replace: JSON files under `skills/prompt-to-loop-engineering/examples/codex-loop/evidence/activation/`
- Replace: JSON files under `skills/prompt-to-loop-engineering/examples/codex-loop/evidence/handoff/`
- Replace: JSON files under `skills/prompt-to-loop-engineering/examples/codex-loop/evidence/completion/`

**Interfaces:**
- Produces: topology indexes `owned_nodes: dict[str, str]`, `node_ids: set[str]`, and `edge_pairs: set[tuple[str, str]]`.
- Consumes: dynamic evidence filenames; identity comes from JSON fields, not filenames.

- [ ] **Step 1: Add failing dynamic-evidence tests**

Test four arbitrary role ids and reject activation for an undeclared role, completion by the wrong role, handoff to an undefined node, handoff not represented by an edge, missing activation/completion coverage for a declared subagent node, and duplicate lifecycle evidence for one node.

- [ ] **Step 2: Run evidence tests and confirm failure**

Expected: FAIL because v2 trusts the hand-written evidence list and does not validate handoffs against graph edges.

- [ ] **Step 3: Implement graph-bound evidence validation**

Change handoff validation to:

```python
def validate_handoff(path, evidence, node_ids, edge_pairs):
    from_node = evidence["from_node"]
    to_node = evidence["to_node"]
    require(from_node in node_ids and to_node in node_ids, "handoff references undefined node")
    require((from_node, to_node) in edge_pairs, "handoff does not match a LoopSpec edge")
```

Index evidence by `(evidence_type, node_id)` and require exactly one activation and completion entry for every executed subagent node represented by the final required evidence set. Keep reasoning inheritance assertions for every activation.

- [ ] **Step 4: Migrate example lifecycle evidence and required refs**

Rename evidence files to the four professional ids and valid edge handoffs. Keep terminal completion owned by the Codex host rather than a fake verifier subagent.

- [ ] **Step 5: Run evidence and scaffold validators**

Expected: both validators pass for the migrated example.

- [ ] **Step 6: Commit lifecycle evidence**

```bash
git add skills/prompt-to-loop-engineering/scripts/validate_dag_execution_evidence.py skills/prompt-to-loop-engineering/scripts/test_dag_execution_evidence.py skills/prompt-to-loop-engineering/examples/codex-loop
git commit -m "feat: bind lifecycle evidence to dynamic topology"
```

### Task 5: Rewrite the Skill and project gate around dynamic roles

**Files:**
- Modify: `skills/prompt-to-loop-engineering/SKILL.md`
- Modify: `skills/prompt-to-loop-engineering/templates/agents-gate/AGENTS.md`
- Modify: `examples/agents-gate/AGENTS.md`
- Modify: `skills/prompt-to-loop-engineering/agents/openai.yaml`
- Modify: `skills/prompt-to-loop-engineering/scripts/test_skill_surface.py`

**Interfaces:**
- Produces: v3 host instructions that derive professional roles from LoopSpec and reserve termination authority for Codex.

- [ ] **Step 1: Add failing surface tests for v3 wording and template parity**

Assert the Skill contains `Dynamic Professional Role Contract`, `delegation.agent_registry`, `termination_control`, `codex_host_controller`, `reviewer_authority=evidence_only`, `no universal subagent count limit`, and the pause/amend/revalidate rule. Assert neither AGENTS template mandates `planner.md` or `executor.md`, and both copies remain byte-identical.

- [ ] **Step 2: Run surface tests and confirm failure**

Expected: FAIL on fixed-role wording and v2 metadata.

- [ ] **Step 3: Rewrite fixed-role and lifecycle clauses**

Replace the defensive fallback's mandatory named pair with the smallest evidence-justified lineup. Explain that all governance roles may have multiple professional instances, live activation is on demand, and newly discovered roles require a paused scaffold amendment.

Replace `<role>.md` examples with `<agent-id>.md`. State that reviewers emit structured evidence only and the main Codex host owns `.status`, edge selection, hard-stop precedence, and terminal export.

- [ ] **Step 4: Update AGENTS gate and UI metadata**

Require Stage 1 lineup proposals to list professional id, specialization, governance role, activation nodes, tools, and rationale. Keep explicit GO before any scaffold or live activation. Update `openai.yaml` to v3 without claiming unlimited concurrency.

- [ ] **Step 5: Run surface tests**

Expected: PASS.

- [ ] **Step 6: Commit Skill instructions**

```bash
git add skills/prompt-to-loop-engineering/SKILL.md skills/prompt-to-loop-engineering/templates/agents-gate/AGENTS.md examples/agents-gate/AGENTS.md skills/prompt-to-loop-engineering/agents/openai.yaml skills/prompt-to-loop-engineering/scripts/test_skill_surface.py
git commit -m "docs: govern dynamic professional roles"
```

### Task 6: Update English and Chinese release documentation

**Files:**
- Modify: `README.md`
- Modify: `README-CN.md`
- Modify: version-bearing JSON examples under `skills/prompt-to-loop-engineering/`
- Modify: `skills/prompt-to-loop-engineering/scripts/test_skill_surface.py`

**Interfaces:**
- Produces: synchronized public v3 installation, behavior, migration, and architecture-boundary documentation.

- [ ] **Step 1: Add failing documentation assertions**

Assert both READMEs describe topology-derived professional roles, no universal declared-role ceiling, finite static Manifests, capability-bound concurrency, controller-owned termination, evidence-only reviewers, and v2-to-v3 migration. Assert old fixed live-process mappings are absent.

- [ ] **Step 2: Rewrite public examples and scaffold trees**

Show a representative dynamic tree:

```text
.codex-loop/subagents/
|-- requirements-analyst.md
|-- feature-engineer.md
|-- test-verifier.md
`-- security-auditor.md
```

Explain that these names are examples, not reserved roles. Update the architecture efficacy section to state that declared role count scales prompt/evidence overhead and that concurrency remains bounded by host capabilities.

- [ ] **Step 3: Add v3.0.0 release and migration notes**

Document the breaking Manifest schema, removal of the fixed three-role ceiling, new registry/agent bindings, independent subject/evaluator identity, controller termination, and the need to regenerate v2 scaffolds rather than silently infer permissions.

- [ ] **Step 4: Update all version markers**

Set Skill/package references to `3.0.0` and Manifest schema examples to `2.0.0`. Preserve historical release notes unchanged.

- [ ] **Step 5: Run surface tests and repository version scan**

Run:

```powershell
python -B -m unittest discover -s skills/prompt-to-loop-engineering/scripts -p "test_skill_surface.py" -v
rg -n "Skill version|created_by_skill|prompt-to-loop-engineering v2|maxItems.*3" README.md README-CN.md skills/prompt-to-loop-engineering
```

Expected: only historical v2 references remain; active metadata is v3.

- [ ] **Step 6: Commit release documentation**

```bash
git add README.md README-CN.md skills/prompt-to-loop-engineering
git commit -m "docs: publish v3 dynamic topology guidance"
```

### Task 7: Full regression, package validation, and local install dry-run

**Files:**
- Modify only if a failing check reveals a v3 contract defect.

**Interfaces:**
- Produces: release evidence; does not push or publish without a separate explicit user request.

- [ ] **Step 1: Run the full unit suite**

```powershell
python -B -m unittest discover -s skills/prompt-to-loop-engineering/scripts -p "test_*.py" -v
```

Expected: all old and new tests pass.

- [ ] **Step 2: Parse every JSON asset**

```powershell
Get-ChildItem skills/prompt-to-loop-engineering -Recurse -Filter *.json | ForEach-Object { python -m json.tool $_.FullName > $null }
```

Expected: exit code 0.

- [ ] **Step 3: Run all standalone validators**

```powershell
python -B skills/prompt-to-loop-engineering/scripts/validate_codex_loop_scaffold.py skills/prompt-to-loop-engineering/examples/codex-loop
python -B skills/prompt-to-loop-engineering/scripts/validate_dag_execution_evidence.py skills/prompt-to-loop-engineering/examples/codex-loop
python -B skills/prompt-to-loop-engineering/scripts/validate_loop_progress_evidence.py skills/prompt-to-loop-engineering/examples/codex-loop
python -B skills/prompt-to-loop-engineering/scripts/test_spec_loading.py
```

Expected: four successful validator messages.

- [ ] **Step 4: Run Skill package and installer verification**

```powershell
python C:/Users/31910/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/prompt-to-loop-engineering
python -B skills/prompt-to-loop-engineering/scripts/install_local.py --dry-run --verify
git diff --check
git status -sb
```

Expected: Skill valid, installer verification successful, no whitespace errors, and only intended commits ahead of the remote.

- [ ] **Step 5: Record the final test count and changed-file list**

Use `git diff origin/main...HEAD --stat` and the complete test output. Do not claim v3 ready unless every command above exits `0`.
