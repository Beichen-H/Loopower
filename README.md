# Meta Skills Library

Portable, contract-first skills for Codex-native agent workflows.

The first published skill is [`prompt-to-loop-engineering`](skills/prompt-to-loop-engineering/SKILL.md), version `1.4.0`: a Codex-native Loop Agent Builder and Live Subagent Bridge. It turns a natural-language task into a validated `loop_design_result`, persists a lightweight `.codex-loop/` Agent Config Scaffold when requested, and defines how Codex should activate the scaffold through host-native live sub-agent APIs when those APIs are available.

This project does not contain an independent Runtime Engine. Codex is the host executor: it reads project-local configuration, respects guardrails, activates approved live sub-agents through the current Codex host, and continues work under the active user/session permissions.

[中文说明](README-CN.md)

## What it gives Codex

`prompt-to-loop-engineering` helps Codex design and persist:

- a `LoopSpec` with loop rules, priorities, budgets, progress signals, and exit paths;
- an `agent_manifest.json` binding Codex to tools, knowledge sources, sub-agent prompts, and resume rules;
- a `guardrails.json` file for forbidden commands, write boundaries, approval-required actions, and stop conditions;
- compact sub-agent prompts such as `planner.md` and `executor.md`;
- an optional `.status` file that stores only the current stage/node id;
- an activation contract for aligning `.codex-loop/subagents/*.md` with the Codex host's Live Subagents Panel.

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
