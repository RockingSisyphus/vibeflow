# 03. Config 与 Pipeline 规范

配置文件使用 `.jsonc`，支持 `//` 行注释和 `/* ... */` 块注释。不支持 trailing comma。

## 标准结构

```jsonc
{
  "pipeline": {
    "inputs": [],
    "max_steps": 1000,
    "nodes": [],
    "edges": []
  },
  "nodesets": [],
  "plugins": [],
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

## node 调用

```jsonc
{
  "name": "add",
  "type": "demo.add",
  "requires": ["value.in"],
  "provides": ["value.out"],
  "config": {"delta": 3}
}
```

字段说明：

- `name`：本次调用的 node_id，在当前 pipeline 内必须唯一。
- `type`：注册表中的 node_type。
- `status`：可选，`implemented` 或 `planned`，默认 `implemented`。
- `flow_kind`：只允许 planned node 使用；implemented node 的 flow_kind 来自 registry 中的 `NODE_INFO`。
- `requires`：本次调用需要从上下文读取的 key。
- `provides`：本次调用写入上下文的 key。
- `config`：本次调用覆盖注册默认值的配置。
- `node_configs`：调用 nodeset 时，用来覆盖内部 node 配置。
- `async`：可选，`detached` 或 `result_key`；只用于显式后台 side task。
- `result_key`：仅当 `async: "result_key"` 时必填，表示 future 结果写入的唯一 key，且必须在 `provides` 中声明。

## terminal start/end

每个可执行 pipeline 和 nodeset 内部 pipeline 都应有 terminal start/end：

```jsonc
{
  "pipeline": {
    "inputs": ["value.in"],
    "nodes": [
      {"name": "start", "type": "demo.start"},
      {"name": "input", "type": "demo.input", "requires": ["value.in"]},
      {"name": "add", "type": "demo.add", "requires": ["value.in"], "provides": ["value.out"]},
      {"name": "end", "type": "demo.end", "requires": ["value.out"]}
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
- `when` 只支持小表达式：`key == 'value'`、`key != 'value'`、`flag == true`、`flag == false`。
- 从 `decision` 出发的 edge 必须写 `when`。

## cycle

旧 `pipeline.loops` 已移除。现在 cycle 直接由显式 edge 表达，但必须经过 `decision`：

```jsonc
{
  "pipeline": {
    "max_steps": 1000,
    "nodes": [
      {"name": "start", "type": "demo.start"},
      {"name": "work", "type": "demo.work", "requires": ["value.in"], "provides": ["value.out"]},
      {"name": "route", "type": "demo.route", "requires": ["value.out"], "provides": ["flow.route"]},
      {"name": "copy", "type": "demo.copy", "requires": ["value.out"], "provides": ["value.in"]},
      {"name": "end", "type": "demo.end", "requires": ["value.out"]}
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

planned 内容会在健康检查中给 warning，但 runtime 会拒绝执行。

## async node

异步是显式配置能力，不会自动并行普通节点：

```jsonc
{"name": "metrics", "type": "demo.metrics", "async": "detached", "requires": ["batch"], "provides": ["metrics"]}
{"name": "load", "type": "demo.load", "async": "result_key", "result_key": "data.batch", "provides": ["data.batch"]}
```

- `detached`：主流程不等待，run 结束时 flush；失败记录 trace warning，不默认中断主流程。
- `result_key`：下游 `requires` 该 key 时 join，结果只写入 `result_key`。
- runtime 不自动 merge async context；共享对象的线程安全由业务对象负责。
- async 不支持 nodeset。

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
