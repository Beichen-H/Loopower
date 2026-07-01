# Meta Skills Library

Portable, contract-first skills for Codex-native agent workflows.

The first published skill is [`prompt-to-loop-engineering`](skills/prompt-to-loop-engineering/SKILL.md), version `1.3.0`: a Codex-native Loop Agent Builder that turns a natural-language task into a validated `loop_design_result` and, when requested, a lightweight `.codex-loop/` Agent Config Scaffold.

This project does not contain an independent Runtime Engine. Codex is the host executor: it reads persisted project-local configuration, respects guardrails, and continues work under the active user/session permissions.

[中文说明](README-CN.md)

## What it gives Codex

`prompt-to-loop-engineering` helps Codex design and persist:

- a `LoopSpec` with loop rules, priorities, budgets, progress signals, and exit paths;
- an `agent_manifest.json` binding Codex to tools, knowledge sources, sub-agent prompts, and resume rules;
- a `guardrails.json` file for forbidden commands, write boundaries, approval-required actions, and stop conditions;
- compact sub-agent prompts such as `planner.md` and `executor.md`;
- an optional `.status` file that stores only the current stage/node id.

It is intentionally small. `.codex-loop/` is configuration, not a database, queue, checkpoint store, or hidden runtime.

## Repository layout

```text
meta-skills-library/
├── README.md
├── README-CN.md
├── LICENSE
├── examples/
│   └── agents-gate/AGENTS.md
├── install_local.py
├── install_local.ps1
└── skills/
    └── prompt-to-loop-engineering/
        ├── SKILL.md
        ├── loop_spec.json
        ├── agents/openai.yaml
        ├── schemas/
        ├── examples/
        └── scripts/
```

## Local Installation

Clone the repository:

```bash
git clone https://github.com/<your-org>/meta-skills-library.git
cd meta-skills-library
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

## Optional AGENTS.md delegation gate

For teams that want Codex to proactively consider Loop Agent scaffolding and sub-agent delegation, copy the optional gate into the target project root:

```bash
mkdir -p examples
cp examples/agents-gate/AGENTS.md /path/to/your-project/AGENTS.md
```

On Windows PowerShell:

```powershell
Copy-Item .\examples\agents-gate\AGENTS.md C:\path\to\your-project\AGENTS.md
```

The template at [`examples/agents-gate/AGENTS.md`](examples/agents-gate/AGENTS.md) defines a `Two-stage Delegation Approval Gate`:

1. For Non-trivial work, Codex first presents a `Lineup Recommendation`, `Loop Boundary`, risks, and scaffold decision.
2. Codex then prints `STOP — Waiting for user approval`.
3. Only after explicit user approval may Codex initialize or update `.codex-loop/`, generate sub-agent prompts, and run `validate_codex_loop_scaffold.py`.

This gate is advisory and permission-preserving. It does not install a Runtime Engine, does not grant tool permissions, and does not allow Codex to bypass user approval.

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
├── loop_spec.json
├── agent_manifest.json
├── guardrails.json
├── subagents/
│   ├── planner.md
│   └── executor.md
└── .status
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
