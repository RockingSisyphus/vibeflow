# 系统架构

本文面向 VibeFlow 内核设计与维护人员，说明稳定分层和信息来源；用户项目开发使用 `docs/user/`。

## 分层

```text
Tooling → targets/python ──────┐
        → targets/javascript ─┴→ Block Compiler → Core
```

- **Core**：语言无关模型、契约、有效图、图算法、finding，以及 Rule/Ruleset 的组合、参数覆盖、类型化资料和执行计划。
- **Block Compiler**：把已验证 workflow 编译为公共 `WorkflowPlan` / `BlockPlan`。
- **Python Target**：Python 插件 SDK、按 workflow 装配的内部 NodeRegistry、直接与延迟绑定、源码服务、Rule handler、BindingPlan 和 Runtime。
- **JavaScript Target**：JS/TS 插件 SDK、worker 中的声明与函数绑定、源码服务、Rule ABI、BindingPlan、AOT emitter 与工具链协议。
- **Tooling**：workspace 与 workflow 文件、选中插件装配、CLI、架构展示和 Target-specific Application 编排。

Core 接收可移植声明、源码定位与事实；Target 持有 callable、worker 对象及工具链配置。依赖沿图中方向流动，内部 NodeRegistry 为 Python 实现绑定服务；用户资源由代码插件贡献。

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

公开规则模型位于 `vibeflow.core.rules`，完整 Node 声明和 ContributionBuilder/PluginContributions 位于 `vibeflow.core.descriptors`。Node 自己声明规则和默认展示；省略 `rulesets` 与显式 `[]` 都表示不选择 Node 审查规则。workflow 与 Nodeset 的顶层 `rulesets` 默认选择 `vibeflow.workflow`。自由 tags/metadata 可供领域规则识别业务含义，不改变原生 Node/Nodeset/Loop 的组合与执行。

Rule 图使用独立的 includes/requires/overrides 关系，不使用业务边的调度和数据传递语义。Core 先展开组合、解析显式覆盖，再按具名资料依赖执行选中规则。覆盖链决定优先级，文件加载顺序不决定结果；规则不能删除其他规则的诊断。

Target 提供当前检查范围的源码、符号、导入、实际实现和 helper 归属，选中的 Rule 消费这些事实作判断。Rule ABI 为 `vibeflow.rule.v1`，接口是 `check(context, inputs, params)`；Plugin ABI 为 `vibeflow.plugin.v3`。固定插件经 Python/JS SDK 贡献资源，并可提供 compiler/runtime 生命周期与变换；workflow 的 plugins 是自定义资源唯一启用入口。公开上下文提供只读视图，受信扩展代码仍可访问文件系统，不构成操作系统沙箱。

Rule 使用 `RuleImplementationDescriptor(language, source)` 表达执行语言与入口，每个执行族最多一个兼容实现。JS Rule 在 Node worker 中检查，用户程序平台通过上下文提供。Target 提取 `ProjectQualityFacts`，Core 的 `evaluate_project_quality(facts, rulesets=..., rules=..., ruleset_catalog=..., handlers=...)` 将事实交给选定规则图；报告保留 rule_executions 与 record_availability。

## 插件装配与多文件源码

Tooling 先读取原始 workflow 的插件选择；Target 加载受信插件入口及其直接导入，取得固定资源和实现绑定。`ContributionBuilder` 校验并冻结为 `PluginContributions`，内置资源与选中贡献合并为本次 Catalog，再解析工作流引用。加载和声明错误是装配根因；后续阶段在资源集合有效后进行。不同 workflow 的 Catalog、配置和生命周期实例相互隔离。

四类资源将 `implementation_files` 归一化为 ImplementationDescriptor 的显式源码引用，SDK 路径相对声明模块。Target 保存声明、入口、支撑文件、独立库、符号及真实导入边，并区分引用关系和所有权。Host 与生命周期 Plugin 用 base_libs 引用库；Host dependencies 保留其他宿主实例依赖语义。

PluginContributions 同时保存插件包声明来源。declaration_rulesets 审查包声明，Plugin rulesets 审查 compiler/runtime 实现。各资源明确选择自己的规则；共享文件分别按所属资源检查，默认 maintainability 使用逐文件指标和 500 行上限。AOT 根据实际运行引用打包代码，登记的未使用文件仍作为审查资料。

## 架构事实

Architecture 从真实 Config、Nodeset、插件资源及编译事实确定性生成。结构变更写入真实 source，再重新生成；新鲜度检查比较 canonical bytes。

Node、BaseLib、Plugin 与 Host 共用展示解析，按 native → resource → status → use 合并并记录逐字段来源。资源选择覆盖颜色，声明指定形状与图标；执行身份、效果约束和状态标记独立保存。

implementation_graph 同时供 Architecture JSONC 与正式展开 SVG 使用，包含资源、源码角色、归属、实际导入、库依赖、插件贡献和有效规则。资源区统一渲染以保留跨资源关系，虚线依赖与 Workflow 执行连边分别表达。

`review-rules` 加载选中插件取得声明，展开规则计划；框架不调用 Rule、Node、Host 或生命周期工厂。插件直接导入可能已初始化业务模块，源码服务如实记录 loaded/not_loaded/unknown。尚未加载的延迟实现先执行所选 import 检查，再由 Target 绑定。

公开状态范围模型位于 Core/Tooling 共享边界，使 Python 与 JavaScript presenter 使用相同 coverage ID，同时只报告本次命令实际完成的检查。
