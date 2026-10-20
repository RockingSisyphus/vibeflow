# Rule 机制：设计理念与维护边界

本文描述当前设计及维护时应坚持的原因。面向插件作者的写法见 [用户规则手册](../../distribution/docs/user/rules-and-nodes.md)；迁移工作与当时的全量验证见 [实施计划](../maintainers/history/rule-mechanism-refactor.md)和 [验收记录](../maintainers/history/rule-mechanism-refactor-results.md)。历史方案不能替代本文的当前契约。

## 目标与基本区分

用户应能回答：对象最终遵守哪些规则、选择来自哪里、哪些默认被替代、规则可读取什么、本次负责什么，以及为什么执行一次或多次。设计同时服务于 Plugin 提供可复用默认和 Config 表达具体场景，不建立两套规则系统。

必须分清三种信息：

1. **资源定义**：Rule 的实现、参数、输入输出；Ruleset 的组合、依赖、入口及范围。资源由内置及所选 Plugin 贡献。
2. **资源选择**：类型默认、Workflow 默认、继承或 Config 明确列表。选择不复制规则实现。
3. **执行任务**：有效选择在实际调用位置、阶段和负责范围上的一次检查。相同资源 ID 不代表相同任务。

静态和动态只有选择来源不同。读入后都使用 `RuleSelection` 和同一规划、组合、执行及诊断机制。

## 为什么采用整表替代

| 位置 | 缺省 | 非空显式列表 | 显式 `[]` |
| --- | --- | --- | --- |
| Workflow | 内置及所选 Plugin 的 Workflow 默认 | 替代全部默认 | 取消根图选择 |
| Nodeset 定义 | 继承上级有效图选择 | 接管内部 | 接管内部并停止继承 |
| Node 调用 | 类型的局部默认 | 替代当前调用默认 | 取消当前调用局部选择 |

Workflow 默认由既有 `RulesetDescriptor.workflow_default` 标记贡献，按资源 ID 稳定排序；不新增全局注册表或独立默认文件。Node 类型声明本身未选择规则时，其局部默认为空。

如果类型默认要求十个 t，调用 Config 改选十个 d，那么该调用只检查 d。整表替代消除“替换后旧默认仍偷偷执行”的歧义。同类型其他调用的默认不变；不能修改 canonical Descriptor 来实现调用覆盖。

缺省与空列表必须从模型、Schema、解析、序列化一直保留到规划。显式选择即使与父列表相同，也代表用户主动建立新的范围入口。不能按列表相等消除该边界，更不能把原始 Config 递归填满默认后再推测来源。

所有选择位置共用引用契约：字符串是 Ruleset，直接 Rule 是 `{rule_id, params}`。Rule 依赖只由 Ruleset 的 `requires/bindings` 表达，不以选择列表的先后顺序传递结果。

## 为什么分开局部资料与图资料

使用位置决定公开上下文，而不是规则来源或实现语言。

Node 类型或调用选择的规则仅获得当前声明、当前调用、实现与继承实现、实际 helper 和相关引用。`scope="source"` 进一步移除调用参数及调用列表。共享文件不是授权边界：同文件另一个 Node 的文本、AST、符号、引用或归属查询不能从当前局部视图取得。这样源码检查不必依赖全局 Catalog，也使局部计算能独立复用。

Workflow/Nodeset 选择的图规则可读取当前命令取得的图、相关声明、源码闭包与语言事实，以实现连接、可达性、跨层路径或数量约束。“全局”不包含整个磁盘项目及未关联文件。

局部 A 与图级 B 独立调度、共同生效。B 不作为 A 所在 Node 的局部规则再运行一次。Node 调用 `[]` 只取消自身局部选择，不能解除 B 对图关系的约束。

公开视图按允许字段构造，不依靠事后删几个键。Targets 内部仍持有完整语言分析资料，实际模块初始化、非法依赖、解析和绑定错误不能因公开视图过滤而漏掉。文件级或跨资源判定应迁入图规则，不能为维持旧检查而放宽 Node 资料边界。公开上下文只读，但可信扩展能自行读取文件系统；这里不是安全沙箱。

## 为什么可读背景不等于负责范围

```text
Workflow B
├─ X：局部 A                  → B+A
└─ Nodeset S：显式图选择 C
   ├─ Y：局部 A               → C+A
   └─ Z：局部 D               → C+D
```

B 可以检查 S 在父图中的输入输出和外部连接，内部节点与连接由 C 负责。显式 `[]` 同样建立边界，只是不再有内部继承图规则。若给 B 完整背景后默认递归所有可见节点，C 的接管就失去了用户可观察意义。

因此图上下文同时表达当前检查对象、有限的全局背景、本任务负责的图/调用路径及接管边界。`facts.graph` 将子 Nodeset 保留为外部契约；`facts.graphs` 给出本任务负责的各图；`facts.global_graph` 支持查询背景。`scope.graph_paths`、`call_path` 和 `boundaries` 提供对应范围事实。默认遍历必须消费负责图，不递归整个背景。

同一 Nodeset 定义在 left/right 调用时分别解析继承与边界，按完整路径记录。未调用定义独立审查：自身显式选择优先，否则使用 Workflow 静态默认，不假装属于根的实际调用。Loop 按静态调用结构检查，运行迭代不新增规则任务。

## 为什么明确两种图范围后再去重

`current_graph` 是缺省：一级图检查 X、S、W 的连接，子任务检查 S 内部 Y、Z。两层都运行规则 A，内容不同，不算重复检查。

`effective_subtree` 在有效范围入口执行一次，负责所有继承图，继承该选择的子图不重复调度同一个整体检查。遇到显式子选择停止内部遍历，子选择另开任务。父任务仍看到边界调用。

每个完整 Ruleset 依赖计划只有一种图范围。嵌套 Ruleset 未声明范围则继承外层，显式冲突报 `RULE.GRAPH_SCOPE.CONFLICT`。Node 不接受整体图范围的 Ruleset。Rule 的 `source/call` 表示源码复用与调用资料契约；它不是图范围，也不是 import/static/run 阶段。

框架不能可靠推测任意 handler 已检查过哪些节点。因此先用范围规划防止重叠，再复用等价计算；不能按资源 ID 全局跳过，也不能先重复执行再删除重复诊断。

## Rule 协作与执行顺序

选择解析先生成图任务及局部任务，再在每个任务内展开 Ruleset 依赖计划。不是全局选一条 Rule 扫描全部对象，也不是把继承图规则逐个附加到叶 Node 后执行。

同范围分析 Rule 输出 Records，消费者以 `requires/bindings` 显式绑定具名输入。提供者先执行，消费者不读取可变全局状态、不猜测其他任务已完成。完成且满足契约的 Records 可以伴随诊断；失败、不可用或缺失所需输出时，依赖消费者不能假造空输入继续检查。

内置 `vibeflow.workflow` 保留用户可见综合能力，采用整体范围的明确 analysis、flow、join、nodesets、duplicates、planned、review 和 summary 计划。叶检查消费各图分析 Records，保留 `planned_events`、`workflow_review` 及实际归属。handler 不私下递归其他检查。不要为共享分析新增第二个执行状态机或跨范围结果分发系统。

import、static、run 是独立阶段。import 阶段没有伪造编译资料；固定 Plugin 入口及直接导入可能已经初始化，延迟实现则在有效 import 检查之后绑定。首次运行不能重新执行已被调用选择替代的类型规则。独立 Node 查询没有当前调用时才使用类型默认。空规则列表不能绕过原生语法、符号绑定、ABI 或编译错误。

## 目录与职责

具体内置资源由各 Target 独立提供，不存放在 Core 或顶层 Builtin 目录：

```text
targets/python/                 targets/javascript/
  rules/                          rules/
    graph/        图检查             graph/
    node/         节点源码检查         node/
    project.py    项目源码检查         project.py
    plugin.py     标准 Plugin 装配     plugin.py
  rulesets/       组合与默认          rulesets/
  nodetypes/      节点声明与接口       nodetypes/
  quality/        事实与执行适配       quality/
targets/shared/
  quality_support/ 纯分析、数据与报告
  rule_support/    共用算法、政策、Records 与装配辅助
```

共用支持层不贡献资源声明；声明来源属于对应 Target。Core 不依赖 Target，不预置具体规则或质量阈值。Node 的流程类别与公共 Descriptor 模型仍属于 Core 的工作流契约，Node 声明入口和语言实现协议属于 Target。根目录 `repo_check/` 是不导入 VibeFlow 的独立仓库自检工具。


```text
src/vibeflow/core/rules/
  selection/
    static/        类型默认、Workflow 默认的读取
    dynamic/       Config 明确选择的读取
    models.py      统一选择、来源及被替代列表
    resolve.py     唯一默认/继承/替代判定
  planning.py      实际调用层级、任务与负责范围
  graph.py         组合、参数覆盖与 Records 依赖
  execution.py     统一执行、结果与复用
```

读取器不执行规则；规划不解析语言源码。Python/JavaScript Target 提供语言事实、局部符号视图及实现绑定，消费相同选择和范围；不能各自再实现继承或接管。Tooling 负责配置、Plugin 装配、命令与报告投影，不增加隐式默认注入。

JavaScript 的公开源码服务对未知路径报 `RULE.SOURCE.UNAVAILABLE`，不回退磁盘读取；有限图引用避免完整注册结构形成循环 JSON。Rule ABI 为 v2，Plugin ABI v3 与 Workflow ABI v9 继续承担各自原生协议。

## 复用与可解释报告

缓存只在当前命令内复用等价计算。局部键包含可见源码/声明、实现、Rule 参数、阶段和输入 Records；call 检查还要考虑调用资料，无关 Node 改动不应使局部源码检查失效。图键包含实际调用、配置、负责范围、边界、可读背景快照及输入。source 检查不含某次调用的业务参数。

复用要保留所有受影响位置，并记录选择来源、替代列表、范围、实际执行与复用关系。具体调用的政策不能被类型摘要覆盖。执行次数减少只证明调度或复用变化；没有同条件耗时对照，不能宣称性能改善。

## 验证与后续维护判断

当前综合案例见 [Python](../../sandbox/python/rule_selection/README.md) 与 [JavaScript](../../sandbox/javascript/rule_selection/README.md)。同一嵌套图的 default/dynamic/empty 三份配置，验证静态 Workflow 默认、动态替代、Nodeset 接管、Node 调用选择、局部与图规则共存、重复调用路径和同范围 Records。默认 B 分别负责根/left/right；整体 D 在入口一次负责三张图；接管 C 另行负责 takeover；muted 不继承图规则但保留局部 A。不同执行阶段分别统计。

源码隔离、首次延迟加载、原生错误、混合范围和复用边界的更细回归位于 `tests/core/test_rule_selection.py`、`tests/targets/python/test_rule_selection_boundaries.py`、`tests/targets/python/test_rule_graph_ranges.py` 和 `tests/targets/javascript/test_rule_source_api.py`。综合沙箱补充用户接入情境，不能替代这些回归或整仓库验收。

新机制或修复应检查是否仍满足以下判断依据：

- 用户显式替代后，旧默认不会复活；未填写与空列表仍可解释。
- 读取背景不会扩大负责范围；没有补回隐藏递归。
- 新的语言能力由 Target 提供，不复制公共选择和规划。
- 协作仍通过同范围 Records；缓存不会丢失诊断归属。
- 用户手册只需解释公开用法；内部结构、缓存和维护取舍留在开发者文档。

并发分支沿用普通节点的源码归属和图结构检查；规则不会授予节点启动或回收其他节点的接口。共享图协调器负责调度与清理，见[图并发设计](graph-concurrency.md)。

若实践证据推翻关键假设，复核目标、剩余实现量、验证成本及维护负担。等价修复自主完成；需要改变用户可观察的替代、接管或资料边界时，先说明同一场景下的结果差异，再让用户判断，不以降低实现成本为由静默缩减目标。
