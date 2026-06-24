# Meta Skills Library

`meta-skills-library` 是面向 Agent、编排器和轻量级运行时的可移植技能资产仓库。仓库只发布角色中立、合同优先、可独立校验的 Skill；调用者身份、全局权限、凭据、执行策略与最终审批始终由外部控制器负责。

当前首个资产是 [`prompt-to-loop-engineering`](skills/prompt-to-loop-engineering/SKILL.md)：接收自然语言任务，依据 **Loop Engineering KB v4.0.2** 生成确定性的 `loop_design_result`。简单任务返回 `one_shot`，只有固定多步路径或环境反馈确实改变后续动作时才生成完整 `LoopSpec`。

## 仓库结构

```text
meta-skills-library/
├── README.md
└── skills/
    └── prompt-to-loop-engineering/
        ├── SKILL.md
        ├── loop_spec.json
        └── scripts/
```

每个 Skill 目录必须自包含：`SKILL.md` 负责发现、合同和操作说明；`loop_spec.json`（如存在）描述该 Skill 自身的可执行控制图；`scripts/` 只放可重复、确定性且经过测试的实现。不得把宿主角色、人设、全局调度、凭据或平台特权写入 Skill。

## 导出与运行时接入

1. 以 `skills/<skill-name>/` 为资产边界复制目录，或在发布流水线中将该目录打包为 tar/zip；不要只导出 `SKILL.md`。
2. 外部 Runtime Engine 读取 `SKILL.md` 的输入/输出合同，加载 `loop_spec.json`，校验 `version`、引用、节点、边、权限与运行时能力快照。
3. Runtime 将 `Loop_design_request` 注入入口节点，并按 `edge_selection_policy` 由确定性控制器选择边；模型只能生成声明过的结构化输出或提出候选，不能直接执行工具或改变控制流。
4. Runtime 接收 `loop_design_result`。仅当 `build_report.status=spec_ready` 且 `validation_report.valid=true` 时，才可将其中的 `loop_spec` 交给另一个执行运行时。`no_loop_needed` 应执行一次性方案；`needs_input`、`unsupported`、`rejected` 均不得执行 Loop。
5. 构建结果不等于任务已执行。只有执行运行时产生的 `runtime_result.status=passed` 才表示用户任务通过。

建议运行时最小能力：JSON Schema 校验、确定性边选择、状态读写范围检查、能力/权限绑定、预算与终态检查、结构化审计日志。Skill 不会自行授予这些能力。

## 贡献约定

- 版本遵循 Semantic Versioning：`MAJOR.MINOR.PATCH`；文件内容使用 `1.0.0`，Git tag/发布名使用 `v1.0.0`。
- 破坏输入/输出合同或状态语义时升级 MAJOR；向后兼容地增加能力时升级 MINOR；兼容修复升级 PATCH。
- 新增或修改 Skill 时，先提供失败基线，再实现最小合同，最后运行 JSON、图可达性、边优先级、引用解析和示例验证。
- 所有阈值必须记录来源与理由；禁止无预算、无停滞规则或无退出路径的循环。
- 外部写入、网络、凭据、审批和不可逆操作必须由宿主策略显式授权；第三方 Skill 合入前必须审查来源、依赖、脚本与副作用。
- 一个提交只处理一个可审查的资产变化；不要提交密钥、运行时状态、缓存、生成产物或本地工作区。

## Release Notes

### v1.0.0 (2026-06-22)

- 正式初始化多技能资产仓库结构。
- 发布首个超级 Skill：`prompt-to-loop-engineering`。
- 固化 Loop Engineering KB v4.0.2 的 `Loop_design_request` / `loop_design_result` 合同、`one_shot` 合法终态与 build/runtime 结果隔离原则。
- 发布该 Skill 自身的五阶段控制图：`workspace_preflight` → `task_contract_building` → `orthogonal_composing` → `static_validation` → `terminal_export`。
- 明确资产导出、轻量级 Runtime Engine 接入、语义化版本和贡献质量门禁。

