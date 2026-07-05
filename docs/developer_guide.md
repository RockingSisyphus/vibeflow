# VibeFlow 使用者开发引导

本文面向使用 VibeFlow（包名 `vibeflow`）编写业务 node、nodeset、plugin、base_lib 和 JSONC config 的开发者。

## Node

node 只实现：

```python
def run_pure(self, inputs, params):
    ...
```

必须声明：

- `NODE_INFO: NodeInfo`
- `CONTRACT: NodeContract`

`NodeInfo.flow_kind` 必填，合法值：

- `terminal`
- `process`
- `decision`
- `io`
- `predefined`
- `data_store`
- `document`
- `preparation`

示例：

```python
NODE_INFO = NodeInfo(
    type_key="demo.add",
    display_name="Add",
    category="demo",
    description="Add a configured delta.",
    version="0.1.0",
    flow_kind="process",
)
```

规则：

- node 不读写文件、网络、数据库、浏览器、环境变量。
- node 不启动进程，不动态 import，不使用 `eval/exec`。
- node 不导入其他 node，不调用其他 node。
- node 输出 key 必须是 `CONTRACT.provides` 中声明的 `DataProvider.key` 字符串字面量。
- `run_pure(inputs, params)` 收到的是 envelope，不是裸值。`exactly_one` 输入形如 `inputs["value.in"] == {"key": "...", "type": "value.in", "value": ..., "source_node": "..."}`，业务值在 `["value"]`。
- node 不修改 `inputs`；如果训练类场景确实需要共享对象原地更新，应让这个行为成为显式业务语义，并通过输出 key 暴露更新后的引用。
- 简单 wrapper node 可以只取输入、调用纯 helper/base_lib 函数、返回固定输出；VibeFlow 会识别这种标准形态，避免误报 duplicate logic。

## 外部依赖 Node

如果 node 只是包装第三方库或外部维护代码，设置：

```python
NodeInfo(..., flow_kind="process", external=True)
```

`external=True` 只跳过内部源码质量检查，例如复杂度、导入链、源码规模。它不会跳过：

- 元数据检查。
- 契约检查。
- `flow_kind` 检查。
- config / topology 检查。
- decision `when` 检查。
- runtime trace 和输出 key 检查。

如果外部依赖承担路由逻辑，仍应声明 `flow_kind="decision"`，并提供 route-like output。

## Base Lib

`base_lib/` 只放纯函数 helper，可被 node 导入。

允许示例：

```python
from vibeflow import BaseLibInfo

BASE_LIB_INFO = BaseLibInfo(
    module="base_lib.math_tools",
    display_name="Math Tools",
    category="math",
    description="Pure arithmetic helpers.",
    version="0.1.0",
)

def add(left: float, right: float) -> float:
    return left + right
```

禁止把文件、网络、数据库、浏览器、环境变量或进程副作用放进 `base_lib`。

项目 config 顶层声明允许使用的 base_lib：

```jsonc
{
  "base_lib": {
    "paths": ["../base_lib"],
    "modules": [
      {
        "module": "base_lib.math_tools",
        "status": "implemented",
        "display_name": "Math Tools",
        "category": "math",
        "description": "Pure arithmetic helpers.",
        "version": "0.1.0"
      },
      {
        "module": "base_lib.future_tools",
        "status": "planned",
        "display_name": "Future Tools",
        "category": "math",
        "description": "planned helper library",
        "version": "0.1.0"
      }
    ]
  }
}
```

只有 `implemented` base_lib 会进入 node import allowlist；`planned` base_lib 只用于规划和 Mermaid 展示。implemented base_lib 必须提供 `BASE_LIB_INFO`。config 中的 base_lib 声明也应该写 `display_name` 和 `description`；缺失会产生 `CONFIG.SMELL.MISSING_BASE_LIB_DISPLAY_NAME` 或 `CONFIG.SMELL.MISSING_BASE_LIB_DESCRIPTION` warning，即使源码里的 `BASE_LIB_INFO` 已经完整。

## Config / Pipeline

控制流只来自显式 `pipeline.edges`：

数据契约使用严格 key/type 结构，不支持旧字符串简写：

```jsonc
"inputs": [{"key": "value.in", "type": "value.in"}],
"outputs": [{"type": "value.out", "cardinality": "exactly_one"}],
"requires": [{"type": "value.in", "cardinality": "exactly_one"}],
"provides": [{"key": "value.out", "type": "value.out"}]
```

- `key` 是唯一数据地址，用于输出 mapping、trace 和 provenance。
- `type` 是逻辑数据类型，可以重复；下游按 `type` 消费。
- `cardinality` 必须显式写 `exactly_one`、`optional_one` 或 `all`。
- runtime 使用 node inbox / edge payload。node 只能收到直接 incoming edge 投递的数据；早期上游输出不会被跨多跳读取。
- `pipeline.outputs` 决定 run result 保留哪些 envelope；未声明的中间值不会出现在最终结果中。

### config node 可视化元数据

每个 `pipeline.nodes[]` 调用点都应该声明面向图审查的元数据：

```jsonc
{
  "name": "add",
  "type": "demo.add",
  "display_name": "Add Delta",
  "description": "Add a configured delta to the incoming value.",
  "category": "demo",
  "version": "0.1.0",
  "style": {
    "fill": "#f8fafc",
    "stroke": "#475569",
    "text": "#111827"
  },
  "similar_to": {
    "node": "base_add",
    "relationship": "variant",
    "reason": "Same pure implementation shape, different call-site contract."
  },
  "join_policy": "safe_any",
  "requires": [{"type": "value.in", "cardinality": "exactly_one"}],
  "provides": [{"key": "value.out", "type": "value.out"}],
  "config": {"delta": 3}
}
```

- `display_name` 和 `description` 是 node 实例级说明；即使注册类 `NODE_INFO` 已有说明，调用点没写也会产生 `GRAPH.SMELL.MISSING_NODE_DISPLAY_NAME` 或 `GRAPH.SMELL.MISSING_NODE_DESCRIPTION` warning。
- `display_name`、`category`、`version`、`description`、`style`、`similar_to` 是调用点元数据，不会进入运行时 `params`。
- 如果 node 运行时确实需要同名参数，必须写进 `"config": {...}`。
- `style` 只允许 `fill`、`stroke`、`text` 三个 `#RRGGBB` hex 颜色；大小写会规范化。
- 自定义颜色会作为节点级 `style` 覆盖系统 class 的 fill/stroke/text 颜色，包括 health warning/error、planned、document、nodeset、loop、external dependency 等节点；节点形状、finding 注释和 planned 虚线等非颜色语义仍保留。自定义色仍不能使用 VibeFlow 系统保留色。
- `similar_to` 用来声明本调用点是同一 pipeline 或同一 nodeset 内另一个 node 的 `variant` 或 `copy`，必须写 `node`、`relationship` 和 `reason`；它只影响 `GRAPH.SMELL.DUPLICATE_LOGIC` 的有意重复豁免，不影响运行、编译、拓扑或契约。
- `similar_to` 也是调用点元数据，不会进入运行时 `params`。如果运行时确实需要名为 `similar_to` 的参数，必须写进 `"config": {...}`。
- `join_policy` 是可选调度语义字段，不进入运行时 `params`；可写 `safe_any`、`any_active` 或 `all`。默认 `safe_any`。

VibeFlow 系统颜色是保留语义色，不能作为 `style` 自定义色使用；使用时会产生 `CONFIG.SCHEMA.NODE_STYLE_RESERVED_COLOR`。

| 系统样式 | fill | stroke | text |
| --- | --- | --- | --- |
| 普通 node `defaultNode` | `#ECECFF` | `#9370DB` | `#333333` |
| planned node / planned resource | `#fef08a` | `#ca8a04` | `#713f12` |
| plugin resource | `#eff6ff` | `#2563eb` | `#1e3a8a` |
| base_lib resource | `#ecfdf5` | `#059669` | `#064e3b` |
| health error | `#fee2e2` | `#dc2626` | `#7f1d1d` |
| health warning | `#fef3c7` | `#d97706` | `#78350f` |
| external dependency | `#e0f2fe` | `#0284c7` | `#0c4a6e` |
| document node | `#f0fdf4` | `#16a34a` | `#14532d` |
| nodeset node | `#ede9fe` | `#7c3aed` | `#3b0764` |

```jsonc
{
  "global_config": {"config": {"tenant": "demo"}, "allow_config_override": false},
  "base_lib": {
    "paths": ["../base_lib"],
    "modules": [
      {
        "module": "base_lib.math_tools",
        "display_name": "Math Tools",
        "category": "math",
        "description": "Pure arithmetic helpers used by this config.",
        "version": "0.1.0"
      }
    ]
  },
  "plugins": [
    {
      "module": "../plugins/policy.py",
      "class": "PolicyPlugin",
      "type": "policy",
      "display_name": "Project Policy",
      "category": "policy",
      "description": "Project policy extension used by this config.",
      "version": "0.1.0",
      "config": {"level": "strict"}
    },
    {
      "name": "future_runtime_plugin",
      "type": "runtime",
      "status": "planned",
      "display_name": "Future Runtime Plugin",
      "category": "runtime",
      "description": "planned runtime hook",
      "version": "0.1.0"
    }
  ],
  "pipeline": {
    "inputs": [{"key": "value.in", "type": "value.in"}],
    "outputs": [{"type": "value.out", "cardinality": "exactly_one"}],
    "nodes": [
      {"name": "start", "type": "demo.start", "display_name": "Start", "description": "Starts the demo pipeline."},
      {
        "name": "input",
        "type": "demo.input",
        "display_name": "Read Input",
        "description": "Reads the incoming value envelope.",
        "requires": [{"type": "value.in", "cardinality": "exactly_one"}],
        "provides": [{"key": "value.in.input", "type": "value.in"}]
      },
      {
        "name": "add",
        "type": "demo.add",
        "display_name": "Add Delta",
        "description": "Adds a configured delta to the input value.",
        "requires": [{"type": "value.in", "cardinality": "exactly_one"}],
        "provides": [{"key": "value.out", "type": "value.out"}]
      },
      {"name": "end", "type": "demo.end", "display_name": "End", "description": "Consumes the final output.", "requires": [{"type": "value.out", "cardinality": "exactly_one"}]}
    ],
    "edges": [
      ["start", "input"],
      ["input", "add"],
      ["add", "end"]
    ],
    "max_steps": 1000
  }
}
```

注意：

- `global_config` 会作为 `params["_global"]` 传给每个普通 node，不参与 node config schema 校验。
- `global_config` 中和 node config schema 同名的键还会覆盖 node 的实际 params；其他键只通过 `_global` 传递。
- 推荐写成 `{"config": {...}, "allow_config_override": false}`。无论 `allow_config_override` 是否为 `true`，同名键都会覆盖局部 config；当它为 `false` 且发生覆盖时，健康检查给 warning。
- `base_lib` 和 `plugins` 是资源声明，不进入主流程拓扑、execution plan 或 flow health 的孤儿/可达性检查。
- implemented plugin 必须提供 `PLUGIN_INFO`；planned plugin 不加载、不注册、不执行 hook。
- `plugins[].config` 和 `plugins[].settings` 都可传插件设置，值必须是对象；插件实例会收到 `plugin.config`，如果实现了 `configure(config)` 会在加载时被调用。
- `requires/provides` 不会自动生成控制流；Mermaid/SVG 只会在已有连边上显示能由 `provides.type` 匹配到下游 `requires.type` 的数据契约。
- 每个可执行 pipeline 和 nodeset 内部 pipeline 都要有 `terminal` start/end。
- 每个已实现 node 都必须从 start 可达，并能到达 end。
- 旧 `pipeline.loops`、pipeline/edge 级 `max_iterations`、edge `max_executions` 已移除；训练循环使用一等 loop node 的 `loop.max_iterations`。

## Decision / Cycle

`decision` node 只用于分支选择，不再用于模拟循环：

```jsonc
{"from": "route", "to": "left", "when": "flow.route == 'left'"}
```

规则：

- decision 必须提供 route-like output，例如 `flow.route`。
- decision 的 outgoing edge 必须写 `when`。
- schema enum / boolean 中声明的分支值必须被覆盖。
- 每个分支必须能到达 terminal end。
- 普通 `pipeline.edges` / nodeset 内部 `pipeline.edges` 不允许形成环；出现环会报 `GRAPH.CYCLE.FORBIDDEN`。
- `max_steps` 只是运行时护栏，不是架构语义。
- 循环、retry、batch/epoch、carry state 和 metrics collect 必须使用一等 loop node。

## Loop

训练循环、批处理循环和 retry-until 循环用系统 loop node 表达，不要用 decision edge cycle 模拟循环。当前唯一一等 loop 类型是：

- `vibeflow.loop.while`：重复执行一个 nodeset body，直到固定轮数到达，或 body/state 输出的 bool 条件满足。

loop node 必须声明普通 `requires/provides`，并在顶层写 `loop` 对象。`loop` 是执行语义元数据，不进入运行时 `params`。body 指向同一 config 中的 nodeset；展开 SVG 时，loop body 会像 nodeset 一样展开。

```jsonc
{
  "name": "train_loop",
  "type": "vibeflow.loop.while",
  "display_name": "Training Loop",
  "description": "Runs a training body until it reports completion.",
  "requires": [
    {"type": "train.model", "cardinality": "exactly_one"},
    {"type": "train.optimizer", "cardinality": "exactly_one"}
  ],
  "provides": [
    {"key": "train.model_after", "type": "train.model_after"},
    {"key": "train.loss_history", "type": "train.loss_history"},
    {"key": "loop.iterations", "type": "loop.iterations"}
  ],
  "loop": {
    "body": "training.batch_step",
    "max_iterations": 1000,
    "stop_when": {"from": "loop.done", "equals": true},
    "carry": [
      {"from": "train.model", "as": "train.model", "update": "train.model_after"},
      {"from": "train.optimizer", "as": "train.optimizer", "update": "train.optimizer_after"}
    ],
    "collect": [
      {"from": "train.loss", "as": "train.loss_history"}
    ],
    "outputs": [
      {"from": "train.model_after", "as": "train.model_after"},
      {"from": "train.loss_history", "as": "train.loss_history"},
      {"from": "loop.iterations", "as": "loop.iterations"}
    ]
  }
}
```

`carry` 把上一轮 body output 写回下一轮 body input；`collect` 把每轮 body output 追加成 list；`outputs` 决定 loop node 最终返回哪些 key。batch/epoch/遍历语义不要写成 `items` 或 `epochs`，而是在 body nodeset 内用 index/counter/batch selector 节点表达，并通过 `carry` 写回下一轮状态。

退出条件必须二选一：

- `stop_after`：固定执行 N 轮，必须是 `>= 1` 的整数，且不能大于 `max_iterations`。
- `stop_when`：从 body output 或 loop state 读取 bool，例如 `{"from": "loop.done", "equals": true}`；缺失或非 bool 会在运行时报明确错误。

固定轮数循环：

```jsonc
"loop": {
  "body": "loop.retry_step",
  "max_iterations": 10,
  "stop_after": 3,
  "carry": [{"from": "loop.current", "as": "loop.current", "update": "loop.next"}]
}
```

条件循环：

```jsonc
"loop": {
  "body": "loop.retry_step",
  "max_iterations": 10,
  "stop_when": {"from": "loop.done", "equals": true},
  "carry": [{"from": "loop.current", "as": "loop.current", "update": "loop.next"}],
  "outputs": [{"from": "loop.next", "as": "loop.next"}]
}
```

`vibeflow.loop.for_each`、`loop.items`、`loop.epochs`、`loop.until` 已移除。`max_iterations` 是 loop 的硬上限，超过会抛 runtime error。顶层 `runtime.step_count` 仍只统计顶层 node；包含 loop body 的总步数看 `runtime.total_step_count`，完整顺序看 `runtime.qualified_exec_order`。

`execution="block"` 和 `execution="compiled"` 会执行结构化 `LoopBlock`。如果 loop body 不能被 block compiler 编译，block/compiled 模式会报错，不会静默降级到普通 nested runtime。普通 execution 仍保留同语义的 nested runtime 兼容路径。

Mermaid/SVG 中 while loop 使用独立 trapezoid (`trap-b`) 形状和默认 `loopNode` 系统样式，label 会显示 `body:`、`stop:`、`max:`。`loopNode` 默认颜色属于系统保留色，不允许作为自定义 `style` 颜色；如需改 loop 颜色，应写其他非保留 hex 色。

## Join Policy

默认 join 是 safe OR：目标 node 只要本轮 active incoming branch 提供了所需输入即可运行，但不会静默选择含糊输入。

- 默认 `join_policy: "safe_any"`：适合互斥分支汇入同一个消费 node。若某条 conditional incoming 只是控制门、不提供目标所需数据，runtime 会等待对应条件边激活，避免未选中分支提前运行。
- `join_policy: "any_active"`：显式 OR join。只有当你确认任一 active incoming 都足够触发目标时使用。
- `join_policy: "all"`：等待所有 incoming edge 在本轮都激活后才调度目标。

安全规则：

- 同一 `exactly_one` requirement 收到多个 active provider 时，runtime 报错。
- conditional provider 和 unconditional provider 同时可能满足同一 requirement 时，health 报 `GRAPH.JOIN.AMBIGUOUS_UNCONDITIONAL`，建议改成显式 merge/select node、互斥分支，或 `join_policy: "all"`。
- 每次调度只消费本轮 edge activation 送进 inbox 的输入；不要依赖旧输出留在全局 context 触发后续 join。

## Nodeset

复杂功能优先拆成多个 node，再用 nodeset 组合。大型项目应把可复用 nodeset 放到独立 JSONC 文件，并在 runnable config 中导入：

```jsonc
{
  "nodeset_imports": [
    {"path": "nodesets.jsonc", "names": ["paperflow.catalog"]}
  ],
  "pipeline": {
    "nodes": [
      {
        "name": "catalog",
        "type": "nodeset.paperflow.catalog",
        "display_name": "Catalog Papers",
        "description": "Runs the paper cataloging composite flow.",
        "requires": [{"type": "query.in", "cardinality": "exactly_one"}],
        "provides": [{"key": "catalog.out", "type": "catalog.out"}]
      }
    ],
    "edges": [["start", "catalog"], ["catalog", "end"]]
  }
}
```

规则：

- `path` 相对当前 config 文件。
- `names` 可省略，表示导入文件中的全部 nodeset。
- 导入的 nodeset 和当前文件内联 nodeset 不允许重名。
- `nodeset_imports` 只导入 nodeset，不导入 pipeline、policy 或 plugins。
- VibeFlow 会先为同一 config 中所有导入和内联 nodeset 建立符号表，再解析各 nodeset；因此 `nodeset.xxx` 和 loop 的 `loop.body` 可以引用同一 config 中后面才声明的 nodeset。
- `nodeset.xxx` 调用和 `vibeflow.loop.while.loop.body` 都构成 nodeset dependency。直接或间接递归会报 `NODESET.RECURSION`，不要用 nodeset/loop body 相互引用来表达循环；循环只能写成 loop node 自身的执行语义。
- 为消除 `NODESET.SMELL.TOO_WIDE` 拆分出更多小 nodeset 是推荐做法；parser 按符号表解析，不要求靠声明顺序或前缀重解析来管理可见性。
- nodeset 内部 pipeline 也必须显式写 edges。
- nodeset 可以声明自己的 `global_config`；外部 nodeset JSONC 文件的顶层 `global_config` 会作为该文件内 nodeset 的默认内部配置。
- 调用 nodeset 时可以在调用节点上写 `config`，这会覆盖 nodeset 内部 `global_config`，再覆盖内部 node 局部 config。
- 调用节点上的 `allow_config_override` 控制这些覆盖是否产生 warning：为 `false` 时仍覆盖，但同名覆盖会 warning。

如果怀疑配置读取或 nodeset 解析很慢，可临时加环境变量查看轻量解析 trace：

```bash
VIBEFLOW_CONFIG_TRACE=1 vibeflow validate --config workflow.jsonc
```

trace 会输出 import 文件、展开后的 nodeset 数、每个 nodeset 解析耗时、引用到的 nodeset 和总耗时。

## 运行时数据和性能选项

Runtime 审计流程，不默认审计数据内容：

- node 间可以按引用传递 tensor、model、optimizer、batch 等任意 Python 对象。
- 默认不要求输出值 JSON serializable，也不要求可 deepcopy。
- 默认 trace 只记录流程事件和 summary，不记录真实对象内容。
- 输出仍必须是 mapping，且 key 必须和调用点 `provides` 完全一致。
- `CONTRACT.examples` 只包含 `inputs` 和 `params`，用于证明最小输入/参数可运行并返回声明 key；不要在 examples 中写 `outputs`。

健康检查 warning/error 的 JSON 报告会保留 `details`，CLI 文本报告也会追加紧凑 details。先看 `object_id`、`source_location` 和 `details.owner`；nodeset 内部问题会用 `nodeset:<name>` 标明层级。`GRAPH.SMELL.DUPLICATE_LOGIC` 会列出具体相似 node、node type、fingerprint、duplicate group 和 `similar_to` 豁免提示；flow/data 问题会列出相关 node、incoming/outgoing edge、direct sources、provider type 或 downstream requirement 摘要。不要只看 rule_id 就判断原因。

当 nested nodeset / loop body 的静态展开导致同一个根因被多条定义路径重复发现时，报告会按根因聚合。聚合后的 finding 会在 `details` 中带 `aggregated: true`、`occurrences` 和 `suppressed_duplicates`。这表示需要优先修代表 finding 指向的 `owner` / `node` / `required_type` / `direct_sources`；`occurrences` 是被压缩的重复展开次数，不是独立 bug 数。

可选执行和 trace：

```python
from vibeflow import RuntimeOptions, run_checked

run_checked(..., runtime_options=RuntimeOptions(trace="boundary", node_hooks=False, execution="compiled"))
```

- `trace="full"`：默认逐 node/nodeset 事件。
- `trace="boundary"`：只保留 run/nodeset/failure 边界事件。
- `trace="off"`：只写 runtime summary。
- `execution="plan"`：默认执行计划模式。
- `execution="block"`：显式 opt-in 的保守 block 模式，仅支持线性链和简单条件 loop。
- `execution="compiled"`：显式 opt-in 的低开销线性 `CompiledBlock` 模式；遇到不满足条件的图会回退到 plan。

trace 兼容两层视图：`runtime.exec_order`、`runtime.node_runs`、`runtime.edge_executions`、`runtime.step_count` 仍表示顶层 pipeline；嵌套 nodeset/loop 的完整顺序看 `runtime.qualified_exec_order`、`runtime.qualified_node_runs`、`runtime.qualified_edge_executions` 和 `runtime.total_step_count`。事件中同时有机器可读 `path` 数组和人类可读 `qualified_node`，例如 `["outer", "inner", "add"]` / `outer.inner.add`。

异步 side task 只通过 config 显式开启：

```jsonc
{
  "name": "metrics",
  "type": "demo.metrics",
  "async": "detached",
  "requires": [{"type": "batch", "cardinality": "exactly_one"}],
  "provides": [{"key": "metrics", "type": "metrics"}]
}
{
  "name": "load",
  "type": "demo.load",
  "async": "result_key",
  "result_key": "data.batch",
  "provides": [{"key": "data.batch", "type": "data.batch"}]
}
```

- `detached`：主流程不等待，run 结束时 flush；失败记录 trace warning，不自动中断主流程。
- `result_key`：下游直接 edge 上的节点按 `type` require 该异步结果时 join，结果写入 `result_key` 对应的 provider key。
- runtime 不自动 merge async context；共享对象线程安全由业务对象负责。

## Planned Architecture

AI 可以先提交 planned flowchart：

```jsonc
{"name": "classify", "status": "planned", "flow_kind": "decision"}
```

planned 内容只用于架构审查：

- health 给 warning。
- 默认 runtime 拒绝执行。
- Mermaid / ASCII / SVG 会显示 `planned blocking`、`planned transparent` 或 `planned python_stub` 标记。
- `blocking` 是默认行为，不参与主流程连通性检查。
- `transparent` 仍是 planned warning，但会参与 start/end、reachability、orphan 等 flow health，用于设计期把前后 implemented 节点连起来。
- `python_stub` 仍是 planned warning，并额外产生 `GRAPH.PLANNED.PYTHON_STUB_DEV_ONLY` warning；它参与 flow health，只能在开发测试时配合 `--allow-planned-stub` 执行。
- implemented nodeset 内含 blocking planned child 仍是 error；内含 transparent 或 python_stub planned child 会降为 warning。

`python_stub` 写法：

```jsonc
{
  "name": "runtime_control",
  "status": "planned",
  "flow_kind": "process",
  "requires": [{"type": "state.in", "cardinality": "exactly_one"}],
  "provides": [{"key": "state.out", "type": "state.out"}],
  "planned_behavior": {
    "kind": "python_stub",
    "stub_module": "project/stubs/runtime_control_stub.py"
  }
}
```

stub 模块必须位于主项目的 `project/stubs/` 下，入口固定为 `run_stub(inputs, params)`。内核会检查文件存在、签名、危险 import/call；运行时只传入该节点声明的 `requires` 输入和合并后的 params，返回 mapping 的 key 必须严格等于 `provides`。含 planned 或 python_stub 的配置始终不是 production ready。

## Plugin

plugin 可扩展治理规则，但不能绕过绝对规则。支持类型：

- `policy`
- `compiler`
- `runtime`

config 中只有显式写入 `plugins` 的插件会启用。implemented plugin 必须暴露 `PLUGIN_INFO`，planned plugin 可以不存在、不会加载或执行 hook。config 中的 plugin 声明本身也应该写 `display_name` 和 `description`；缺失会产生 `CONFIG.SMELL.MISSING_PLUGIN_DISPLAY_NAME` 或 `CONFIG.SMELL.MISSING_PLUGIN_DESCRIPTION` warning，即使插件代码里的 `PLUGIN_INFO` 已经完整。

插件配置示例：

```jsonc
{
  "plugins": [
    {
      "module": "../plugins/policy.py",
      "class": "PolicyPlugin",
      "type": "policy",
      "display_name": "Project Policy",
      "category": "policy",
      "description": "Project policy extension.",
      "version": "0.1.0",
      "config": {"level": "strict"}
    },
    {
      "name": "future_runtime_plugin",
      "type": "runtime",
      "status": "planned",
      "display_name": "Future Runtime Plugin",
      "category": "runtime",
      "description": "planned runtime hook",
      "version": "0.1.0"
    }
  ]
}
```

若 plugin 放宽可降级规则，必须声明作用域、原因和来源。项目级语义规则适合通过 policy plugin 增加。

## Registry

推荐按 namespace 分组注册：

```python
def _register_fulltext_nodes(registry):
    registry.register("fulltext.plan_provider_routes", PlanProviderRoutesNode, config_schema={}, config_defaults={})
```

如果 `_register_fulltext_nodes()` 注册了 `literature.*`，内核会给 `REGISTRY.SMELL.NAMESPACE_MISMATCH` warning。迁移期可以保留 warning，但长期应把注册移动到对应分组函数，或用项目 plugin 明确例外。

## 图形输出

推荐每次设计或修改后生成图：

```powershell
vibeflow export-mermaid --config workflow.jsonc --output graph.mmd
vibeflow export-ascii --config workflow.jsonc --output graph.txt
vibeflow export-svg --config workflow.jsonc --output graph.svg
vibeflow export-svg --config workflow.jsonc --expand-nodesets --output graph.expanded.svg
```

正式运行也会写出 `graph.mmd`、`graph.txt`、快速图 `graph.svg` 和详细审查图 `graph.expanded.svg`。

Mermaid/SVG 节点 label 使用纯文本分区展示：首行是 `display_name`，缺省时回退到注册类 `NODE_INFO.display_name` 或 `name`；随后显示 `id:`、`type:`，再用 `---------- meta ----------`、`---------- status ----------`、`---------- nodeset ----------` 等分区展示说明。`requires/provides/exports` 不再塞进节点内；数据契约显示在连边 label 上，例如 `seed -->|value.in| add`，当 provider key 与 type 不同时显示 `value.copy -> value.in`。

SVG 渲染保持 `htmlLabels=false`，但会在 Mermaid CLI 输出后对原生 SVG 文本做增强：标题加粗，字段名前缀加粗，字段行左对齐，分区行加粗并弱化颜色。plugin/base_lib 资源列使用同样的 label 规则，config 元数据优先于 `PLUGIN_INFO` / `BASE_LIB_INFO`。

`export-svg` 会向 Mermaid CLI 传入渲染配置。普通图默认 `maxTextSize=200000`、`maxEdges=2000`；展开 nodeset 时默认 `maxTextSize=500000`、`maxEdges=5000`。如仍遇到 Mermaid 限制，可用 `--mermaid-max-text-size` 和 `--mermaid-max-edges` 覆盖。
展开 nodeset 的 SVG 固定使用确定性 `review-columns` composer：最外层主流程在左侧纵向展示，plugins、base_lib 分列展示，展开的 nodeset 按顶层调用顺序放到右侧。nodeset 内部使用递归 detail-panel 布局：无直接子 nodeset 时横向展示；有直接子 nodeset 时父图保持 collapsed call-site 和原始连边，直接子 nodeset 作为右侧详情列按调用顺序纵向排列。审查图单个片段显示宽度默认上限为 `3200px`，可用 `--review-fragment-max-width` 覆盖。
展开 Mermaid 源码只用于调试源码，不是详细审查 SVG 的输入；不要把 expanded `.mmd` 直接交给 Mermaid CLI/mmdc 转成 SVG。
SVG 渲染不要求系统预装 Google Chrome；正常 `npm install` 后会优先使用 Puppeteer 自己安装/缓存的浏览器。如果该缓存不可用，再尝试非 snap 的系统 Chrome/Chromium。`/snap/bin/chromium` 会被跳过，因为它在 Puppeteer/mermaid-cli 下常见 profile lock 启动失败。
