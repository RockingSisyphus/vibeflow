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
- `requires`：本次调用按逻辑 `type` 消费的数据，必须写对象并显式声明 `cardinality`。
- `provides`：本次调用输出的数据，必须写对象并同时声明唯一 `key` 与逻辑 `type`。
- `config`：本次调用覆盖注册默认值的配置。
- `node_configs`：调用 nodeset 时，用来覆盖内部 node 配置。
- `allow_config_override`：调用 nodeset 时控制同名配置覆盖是否产生 warning；默认 `false`，不阻止实际覆盖。
- `async`：可选，`detached` 或 `result_key`；只用于显式后台 side task。
- `result_key`：仅当 `async: "result_key"` 时必填，表示 future 结果写入的唯一 key，且必须在 `provides` 中声明。

`name` 是运行时图中的唯一节点名，不等于 node 类型。同一个 `type` 可以在同一 pipeline 中调用多次，但每次必须有不同 `name`。输出 `key` 全图唯一；输出 `type` 可以重复，下游按 `type` 消费。

`config` 必须是对象。调用处 config 会覆盖 registry 默认值，但不能出现 registry schema 未声明的字段。

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
      {"name": "start", "type": "demo.start"},
      {"name": "input", "type": "demo.input", "requires": [{"type": "value.in", "cardinality": "exactly_one"}], "provides": [{"key": "value.in.input", "type": "value.in"}]},
      {"name": "add", "type": "demo.add", "requires": [{"type": "value.in", "cardinality": "exactly_one"}], "provides": [{"key": "value.out", "type": "value.out"}]},
      {"name": "end", "type": "demo.end", "requires": [{"type": "value.out", "cardinality": "exactly_one"}]}
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
- `requires/provides` 不会自动推导控制流。
- `when` 只支持小表达式：`key == 'value'`、`key != 'value'`、`flag == true`、`flag == false`。字符串可以用单引号或双引号；布尔值必须小写 `true` / `false`。
- 从 `decision` 出发的 edge 必须写 `when`。

edge 只能连接当前 pipeline 内已经声明的 node。对象形式也兼容 `source` / `target` 字段名：

```jsonc
{"source": "route", "target": "end", "when": "flow.route == 'done'"}
```

## cycle

旧 `pipeline.loops` 已移除。现在 cycle 直接由显式 edge 表达，但必须经过 `decision`：

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
      {
        "name": "copy",
        "type": "demo.copy",
        "requires": [{"type": "value.out", "cardinality": "exactly_one"}],
        "provides": [{"key": "value.in.next", "type": "value.in"}]
      },
      {"name": "end", "type": "demo.end", "requires": [{"type": "value.out", "cardinality": "exactly_one"}]}
    ],
    "edges": [
      ["start", "work"],
      ["work", "route"],
      {"from": "route", "to": "copy", "when": "flow.route == 'again'"},
      ["copy", "work"],
      {"from": "route", "to": "end", "when": "flow.route == 'done'"}
    ]
  }
}
```

`max_steps` 是运行时防护，不是架构语义。

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

## 已移除字段

这些字段出现时会失败：

- `boundary`
- `pipeline.loops`
- edge `max_executions`
- edge `loop`
- `max_iterations`

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
- `GRAPH.CYCLE.MISSING_DECISION_EXIT`：cycle 中没有 decision exit 能到达 terminal end。
- `GRAPH.DATA.MISSING_DIRECT_PROVIDER`：某个 require `type` 没有直接 incoming flow predecessor 或入口输入提供；检查 edge、`pipeline.inputs` 或中间 pass-through node。
- `GRAPH.DATA.TYPE_CARDINALITY_AMBIGUOUS`：某个 require `type` 的直接来源数量可能违反 `exactly_one` / `optional_one`。
- `GRAPH.DATA.UNCONSUMED_PROVIDER`：某个 provider `key/type` 没有直接下游消费；如果是预期最终产物，确保 `pipeline.outputs` 声明它，且必要时由 end/io/document 节点消费。
