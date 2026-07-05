# 03. Config 与 Pipeline 规范

配置文件使用 `.jsonc`，支持 `//` 行注释和 `/* ... */` 块注释。不支持 trailing comma。

## 标准结构

```jsonc
{
  "global_config": {},
  "base_lib": {
    "paths": [],
    "modules": []
  },
  "plugins": [],
  "pipeline": {
    "inputs": [],
    "max_steps": 1000,
    "nodes": [],
    "edges": []
  },
  "nodesets": [],
  "policy": {}
}
```

也兼容简写：

```jsonc
{
  "nodes": []
}
```

推荐长期项目使用标准结构。

## 顶层资源声明

`global_config`、`base_lib`、`plugins` 是 config 资源元数据，不是主流程 node。它们不会进入 `GraphConfig.nodes`、execution plan、`effective_edges` 或孤儿节点/可达性等 flow health 检查。Mermaid 会把它们画成独立资源区。

```jsonc
{
  "global_config": {"config": {"tenant": "demo"}, "allow_config_override": false},
  "base_lib": {
    "paths": ["../base_lib"],
    "modules": [
      {"module": "base_lib.math_tools", "status": "implemented"},
      {"module": "base_lib.future_tools", "status": "planned", "description": "planned helper library"}
    ]
  },
  "plugins": [
    {"module": "../plugins/policy.py", "class": "PolicyPlugin", "type": "policy", "config": {"level": "strict"}},
    {"name": "future_runtime_plugin", "type": "runtime", "status": "planned", "description": "planned runtime hook"}
  ],
  "pipeline": {"nodes": []}
}
```

- `global_config` 必须是对象。运行时会把实际配置作为 `params["_global"]` 传给每个普通 node。
- `global_config` 中和 node config schema 同名的键会覆盖 node 的实际 params；其他键只通过 `_global` 传递。
- 推荐写成 `{"config": {...}, "allow_config_override": false}`。无论 `allow_config_override` 是否为 `true`，同名键都会覆盖局部 config；当它为 `false` 且发生覆盖时，健康检查给 warning。
- `base_lib.paths` 是相对当前 config 文件的搜索路径。
- `base_lib.modules` 可写字符串简写，等价于 `{"module": "...", "status": "implemented"}`。
- `plugins[].config` 和 `plugins[].settings` 都可传插件设置，值必须是对象；插件实例会收到 `plugin.config`，如果实现了 `configure(config)` 会在加载时被调用。
- `status` 只允许 `implemented` 或 `planned`，默认 `implemented`。
- `planned` 资源可以不存在、不会加载、不会执行，只用于规划、inspect 和 Mermaid 展示。
- implemented base_lib 必须提供 `BASE_LIB_INFO`；implemented plugin 必须提供 `PLUGIN_INFO`。

只有顶层 `base_lib.modules` 中声明为 `implemented` 的模块会进入 base_lib allowlist。implemented node 如果导入未声明或只声明为 `planned` 的 base_lib，会被健康检查拒绝。

nodeset 也可以声明自己的 `global_config`。外部 nodeset JSONC 文件的顶层 `global_config` 会作为该文件内 nodeset 的默认内部配置。调用 nodeset 时，调用节点上的 `config` 会覆盖 nodeset 内部 `global_config`，再覆盖内部 node 局部 config；调用节点上的 `allow_config_override` 控制这些覆盖是否产生 warning。

## node 调用

```jsonc
{
  "name": "add",
  "type": "demo.add",
  "display_name": "Add Delta",
  "description": "Adds a configured delta to the incoming value.",
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

字段说明：

- `name`：本次调用的 node_id，在当前 pipeline 内必须唯一。
- `type`：注册表中的 node_type；也兼容旧字段名 `registry_key`。
- `status`：可选，`implemented` 或 `planned`，默认 `implemented`。
- `flow_kind`：只允许 planned node 使用；implemented node 的 flow_kind 来自 registry 中的 `NODE_INFO`。
- `display_name`：本次调用的易读名，用于 Mermaid/SVG label。调用点没写会产生 `GRAPH.SMELL.MISSING_NODE_DISPLAY_NAME` warning。
- `description`：本次调用的说明，用于 Mermaid/SVG label。调用点没写会产生 `GRAPH.SMELL.MISSING_NODE_DESCRIPTION` warning。
- `category` / `version`：可选可视化元数据，用于图审查展示。
- `style`：可选可视化颜色对象，只允许 `fill`、`stroke`、`text` 三个 `#RRGGBB` hex 颜色。
- `similar_to`：可选相似性声明，表示本调用点是同作用域另一个 node 的 `variant` 或 `copy`；对象内必须写 `node`、`relationship` 和 `reason`。
- `requires`：本次调用按逻辑 `type` 消费的数据，必须写对象并显式声明 `cardinality`。
- `provides`：本次调用输出的数据，必须写对象并同时声明唯一 `key` 与逻辑 `type`。
- `config`：本次调用覆盖注册默认值的配置。
- `node_configs`：调用 nodeset 时，用来覆盖内部 node 配置。
- `allow_config_override`：调用 nodeset 时控制同名配置覆盖是否产生 warning；默认 `false`，不阻止实际覆盖。
- `join_policy`：可选调度语义，`safe_any`、`any_active` 或 `all`；默认 `safe_any`，不进入运行时 `params`。
- `async`：可选，`detached` 或 `result_key`；只用于显式后台 side task。
- `result_key`：仅当 `async: "result_key"` 时必填，表示 future 结果写入的唯一 key，且必须在 `provides` 中声明。

`name` 是运行时图中的唯一节点名，不等于 node 类型。同一个 `type` 可以在同一 pipeline 中调用多次，但每次必须有不同 `name`。输出 `key` 全图唯一；输出 `type` 可以重复，下游按 `type` 消费。

`config` 必须是对象。调用处 config 会覆盖 registry 默认值，但不能出现 registry schema 未声明的字段。

`display_name`、`category`、`version`、`description`、`style`、`similar_to` 是调用点元数据，不会进入运行时 `params`。如果 node 运行时确实需要同名参数，必须写进 `"config": {...}`。

`similar_to.node` 必须指向同一 pipeline 或同一 nodeset 内已存在的 node，不能指向自己；`relationship` 只允许 `variant` 或 `copy`；`reason` 必须非空。它只用于有意重复实现的健康检查豁免：A 指向 B、B 指向 A，或 A/B 共同指向同一个 base 时，会跳过对应 `GRAPH.SMELL.DUPLICATE_LOGIC` pair；未声明覆盖的重复 pair 仍会 warning。这个字段不改变编译、运行、拓扑、契约或 Mermaid 连边。

Mermaid/SVG label 默认以可读性优先，使用纯文本分区展示：节点首行是 `display_name`，缺省时回退到注册类 `NODE_INFO.display_name` 或 `name`；随后显示 `id:`、`type:`，再用 `-- meta --`、`-- status --`、`-- nodeset --` 等分区展示说明。`requires/provides/exports` 不再塞进节点内；数据契约显示在连边 label 上，例如 `seed -->|value.in| add`，当 provider key 与 type 不同时显示 `value.copy -> value.in`。长说明会确定性换行并在必要时截断。SVG 渲染使用更大的 node spacing、rank spacing、wrapping width 和 diagram padding；普通图和展开审查图都按可读优先生成。

自定义 `style` 只应用于普通可自定义节点。health error/warning、planned node、resource、document、nodeset、external dependency 等系统语义样式优先级更高。

系统颜色是保留语义色，不能作为自定义 `style.fill`、`style.stroke` 或 `style.text` 使用；大小写不敏感。使用时 schema 会报 `CONFIG.SCHEMA.NODE_STYLE_RESERVED_COLOR`。

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

## 严格 key/type 与 inbox 数据流

旧字符串形式不再支持：

```jsonc
"requires": ["value.in"],
"provides": ["value.out"],
"inputs": ["value.in"]
```

必须写成：

```jsonc
"inputs": [{"key": "value.in", "type": "value.in"}],
"outputs": [{"type": "value.out", "cardinality": "exactly_one"}],
"requires": [{"type": "value.in", "cardinality": "exactly_one"}],
"provides": [{"key": "value.out", "type": "value.out"}]
```

- `key` 是唯一数据地址，用于 node 返回 mapping、trace、调试和来源记录。
- `type` 是逻辑数据类型，可以重复，用于表达多个互斥分支产出同一种逻辑结果。
- `cardinality` 只允许 `exactly_one`、`optional_one`、`all`。
- runtime 使用 node inbox / edge payload。node 只能收到直接 incoming edge 投递的数据，不会跨多跳从全局 Context 读取早期输出。
- node 收到 envelope：`inputs["value.in"]["value"]` 是业务值，`inputs["value.in"]["key"]` 是实际来源 key。
- `pipeline.outputs` 决定最终 run result 保留哪些 envelope；未声明的中间值会释放。

## terminal start/end

每个可执行 pipeline 和 nodeset 内部 pipeline 都应有 terminal start/end：

```jsonc
{
  "pipeline": {
    "inputs": [{"key": "value.in", "type": "value.in"}],
    "outputs": [{"type": "value.out", "cardinality": "exactly_one"}],
    "nodes": [
      {"name": "start", "type": "demo.start", "display_name": "Start", "description": "Starts the demo pipeline."},
      {"name": "input", "type": "demo.input", "display_name": "Read Input", "description": "Reads the incoming value.", "requires": [{"type": "value.in", "cardinality": "exactly_one"}], "provides": [{"key": "value.in.input", "type": "value.in"}]},
      {"name": "add", "type": "demo.add", "display_name": "Add Delta", "description": "Adds a configured delta.", "requires": [{"type": "value.in", "cardinality": "exactly_one"}], "provides": [{"key": "value.out", "type": "value.out"}]},
      {"name": "end", "type": "demo.end", "display_name": "End", "description": "Consumes the final output.", "requires": [{"type": "value.out", "cardinality": "exactly_one"}]}
    ],
    "edges": [["start", "input"], ["input", "add"], ["add", "end"]]
  }
}
```

`io` 不是 start/end。推荐结构是：

```text
terminal start -> io input -> process... -> io output -> terminal end
```

## edge

二元数组形式：

```jsonc
["seed", "add"]
```

对象形式：

```jsonc
{"from": "route", "to": "retry", "when": "flow.route == 'again'"}
```

规则：

- `pipeline.edges` 是唯一控制流来源。
- `requires/provides` 不会自动推导控制流；图上只会在已有连边上标出能匹配到的 contract。
- `when` 只支持小表达式：`key == 'value'`、`key != 'value'`、`flag == true`、`flag == false`。字符串可以用单引号或双引号；布尔值必须小写 `true` / `false`。
- 从 `decision` 出发的 edge 必须写 `when`。

edge 只能连接当前 pipeline 内已经声明的 node。对象形式也兼容 `source` / `target` 字段名：

```jsonc
{"source": "route", "target": "end", "when": "flow.route == 'done'"}
```

## cycle

普通 `pipeline.edges` 和 nodeset 内部 `pipeline.edges` 不允许形成环。旧 `pipeline.loops` 已移除，显式 edge 回环也会被 `GRAPH.CYCLE.FORBIDDEN` 拒绝；需要循环时使用 `vibeflow.loop.while`。

`decision` 只负责分支选择，例如：

```jsonc
{
  "pipeline": {
    "inputs": [{"key": "value.in", "type": "value.in"}],
    "outputs": [{"type": "value.out", "cardinality": "exactly_one"}],
    "max_steps": 1000,
    "nodes": [
      {"name": "start", "type": "demo.start"},
      {
        "name": "work",
        "type": "demo.work",
        "requires": [{"type": "value.in", "cardinality": "exactly_one"}],
        "provides": [{"key": "value.out", "type": "value.out"}]
      },
      {
        "name": "route",
        "type": "demo.route",
        "requires": [{"type": "value.out", "cardinality": "exactly_one"}],
        "provides": [{"key": "flow.route", "type": "flow.route"}]
      },
      {"name": "left", "type": "demo.left", "requires": [{"type": "value.out", "cardinality": "exactly_one"}]},
      {"name": "end", "type": "demo.end", "requires": [{"type": "value.out", "cardinality": "exactly_one"}]}
    ],
    "edges": [
      ["start", "work"],
      ["work", "route"],
      {"from": "route", "to": "left", "when": "flow.route == 'left'"},
      {"from": "left", "to": "end"},
      {"from": "route", "to": "end", "when": "flow.route == 'done'"}
    ]
  }
}
```

`max_steps` 是运行时防护，不是架构语义。普通 `pipeline.edges` / nodeset 内部 `pipeline.edges` 不允许形成环；出现环会报 `GRAPH.CYCLE.FORBIDDEN`。

`decision` 只负责分支选择，不再承担 retry / again / done 循环语义。训练循环、批处理循环和 retry-until 循环都应使用一等 loop node。

## 一等 loop node

系统 loop node 是运行时能力，不需要在 registry 中注册：

- `vibeflow.loop.while`：重复执行一个 nodeset body，直到固定轮数到达，或 body/state 输出的 bool 条件满足。

loop node 像普通 node 一样声明 `requires/provides`，并额外写顶层 `loop` 对象。`loop` 不进入运行时 `params`；如果业务 node 真需要同名参数，必须写到 `config`。body 必须指向同一 config 或已导入的 nodeset；展开 SVG 时 loop body 会像 nodeset 一样展开。

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
    "collect": [{"from": "train.loss", "as": "train.loss_history"}],
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

Mermaid/SVG 中 while loop 使用独立 hourglass 形状和 `loopNode` 系统样式，label 会显示 `body:`、`stop:`、`max:`。`loopNode` 颜色属于系统保留色，不允许作为自定义 `style` 颜色。

## join_policy 与 safe OR join

默认 join 语义是 safe OR：目标 node 只要本轮 active incoming branch 提供了所需输入即可运行，但不会静默选择含糊输入。

- `join_policy: "safe_any"`：默认值。适合互斥分支汇入同一个消费 node；如果某条 conditional incoming 只是控制门、不提供目标所需数据，runtime 会等待该条件边激活，避免未选中分支提前运行。
- `join_policy: "any_active"`：显式 OR join。只有确认任一 active incoming 都足够触发目标时使用。
- `join_policy: "all"`：等待所有 incoming edge 在本轮都激活后才调度目标。

安全规则：

- 同一 `exactly_one` requirement 收到多个 active provider 时，runtime 报错。
- conditional provider 和 unconditional provider 同时可能满足同一 requirement 时，health 报 `GRAPH.JOIN.AMBIGUOUS_UNCONDITIONAL`。通常应改成显式 merge/select node、互斥分支，或 `join_policy: "all"`。
- 每次调度只消费本轮 edge activation 送进 inbox 的输入；不要依赖旧输出留在全局 context 触发后续 join。

## planned node

可用 planned node 先登记架构：

```jsonc
{
  "name": "classify",
  "status": "planned",
  "flow_kind": "decision"
}
```

planned 内容会在健康检查中给 warning；runtime 默认拒绝执行。只有 `planned_behavior.kind == "python_stub"` 且显式加 `--allow-planned-stub` 时，才可作为开发测试 stub 执行。

planned node 可以暂时不写 `type`，此时内核会用 `planned.<name>` 作为占位类型。planned node 必须写 `flow_kind`，因为图形审查需要知道它的流程图形状。implemented node 不能在 config 里写 `flow_kind`，必须来自 `NODE_INFO`。

planned node / planned nodeset 可选 `planned_behavior`：

```jsonc
{"planned_behavior": "blocking"}
{"planned_behavior": "transparent"}
{"planned_behavior": {"kind": "python_stub", "stub_module": "project/stubs/runtime_control_stub.py"}}
```

- 默认 `blocking`：保持传统 planned 行为，不参与主流程健康检查的连通性判断。
- `transparent`：仍产生 planned warning，但参与 start/end、reachability、orphan 等 flow health，适合设计期连接前后 implemented 节点。
- `python_stub`：仍产生 planned warning，并额外产生 `GRAPH.PLANNED.PYTHON_STUB_DEV_ONLY`；参与 flow health。只有运行命令显式加 `--allow-planned-stub` 时才可执行。
- `blocking` 和 `transparent` 永远不可执行；含 planned/python_stub 的配置不能视为 production ready。
- `stub_module` 必须是主项目相对路径，且落在 `project/stubs/*.py`。stub 文件必须暴露 `run_stub(inputs, params)`，不能做文件、网络、进程、线程、动态 import 等高风险操作。
- `run_stub` 只收到该节点声明的 `requires` 输入和合并后的 params；返回值必须是 mapping，key 必须严格等于该节点 `provides`。
- planned nodeset 若使用 `python_stub`，会按单个 stub 节点执行，不展开内部 pipeline；调用节点的 `requires/provides` 必须与 nodeset 声明匹配，`exports` 必须覆盖 `provides`。

## async node

异步是显式配置能力，不会自动并行普通节点：

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

- `detached`：主流程不等待，run 结束时 flush；失败记录 trace warning，不默认中断主流程。
- `result_key`：下游直接 edge 上的节点按 `type` require 该异步结果时 join，结果写入 `result_key` 对应的 provider key。
- runtime 不自动 merge async context；共享对象的线程安全由业务对象负责。
- async 不支持 nodeset。

CLI 中 `--runtime-profile train` 会自动启用偏训练场景的选项：`trace="boundary"`、`execution="compiled"`、run/block hooks 开启、node/nodeset hooks 关闭、async flush timeout 为 30 秒。`--runtime-profile debug` 会启用完整 trace 和所有 hook。

诊断 trace 保留兼容字段和嵌套字段两套视图：`runtime.exec_order`、`runtime.node_runs`、`runtime.edge_executions`、`runtime.step_count` 仍只描述顶层 pipeline；嵌套 nodeset/loop 的完整顺序看 `runtime.qualified_exec_order`、`runtime.qualified_node_runs`、`runtime.qualified_edge_executions` 和 `runtime.total_step_count`。每个 trace event 都带 `path` 数组、`qualified_node` 和 `depth`，例如 `["outer_call", "inner_call", "add"]` / `outer_call.inner_call.add`。机器读取应优先用 `path`，不要解析 dotted 字符串。

## 已移除字段

这些字段出现时会失败：

- `boundary`
- `pipeline.loops`
- edge `max_executions`
- edge `loop`
- pipeline/edge 级 `max_iterations`；loop 使用 `loop.max_iterations`

## policy

项目目录可放 `kernel_policy.jsonc` 或 `governance.jsonc`。也可以在 config 中写内联 `policy`，内联优先级最高。

```jsonc
{
  "policy": {
    "node_source": {
      "max_lines": 500,
      "max_bytes": 60000,
      "warn_lines": 450,
      "warn_bytes": 54000
    }
  }
}
```

通常不要放宽硬规则。确实需要临时放宽时，应写明 reason 和 expires。

policy 来源优先级：

1. 默认内核 policy。
2. config 文件同目录的 `kernel_policy.jsonc` 或 `governance.jsonc`。
3. 命令行 `--policy` 指定的文件。
4. config 内联 `policy`。
5. policy plugin 返回的 policy 更新。

后面的来源会覆盖或追加前面的设置。`rules.downgrades` 和 `rules.exemptions` 是追加列表，其他对象字段按深度合并。

## 常见拓扑问题

- `GRAPH.FLOW.MISSING_START`：没有 terminal start，或 start 有 incoming edge。
- `GRAPH.FLOW.MISSING_END`：没有 terminal end，或 end 有 outgoing edge。
- `GRAPH.FLOW.UNREACHABLE_FROM_START`：某个 implemented node 从 start 走不到。
- `GRAPH.FLOW.CANNOT_REACH_END`：某个 implemented node 不能到达 end。
- `GRAPH.DECISION.MISSING_BRANCH_VALUE`：decision 的 `output_schema` 声明了 enum/boolean 分支，但 edge 没覆盖。
- `GRAPH.CYCLE.FORBIDDEN`：普通 graph 中出现显式 edge 环；请改用 `vibeflow.loop.while`。
- `GRAPH.DATA.MISSING_DIRECT_PROVIDER`：某个 require `type` 没有直接 incoming flow predecessor 或入口输入提供；检查 edge、`pipeline.inputs` 或中间 pass-through node。
- `GRAPH.DATA.TYPE_CARDINALITY_AMBIGUOUS`：某个 require `type` 的直接来源数量可能违反 `exactly_one` / `optional_one`。
- `GRAPH.DATA.UNCONSUMED_PROVIDER`：某个 provider `key/type` 没有直接下游消费；如果是预期最终产物，确保 `pipeline.outputs` 声明它，且必要时由 end/io/document 节点消费。
- `GRAPH.SMELL.DUPLICATE_LOGIC`：两个 config node 的 `run_pure` fingerprint 相同；报告 `details` 会列出具体 nodes、node_types、fingerprint、duplicate_group 和 `similar_to` 豁免提示。
