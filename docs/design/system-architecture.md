# 系统架构

本文面向 VibeFlow 内核设计与维护人员，说明稳定分层和信息来源；用户项目开发使用 `docs/user/`。

## 分层

```text
Tooling → targets/python ──────┐
        → targets/javascript ─┴→ Block Compiler → Core
```

- **Core**：语言无关模型、契约、有效图、图算法、finding，以及 Rule/Ruleset 的组合、参数覆盖、类型化资料和执行计划。
- **builtin**：默认资源声明、主题判定和默认参数。具体语言实现及其配对由各 Target 的内置插件定义提供；Application 自动接入。
- **Block Compiler**：把已验证 workflow 编译为公共 `WorkflowPlan` / `BlockPlan`。
- **Python Target**：Python 插件 SDK、按 workflow 装配的内部 NodeRegistry、直接与延迟绑定、源码服务、Rule handler、BindingPlan 和 Runtime。
- **JavaScript Target**：JS/TS 插件 SDK、worker 中的声明与函数绑定、源码服务、Rule ABI、BindingPlan、AOT emitter 与工具链协议。
- **Tooling**：workspace 与 workflow 文件、选中插件装配、CLI、架构展示和 Target-specific Application 编排。

Core 接收可移植声明、源码定位与事实；Target 持有 callable、worker 对象及工具链配置。依赖沿图中方向流动，内部 NodeRegistry 为 Python 实现绑定服务；用户资源由代码插件贡献。

内置与外部贡献经过同一校验、冻结、来源记录和冲突处理，一次合并为 Catalog。默认资源不会由 Core evaluator 或 Target adapter 再次注入。绑定保留 canonical Descriptor，只补充实际路径、导出对象、配置和实例，不转换为旧 Registry metadata。实现由贡献来源及实现身份解析，内置 ID 没有执行优先权。

## 唯一有效图

Core 在拓扑分析前解析调用契约：

- implemented Node 从唯一权威的 NodeDescriptor 继承，Registry 只绑定实现，不读取实现类内的元数据；
- Nodeset 调用从定义继承；
- planned 与系统调用使用 Config 契约。

编译结果携带有效图和编译拓扑。Runtime、AOT、review、Architecture 和静态检查消费同一份有效事实，避免调用点与类型登记形成两套真相。

公共 `pipeline.inputs` 的每项必须声明布尔 `required`。Core 是输入合同的权威，portable plan 直接投影 key、type、required 及顺序；低层 supplied 输入也必须与原声明一致。Python 原生 Runtime 与 JavaScript 执行都先拒绝未知键，再检查必填键；空声明只接受空对象。Nodeset 和 Loop body 使用同一输入模型，外层 requires/provides 继续使用 cardinality，不互相替代。

## 公共计划

Workflow ABI 为 `vibeflow.workflow.v5`。公共计划只保存稳定 ID、可移植值、端口、路由、合流、TaskPlan、Loop、SourceRef、effect scope 与 execution-lock 事实。Target BindingPlan 保存语言实现。

Python 和 JavaScript Target 使用相同 Core 语义，但分别声明可执行 feature。Target 不支持的 implemented 语义以稳定 finding 拒绝；planned 内容仍可进入架构审核。

## 规则与 Node 声明

公开规则模型位于 `vibeflow.core.rules`，完整 Node 声明和 ContributionBuilder/PluginContributions 位于 `vibeflow.core.descriptors`。Node 自己声明规则和默认展示；省略 `rulesets` 与显式 `[]` 都表示不选择 Node 审查规则。workflow 与 Nodeset 的顶层 `rulesets` 默认选择 `vibeflow.workflow`。自由 tags/metadata 可供领域规则识别业务含义，不改变原生 Node/Nodeset/Loop 的组合与执行。

Rule 图使用独立的 includes/requires/overrides 关系，不使用业务边的调度和数据传递语义。Core 先展开组合、解析显式覆盖，再按具名资料依赖执行选中规则。覆盖链决定优先级，文件加载顺序不决定结果；规则不能删除其他规则的诊断。

Target 提供当前检查范围的源码、符号、导入、实际实现和 helper 归属，选中的 Rule 消费这些事实作判断。Rule ABI 为 `vibeflow.rule.v1`，接口是 `check(context, inputs, params)`；Plugin ABI 为 `vibeflow.plugin.v3`。固定插件经 Python/JS SDK 贡献资源，并可提供 compiler/runtime 生命周期与变换；workflow 的 plugins 是自定义资源唯一启用入口。公开上下文提供只读视图，受信扩展代码仍可访问文件系统，不构成操作系统沙箱。

Rule 使用 `RuleImplementationDescriptor(language, source)` 表达执行语言与入口，每个执行族最多一个兼容实现。JS Rule 在 Node worker 中检查，用户程序平台通过上下文提供。Target 提取 `ProjectQualityFacts`，Core 的 `evaluate_project_quality(facts, rulesets=..., rules=..., ruleset_catalog=..., handlers=...)` 将事实交给选定规则图；报告保留 rule_executions 与 record_availability。

JS 内置 Rule 可绑定原生 Python callable，与外部 worker 绑定共用解析。综合主题直接调用判定算法，不在内部创建固定小规则图；独立 topic Rule 的选择和执行单独记录。项目默认规则由 Application 装配，Core 空选择只返回事实。

Python 的 Node、BaseLib、Plugin 和普通源码共用效果 visitor，真实解析调用优先于函数名称猜测；各资源保留自己的结构、接口、支撑文件和诊断等级要求。两种 Target 都将 RulePlan 的有效参数传入实际判定，JavaScript 通过独立 `ruleParams` 传递；资源 owner 和依赖只作为事实，不承载另一份效果权限。缓存包含有效参数与源码归属，`effect_policy` 记录实际约束。

效果检查按当前 subject 的真实实现符号、支撑文件及可达 helper 取范围；同一声明模块中的独立资源不会相互套用参数。Node 实际调用库 helper 时仍按 Node 的选择检查函数体，库自身审查保持独立。完整源码闭包继续供导入初始化、ownership 和领域 Rule 查询；编译专用源码不会因为与 runtime 同文件而成为 runtime 的效果，但其所属 compiler Plugin 仍按自己的规则检查。

默认参数按实际绑定的 handler 提供。effects/imports 只消费导入政策，指标参数只进入对应指标规则；未知或不相关参数明确失败。Core 对对象参数的整体替换及逐参数来源记录保持不变。导入允许不解除效果或资源依赖约束，`global_state` 不允许修改 builtin、原型或宿主关键状态。

## 插件装配与多文件源码

Tooling 先读取原始 workflow 的插件选择；Target 加载受信插件入口及其直接导入，取得固定资源和实现绑定。`ContributionBuilder` 校验并冻结为 `PluginContributions`，内置资源与选中贡献合并为本次 Catalog，再解析工作流引用。加载和声明错误是装配根因；后续阶段在资源集合有效后进行。不同 workflow 的 Catalog、配置和生命周期实例相互隔离。

四类资源将 `implementation_files` 归一化为 ImplementationDescriptor 的显式源码引用，SDK 路径相对声明模块。Target 保存声明、入口、支撑文件、独立库、符号及真实导入边，并区分引用关系和所有权。Host 与生命周期 Plugin 用 base_libs 引用库；Host dependencies 保留其他宿主实例依赖语义。

PluginContributions 同时保存插件包声明来源。declaration_rulesets 审查包声明，Plugin rulesets 审查 compiler/runtime 实现。各资源明确选择自己的规则；共享文件分别按所属资源检查，默认 maintainability 使用逐文件指标和 500 行上限。AOT 根据实际运行引用打包代码，登记的未使用文件仍作为审查资料。

## 架构事实

Architecture 从真实 Config、Nodeset、插件资源及编译事实确定性生成。结构变更写入真实 source，再重新生成；新鲜度检查比较 canonical bytes。

Node、BaseLib、Plugin 与 Host 共用展示解析，按 native → resource → status → use 合并并记录逐字段来源。资源选择覆盖颜色，声明指定形状与图标；执行身份、效果约束和状态标记独立保存。

用户项目 SVG 从实际 Workflow 调用与配置资源选择生成。Plugin、BaseLib、Host 使用目录父节点连接本次使用的资源；Node 位于业务调用处。公开图形层不接收 Catalog 定义图、源码文件依赖图或规则实现图作为业务架构。

Architecture JSONC 的 implementation_graph 保存当前项目的资源、源码角色、归属、真实导入、库依赖、插件贡献和有效规则。这些资料用于源码审核、来源查询与架构新鲜度校验，不直接投影为 SVG。Core/Target 内部开发信息与用户项目展示边界独立；统一 SDK 注册不会改变图形读者或展示层级。

`review-rules` 加载选中插件取得声明，展开规则计划；框架不调用 Rule、Node、Host 或生命周期工厂。插件直接导入可能已初始化业务模块，源码服务如实记录 loaded/not_loaded/unknown。尚未加载的延迟实现先执行所选 import 检查，再由 Target 绑定。

公开状态范围模型位于 Core/Tooling 共享边界，使 Python 与 JavaScript presenter 使用相同 coverage ID，同时只报告本次命令实际完成的检查。
