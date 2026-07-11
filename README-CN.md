# Meta Skills Library

面向 Codex-native agent workflow 的可移植、合同优先 Skill 资产库。

当前首个发布 Skill 是 [`prompt-to-loop-engineering`](skills/prompt-to-loop-engineering/SKILL.md)，版本 `2.0.0`：它是具备可验证请求规范化、预算来源追踪、Evidence-Locked DAG Execution Governance、基于访问模式的审阅者隔离以及版本化多循环进展证据的 Codex-native Loop Agent Builder。它可以把自然语言任务转换为经过验证的 `loop_design_result`，在需要时持久化轻量 `.codex-loop/` Agent Config Scaffold，并在不独占会话路由的前提下治理审批、宿主原生 live sub-agent 激活与后验轨迹验证。

本项目不包含独立 Runtime Engine。Codex 就是宿主执行器：它读取项目本地配置，遵守 guardrails，在宿主支持时通过当前 Codex 宿主的原生能力激活已批准的 live sub-agents，与其他 specialized skills 协作，并在当前用户/会话权限下继续工作。

[English README](README.md)

## 它让 Codex 获得什么能力

`prompt-to-loop-engineering` 帮 Codex 设计并持久化：

- `LoopSpec`：循环规则、优先级、预算、进度信号和退出路径；
- `agent_manifest.json`：绑定 Codex、工具、知识源、sub-agent prompts 和续跑规则；
- `guardrails.json`：禁止命令、写入边界、需要审批的动作和停止条件；
- 精简 sub-agent prompts，例如 `planner.md` 和 `executor.md`；
- 可选 `.status` 文件，只记录当前 stage/node id；
- 用于对齐 `.codex-loop/subagents/*.md` 与 Codex 宿主 Live Subagents Panel 的激活合同；
- non-exclusive 治理覆盖层，让 specialized skills 继续作为 host-resolved atomic capabilities 被使用；
- `required_subagent_reasoning_intensity` 标记，用于记录复杂 live sub-agent 工作所需的 `extended_thought` 推理强度；
- Evidence-Locked DAG Execution Governance，用于阻止已声明的 sub-agent 节点被主会话 inline execution 替代。

它刻意保持轻量。`.codex-loop/` 是配置脚手架，不是数据库、队列、checkpoint 存储，也不是隐藏 runtime。

## 仓库结构

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

## Clone 和本地安装

克隆仓库：

```bash
git clone https://github.com/Beichen-H/meta-skills.git
cd meta-skills
```

安装到本地 Codex skills 目录，并验证内置 LoopSpec：

```bash
python install_local.py --verify
```

Windows PowerShell：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install_local.ps1 -Verify
```

默认安装位置：

```text
~/.codex/skills/prompt-to-loop-engineering/
```

只预览，不写入：

```bash
python install_local.py --dry-run
```

覆盖已有安装：

```bash
python install_local.py --force --verify
```

## installed-mode 兼容性

Codex 的 GitHub skill installer 可能只安装 `skills/prompt-to-loop-engineering/`，而不会复制完整仓库根目录。因此，本项目把运行所需模板也打包进 skill 目录内部。

安装后，委派门禁模板位于：

```text
~/.codex/skills/prompt-to-loop-engineering/templates/agents-gate/AGENTS.md
```

复制到目标项目：

```bash
cp ~/.codex/skills/prompt-to-loop-engineering/templates/agents-gate/AGENTS.md /path/to/your-project/AGENTS.md
```

Windows PowerShell：

```powershell
Copy-Item "$env:USERPROFILE\.codex\skills\prompt-to-loop-engineering\templates\agents-gate\AGENTS.md" C:\path\to\your-project\AGENTS.md
```

仓库根目录的 [`examples/agents-gate/AGENTS.md`](examples/agents-gate/AGENTS.md) 会与打包副本 [`skills/prompt-to-loop-engineering/templates/agents-gate/AGENTS.md`](skills/prompt-to-loop-engineering/templates/agents-gate/AGENTS.md) 保持逐字一致。

## 可选 AGENTS.md 全局委派门禁

如果你希望 Codex 在非平凡任务开始前主动判断是否需要 Loop Agent scaffold 和 sub-agent delegation，可以把可选门禁复制到目标项目根目录：

```bash
cp skills/prompt-to-loop-engineering/templates/agents-gate/AGENTS.md /path/to/your-project/AGENTS.md
```

该模板定义了 `Two-stage Delegation Approval Gate`：

1. 对 Non-trivial 任务，Codex 必须先给出 `Lineup Recommendation`、`Loop Boundary`、风险和 scaffold 决策。
2. Codex 必须输出 `STOP — Waiting for user approval`。
3. 只有得到用户显式授权后，Codex 才能初始化或更新 `.codex-loop/`、生成 sub-agent prompts，并运行 `validate_codex_loop_scaffold.py`。

这个门禁只负责审批流程和结构化提醒，不安装 Runtime Engine，不授予额外工具权限，也不允许 Codex 绕过用户批准。

## Live Subagent Bridge

版本 `1.4.0` 增加了 `Agent Lifecycle Activation Contract`。

当用户显式给出 `GO`，并且 `.codex-loop/` 已经写入且验证通过后，Codex 不能只把 scaffold 当作纯文本。如果当前 Codex 宿主暴露 `spawn_subagent`、`spawn_agent` 或等效原生 sub-agent lifecycle API，Codex 必须把 `.codex-loop/subagents/` 下已批准的角色激活为 live host processes。

每个 live role 必须使用对应本地 prompt 文件作为权威 System Prompt 基线：

```text
.codex-loop/subagents/planner.md  -> planner live process
.codex-loop/subagents/executor.md -> executor live process
.codex-loop/subagents/reviewer.md -> optional reviewer live process
```

如果当前 Codex 宿主没有原生 live sub-agent API，Codex 必须报告 `lifecycle_activation_blocked`。它不得通过创建队列、数据库、daemon 或隐藏 Runtime Engine artifact 来伪造 live sub-agent。

## Model Configuration Inheritance Contract

版本 `1.6.0` 增加 `Model Configuration Inheritance Contract`。

当 Codex 通过 `spawn_subagent`、`spawn_agent`、`multi_agent_v1.spawn_agent` 或等效原生 API 激活 live sub-agents 时，如果宿主暴露 model 或 reasoning 配置参数，就必须显式请求继承父会话的推理配置。

推荐宿主声明：

```text
reasoning_intensity: "extended_thought"
model_config: inherit_parent
```

如果当前宿主 API 无法直接传递模型配置参数，生成的 sub-agent prompts 必须包含兜底指令，要求子线程在开始实质性工作前请求对齐父会话的 5.5 ultra-high reasoning profile。若无法确认对齐，子线程必须报告 `model_configuration_degraded`。

任何依赖 live sub-agents 的 `agent_loop` scaffold，都必须在 `loop_spec.json` 中记录该要求：

```json
{
  "runtime_binding": {
    "capabilities_snapshot": {
      "required_subagent_reasoning_intensity": "extended_thought"
    }
  }
}
```

当设计需要 sub-agents 时，同样的值也必须出现在 `runtime_binding.required_capabilities.required_subagent_reasoning_intensity`。验证器可以拒绝缺失或弱化的值。

## Cooperative Governance Overlay

版本 `1.5.0` 明确本 skill 是 non-exclusive 的治理层。它不替代系统级 skills、superpowers-style skills、browser tools、research tools、code-generation skills、debugging skills 或 document/data skills。

当 `$prompt-to-loop-engineering` 被显式调用，或 `AGENTS.md` 加载本合同后，它会在非平凡 scaffold 创建或生命周期激活前治理五个变量：

- `task_classification`
- `capability_snapshot`
- `lineup_recommendation`
- `loop_boundary`
- `approval_state`

Specialized skills 仍然是各自领域的主要能力提供者。loop scaffold 只能把它们引用为 host-resolved atomic capabilities：Codex 可以通过正常宿主路由或明确暴露的 tool API 使用它们，但本 skill 不得假装它们是私有函数、后台 worker 或异步工具。

这是一种 AGENTS-scoped middleware semantics，不是 transparent global interceptor。如果本合同没有通过显式调用或更高优先级指令层加载，它不能静默拦截每一次 Codex action。

## Evidence-Locked DAG Execution Governance

版本 `1.7.0` 增加 `Evidence-Locked DAG Execution Governance`。

在用户显式给出 `GO` 之后，持久化的 `.codex-loop/loop_spec.json` 拥有 DAG 调度权。Codex 仍然可以在授权节点内部使用 specialized host skills 作为 host-resolved atomic capabilities，但这些能力不得接管 scheduler，也不得把脚手架坍缩为 inline execution。

生成的 scaffold 必须声明：

```text
loop_spec.execution_governance.runtime_mode = COOPERATIVE_GOVERNANCE
loop_spec.execution_governance.scheduler = codex_loop_dag
loop_spec.execution_governance.inline_execution_policy = forbidden_for_subagent_nodes
agent_manifest.governance_overlay.host_linear_fulfillment_takeover = forbidden
```

依赖 sub-agent 节点的 GO 阶段工作必须在以下目录创建轻量证据：

```text
.codex-loop/evidence/activation/
.codex-loop/evidence/handoff/
.codex-loop/evidence/completion/
```

使用 post-hoc hard validator 拒绝缺少 activation、handoff、completion、model-inheritance 或 inline-fulfillment 证据的运行轨迹：

```bash
python ~/.codex/skills/prompt-to-loop-engineering/scripts/validate_dag_execution_evidence.py .codex-loop
```

## 在 Codex 项目中使用

安装后，在任意 Codex 项目中输入：

```text
$prompt-to-loop-engineering

请分析当前项目需求，并创建一个轻量 .codex-loop/ Agent Config Scaffold：
- .codex-loop/loop_spec.json
- .codex-loop/agent_manifest.json
- .codex-loop/guardrails.json
- .codex-loop/subagents/planner.md
- .codex-loop/subagents/executor.md
- 可选 .codex-loop/.status
- 可选 .codex-loop/evidence/ lifecycle stubs，在 GO 阶段工作开始后记录证据

然后用本地脚本验证这个 scaffold。
```

Codex 应读取该 Skill，为当前项目生成 scaffold，并运行：

```bash
python ~/.codex/skills/prompt-to-loop-engineering/scripts/validate_codex_loop_scaffold.py .codex-loop
```

如果你正在本仓库内开发，使用：

```bash
python skills/prompt-to-loop-engineering/scripts/validate_codex_loop_scaffold.py \
  skills/prompt-to-loop-engineering/examples/codex-loop
```

## Scaffold 合同

有效 scaffold 的最小结构：

```text
.codex-loop/
|-- loop_spec.json
|-- agent_manifest.json
|-- guardrails.json
|-- subagents/
|   |-- planner.md
|   `-- executor.md
|-- evidence/
|   |-- activation/
|   |-- handoff/
|   `-- completion/
`-- .status
```

可选：

```text
.codex-loop/subagents/reviewer.md
```

验证器会拒绝：

- 缺少必要文件；
- 目录名不是 `.codex-loop`；
- `runtime/`、`state.json`、队列、数据库、checkpoint 存储等 runtime 产物；
- 多行或非法 `.status`；
- manifest 声明的 sub-agent prompt 文件不存在；
- manifest 声称存在独立 Runtime Engine；
- evidence-governed DAG runs 缺少 `activation`、`handoff` 或 `completion` 证据；
- sub-agent-governed nodes 出现 inline execution evidence。

## 本地验证

运行全部测试：

```bash
python -B -m unittest discover -s skills/prompt-to-loop-engineering/scripts -p "test_*.py" -v
```

验证内置 scaffold 示例：

```bash
python -B skills/prompt-to-loop-engineering/scripts/validate_codex_loop_scaffold.py \
  skills/prompt-to-loop-engineering/examples/codex-loop
```

验证 post-hoc DAG execution evidence：

```bash
python -B skills/prompt-to-loop-engineering/scripts/validate_dag_execution_evidence.py \
  skills/prompt-to-loop-engineering/examples/codex-loop
```

验证 Skill 自身静态 DAG：

```bash
python -B skills/prompt-to-loop-engineering/scripts/test_spec_loading.py
```

验证已发布的 design-result 示例：

在设计验证前，先规范化缺少预算字段的原始请求：

```bash
python skills/prompt-to-loop-engineering/scripts/normalize_design_request.py \
  path/to/raw_request.json \
  --output path/to/effective_request.json \
  --report path/to/request_normalization_report.json
```

该命令不会修改源文件。缺失上限使用版本化 `codex-native-safe-v1` 策略；显式无效值会失败，不会被悄悄替换。随后使用 effective request 执行下面的验证命令。

```bash
python -B skills/prompt-to-loop-engineering/scripts/validate_design_result.py \
  path/to/loop_design_result.json \
  --request path/to/effective_request.json \
  --raw-request path/to/raw_request.json \
  --normalization-report path/to/request_normalization_report.json
```

## License

本仓库采用 [MIT License](LICENSE) 发布。

## Release notes

### v2.0.0 (2026-07-10)

- 将 raw/effective request 哈希与规范化来源报告升级为 Validator 强制输入。
- 统一能力 Schema 与 Validator，包括 `required_subagent_reasoning_intensity`。
- 分离设计期 LoopSpec 与 GO 阶段 scaffold 的治理字段要求。
- 使用声明式 `access_mode` 替代 reviewer 工具名黑名单。
- 新增 `progress_evidence.schema.json` v2，覆盖 run/cycle 身份、连续序列、权威计数器与多 Cycle 隔离。
- 增加发布表面回归测试与更严格的 CI 门禁。

### v1.9.0 (2026-07-10)

- 新增 `scripts/normalize_design_request.py`，在不修改用户原始输入的前提下生成严格的 effective request。
- 新增版本化 `codex-native-safe-v1` 预算策略：900 秒、3 次迭代、45,000 Token、1 次无进展循环。
- 新增确定性规范化来源报告，记录 raw/effective 哈希以及显式值和默认值。
- 保持 `validate_design_result.py` fail-closed，禁止验证器隐式修复输入。
- 扩展 `validate_loop_progress_evidence.py`，根据持久化 LoopSpec 阈值执行运行时长、迭代、Token 和无进展四项熔断。

### v1.8.0 (2026-07-09)

- 增加 `Evidence-Locked & Role-Isolated Governance`。
- 强制四个循环硬上限：`max_runtime_seconds`、`max_iterations`、`max_token_budget` 和 `max_no_progress_loops`。
- 增加 node role metadata 与 implementer/reviewer isolation validation。
- 增加 deterministic no-progress progress-signal 要求。
- 增加 `scripts/validate_loop_progress_evidence.py`，用于 post-hoc stalled-loop detection。

### v1.7.0 (2026-07-07)

- 增加 `Evidence-Locked DAG Execution Governance`。
- 在 `loop_spec.json` 增加 `execution_governance`，在 `agent_manifest.json` 增加 `governance_overlay`。
- 增加 `.codex-loop/evidence/{activation,handoff,completion}/` 示例桩。
- 增加 `scripts/validate_dag_execution_evidence.py`，用于 post-hoc hard validation。
- 明确禁止显式 GO 后由线性 host skill 接管 scheduler；specialized skills 只能作为 node-scoped atomic capabilities 使用。
- 增加缺少 activation、handoff、completion、reasoning-inheritance 与 inline execution 证据时的失败测试。

### v1.6.0 (2026-07-06)

- 增加 `Model Configuration Inheritance Contract`。
- 要求宿主原生 sub-agent 激活在可用时显式请求 `reasoning_intensity: "extended_thought"` 或 `model_config: inherit_parent`。
- 为无法直接传递模型配置参数的宿主增加 sub-agent prompt 兜底要求。
- 在 scaffold capability snapshot 与 required capabilities 中增加 `required_subagent_reasoning_intensity: "extended_thought"`。
- 加强 scaffold 验证：依赖 sub-agent 的 scaffold 若缺少推理强度标记，将被拒绝。

### v1.5.0 (2026-07-05)

- 增加 `Cooperative Governance Overlay` 合同。
- 明确本 skill 是 non-exclusive，不能声称拥有整个会话的独占路由权。
- 定义 AGENTS-scoped middleware semantics，同时禁止 background daemon、global hook、scheduler 或 hidden runtime 行为。
- 将外部 skills、plugins、connectors 和 tools 重构为 host-resolved atomic capabilities，而不是可直接调用的私有函数。
- 增加五个治理变量：`task_classification`、`capability_snapshot`、`lineup_recommendation`、`loop_boundary` 和 `approval_state`。
- 保留 specialized host skills 作为主要能力提供者，同时由本 skill 治理 loop design、approval、scaffold persistence 和 lifecycle boundaries。

### v1.4.0 (2026-07-02)

- 通过 `Agent Lifecycle Activation Contract` 增加 Codex-native Live Subagent Bridge。
- 将 `Two-stage Delegation Approval Gate` 打包进已安装 skill 内部：`templates/agents-gate/AGENTS.md`。
- 保留仓库根目录副本 `examples/agents-gate/AGENTS.md`，并增加测试防止两份模板漂移。
- 增加 installed-mode 兼容性检查，使 path-only Codex 安装后的 skill 也能被验证。
- 增加 GitHub Actions CI，覆盖单元测试、scaffold 验证、DAG 验证和已发布示例验证。

### v1.3.0 (2026-06-30)

- 将 `prompt-to-loop-engineering` 定位为 Codex-native Loop Agent Builder。
- 永久移除独立 Runtime Engine 职责。
- 增加轻量 `.codex-loop/` Agent Config Scaffold 合同。
- 增加 `schemas/agent_manifest.schema.json` 和 `schemas/guardrails.schema.json`。
- 增加 `scripts/validate_codex_loop_scaffold.py`。
- 增加完整 scaffold 示例 `examples/codex-loop/`。
- 增加本地一键安装与验证脚本。
- 增加可选 `Two-stage Delegation Approval Gate` 模板：`examples/agents-gate/AGENTS.md`。
- 以 MIT License 发布仓库。

### v1.0.0 (2026-06-22)

- 初始化多 Skill 资产库。
- 发布首个 Skill：`prompt-to-loop-engineering`。
- 固化 Loop Engineering KB v4.0.2 的 request/result 边界和 build/runtime-result 分离原则。
