# 系统架构

本文面向 VibeFlow 内核设计与维护人员，说明稳定分层和信息来源；用户项目开发使用 `distribution/docs/user/`。

## 分层

```text
Tooling → targets/python ──────┐
        → targets/javascript ─┴→ Block Compiler → Core
```

- **Core**：语言无关模型、契约、有效图、图算法、finding，以及 Rule/Ruleset 的选择、组合、参数覆盖、类型化资料和执行计划；不定义具体内置规则或质量判断。
- **Target 共用支持**：跨语言复用的纯检查算法、事实模型、政策、Records 与装配辅助；不贡献资源声明，也不依赖具体语言 Target。
- **Block Compiler**：把已验证 workflow 编译为公共 `WorkflowPlan` / `BlockPlan`。
- **Python Target**：Python 插件 SDK、按 workflow 装配的内部 NodeRegistry、直接与延迟绑定、源码服务、Rule handler、BindingPlan、Runtime 与目录 AOT。
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

Workflow ABI 为 `vibeflow.workflow.v8`。公共计划只保存稳定 ID、可移植值、端口、路由、合流、普通图 Block、Loop、SourceRef、effect scope 与 execution-lock 事实。Target BindingPlan 保存语言实现。

Python 和 JavaScript Target 使用相同 Core 语义，但分别声明可执行 feature。Target 不支持的 implemented 语义以稳定 finding 拒绝；planned 内容仍可进入架构审核。

## 规则与 Node 声明

公开规则模型位于 `vibeflow.core.rules`。`selection/static` 与 `selection/dynamic` 只读选择来源，`selection/resolve.py` 统一默认、继承与完整替代，`planning.py` 统一调用路径、范围与接管边界；Targets 负责语言事实与绑定。内置及所选 Plugin 的 `workflow_default` Ruleset 贡献根默认，不向 Config 递归注入规则。

各 Target 的 `rules/graph/` 和 `rules/node/` 分别保存图检查、节点源码检查的声明与实现，`rulesets/` 保存组合与默认，`nodetypes/` 保存现有节点声明与语言接口。`quality/` 负责事实、上下文、检查组织与报告。语言差异直接写在各自定义中；内置 Plugin 装配不再修改另一语言的组合。根目录 `repo_check/` 是独立仓库自检工具，不属于产品资源。

Node 类型声明提供局部默认，调用 Config 缺省使用默认、非空完整替代、`[]` 取消当前调用的局部选择。Workflow 缺省使用静态默认；Nodeset 缺省继承，显式选择接管内部。Node 局部与所属图规则共同生效。父图保留子调用外部契约，内部由子选择负责。

图 Rule 的背景资料与负责范围分开：`current_graph` 逐图检查，`effective_subtree` 在范围入口执行一次，显式子选择停止遍历。每个完整 Ruleset 依赖计划只有一种图范围，Records 只在显式同范围依赖中传递。范围规划先避免重叠，再由统一执行器复用等价 source 计算。

Node 公开上下文只含当前声明、调用、实现/继承实现及实际 helper 闭包，不含其他 Node、全图或 Catalog。源码、AST、引用和归属遵守同一符号边界，保留真实位置。Target 内部继续分析真实模块初始化和资源归属；原生解析、绑定、编译错误独立于规则选择。

Rule ABI 为 `vibeflow.rule.v2`，入口是 `check(context, inputs, params)`；Plugin ABI 保持 `vibeflow.plugin.v3`。内置 Workflow 由明确的分析、叶检查、汇总和 Records 依赖组成，保留统一执行器和诊断。公开上下文只读，可信扩展仍可访问文件系统，不构成安全沙箱。设计理由、范围示例、目录职责与回归依据见 [Rule 机制设计](rule-system.md)；插件定义与使用见 [用户规则手册](../../distribution/docs/user/rules-and-nodes.md)，升级见 [迁移手册](../../distribution/docs/user/rule-system-migration.md)。

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

并发工作使用普通节点和显式边：分发、工作、统一 all 汇合、结束。所有分支接受相同的断路检查；取消和真实清理由 Target 调度器持有，不再存在独立任务管理层。

当前并发编译、Runtime/AOT 实现位置和退出顺序见[普通图并发设计](graph-concurrency.md)，维护时应同时核对公共计划、分发局部额度、SDK 操作归属及最终收尾边界。


## 双语言计划与 AOT

`core.graph_calls` 统一实际调用身份、子图、Loop、配置继承。Rule 在相同身份之上补充未调用定义的审查范围；它们不会成为执行调用。Block Compiler 生成可序列化及读取的 WorkflowPlan/BlockPlan，实际并发执行由 Target 的通用图调度器持有。ABI v8 不携带旧 async/result_key 并发字段。

Python 将准备与装配分开：静态阶段保存共同计划及有限的原生图/编译记录，运行阶段绑定类、独立参数容器、活对象和现有 PipelineRuntime。源码与目录 bundle 共用装配函数。生成块在调用时读取追踪和 Hook 选项，不为各 profile 复制编译逻辑。无法生成块的结构保留原动态调度。

Python 的文件收集、加载 API 与 CLI 属于 Tooling；框架通过包资源读取，因此源码、wheel 和 ZIP 发行采用同一构建入口。两种 Target 共用暂存、原子发布、构建结果与 v3 元数据；JS 保留 emitter、esbuild、Node/Browser runtime。加载只解析格式、ABI 和运行所需字段，不重新扫描源码或校验文件哈希。
