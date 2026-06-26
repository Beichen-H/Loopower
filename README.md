# Meta Skills Library

`meta-skills-library` 是面向 Codex、其他 AI Agent、编排器和轻量运行时的可移植技能资产仓库。仓库只发布角色中立、合同优先、可独立校验的 Skill；调用者身份、权限、凭据、执行策略和最终审批始终由外部控制器负责。

首个资产是 [`prompt-to-loop-engineering`](skills/prompt-to-loop-engineering/SKILL.md)：接收自然语言任务，依据 **Loop Engineering KB v4.0.2** 生成确定性的 `loop_design_result`。简单任务返回 `one_shot`；只有固定多步路径或环境反馈确实会改变后续动作时，才生成 `workflow` 或 `agent_loop`。

## 仓库结构

```text
meta-skills-library/
├── README.md
└── skills/
    └── prompt-to-loop-engineering/
        ├── agents/openai.yaml
        ├── examples/
        │   ├── one_shot.json
        │   ├── workflow.json
        │   ├── agent_loop.json
        │   ├── needs_input.json
        │   └── unsupported.json
        ├── schemas/
        │   ├── loop_design_request.schema.json
        │   ├── loop_design_result.schema.json
        │   └── loop_spec.schema.json
        ├── scripts/
        │   ├── validate_design_result.py
        │   ├── test_spec_loading.py
        │   ├── test_skill_surface.py
        │   └── test_validate_design_result.py
        ├── SKILL.md
        └── loop_spec.json
```

每个 Skill 目录必须自包含：`SKILL.md` 负责发现、合同和操作说明；`agents/openai.yaml` 提供 Codex/OpenAI 界面元数据；`schemas/` 固化机器可读合同；`examples/` 提供可回归的参考结果；`scripts/` 只放确定性且经过测试的实现。

## 直接作为 Codex Skill 使用

当前 `v1.2.0` 不包含、也不依赖专用 Runtime Engine。将完整 Skill 目录安装或链接到 Codex 的技能目录后，在请求中使用 `$prompt-to-loop-engineering`。Agent 必须保存规范化请求和一个 `loop_design_result` JSON，并在返回 `spec_ready` 前执行：

```bash
python scripts/validate_design_result.py path/to/loop_design_result.json \
  --request path/to/Loop_design_request.json
```

验证失败时不得输出 `spec_ready`。`scripts/test_spec_loading.py` 只验证 Skill 自身五阶段流程是 DAG；生成的 `agent_loop` 可以包含 Cycle，但必须通过结果验证器证明该 Cycle 已声明进度信号、预算、停滞规则和退出路径。

## 导出与外部 Runtime 接入

1. 以 `skills/<skill-name>/` 为资产边界复制目录，或将完整目录打包为 tar/zip；不要只导出 `SKILL.md`。
2. 不执行生成结果时，Codex 或其他支持文件读取与 Python 命令的 Agent 已足够，无需 Runtime Engine。
3. 需要真正执行 `workflow` 或 `agent_loop` 时，外部 Runtime 再加载已验证的 `loop_spec`，并负责确定性边选择、状态、工具权限、预算、终态和审计。
4. 仅当 `build_report.status=spec_ready` 且 `validation_report.valid=true` 时，Runtime 才能接收生成的 `loop_spec`。`needs_input`、`unsupported` 和 `rejected` 不得执行。
5. 构建成功不等于用户任务通过；只有执行运行时产生的 `runtime_result.status=passed` 才表示任务通过。

Runtime Engine 不属于本 Skill 的职责或目录边界。若需要执行已验证的蓝图，应由独立仓库或宿主框架实现外部控制器。

## 质量检查

在仓库根目录执行：

```bash
python -m unittest discover -s skills/prompt-to-loop-engineering/scripts -p "test_*.py" -v
```

验证器为纯 Python 标准库实现，不要求第三方依赖。提交中不得包含 `__pycache__`、`.pyc`、密钥、运行时状态或本地生成产物。

## 贡献约定

- 版本遵循 Semantic Versioning：文件内容使用 `MAJOR.MINOR.PATCH`，Git tag/发布名使用 `vMAJOR.MINOR.PATCH`。
- 破坏输入/输出合同或状态语义时升级 MAJOR；向后兼容地增加能力时升级 MINOR；兼容修复升级 PATCH。
- 新增或修改 Skill 时，先提供失败基线，再实现最小合同，最后运行 JSON、图、引用、优先级和示例验证。
- 所有阈值必须记录来源与理由；禁止无预算、无停滞规则或无退出路径的循环。
- 外部写入、网络、凭据、审批和不可逆操作必须由宿主策略显式授权。

## Release Notes

### v1.2.0 (2026-06-24)

- 将静态验证改为 `Loop_design_request` 与 `loop_design_result` 成对校验，拒绝伪造的能力快照。
- 强制 `one_shot`、`needs_input`、`unsupported`、`rejected` 的 `loop_spec=null`。
- 校验工具、持久化、checkpoint、审批、并行、worker/sub-agent 与 sandbox 的真实能力绑定。
- 将 Edge、Cycle exit 与进度信号改为结构化、控制器可观察的谓词。
- 完整校验六维正交架构、验收证据和 evaluator bindings、可达性、状态范围、策略与阈值引用。
- 修复 agent-loop 示例中的虚构持久化、非规范架构标签和 pass/stop 终态混用。
- 明确排除 Runtime Engine：本资产只负责静态设计、构建结果与静态验证。

### v1.1.0 (2026-06-24)

- 增加 Codex/OpenAI 技能发现元数据 `agents/openai.yaml`。
- 发布 `Loop_design_request`、`loop_design_result` 与 `LoopSpec` 三个 JSON Schema。
- 增加纯标准库结果验证器，验证状态映射、拓扑引用、优先级和受控 Cycle 完整性。
- 发布 `one_shot`、`workflow`、`agent_loop`、`needs_input`、`unsupported` 五类回归示例。
- 在 `SKILL.md` 中强制执行“读取自身运行图 → 生成结果 → 本地验证 → 验证失败不得 `spec_ready`”协议。
- 保持无专用 Runtime 依赖，并将执行职责留给外部控制器。

### v1.0.0 (2026-06-22)

- 初始化多技能资产仓库结构。
- 发布首个超级 Skill：`prompt-to-loop-engineering`。
- 固化 Loop Engineering KB v4.0.2 的输入/输出合同、`one_shot` 合法终态与 build/runtime 结果隔离原则。
- 发布五阶段控制图：`workspace_preflight` → `task_contract_building` → `orthogonal_composing` → `static_validation` → `terminal_export`。
