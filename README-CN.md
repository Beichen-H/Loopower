# Meta Skills Library

面向 Codex-native agent workflow 的可移植、合同优先 Skill 资产库。

当前首个发布 Skill 是 [`prompt-to-loop-engineering`](skills/prompt-to-loop-engineering/SKILL.md)，版本 `1.3.0`：它是 Codex-native Loop Agent Builder，可以把自然语言任务转成经过验证的 `loop_design_result`，并在需要时生成轻量 `.codex-loop/` Agent Config Scaffold。

本项目彻底不包含独立 Runtime Engine。Codex 就是宿主执行器：它读取项目内持久化配置、遵守 guardrails，并在当前用户/会话权限下续跑任务。

[English README](README.md)

## 它让 Codex 获得什么能力

`prompt-to-loop-engineering` 帮 Codex 设计并持久化：

- `LoopSpec`：循环规则、优先级、预算、进度信号和退出路径；
- `agent_manifest.json`：绑定 Codex、工具、知识源、sub-agent prompts 和续跑规则；
- `guardrails.json`：禁止命令、写入边界、需要审批的动作和停止条件；
- 精简 sub-agent prompts，例如 `planner.md` 和 `executor.md`；
- 可选 `.status` 文件，只记录当前 stage/node id。

它刻意保持轻量。`.codex-loop/` 是配置脚手架，不是数据库、队列、checkpoint 存储，也不是隐藏 Runtime。

## 仓库结构

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

## Clone 和本地安装

克隆仓库：

```bash
git clone https://github.com/<your-org>/meta-skills-library.git
cd meta-skills-library
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

## 可选 AGENTS.md 全局委派门禁

如果你希望 Codex 在非平凡任务开始前主动判断是否需要 Loop Agent scaffold 和 sub-agent delegation，可以把可选门禁复制到目标项目根目录：

```bash
mkdir -p examples
cp examples/agents-gate/AGENTS.md /path/to/your-project/AGENTS.md
```

Windows PowerShell：

```powershell
Copy-Item .\examples\agents-gate\AGENTS.md C:\path\to\your-project\AGENTS.md
```

模板 [`examples/agents-gate/AGENTS.md`](examples/agents-gate/AGENTS.md) 定义了 `Two-stage Delegation Approval Gate`：

1. 对 Non-trivial 任务，Codex 必须先给出 `Lineup Recommendation`、`Loop Boundary`、风险和 scaffold 决策。
2. Codex 必须输出 `STOP — Waiting for user approval`。
3. 只有得到用户显式授权后，Codex 才能初始化或更新 `.codex-loop/`、生成 sub-agent prompts，并运行 `validate_codex_loop_scaffold.py`。

这个门禁只负责审批流程和结构化提醒，不安装 Runtime Engine，不授予额外工具权限，也不允许 Codex 绕过用户批准。

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
├── loop_spec.json
├── agent_manifest.json
├── guardrails.json
├── subagents/
│   ├── planner.md
│   └── executor.md
└── .status
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
- manifest 声称存在独立 Runtime Engine。

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

验证 Skill 自身静态 DAG：

```bash
python -B skills/prompt-to-loop-engineering/scripts/test_spec_loading.py
```

验证已发布的 design-result 示例：

```bash
python -B skills/prompt-to-loop-engineering/scripts/validate_design_result.py \
  skills/prompt-to-loop-engineering/examples/agent_loop.json \
  --request skills/prompt-to-loop-engineering/examples/requests/agent_loop.json
```

## License

本仓库采用 [MIT License](LICENSE) 发布。

## Release notes

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
