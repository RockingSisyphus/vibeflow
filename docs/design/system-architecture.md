# 系统架构

本文面向 VibeFlow 内核设计与维护人员，说明稳定分层和信息来源；用户项目开发使用 `docs/user/`。

## 分层

```text
Tooling → targets/python ──────┐
        → targets/javascript ─┴→ Block Compiler → Core
```

- **Core**：语言无关模型、契约、有效图、图算法、finding，以及 Rule/Ruleset 的组合、参数覆盖、类型化资料和执行计划。
- **Block Compiler**：把已验证 workflow 编译为公共 `WorkflowPlan` / `BlockPlan`。
- **Python Target**：声明驱动的 Registry、延迟实现绑定、源码查询服务、Rule handler、BindingPlan 和 Runtime。
- **JavaScript Target**：descriptor catalog、源码查询服务、Rule ABI worker、BindingPlan、AOT emitter 与工具链协议。
- **Tooling**：workspace 文件、CLI、架构展示和 Target-specific Application 编排。

依赖只沿图中方向流动。语言实现、Python callable、JavaScript source 和 bundler 配置不进入 Core 公共模型。

## 唯一有效图

Core 在拓扑分析前解析调用契约：

- implemented Node 从唯一权威的 NodeDescriptor 继承，Registry 只绑定实现，不读取实现类内的元数据；
- Nodeset 调用从定义继承；
- planned 与系统调用使用 Config 契约。

编译结果携带有效图和编译拓扑。Runtime、AOT、review、Architecture 和静态检查消费同一份有效事实，避免调用点与类型登记形成两套真相。

## 公共计划

Workflow ABI 为 `vibeflow.workflow.v4`。公共计划只保存稳定 ID、可移植值、端口、路由、合流、TaskPlan、Loop、SourceRef、effect scope 与 execution-lock 事实。Target BindingPlan 保存语言实现。

Python 和 JavaScript Target 使用相同 Core 语义，但分别声明可执行 feature。Target 不支持的 implemented 语义以稳定 finding 拒绝；planned 内容仍可进入架构审核。

## 规则与 Node 声明

公开规则模型位于 `vibeflow.core.rules`，完整 Node 声明和 bundle 位于 `vibeflow.core.descriptors`。Node 自己声明规则和默认展示；省略 `rulesets` 与显式 `[]` 都表示不选择 Node 审查规则。workflow 与 Nodeset 的顶层 `rulesets` 默认选择 `vibeflow.workflow`。自由 tags/metadata 可供领域规则识别业务含义，不改变原生 Node/Nodeset/Loop 的组合与执行。

Rule 图使用独立的 includes/requires/overrides 关系，不使用业务边的调度和数据传递语义。Core 先展开组合、解析显式覆盖，再按具名资料依赖执行选中规则。覆盖链决定优先级，文件加载顺序不决定结果；规则不能删除其他规则的诊断。

Target 提供当前检查范围的源码、符号、导入、实际实现和 helper 归属，选中的 Rule 消费这些事实作判断。Rule ABI 为 `vibeflow.rule.v1`，接口是 `check(context, inputs, params)`；Plugin ABI 为 `vibeflow.plugin.v2`，仅保留 compiler/runtime 生命周期与变换。公开上下文提供只读视图，受信扩展代码仍可访问文件系统，不构成操作系统沙箱。

## 架构事实

Architecture 从真实 Config、Nodeset、Node 类型、资源登记和编译事实确定性生成。生成文档不是可执行配置，也不是可编辑 source。新鲜度检查通过重新生成并比较 canonical bytes 完成。

Node 和调用点的图形默认值按 native → Node → status → call 合并，每个字段保留来源。Architecture 与两个 Target 的 Mermaid presenter 使用同一个展示解析器；自定义颜色和形状不替代独立的 flow_kind、效果约束与状态标记。`review-rules` 只读取声明和展开有效规则计划，不导入业务 Node 或执行 Rule 实现。

公开状态范围模型位于 Core/Tooling 共享边界，使 Python 与 JavaScript presenter 使用相同 coverage ID，同时只报告本次命令实际完成的检查。
