# 拓扑内核目标愿景

## 设计初衷：面向人机协同开发

`topology-kernel` 的根本目标是服务于人机协同开发，尤其是大量依赖 LLM 编写和维护程序的场景。

LLM 在开发中很有价值，但也容易出现几类长期风险：

- 把功能越写越大，形成巨型函数或巨型模块。
- 出现问题时倾向于局部打补丁，而不是定位根因并做必要的小规模重构。
- 在多轮修改后积累隐式调用链、隐藏依赖和副作用污染。
- 代码表面上能运行，但架构逐步失去可审计性。

这个内核的目标不是让 LLM 或开发者写代码更自由，而是反过来用硬性规则限制自由度：

- 每个功能块必须足够小。
- 每个功能块必须是纯函数。
- 功能块之间不允许代码层面的耦合。
- 程序结构必须由配置显式组织。
- 健康检查必须能在代码层面发现违反规则的实现。

理想状态下，只要 LLM 按这个内核开发 node 模式程序，使用者就不需要逐行审查每个 node 的工程质量。内核应当通过验证器、编译器、运行时和策略系统把高内聚、低耦合、原子化拆分变成硬约束。

## 核心目标

`topology-kernel` 的目标是成为一个可迁移、可复用、超级严格的拓扑程序内核。它不绑定 Paperflow，也不绑定任何具体业务。开发者只需要编写小型纯函数 node，再用 JSONC 配置把 node 和 nodeset 组织成完整程序。

最终目标不是让开发最省事，而是最大限度限制：

- node 间耦合。
- 隐式调用链。
- 代码文件膨胀。
- 副作用污染。
- 文件系统混乱。
- 后期维护不可控。
- LLM 反复补丁式修改造成的架构腐化。

内核应当把“架构质量”从人工代码审查的软要求，尽量转化为可执行、可失败、可报告的硬性检查。

## 术语边界

为避免后续 schema、健康检查和 Mermaid 导出出现概念混乱，内核目标中统一使用以下术语：

- `node`: 原子纯函数单元，只通过 `run_pure(inputs, params) -> outputs` 执行。
- `nodeset`: 由多个 node 或其他 nodeset 组成的复合纯函数拓扑单元。
- `pipeline`: 最终可运行拓扑，由 JSONC 配置声明 node、nodeset、edge、loop 和 boundary。
- `boundary`: 框架级全局副作用边界，不是 node，不进入 node registry。
- `base_lib`: 受控纯函数基础库，可被 node 依赖，但必须接受健康检查。
- `policy`: 治理规则集合，决定哪些限制硬失败、哪些限制可降级。
- `plugin`: 扩展治理、编译或运行能力的机制，不能隐式绕过绝对规则。

## 项目级治理策略

内核应把治理策略作为一等输入，而不是只依赖文档说明或开发者自觉。

目标策略文件可以命名为 `kernel_policy.jsonc` 或 `governance.jsonc`，用于声明：

- node 最大行数、最大字节数、复杂度阈值。
- 允许的标准库、第三方库和 `base_lib`。
- nodeset、pipeline、boundary 的命名和结构要求。
- 插件加载列表、优先级、作用域和冲突策略。
- 哪些规则是绝对硬失败，哪些规则允许在显式理由下降级为 warning。
- 豁免项的原因、作用域和过期条件。

策略分层应清晰：

1. 内核默认策略。
2. 组织级策略。
3. 项目级策略。
4. nodeset 局部策略。
5. 插件追加或收紧的策略。
6. 显式豁免策略。

规则合并结果必须可解释。健康报告应显示每条生效规则来自哪里、为什么适用于当前对象、是否被插件或项目策略降级。

## 绝对规则

1. node 必须是纯函数。
2. nodeset 也必须表现为纯函数。
3. node 不允许直接读写文件、网络、数据库、浏览器、环境变量。
4. node 不允许调用其他 node。
5. node 不允许 import 其他 node。
6. node 只能依赖框架允许的基础库和项目声明的 `base_lib`。
7. node 必须完整报告自身元数据、输入、输出、语义和参数结构模式。
8. 配置文件拥有全部拓扑组织权。
9. 普通图允许环路，但所有环路必须显式声明且有执行次数上限。
10. 未声明环路一律非法。
11. node 源码必须满足文件行数和字节数限制，默认目标是不超过 500 行。
12. node 的职责必须能由元数据、契约和语义信息解释清楚。
13. LLM 生成或修改 node 后，必须能被健康检查独立判定是否仍符合治理规则。

## 代码规模与根因修复目标

文件大小限制不是单纯的风格要求，而是该内核的核心治理机制之一。

默认目标：

- 单个原子 node 文件不超过 500 行。
- 单个 node 只表达一个明确功能。
- 如果实现超过限制，应拆分为多个 node 或抽取到受控 `base_lib`，再通过 nodeset 组合。
- 超限不能默认通过注释豁免；任何豁免都必须由显式策略或插件声明，并在健康报告中可见。

这个规则服务于一个实际维护目标：当大程序后期出现 bug 时，问题应被限制在小型、可审计的功能块或明确的配置拓扑中，而不是散落在跨模块隐式调用链里。

内核还应鼓励根因修复，而不是补丁堆叠：

- 验证器应报告重复、过大、契约不清、输出未消费、语义不匹配等架构气味。
- 健康报告应帮助定位是 node 实现问题、契约问题、配置拓扑问题，还是边界问题。
- 当一个 node 因规模或职责过宽失败时，推荐修复方式应是拆分 node 或提升为 nodeset，而不是继续扩写。

## 全局出入口

唯一不受 node 规则限制的是框架级全局出入口。

全局出入口不是 node：

- 不进入 node registry。
- 不参与 node 纯函数策略。
- 不能被 node 直接调用。
- 只能由运行时在拓扑前、拓扑后或有界循环轮次边界调用。

node 如果需要触发外部能力，只能输出结构化请求、效果或发件箱数据。全局出口读取这些数据执行真实副作用。全局入口把外部结果转换成下一轮拓扑输入。

## 显式有界环路

图允许存在环路，但必须满足：

- 每个环路都在 `pipeline.loops` 中声明。
- 环路必须有 `max_iterations`。
- 环路中每条边必须可追踪执行次数。
- 环路可声明 `until` key 作为提前停止条件。
- 运行时必须能报告每条边的实际执行次数。

目标是允许复杂反馈流程，同时避免无限循环和隐式控制流。

## 嵌套式 nodeset

复杂功能不应该写成巨型 node，而应该用 nodeset 组合多个小 node。

nodeset 的目标规则：

- nodeset 像 node 一样有 `name/type/category/description/version`。
- nodeset 像 node 一样有 `requires/provides`。
- nodeset 内部可以包含 node 和其他 nodeset。
- nodeset 默认隐藏内部中间 key。
- nodeset 只能通过 `exports` 暴露输出。
- nodeset 禁止递归引用。

## 插件目标

插件应能扩展框架治理规则，而不仅是运行时钩子。

目标插件类型：

- `PolicyPlugin`: 扩展元数据结构模式、契约结构模式、纯函数规则、文件大小规则。
- `CompilerPlugin`: 扩展图编译、边策略、语义兼容性、图优化器。
- `RuntimePlugin`: 扩展追踪、清单、进度、缓存、GUI 事件。
- `BoundaryPlugin`: 注册或配置全局出入口能力。

示例：

- 要求所有 node 声明最大空间占用。
- 要求所有 node 声明最大输出规模。
- 将 node 文件最大行数从 500 改为 300。
- 限制某类 node 不能使用某个 `base_lib`。

插件不能成为绕过内核治理的后门。用于 policy enforcement 的插件必须采用 fail-closed 原则：

- 纯函数、导入、契约、结构模式、边界权限、文件规模等治理插件异常时，默认判为健康检查失败。
- 观测、追踪、统计类插件可以不阻断运行，但异常必须进入健康报告。
- 插件放宽限制时，必须声明作用域、理由和来源，并在健康报告中可见。
- 插件不能放宽内核绝对规则，除非该规则在内核策略中被明确定义为可降级规则。

## 必备开发工具

配置应优先支持 JSONC，而不是只支持严格 JSON。

原因：

- 大型拓扑配置需要注释解释设计意图。
- 环路、边界、nodeset 导出等结构需要局部说明。
- 人和 LLM 都需要在配置里留下可读的架构备注。

目标要求：

- CLI 接受 `.json` 和 `.jsonc`。
- JSONC 注释只作为人类说明，不进入运行时语义。
- 验证器报错位置应尽量保留原始 JSONC 行列信息。
- Mermaid 导出可以选择显示配置中的描述、语义、契约 key，但不直接依赖注释文本。

目标 CLI：

```text
topology-kernel validate --config workflow.json
topology-kernel inspect-node --type some.node
topology-kernel inspect-config --config workflow.json
topology-kernel export-mermaid --config workflow.json --output graph.mmd
```

目标检查：

- JSON / JSONC 结构模式。
- node 元数据完整性。
- 契约完整性。
- import 白名单。
- AST purity。
- node 源码行数和字节数。
- node 间导入或调用禁止。
- base_lib purity。
- requires/provides。
- 语义兼容性。
- 显式有界环路。
- nodeset exports。
- 插件策略。
- node 文件大小和职责边界。
- 配置注释保留与错误定位。
- LLM 生成代码常见风险，例如越界输出、隐藏副作用、动态 import、隐式全局状态。

## 健康报告目标

健康报告应成为稳定接口，而不是临时日志文本。它既要给人阅读，也要能被工具消费。

整体状态建议固定为：

- `PASS`: 所有硬检查通过。
- `CONCERNS`: 无硬失败，但存在需要关注的 warning 或治理气味。
- `FAIL`: 存在规则违反，禁止运行。
- `ERROR`: 检查器、插件或配置解析过程自身异常，禁止运行。
- `SKIPPED`: 某项检查因明确策略被跳过，必须报告原因。

每条 finding 至少应包含：

- `rule_id`: 稳定规则编号。
- `severity`: `error`、`warning`、`info`。
- `object_type`: `node`、`nodeset`、`pipeline`、`base_lib`、`boundary`、`plugin`、`policy`。
- `object_id`: 失败对象标识。
- `source_location`: 文件、行、列或 Python 对象位置。
- `rule_source`: 规则来自内核默认策略、项目策略还是插件。
- `failure_layer`: `schema`、`contract`、`implementation`、`topology`、`boundary`、`runtime`。
- `message`: 明确失败原因。
- `suggested_fix_type`: `split_node`、`fix_contract`、`fix_nodeset`、`move_to_boundary`、`tighten_policy`、`fix_base_lib` 等。

健康报告必须区分“规则被违反”和“检查器自身失败”。规则违反是 `FAIL`，检查器自身失败是 `ERROR`，两者都不得继续运行。

## Mermaid 目标

框架应能从配置直接生成 Mermaid 图。

导出模式：

- 折叠 nodeset。
- 展开 nodeset。
- 显示契约 key。
- 显示语义。
- 显示环路和最大执行次数。
- 显示策略检查结果。
- 显示全局出入口。

## 运行产物目标

每次正式运行都应有独立 `run_id` 和 `run_dir`。运行产物用于调试、审计、复现和长期维护，不应散落在项目根目录。

建议运行目录：

```text
runs/<run_id>/
  input_summary.json
  effective_policy.json
  compiled_graph.json
  health_report.json
  graph.mmd
  runtime_trace.jsonl
  boundary_trace.jsonl
```

其中：

- `effective_policy.json` 记录最终合并后的治理策略。
- `compiled_graph.json` 记录编译后的有效拓扑。
- `health_report.json` 记录运行前强制健康检查结果。
- `runtime_trace.jsonl` 记录 node、nodeset、loop 的执行顺序、输入输出摘要和失败原因。
- `boundary_trace.jsonl` 记录全局出入口调用、外部副作用摘要、目标位置和结果。

全局出入口产生的文件、缓存、下载物、数据库或外部进程产物，必须进入 `run_dir` 或进入配置显式声明的受控路径。内核应避免副作用产物污染项目结构。

## 基于人机协同仍需补强的目标

为了更完整地服务 LLM 参与的大型程序开发，目标设计还应补强以下能力：

- 复杂度检查：除文件行数外，还应检查函数数量、分支复杂度、嵌套深度、参数规模和契约 key 数量。
- 单一职责检查：元数据、描述、`requires/provides`、语义应能共同证明 node 职责边界清晰。
- 重复逻辑发现：健康报告应能提示多个 node 或 base_lib 中的明显重复实现。
- 测试要求：每个 node 应有最小单元测试或示例输入输出，验证器可报告缺失测试。
- 变更影响分析：修改 node、契约或配置后，应能报告受影响的下游 node、nodeset 和 Mermaid 结构。
- 运行可追踪性：运行时应保存 node 输入摘要、输出摘要、执行顺序、环路次数和边界调用摘要，便于定位 bug。
- 架构漂移检测：长期迭代后，健康报告应能指出节点数量膨胀、未消费输出、临时 key、命名混乱、nodeset 过宽等趋势。
- 豁免治理：所有放宽规则的地方都必须显式、可审计、可过期，避免策略逐步被例外掏空。
- `base_lib` 防逃逸：`base_lib` 也必须接受文件规模、复杂度、导入白名单、纯函数性和依赖闭包检查，避免把巨型 node 或副作用转移到基础库中。

## 最终使用方式

理想项目结构：

```text
my_project/
  topology_kernel/
    ...
  base_lib/
  nodes/
  plugins/
  nodesets/
  configs/
```

其中 `topology_kernel/` 是可迁移内核包，可以复制进项目，也可以作为独立依赖安装。业务项目只在内核之外提供纯函数 node、受控 `base_lib`、可选插件、nodeset JSONC 和最终程序 JSONC。

开发流程：

1. 开发小型纯函数 node。
2. 按需开发插件，用于扩展或收紧项目治理规则。
3. 用 nodeset JSONC 组织中大型功能模块。
4. 用最终程序 JSONC 组织完整程序拓扑，并声明必要的全局出入口。
5. 直接运行最终程序配置。

运行原则：

- 运行入口必须先自动执行强制健康检查。
- 健康检查不通过时，内核必须拒绝运行。
- 拒绝运行时必须给出明确原因、定位信息和修复建议。
- 问题应根据健康报告定位到 node、插件、`base_lib`、nodeset JSONC 或最终程序 JSONC 后再修正。
- 修正后再次运行，内核重新执行完整健康检查。
- 只有全部硬性检查通过后，运行时才允许真正执行拓扑。

该内核的价值在于把复杂程序强行拆成可审计、可组合、低耦合的小块。
