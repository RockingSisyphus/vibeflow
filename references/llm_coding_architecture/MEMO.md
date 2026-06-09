# LLM 编程架构治理参考备忘录

本备忘录按项目逐个记录。每看完一个参考项目，立即写入该项目对 `topology-kernel` 有用的内容、来源位置和可转化为内核设计的点。

记录原则：

- 只记录对“防止 LLM 编程导致架构腐化、强化程序结构治理、把规则转化为硬检查”有帮助的内容。
- 每条尽量标明来源文件路径，便于回看原文。
- 不把参考项目目标等同于本项目目标；只吸收有用机制。

## 1. github/spec-kit

本地目录：`references/llm_coding_architecture/github__spec-kit/`

上游定位：规范驱动开发工具，把“项目原则、需求规格、技术计划、任务拆分、实现执行”组织成一套 AI agent 可调用的命令和工作流。

### 对 topology-kernel 有用的点

1. 先建立“项目宪法/治理原则”，再允许后续开发。

   来源：

   - `github__spec-kit/README.md`
   - `github__spec-kit/templates/commands/constitution.md`
   - `github__spec-kit/templates/constitution-template.md`

   可借鉴点：

   - `topology-kernel` 可以有项目级 `kernel_policy.jsonc` 或 `governance.jsonc`，声明本项目对 node 最大行数、允许 `base_lib`、插件、边界能力、命名规则、测试要求的策略。
   - 这些治理原则不能只给 LLM 看，应被健康检查加载并强制执行。

2. 开发流程被拆为固定阶段，而不是让 LLM 直接写代码。

   来源：

   - `github__spec-kit/README.md`
   - `github__spec-kit/templates/commands/specify.md`
   - `github__spec-kit/templates/commands/plan.md`
   - `github__spec-kit/templates/commands/tasks.md`
   - `github__spec-kit/templates/commands/implement.md`

   可借鉴点：

   - 对 `topology-kernel` 来说，可以形成固定顺序：写/改 node 契约 -> 写/改 node 实现 -> 写/改 nodeset JSONC -> 写/改最终程序 JSONC -> 自动健康检查 -> 运行。
   - LLM 修复健康检查失败时，也应被引导到明确阶段，例如“这是契约问题，不要改运行时”，“这是拓扑问题，不要让 node 互相调用”。

3. 支持“检查表”和跨产物一致性分析。

   来源：

   - `github__spec-kit/templates/commands/checklist.md`
   - `github__spec-kit/templates/commands/analyze.md`
   - `github__spec-kit/templates/checklist-template.md`

   可借鉴点：

   - 健康报告可以不只是 errors/warnings，还可以输出“架构检查表”。
   - 可检查 node 元数据、契约、语义、JSONC 拓扑、Mermaid 图之间是否一致。
   - 对 LLM 特别有用的是把“缺失信息”和“矛盾信息”分开报告。

4. 扩展和预设具有优先级和可追踪解析顺序。

   来源：

   - `github__spec-kit/README.md`
   - `github__spec-kit/docs/reference/presets.md`
   - `github__spec-kit/docs/reference/extensions.md`

   可借鉴点：

   - `topology-kernel` 的 `PolicyPlugin` 应有明确优先级、冲突策略和可解释解析结果。
   - 健康报告应能说明某条规则来自内核默认策略、项目策略，还是某个插件。
   - 当插件放宽限制时，必须在报告中显示来源和原因。

5. workflow gate 和运行状态持久化适合借鉴到健康检查与运行入口。

   来源：

   - `github__spec-kit/workflows/speckit/workflow.yml`
   - `github__spec-kit/workflows/ARCHITECTURE.md`
   - `github__spec-kit/docs/reference/workflows.md`

   可借鉴点：

   - `topology-kernel` 的运行入口应先执行健康检查 gate，失败则停止。
   - 每次运行可保存 `health_report.json`、`compiled_graph.json`、`runtime_trace.jsonl`。
   - 如果未来支持长流程或人工确认，健康检查状态和运行状态应可恢复、可追踪。

6. 多 agent 集成说明了“规则文件可以适配不同工具，但核心语义应统一”。

   来源：

   - `github__spec-kit/AGENTS.md`
   - `github__spec-kit/docs/reference/integrations.md`

   可借鉴点：

   - `topology-kernel` 可以生成不同 AI 工具能读的说明文件，例如 `AGENTS.md`、`.cursor/rules`、`CLAUDE.md`。
   - 但这些文件只用于引导 LLM，真正的规则仍必须由内核健康检查强制实现。

### 不应直接照搬的点

- Spec Kit 偏向“规范生成代码”，而 `topology-kernel` 偏向“限制代码形态和拓扑结构”。
- Spec Kit 的很多约束通过模板和 prompt 引导实现；本项目不能依赖 LLM 自觉，必须把关键规则转为确定性检查。

## 2. bmad-code-org/BMAD-METHOD

本地目录：`references/llm_coding_architecture/bmad-code-org__BMAD-METHOD/`

上游定位：面向 AI 驱动开发的敏捷方法框架，用阶段、角色、工作流、产物和检查点来组织 LLM 协作开发。

### 对 topology-kernel 有用的点

1. 按阶段逐步构造上下文，后续阶段消费前置阶段产物。

   来源：

   - `bmad-code-org__BMAD-METHOD/docs/reference/workflow-map.md`

   可借鉴点：

   - `topology-kernel` 可以把上下文也分层：node 元数据/契约 -> nodeset JSONC -> 最终程序 JSONC -> 编译图 -> 健康报告 -> 运行 trace。
   - 健康检查可以明确指出某个失败属于哪一层：node 实现层、契约层、nodeset 组合层、最终拓扑层、边界层、环路层。

2. `project-context.md` 用作项目级实现规则，所有工作流自动加载。

   来源：

   - `bmad-code-org__BMAD-METHOD/docs/reference/workflow-map.md`
   - `bmad-code-org__BMAD-METHOD/docs/explanation/project-context.md`

   可借鉴点：

   - `topology-kernel` 也需要项目级策略文件，例如 `kernel_policy.jsonc`。
   - 但本项目应进一步把项目规则转成健康检查输入，而不是只作为 LLM 上下文。
   - 可以允许从现有项目扫描生成初始 policy，再由人审阅固定。

3. 工作流中的“Implementation Readiness”和 Code Review gate 很适合转化为运行前硬 gate。

   来源：

   - `bmad-code-org__BMAD-METHOD/docs/reference/workflow-map.md`
   - `bmad-code-org__BMAD-METHOD/docs/reference/testing.md`

   可借鉴点：

   - `topology-kernel run` 应内置 readiness gate：配置可解析、node 可解析、契约完整、无非法依赖、无未声明环路、无非法副作用，全部通过才运行。
   - 可把健康报告状态设计为 `PASS / CONCERNS / FAIL`：硬失败拒绝运行；可降级问题进入 CONCERNS；完全通过才 PASS。

4. 角色/agent 分工说明“不同任务需要不同视角”，但内核不应依赖角色自觉。

   来源：

   - `bmad-code-org__BMAD-METHOD/docs/reference/agents.md`

   可借鉴点：

   - 可以为 LLM 生成不同修复提示：契约修复提示、拓扑修复提示、node 拆分提示、边界迁移提示、测试补全提示。
   - 但这些只是辅助；真实规则仍由健康检查执行。

5. 测试策略有“轻量内置 QA”和“企业级 Test Architect”两层。

   来源：

   - `bmad-code-org__BMAD-METHOD/docs/reference/testing.md`

   可借鉴点：

   - `topology-kernel` 可默认要求每个 node 有最小示例或单元测试。
   - 高风险项目可通过插件启用更严格测试策略，例如契约到测试的 traceability、风险分级、release gate。
   - 健康报告应区分“缺测试”“测试存在但未覆盖契约”“测试失败”。

6. Quick Dev 的根因回退原则非常贴合本项目。

   来源：

   - `bmad-code-org__BMAD-METHOD/docs/explanation/quick-dev.md`

   可借鉴点：

   - 如果实现错是因为意图错，不应继续补代码；如果代码错是因为规格弱，应回到规格层。
   - 对本项目可转化为健康报告建议：如果是契约不清，建议改契约；如果是拓扑错误，建议改 JSONC；如果是 node 过大，建议拆分；如果是副作用，建议迁移到全局出入口。

7. 大文档拆分工具对应本项目的“node 文件大小限制”思想。

   来源：

   - `bmad-code-org__BMAD-METHOD/docs/reference/core-tools.md`

   可借鉴点：

   - 500 行限制不只适用于 node，也可扩展到大型 JSONC、nodeset、文档和 policy。
   - 当 JSONC 或文档过大时，健康报告可以建议拆分 nodeset 或拆分配置。

8. 防止 agent 冲突的核心是共享架构上下文。

   来源：

   - `bmad-code-org__BMAD-METHOD/docs/explanation/preventing-agent-conflicts.md`

   可借鉴点：

   - Mermaid、compiled graph、health report 应成为 LLM 的共享架构上下文。
   - 长期目标可以生成 `TOPOLOGY_CONTEXT.md`，但它必须来自内核编译结果，而不是人工维护。

### 不应直接照搬的点

- BMAD 依赖阶段文档和 agent 行为来提高质量；`topology-kernel` 不能把核心质量保证交给文档和角色。
- BMAD 的流程适合大范围产品开发；本项目要把其中的 gate、traceability 和 context engineering 转化为更底层的代码/拓扑健康检查。

## 3. Aider-AI/aider

本地目录：`references/llm_coding_architecture/Aider-AI__aider/`

上游定位：终端 AI pair programming 工具，核心优势包括 repo map、自动上下文选择、architect/editor 分工。

### 对 topology-kernel 有用的点

1. 大型仓库不能把完整代码塞给 LLM，应生成结构化摘要。

   来源：

   - `Aider-AI__aider/aider/website/_posts/2023-10-22-repomap.md`
   - `Aider-AI__aider/aider/repomap.py`

   可借鉴点：

   - `topology-kernel` 应生成 `topology_map`：包含 node 名称、类型、元数据摘要、契约、输入输出 key、nodeset 层级、边、环路、全局出入口。
   - 这个 map 可以用于 Mermaid，也可以作为 LLM 修复健康检查失败时的上下文。
   - map 应有 token/大小预算，只输出最相关的 node、nodeset 和 key，避免大型项目后上下文失控。

2. repo map 应抽取“定义和引用关系”，而不是只列文件。

   来源：

   - `Aider-AI__aider/aider/website/_posts/2023-10-22-repomap.md`

   可借鉴点：

   - 对 `topology-kernel`，等价关系不是普通函数调用，而是 contract key 关系、配置边关系、nodeset 包含关系、boundary 依赖关系。
   - 可以构建图排名：被多个 node 消费的 key、公共 nodeset、全局出入口、环路边，应在摘要中优先显示。

3. architect/editor 分工说明“先决策，再编辑”能提高质量。

   来源：

   - `Aider-AI__aider/aider/website/_posts/2024-09-26-architect.md`
   - `Aider-AI__aider/aider/coders/architect_prompts.py`

   可借鉴点：

   - 健康检查失败后，可以让 LLM 先输出“架构修复方案”，再执行文件修改。
   - 对应到本项目：先判断应改 node、契约、nodeset JSONC、最终 JSONC、policy、plugin 还是 boundary，再动手。
   - 这可以降低 LLM 在错误位置打补丁的概率。

4. “需要完整文件时再请求”可转化为渐进式上下文加载。

   来源：

   - `Aider-AI__aider/aider/coders/architect_prompts.py`

   可借鉴点：

   - 默认给 LLM 健康报告 + topology map。
   - 只有当某个 node 失败时，再加载该 node 源码和相邻 contract。
   - 这与“bug 应被限制在小 node 里”的目标一致。

5. 缓存和增量计算值得用于大型项目的健康检查。

   来源：

   - `Aider-AI__aider/aider/repomap.py`

   可借鉴点：

   - 对 node AST、导入关系、源码 hash、contract、schema 检查结果做缓存。
   - 运行前健康检查必须强制执行，但可以增量化，避免大型项目每次都全量慢扫。

### 不应直接照搬的点

- Aider 的 repo map 关注普通代码符号和调用引用；`topology-kernel` 应关注契约 key、拓扑边、nodeset 和 boundary，而不是鼓励 node 互相调用。
- Aider 运行时有缓存、SQLite、文件操作等副作用；这些可以作为内核工具实现，但不能进入用户 node。

## 4. coleam00/Archon

本地目录：`references/llm_coding_architecture/coleam00__Archon/`

上游定位：AI coding workflow engine，用 YAML 把计划、实现、验证、评审、PR 等流程固定下来，让 AI 编程过程可重复、可隔离、可观察。

### 对 topology-kernel 有用的点

1. “流程结构由用户拥有，AI 只填充智能”非常契合本项目。

   来源：

   - `coleam00__Archon/README.md`

   可借鉴点：

   - `topology-kernel` 的对应原则是：拓扑结构由 JSONC 拥有，node 只做纯函数计算。
   - LLM 可以写实现，但运行顺序、依赖关系、环路和副作用边界必须由内核和配置决定。

2. workflow 中混合确定性节点和 AI 节点，但验证节点应尽量确定性。

   来源：

   - `coleam00__Archon/README.md`

   可借鉴点：

   - `topology-kernel` 中，node 可以由 LLM 写，但健康检查、编译、契约验证、环路验证、纯函数扫描必须是确定性程序。
   - 这强化了“LLM 修复，内核裁决”的设计。

3. DAG、depends_on、loop、approval gate 与我们拓扑设计有相似点。

   来源：

   - `coleam00__Archon/README.md`
   - `coleam00__Archon/.claude/docs/workflow-yaml-reference.md`
   - `coleam00__Archon/CLAUDE.md`

   可借鉴点：

   - 内核 JSONC 的 `edges`、`loops`、`until` 可以吸收 Archon 的显式 loop 思路。
   - 运行报告应记录每个 node 的状态、输出、失败原因和重试/循环次数。
   - 如果未来支持人工 gate，应把 gate 放在全局边界或运行时层，而不是普通 node。

4. schema 先行和 load-time validation 很重要。

   来源：

   - `coleam00__Archon/AGENTS.md`
   - `coleam00__Archon/CLAUDE.md`

   可借鉴点：

   - `topology-kernel` 应在加载 JSONC 时做 schema 检查，编译前就拒绝明显错误。
   - node 契约、nodeset、loop、boundary、plugin policy 都应有结构模式。
   - 健康检查应区分“配置 schema 错误”和“拓扑语义错误”。

5. 结构化输出必须验证，不能 best-effort 默默降级。

   来源：

   - `coleam00__Archon/CLAUDE.md`

   可借鉴点：

   - node 输出必须严格匹配 `provides` 和输出结构模式。
   - 如果 node 声明 structured output 却返回不可解析或缺字段，应硬失败，不应自动忽略。

6. 每次 workflow run 有独立 worktree、run id、artifacts 和状态。

   来源：

   - `coleam00__Archon/README.md`
   - `coleam00__Archon/AGENTS.md`
   - `coleam00__Archon/CLAUDE.md`

   可借鉴点：

   - `topology-kernel` 可为每次运行生成 `run_id` 和 `run_dir`，保存健康报告、编译图、Mermaid、输入输出摘要和 runtime trace。
   - 对有副作用的全局边界，应要求 run_dir 隔离，避免污染项目根目录。

7. repo-specific workflow overrides 说明“项目可定制，但覆盖关系必须清楚”。

   来源：

   - `coleam00__Archon/README.md`
   - `coleam00__Archon/CLAUDE.md`

   可借鉴点：

   - `topology-kernel` 的默认 policy、项目 policy、插件 policy 应有清晰覆盖顺序。
   - 健康报告应显示最终生效规则来自哪里。

8. rulecheck/validation skills 提示可做“规则即检查”的用户体验。

   来源：

   - `coleam00__Archon/.claude/skills/rulecheck/SKILL.md`
   - `coleam00__Archon/.claude/commands/validate.md`

   可借鉴点：

   - 可以为 `topology-kernel` 提供 `inspect-rule` / `explain-finding` / `suggest-fix` 类 CLI。
   - LLM 看到健康检查 code 后，可以请求解释该规则和推荐修复路径。

### 不应直接照搬的点

- Archon 允许 workflow node 做 bash、git、PR 等副作用；在 `topology-kernel` 里这些只能存在于全局边界或开发工具层，不能进入普通 node。
- Archon 的 AI workflow 编排目标是自动化开发过程；`topology-kernel` 的目标是限制最终程序结构，重点应放在运行前健康检查和纯函数拓扑。

## 5. SuperClaude-Org/SuperClaude_Framework

本地目录：`references/llm_coding_architecture/SuperClaude-Org__SuperClaude_Framework/`

上游定位：把 Claude Code 组织成结构化开发平台的配置框架，提供命令、agents、modes、MCP 集成、项目规则文件、confidence/self-check/reflexion 机制。

### 对 topology-kernel 有用的点

1. 命令按开发生命周期分类，降低 LLM “下一步做什么”的不确定性。

   来源：

   - `SuperClaude-Org__SuperClaude_Framework/README.md`
   - `SuperClaude-Org__SuperClaude_Framework/docs/user-guide/commands.md`

   可借鉴点：

   - `topology-kernel` 可以提供面向 LLM 的 CLI/命令族：`inspect-node`、`inspect-config`、`explain-finding`、`suggest-split`、`export-mermaid`、`validate`、`run`。
   - 命令应区分“只产出分析/文档”和“会修改/执行”的命令，避免 LLM 把分析步骤误当实现步骤。

2. Document-only commands 和 execution commands 的区分很有价值。

   来源：

   - `SuperClaude-Org__SuperClaude_Framework/docs/user-guide/commands.md`

   可借鉴点：

   - `topology-kernel validate`、`inspect-*`、`export-mermaid` 是只读分析命令。
   - `run` 是执行命令，但必须先强制 validate。
   - `scaffold-node`、`scaffold-nodeset` 是写入命令，应在文档中明确副作用。

3. `PLANNING.md`、`TASK.md`、`KNOWLEDGE.md` 这类稳定上下文文件能提高长期一致性。

   来源：

   - `SuperClaude-Org__SuperClaude_Framework/README.md`
   - `SuperClaude-Org__SuperClaude_Framework/CLAUDE.md`

   可借鉴点：

   - `topology-kernel` 可生成稳定上下文文件，例如 `TOPOLOGY_CONTEXT.md`、`KERNEL_POLICY_SUMMARY.md`、`HEALTH_FINDINGS.md`。
   - 但这些文件必须由内核生成或校验，避免人工文档漂移。

4. Confidence check / self-check / reflexion 可转化为健康报告体验。

   来源：

   - `SuperClaude-Org__SuperClaude_Framework/CLAUDE.md`
   - `SuperClaude-Org__SuperClaude_Framework/src/superclaude/pm_agent/confidence.py`
   - `SuperClaude-Org__SuperClaude_Framework/src/superclaude/pm_agent/self_check.py`
   - `SuperClaude-Org__SuperClaude_Framework/src/superclaude/pm_agent/reflexion.py`

   可借鉴点：

   - LLM 修复前可以先要求“信心检查”：是否理解失败原因、是否知道该改哪一层。
   - 修复后必须 self-check：运行健康检查和测试，不能只声称完成。
   - 反复出现的健康检查失败可记录为 mistake/reflexion，形成项目级反模式库。

5. Agents 和 modes 是行为注入机制，但本项目应把它们降级为辅助层。

   来源：

   - `SuperClaude-Org__SuperClaude_Framework/docs/user-guide/agents.md`
   - `SuperClaude-Org__SuperClaude_Framework/docs/user-guide/modes.md`

   可借鉴点：

   - 可以为不同健康检查类型生成不同修复模式：纯函数违规修复、契约修复、拓扑修复、nodeset 拆分、边界迁移。
   - 这些模式只指导 LLM，不能替代内核硬检查。

6. “不要猜，查官方文档/证据”原则对插件和 boundary 特别重要。

   来源：

   - `SuperClaude-Org__SuperClaude_Framework/CLAUDE.md`

   可借鉴点：

   - 插件允许导入第三方库时，policy 应要求声明理由、版本和风险。
   - 高风险 boundary 能力应要求明确文档、配置和审计信息。

### 不应直接照搬的点

- SuperClaude 主要通过命令和行为提示塑造 LLM；`topology-kernel` 的核心约束必须由代码检查执行。
- agents/modes 容易增加复杂性；本项目应先确保 validator/compiler/runtime 的硬约束，再考虑提示词层体验。

## 6. All-Hands-AI/OpenHands

本地目录：`references/llm_coding_architecture/All-Hands-AI__OpenHands/`

上游定位：自动化 AI 软件工程代理。参考材料主要是仓库级 `AGENTS.md` 和 skills 体系。

### 对 topology-kernel 有用的点

1. 仓库级 `AGENTS.md` 直接告诉 AI 在当前仓库必须遵守什么。

   来源：

   - `All-Hands-AI__OpenHands/AGENTS.md`

   可借鉴点：

   - `topology-kernel` 可以生成 `AGENTS.md` 或 `TOPOLOGY_KERNEL_RULES.md`，告诉 LLM：不能让 node 调用 node、不能写副作用、不能绕过健康检查。
   - 但这些规则文件只负责引导，真正执行仍由健康检查完成。

2. 修改前安装 pre-commit，提交前必须通过 lint/test，是“强制流程”的简洁模板。

   来源：

   - `All-Hands-AI__OpenHands/AGENTS.md`

   可借鉴点：

   - `topology-kernel` 的运行入口应像 pre-commit 一样自动强制执行。
   - 可提供项目 pre-commit hook：提交前运行 `topology-kernel validate --all`。
   - 如果健康检查失败，LLM 不应继续运行或提交。

3. 按代码区域给出不同验证命令。

   来源：

   - `All-Hands-AI__OpenHands/AGENTS.md`

   可借鉴点：

   - 健康检查可以根据改动范围选择增量检查：只改 node 时扫 node；改 nodeset JSONC 时重新编译相关子图；改 boundary 时运行 boundary policy。
   - 报告应说明“为什么跑这些检查”。

4. PR 临时材料放 `.pr/`，审批后清理。

   来源：

   - `All-Hands-AI__OpenHands/AGENTS.md`

   可借鉴点：

   - `topology-kernel` 可把 LLM 的调查笔记、修复计划、健康报告草稿放入临时 run 或 review 目录，避免污染正式 node/nodeset/config。
   - 全局边界的运行产物也应放入明确 run_dir，而不是散落项目目录。

5. skills 分为公共可复用知识和仓库私有指令。

   来源：

   - `All-Hands-AI__OpenHands/skills/README.md`

   可借鉴点：

   - `topology-kernel` 的插件/策略也可以分为内核默认、公共插件、项目私有插件。
   - 加载顺序必须清晰：内核默认规则始终存在，项目规则和插件只能扩展或显式降级允许项。

6. code-review skill 只反馈不修改，有助于分离“审查”和“执行”。

   来源：

   - `All-Hands-AI__OpenHands/skills/code-review.md`

   可借鉴点：

   - `topology-kernel inspect` / `validate` 应只报告问题，不改代码。
   - 自动修复如果未来支持，应是单独命令，且必须重新健康检查。

7. fix_test skill 明确“不要改测试”，防止 LLM 为了通过测试而破坏验证标准。

   来源：

   - `All-Hands-AI__OpenHands/skills/fix_test.md`

   可借鉴点：

   - 当健康检查失败时，LLM 不应通过降低 policy、删掉契约、扩大豁免来“修复”。
   - 健康报告可以标注哪些文件是治理文件，修改这些文件应触发更严格审计。

### 不应直接照搬的点

- OpenHands 允许代理执行广泛开发动作；`topology-kernel` 需要把副作用集中在开发工具或全局边界，不能让普通 node 拥有这些能力。
- skills 的 prompt 约束不能替代内核健康检查。

## 7. continuedev/continue

本地目录：`references/llm_coding_architecture/continuedev__continue/`

上游定位：可配置的 AI coding agent 平台，包含本地/Hub 规则、agent、CLI、headless 模式和工具权限。

### 对 topology-kernel 有用的点

1. `cn check` 把代码检查定义为 markdown agent，并可针对工作区 diff 运行。

   来源：

   - `continuedev__continue/skills/cn-check/SKILL.md`

   可借鉴点：

   - `topology-kernel` 可以支持项目内自定义健康检查插件，但确定性的架构约束必须由代码实现。
   - LLM 可作为“解释和建议修复”的辅助检查器，不能作为最终裁判。
   - 检查报告应支持 `text` 和 `json` 两类输出，便于人读和 CI 消费。

2. 每个 AI check 在临时 git worktree 中隔离运行，最后捕获 patch。

   来源：

   - `continuedev__continue/skills/cn-check/SKILL.md`

   可借鉴点：

   - 未来若支持自动修复，应在临时工作区中生成候选 patch，再由内核重新执行健康检查。
   - 不能让自动修复直接修改主工作区的 policy、contract 或 nodeset 来绕过失败。
   - 对大型项目可按 changed nodes / changed nodesets 做增量检查，减少全量检查成本。

3. 检查结果分为 pass、fail、error，并可输出 patch。

   来源：

   - `continuedev__continue/skills/cn-check/SKILL.md`

   可借鉴点：

   - `topology-kernel` 的健康报告可以固定状态枚举：`PASS`、`FAIL`、`ERROR`、`SKIPPED`。
   - `FAIL` 表示规则被违反；`ERROR` 表示检查器自身无法完成。
   - 修复建议可以作为 report 附件，但不能等同于已修复。

4. `.continue/rules` 支持项目级和组织级规则。

   来源：

   - `continuedev__continue/docs/customize/rules.mdx`
   - `continuedev__continue/docs/customize/deep-dives/rules.mdx`

   可借鉴点：

   - 本项目的 policy 也应分层：内核默认规则、组织规则、项目规则、nodeset 局部规则。
   - 每条规则应声明作用域，而不是全局隐式生效。
   - 但与 Continue 不同，`topology-kernel` 的关键规则必须转成可执行检查。

5. rules 支持 frontmatter，包括 `globs`、`regex`、`alwaysApply`，并按文件名顺序加载。

   来源：

   - `continuedev__continue/docs/customize/deep-dives/rules.mdx`

   可借鉴点：

   - policy/plugin 可以设计 `scope`：按 node 路径、node 类型、nodeset、boundary 类型或文件 glob 生效。
   - 加载顺序和优先级必须可解释，健康报告应显示某条规则从哪里加载、为什么适用。
   - 文件名前缀排序的经验说明：规则顺序不能靠隐式目录遍历，应明确 `priority` 或稳定排序。

6. 工具权限采用 `allow`、`ask`、`exclude`，并支持具体工具调用模式匹配。

   来源：

   - `continuedev__continue/docs/cli/tool-permissions.mdx`
   - `continuedev__continue/docs/cli/tui-mode.mdx`

   可借鉴点：

   - 对 `topology-kernel` 而言，普通 node 应默认没有任何工具权限。
   - boundary/plugin 可以声明能力权限：只读、写入、网络、进程、文件系统、外部服务等。
   - 自动化运行时不能出现需要人类临时决策的 `ask`；应失败并给出原因。

7. headless 模式体现了“自动化环境必须无交互”的要求。

   来源：

   - `continuedev__continue/docs/overview.mdx`
   - `continuedev__continue/docs/cli/headless-mode.mdx`

   可借鉴点：

   - `topology-kernel run` 在 CI 或自动入口中必须是非交互确定性的。
   - 未声明、需确认、需权限提升的行为不能临场询问，应被健康检查拦截。

### 不应直接照搬的点

- Continue 的 rules 主要用于提示 AI 行为；本项目不能把架构健康寄托在提示词上。
- AI check 可帮助发现问题，但纯函数、耦合、输入输出契约、节点行数、boundary 权限等核心限制必须由内核代码硬检查。

## 8. cline/cline

本地目录：`references/llm_coding_architecture/cline__cline/`

上游定位：IDE、CLI、Kanban、SDK 多形态的开源 coding agent。参考重点是审批、checkpoint、rules、memory bank、插件 hook、权限策略和多 agent 任务隔离。

### 对 topology-kernel 有用的点

1. Plan & Act 把“理解/规划”和“修改/执行”分开。

   来源：

   - `cline__cline/README.md`
   - `cline__cline/docs/core-workflows/plan-and-act.mdx`

   可借鉴点：

   - 健康检查失败后的 LLM 修复流程应先进入“架构诊断/修复计划”，再实际改 node、contract 或 nodeset。
   - 对复杂拓扑变更，内核可以生成只读诊断报告和建议步骤，避免 LLM 直接堆补丁。
   - `inspect` / `validate` 应保持只读；`fix` 即使未来支持，也应是独立阶段。

2. 每次工具使用后建立 checkpoint，支持比较和回滚。

   来源：

   - `cline__cline/docs/core-workflows/checkpoints.mdx`

   可借鉴点：

   - `topology-kernel` 可以在运行前后保存 `compiled_graph`、`health_report`、`runtime_trace` 和输入摘要，形成可回放检查点。
   - 对自动修复场景，应在候选 patch 前后都记录健康检查结果，便于判断是修复还是规避。
   - 回滚能力不应依赖主 git 历史；临时运行产物可放在独立 `run_dir`。

3. Rules 支持工作区、全局和跨工具 `AGENTS.md`，并支持条件规则。

   来源：

   - `cline__cline/docs/customization/cline-rules.mdx`
   - `cline__cline/CLAUDE.md`
   - `cline__cline/.github/copilot-instructions.md`

   可借鉴点：

   - 本项目可生成跨工具规则文件，帮助不同 LLM 工具理解同一套内核边界。
   - policy 应支持全局、项目、nodeset、node 类型等层级，但必须有清晰优先级。
   - 条件规则的 `paths` 思路可转化为健康检查作用域：某些检查只对特定 node 类别、目录或 boundary 生效。

4. `.clineignore` 用来减少上下文污染。

   来源：

   - `cline__cline/docs/customization/clineignore.mdx`

   可借鉴点：

   - `topology-kernel` 可以生成给 LLM 使用的上下文清单，只包含 contract、nodeset、Mermaid、健康报告和失败 node 源码。
   - 自动生成的 `TOPOLOGY_CONTEXT.md` 应排除构建产物、运行日志、大数据文件和无关依赖。
   - 对 LLM 来说，“少而准”的上下文比完整仓库更适合维护架构边界。

5. Memory Bank 用结构化文件维持跨会话项目记忆。

   来源：

   - `cline__cline/docs/best-practices/memory-bank.mdx`

   可借鉴点：

   - 本项目可以维护内核专用记忆文件，例如 `TOPOLOGY_CONTEXT.md`、`TOPOLOGY_DECISIONS.md`、`TOPOLOGY_PROGRESS.md`。
   - 其中最重要的是架构模式、当前拓扑、已知违规、最近 policy 变更、待拆分 node。
   - 这些文件应由内核从 JSONC 和检查结果生成或校验，避免变成过期手写文档。

6. Auto Approve 和 YOLO Mode 清楚展示了权限风险。

   来源：

   - `cline__cline/docs/features/auto-approve.mdx`
   - `cline__cline/docs/sdk/guides/permission-handling.mdx`

   可借鉴点：

   - `topology-kernel` 的普通 node 应无权限；副作用只允许通过 boundary/plugin 声明。
   - 权限应分层：读项目文件、写项目文件、外部网络、命令执行、MCP/外部服务。
   - 默认策略应是最小权限；全自动运行中不能接受“临场审批”，未授权能力必须失败。
   - Cline 文档中“未设置策略默认自动批准”的做法不适合本项目；本项目应默认拒绝。

7. Plugin hooks 可在生命周期阶段做审计、阻断和观测。

   来源：

   - `cline__cline/docs/sdk/plugins.mdx`
   - `cline__cline/docs/customization/hooks.mdx`

   可借鉴点：

   - `topology-kernel` 的插件体系可以明确 hook 阶段：解析前、schema 后、图编译后、运行前、node 执行前后、boundary 调用前后、运行结束。
   - 用于 policy enforcement 的 hook 应 `fail_closed`，不能因为插件异常就放行。
   - 观测类 hook 可以异步失败不影响运行，但必须在报告中记录。

8. Kanban 的每个任务独立 worktree、依赖链和 diff review 适合未来自动修复流程。

   来源：

   - `cline__cline/README.md`
   - `cline__cline/docs/kanban/core-workflow.mdx`
   - `cline__cline/docs/sdk/guides/multi-agent-teams.mdx`

   可借鉴点：

   - 如果未来让多个 LLM 同时修复不同健康检查失败项，应给每个修复任务独立工作区。
   - 任务间依赖应显式表达，例如先修 contract，再修 node，再修 nodeset。
   - 多 agent 适合“修复工作流”，不适合内核运行时；内核运行时仍应保持确定性。

9. CLI headless、JSON 输出和命令权限适合 CI/自动化入口。

   来源：

   - `cline__cline/docs/usage/cli-overview.mdx`

   可借鉴点：

   - `topology-kernel validate --json` 应输出机器可读事件或报告。
   - CI 中应支持非交互失败，不能因需要确认而挂起。
   - 命令/外部能力权限可以通过环境或 policy 明确声明，但不能覆盖核心健康检查。

### 不应直接照搬的点

- Cline 是开发代理，允许广泛读写文件、运行命令、联网和接入工具；`topology-kernel` 是程序运行内核，普通 node 必须远比 coding agent 更受限。
- Cline 的 Rules、Memory Bank、Plan/Act 主要是 LLM 行为管理；本项目应把它们作为辅助体验，核心质量保证仍由确定性健康检查承担。
- 多 agent 和 Kanban 会增加复杂度；当前内核优先级应是 schema、健康检查、编译、运行和可解释报告。
