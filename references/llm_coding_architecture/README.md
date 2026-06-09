# LLM 编程与架构治理参考材料

本目录收集与“帮助 LLM 更好地编程、让 LLM 编程过程更可控、更可审计、更符合架构约束”相关的高 star 开源项目材料。

收集时间：2026-06-09。

收集方式：

- 通过 GitHub 和网页搜索筛选相关项目。
- 使用 GitHub API 获取 star、fork、更新时间和描述。
- 对大型仓库使用浅克隆与稀疏检出，只保留 README、docs、规则、模板、skills、agents、commands、workflows 等参考材料。
- 本目录用于设计参考，不表示这些项目的架构目标与 `topology-kernel` 完全一致。

## 已收集项目

| 本地目录 | 上游项目 | 约 star | 参考价值 |
| --- | --- | ---: | --- |
| `github__spec-kit/` | `github/spec-kit` | 110k+ | 规范驱动开发，先建立项目原则、规格、计划和任务，再让编码代理实现。 |
| `All-Hands-AI__OpenHands/` | `All-Hands-AI/OpenHands` | 76k+ | 编码代理工程化实践，包含 `AGENTS.md`、skills、强制测试/预提交规则。 |
| `cline__cline/` | `cline/cline` | 62k+ | IDE/CLI 编码代理、人工审批、任务板、多 worktree 并行开发。 |
| `bmad-code-org__BMAD-METHOD/` | `bmad-code-org/BMAD-METHOD` | 48k+ | AI 敏捷开发方法，强调角色、流程、阶段、检查表和规模自适应。 |
| `Aider-AI__aider/` | `Aider-AI/aider` | 45k+ | repo map、architect 模式、上下文压缩和代码库理解。 |
| `continuedev__continue/` | `continuedev/continue` | 33k+ | 编码代理配置和源控化规则，关注可复用配置和检查。 |
| `SuperClaude-Org__SuperClaude_Framework/` | `SuperClaude-Org/SuperClaude_Framework` | 23k+ | 命令、agents、modes、项目级规则文件，把 Claude Code 组织成结构化开发平台。 |
| `coleam00__Archon/` | `coleam00/Archon` | 22k+ | 用 YAML workflow 固化 AI 编程流程，显式阶段、验证门和人工审批。 |

## 对 topology-kernel 的直接启发

### 1. 规范必须成为可执行资产

`spec-kit` 的核心启发是：规格、原则、计划和任务不应只是文档，而应成为开发流程的一部分。

对 `topology-kernel` 的对应设计：

- node 元数据、契约、语义、参数结构模式必须可被健康检查读取。
- nodeset JSONC 和最终程序 JSONC 应成为唯一拓扑事实来源。
- 健康检查应把文档化约束转化为硬失败或警告。

### 2. 流程应由内核强制，而不是依赖 LLM 自觉

`Archon` 和 `BMAD-METHOD` 都强调固定阶段、验证门、审批、角色和工作流。

对 `topology-kernel` 的对应设计：

- 运行入口必须自动执行健康检查，失败不得运行。
- 健康检查失败时应给出定位和修复建议，引导 LLM 修正根因。
- 插件可以扩展流程和策略，但不能隐式绕过绝对规则。

### 3. 架构上下文需要压缩和显式化

`aider` 的 repo map 说明：LLM 不可能长期依赖完整上下文，必须有结构化摘要帮助理解代码库。

对 `topology-kernel` 的对应设计：

- Mermaid 导出不只是可视化，应成为架构摘要。
- health report 应输出 node、nodeset、key、edge、loop、boundary 的结构摘要。
- 未来可以生成“拓扑 map”，让 LLM 在修复前先理解全局结构。

### 4. 规则应放在仓库中并可版本化

`OpenHands`、`SuperClaude`、`Continue` 都体现了仓库内规则文件、skills、agents、commands 的价值。

对 `topology-kernel` 的对应设计：

- policy、plugin、JSONC 配置和健康检查输出都应进入仓库并可版本控制。
- 项目级规则应能被 LLM 读取，但最终执行必须由内核代码保证。
- 规则文件可以辅助 LLM，但不能替代健康检查。

### 5. AI 可以参与，但确定性检查必须留给程序

多个项目都把 AI 用在规划、实现、解释、审查中，但把测试、lint、CI、workflow gate 等交给确定性机制。

对 `topology-kernel` 的对应设计：

- LLM 可以写 node、插件、JSONC。
- 内核必须用确定性检查验证纯函数性、耦合、规模、契约、拓扑、边界和环路。
- 修复建议可以给 LLM，但是否可运行必须由内核判定。

## 可继续深入阅读的重点文件

- `github__spec-kit/README.md`
- `bmad-code-org__BMAD-METHOD/docs/reference/workflow-map.md`
- `bmad-code-org__BMAD-METHOD/docs/reference/agents.md`
- `SuperClaude-Org__SuperClaude_Framework/README.md`
- `SuperClaude-Org__SuperClaude_Framework/docs/user-guide/commands.md`
- `coleam00__Archon/README.md`
- `All-Hands-AI__OpenHands/AGENTS.md`
- `All-Hands-AI__OpenHands/skills/README.md`
- `Aider-AI__aider/aider/website/_posts/2023-10-22-repomap.md`
- `Aider-AI__aider/aider/website/_posts/2024-09-26-architect.md`

## 与本项目目标的差异

这些项目大多是在“让 AI 编程更顺畅、更强大”，而 `topology-kernel` 的目标更偏向“限制 AI 编程的自由度，防止架构腐化”。

因此，参考这些项目时应重点吸收：

- 规范驱动。
- 阶段化工作流。
- 可版本化规则。
- 上下文摘要。
- 验证门。
- 可解释的错误和修复建议。

不应直接照搬：

- 允许代理自由改动整个代码库的模式。
- 依赖提示词自觉遵守架构规则的模式。
- 只做工作流编排但缺少代码级硬检查的模式。
- 把副作用或工具调用混入普通功能单元的模式。
