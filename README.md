# Meta Skills Library

Portable, contract-first skills for Codex-native agent workflows.

The first published skill is [`prompt-to-loop-engineering`](skills/prompt-to-loop-engineering/SKILL.md), version `1.6.1`: a Codex-native Loop Agent Builder, Live Subagent Bridge, Cooperative Governance Overlay, and Model Configuration Inheritance Contract. It turns a natural-language task into a validated `loop_design_result`, persists a lightweight `.codex-loop/` Agent Config Scaffold when requested, and defines how Codex should coordinate approval, scaffold lifecycle, host-native live sub-agent activation, and sub-agent reasoning intensity alignment without taking exclusive control of the session.

This project does not contain an independent Runtime Engine. Codex is the host executor: it reads project-local configuration, respects guardrails, activates approved live sub-agents through the current Codex host when available, cooperates with other specialized skills, and continues work under the active user/session permissions.

[中文说明](README-CN.md)

## What it gives Codex

`prompt-to-loop-engineering` helps Codex design and persist:

- a `LoopSpec` with loop rules, priorities, budgets, progress signals, and exit paths;
- an `agent_manifest.json` binding Codex to tools, knowledge sources, sub-agent prompts, and resume rules;
- a `guardrails.json` file for forbidden commands, write boundaries, approval-required actions, and stop conditions;
- compact sub-agent prompts such as `planner.md` and `executor.md`;
- an optional `.status` file that stores only the current stage/node id;
- an activation contract for aligning `.codex-loop/subagents/*.md` with the Codex host's Live Subagents Panel;
- a non-exclusive governance overlay that keeps specialized skills available as host-resolved atomic capabilities;
- a `required_subagent_reasoning_intensity` marker that records `extended_thought` requirements for complex live sub-agent work.

It is intentionally small. `.codex-loop/` is configuration, not a database, queue, checkpoint store, or hidden runtime.

## Repository layout

```text
meta-skills-library/
|-- README.md
|-- README-CN.md
|-- LICENSE
|-- .github/workflows/ci.yml
|-- examples/
|   `-- agents-gate/AGENTS.md
|-- install_local.py
|-- install_local.ps1
`-- skills/
    `-- prompt-to-loop-engineering/
        |-- SKILL.md
        |-- loop_spec.json
        |-- agents/openai.yaml
        |-- schemas/
        |-- examples/
        |-- templates/
        |   `-- agents-gate/AGENTS.md
        `-- scripts/
```

## Local Installation

Clone the repository:

```bash
git clone https://github.com/Beichen-H/meta-skills.git
cd meta-skills
```

Install the skill into the local Codex skills directory and verify the bundled LoopSpec:

```bash
python install_local.py --verify
```

On Windows PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install_local.ps1 -Verify
```

Default install location:

```text
~/.codex/skills/prompt-to-loop-engineering/
```

Preview without writing files:

```bash
python install_local.py --dry-run
```

Replace an existing local install:

```bash
python install_local.py --force --verify
```

## Installed-mode compatibility

Codex's GitHub skill installer may install only `skills/prompt-to-loop-engineering/` rather than the full repository root. The skill therefore packages operational templates inside the skill directory itself.

After installation, the delegation gate is available at:

```text
~/.codex/skills/prompt-to-loop-engineering/templates/agents-gate/AGENTS.md
```

Copy it into a target project with:

```bash
cp ~/.codex/skills/prompt-to-loop-engineering/templates/agents-gate/AGENTS.md /path/to/your-project/AGENTS.md
```

On Windows PowerShell:

```powershell
Copy-Item "$env:USERPROFILE\.codex\skills\prompt-to-loop-engineering\templates\agents-gate\AGENTS.md" C:\path\to\your-project\AGENTS.md
```

The repository-root copy at [`examples/agents-gate/AGENTS.md`](examples/agents-gate/AGENTS.md) is kept byte-for-byte aligned with the packaged copy at [`skills/prompt-to-loop-engineering/templates/agents-gate/AGENTS.md`](skills/prompt-to-loop-engineering/templates/agents-gate/AGENTS.md).

## Optional AGENTS.md delegation gate

For teams that want Codex to proactively consider Loop Agent scaffolding and sub-agent delegation, copy the optional gate into the target project root:

```bash
cp skills/prompt-to-loop-engineering/templates/agents-gate/AGENTS.md /path/to/your-project/AGENTS.md
```

The template defines a `Two-stage Delegation Approval Gate`:

1. For Non-trivial work, Codex first presents a `Lineup Recommendation`, `Loop Boundary`, risks, and scaffold decision.
2. Codex then prints `STOP — Waiting for user approval`.
3. Only after explicit user approval may Codex initialize or update `.codex-loop/`, generate sub-agent prompts, and run `validate_codex_loop_scaffold.py`.

This gate is advisory and permission-preserving. It does not install a Runtime Engine, does not grant tool permissions, and does not allow Codex to bypass user approval.

## Live Subagent Bridge

Version `1.4.0` adds the `Agent Lifecycle Activation Contract`.

After a user gives explicit `GO`, and after `.codex-loop/` has been written and validated, Codex must not treat the scaffold as passive text only. If the current Codex host exposes `spawn_subagent`, `spawn_agent`, or an equivalent native sub-agent lifecycle API, Codex must activate approved roles from `.codex-loop/subagents/` as live host processes.

Each live role must use the corresponding local prompt file as its authoritative System Prompt baseline:

```text
.codex-loop/subagents/planner.md  -> planner live process
.codex-loop/subagents/executor.md -> executor live process
.codex-loop/subagents/reviewer.md -> optional reviewer live process
```

If the active Codex host does not expose a native live sub-agent API, Codex must report `lifecycle_activation_blocked`. It must not emulate live sub-agents by creating queues, databases, daemons, or hidden Runtime Engine artifacts.

Before Codex sets `runtime_capabilities.subagents=false`, it must first use `tool_search` to discover `spawn_agent`, `spawn_subagent`, `subagent`, and `multi_agent` lifecycle tools. If discovery finds a host-native lifecycle tool, `subagents` must be `true`; only a recorded `tool_search` miss such as `no_host_native_lifecycle_tool_found` may justify `subagents=false`.

## Model Configuration Inheritance Contract

Version `1.6.0` adds the `Model Configuration Inheritance Contract`.

When Codex activates live sub-agents through `spawn_subagent`, `spawn_agent`, `multi_agent_v1.spawn_agent`, or an equivalent native API, it must explicitly request parent-level reasoning inheritance whenever the host exposes a model or reasoning configuration parameter.

Preferred host declarations include:

```text
reasoning_intensity: "extended_thought"
model_config: inherit_parent
```

If the active host API cannot pass a model configuration parameter, generated sub-agent prompts must include a fallback instruction requiring the child thread to request alignment with the parent 5.5 ultra-high reasoning profile before substantive work. If alignment cannot be confirmed, the child must report `model_configuration_degraded`.

Every generated `agent_loop` scaffold that relies on live sub-agents must log the requirement in `loop_spec.json`:

```json
{
  "runtime_binding": {
    "capabilities_snapshot": {
      "required_subagent_reasoning_intensity": "extended_thought"
    }
  }
}
```

The same value must appear in `runtime_binding.required_capabilities.required_subagent_reasoning_intensity` when sub-agents are required for the design. Validators may reject weaker or missing values.

## Cooperative Governance Overlay

Version `1.5.0` makes the skill explicitly non-exclusive. It does not replace system-level skills, superpowers-style skills, browser tools, research tools, code-generation skills, debugging skills, or document/data skills.

Instead, when `$prompt-to-loop-engineering` is invoked or when an `AGENTS.md` file loads this contract, it governs five variables before non-trivial scaffold creation or lifecycle activation:

- `task_classification`
- `capability_snapshot`
- `lineup_recommendation`
- `loop_boundary`
- `approval_state`

Specialized skills remain primary providers for their own domains. The loop scaffold may reference them only as host-resolved atomic capabilities: Codex may use them through normal host routing or concrete exposed tool APIs, but this skill must not pretend they are private functions, background workers, or asynchronous tools.

This is AGENTS-scoped middleware semantics, not a transparent global interceptor. If the contract is not loaded by explicit invocation or a higher-priority instruction layer, it cannot silently intercept every Codex action.

When this skill is invoked, or when an `AGENTS.md` overlay loads it, its mandatory execution protocol remains the primary workflow for loop design and scaffold lifecycle. External plan helpers such as `superpowers:executing-plans` may be used only as auxiliary checklists after they are reconciled with this skill; they cannot override approval gates, validation, planner/executor separation, or live sub-agent activation.

## Use in a Codex project

After installation, open any project in Codex and ask:

```text
$prompt-to-loop-engineering

Analyze this project request and create a lightweight .codex-loop/ Agent Config Scaffold:
- .codex-loop/loop_spec.json
- .codex-loop/agent_manifest.json
- .codex-loop/guardrails.json
- .codex-loop/subagents/planner.md
- .codex-loop/subagents/executor.md
- optional .codex-loop/.status

Then validate the scaffold with the local script.
```

Codex should read the skill, generate the scaffold for the current project, and run:

```bash
python ~/.codex/skills/prompt-to-loop-engineering/scripts/validate_codex_loop_scaffold.py .codex-loop
```

If you are developing this repository directly, use:

```bash
python skills/prompt-to-loop-engineering/scripts/validate_codex_loop_scaffold.py \
  skills/prompt-to-loop-engineering/examples/codex-loop
```

## Scaffold contract

A valid scaffold has this minimal shape:

```text
.codex-loop/
|-- loop_spec.json
|-- agent_manifest.json
|-- guardrails.json
|-- subagents/
|   |-- planner.md
|   `-- executor.md
`-- .status
```

Optional:

```text
.codex-loop/subagents/reviewer.md
```

Validation rejects:

- missing required files;
- a directory not named `.codex-loop`;
- `runtime/`, `state.json`, queues, databases, checkpoint stores, or similar runtime artifacts;
- multiline or invalid `.status`;
- manifest sub-agents whose prompt files are missing;
- manifests that claim an independent Runtime Engine.

## Local verification

Run all tests:

```bash
python -B -m unittest discover -s skills/prompt-to-loop-engineering/scripts -p "test_*.py" -v
```

Validate the bundled scaffold example:

```bash
python -B skills/prompt-to-loop-engineering/scripts/validate_codex_loop_scaffold.py \
  skills/prompt-to-loop-engineering/examples/codex-loop
```

Validate the skill's own static DAG:

```bash
python -B skills/prompt-to-loop-engineering/scripts/test_spec_loading.py
```

Validate published design-result examples:

```bash
python -B skills/prompt-to-loop-engineering/scripts/validate_design_result.py \
  skills/prompt-to-loop-engineering/examples/agent_loop.json \
  --request skills/prompt-to-loop-engineering/examples/requests/agent_loop.json
```

## License

This repository is released under the [MIT License](LICENSE).

## Release notes

### v1.6.1 (2026-07-08)

- Added workflow precedence rules so external plan helpers, including `superpowers:executing-plans`, cannot override this skill's mandatory execution protocol.
- Required `tool_search` discovery for host-native sub-agent lifecycle tools before normalizing `runtime_capabilities.subagents`.
- Strengthened validation so `subagents=false` requires evidence that `spawn_agent` / `spawn_subagent` / `subagent` / `multi_agent` discovery was attempted and no host-native lifecycle tool was available.

### v1.6.0 (2026-07-06)

- Added the `Model Configuration Inheritance Contract`.
- Required host-native sub-agent activation to request `reasoning_intensity: "extended_thought"` or `model_config: inherit_parent` when those parameters are available.
- Added fallback prompt requirements for hosts that cannot pass model configuration parameters directly.
- Added `required_subagent_reasoning_intensity: "extended_thought"` to scaffold capability snapshots and required capabilities.
- Strengthened scaffold validation to reject sub-agent scaffolds that omit the required reasoning intensity marker.

### v1.5.0 (2026-07-05)

- Added the `Cooperative Governance Overlay` contract.
- Clarified that the skill is non-exclusive and must not claim session-wide routing ownership.
- Defined AGENTS-scoped middleware semantics without background daemon, global hook, scheduler, or hidden runtime behavior.
- Reframed external skills, plugins, connectors, and tools as host-resolved atomic capabilities rather than directly callable private functions.
- Added the five governance variables: `task_classification`, `capability_snapshot`, `lineup_recommendation`, `loop_boundary`, and `approval_state`.
- Preserved specialized host skills as primary capability providers while keeping loop design, approval, scaffold persistence, and lifecycle boundaries under this skill's governance.

### v1.4.0 (2026-07-02)

- Added the Codex-native Live Subagent Bridge through the `Agent Lifecycle Activation Contract`.
- Packaged the `Two-stage Delegation Approval Gate` inside the installed skill at `templates/agents-gate/AGENTS.md`.
- Preserved a repository-level copy at `examples/agents-gate/AGENTS.md` and added tests to prevent divergence.
- Added installed-mode compatibility checks so the skill can be verified after path-only Codex installation.
- Added GitHub Actions CI for unit tests, scaffold validation, DAG validation, and published example validation.

### v1.3.0 (2026-06-30)

- Reframed `prompt-to-loop-engineering` as a Codex-native Loop Agent Builder.
- Permanently removed independent Runtime Engine responsibility from this project.
- Added the lightweight `.codex-loop/` Agent Config Scaffold contract.
- Added `schemas/agent_manifest.schema.json` and `schemas/guardrails.schema.json`.
- Added `scripts/validate_codex_loop_scaffold.py`.
- Added a complete scaffold example under `examples/codex-loop/`.
- Added local install scripts for one-command install and verification.
- Added an optional `Two-stage Delegation Approval Gate` template at `examples/agents-gate/AGENTS.md`.
- Published the repository under the MIT License.

### v1.0.0 (2026-06-22)

- Initialized the multi-skill asset repository.
- Published the first skill: `prompt-to-loop-engineering`.
- Captured the Loop Engineering KB v4.0.2 request/result boundary and build/runtime-result separation.
