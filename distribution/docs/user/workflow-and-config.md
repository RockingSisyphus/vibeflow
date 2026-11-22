# Workflow 与 Config

Config 描述工作流中的调用实例、公共输入输出、资源选择和显式连接。业务 Node 或 NodesetType 定义提供已实现调用的端口契约。

## 最小 pipeline

```jsonc
{
  "pipeline": {
    "inputs": [
      {"key": "request", "type": "payload.request", "display_name": "Public request", "required": true}
    ],
    "nodes": [
      {
        "id": "start",
        "definition_id": "example.start",
        "display_name": "Start request",
        "description": "Starts this request workflow."
      },
      {
        "id": "process",
        "definition_id": "example.process",
        "display_name": "Process request",
        "description": "Applies the business transformation."
      },
      {
        "id": "end",
        "definition_id": "example.end",
        "display_name": "End request",
        "description": "Ends after the response is available."
      }
    ],
    "edges": [["start", "process"], ["process", "end"]],
    "outputs": [
      {"type": "payload.response", "cardinality": "exactly_one", "display_name": "Public response"}
    ]
  }
}
```

每个调用实例必须有非空 `display_name` 和 `description`。`id` 在当前作用域唯一，`definition_id` 指向 业务 Node 的 `id`、NodesetType 的 `type_key` 或系统类型。

已实现普通 Node 和 Nodeset 调用不在 Config 重复写 `requires` / `provides`。planned Node、`vibeflow.loop.while` 以及 pipeline 公共输入输出继续显式声明其结构。

Python Runtime 与 JavaScript/TypeScript AOT 使用同一公共输入契约。每个 `pipeline.inputs` 项都必须显式写布尔值 `required`：`true` 要求调用时提供该 key，`false` 允许省略；两者都拒绝未声明的输入 key。省略 `inputs` 或声明空列表时，调用输入只能是 `{}`。`required` 不能省略或写成 `null`。

## 执行模式

同步图在准备阶段拒绝已知挂起实现，运行时也拒绝与声明不符的 Promise、coroutine 或 Future。Node 的 completion 声明应与实际实现一致。

## 控制与数据

`pipeline.edges` 是控制流的唯一来源。数组 edge 同时调度目标并传递匹配的 envelope：

```jsonc
["parse", "validate"]
```

需要拆开调度和传递时使用对象 edge：

```jsonc
{"from": "metadata", "to": "save", "schedule": false}
{"from": "trigger", "to": "save", "transfer": false}
```

`schedule: false` 只传数据，`transfer: false` 只调度；两者不能同时为 `false`。同步并行分支需要等待全部分支时，在汇合调用写 `join_policy: "all"`。互斥 decision 分支通常使用默认 safe-OR 合流。

分支并发额度与汇合方式见[普通图并发](graph-concurrency.md)。

只有起点、终点、`when`、`schedule`、`transfer` 全部相同的重复声明会合并。未填写的角色设置与显式填写的设置保持为不同声明，不推断条件是否等价。同一对节点可以声明多条不同条件的路线，每条路线分别按自己的条件和角色生效；同一次输出不会因为多条路线匹配而重复执行目标或重复接收同一份 envelope。

## Decision

Decision Node 使用 `flow_kind="decision"`，提供 route-like 输出，例如 `flow.route`。从 Decision 发出的分支 edge 写明 `when`：

```jsonc
{"from": "route", "to": "accept", "when": "flow.route == 'accept'"}
```

分支值由业务实现与项目测试负责；VibeFlow 检查条件语法、分支拓扑和可达性。

## 可执行结构示例

以下片段展示三种数据连接方式，其中 `guide.*` 业务 Node 从 nodes/ 声明发现。顺序主线可以用额外 transfer edge 把早期数据送到后续调用：

<!-- vibeflow-executable-example: sequential-bypass -->
```jsonc
{
  "pipeline": {
    "nodes": [
      {"id":"start","definition_id":"guide.start","display_name":"Start","description":"Starts the flow."},
      {"id":"source","definition_id":"guide.source","display_name":"Source","description":"Produces original and current values."},
      {"id":"normalize","definition_id":"guide.normalize","display_name":"Normalize","description":"Normalizes the current value."},
      {"id":"combine","definition_id":"guide.combine","display_name":"Combine","description":"Combines both values."},
      {"id":"output","definition_id":"guide.output_value","display_name":"Output I/O","description":"Adapts the semantic result."},
      {"id":"end","definition_id":"guide.end","display_name":"End","description":"Ends after the response.","similar_to":{"node":"start","relationship":"copy","reason":"Both terminal calls intentionally use the same empty lifecycle implementation."}}
    ],
    "edges":[["start","source"],["source","normalize"],["normalize","combine"],["source","combine"],["combine","output"],["output","end"]],
    "outputs":[{"type":"response.value","cardinality":"exactly_one","display_name":"Response"}]
  }
}
```

真正的并行 fan-out 在汇合点使用 `join_policy: "all"`：

<!-- vibeflow-executable-example: parallel-all-join -->
```jsonc
{
  "pipeline": {
    "nodes": [
      {"id":"start","definition_id":"guide.start","display_name":"Start","description":"Starts both branches."},
      {"id":"left","definition_id":"guide.left","display_name":"Left","description":"Produces the left value."},
      {"id":"right","definition_id":"guide.right","display_name":"Right","description":"Produces the right value.","similar_to":{"node":"left","relationship":"variant","reason":"The parallel branches intentionally share the same pure constant-source shape."}},
      {"id":"merge","definition_id":"guide.merge","display_name":"Merge","description":"Waits for both branches.","join_policy":"all"},
      {"id":"output","definition_id":"guide.output_merged","display_name":"Output I/O","description":"Adapts the merged value."},
      {"id":"end","definition_id":"guide.end","display_name":"End","description":"Ends after the response.","similar_to":{"node":"start","relationship":"copy","reason":"Both terminal calls intentionally use the same empty lifecycle implementation."}}
    ],
    "edges":[["start","left"],["start","right"],["left","merge"],["right","merge"],["merge","output"],["output","end"]],
    "outputs":[{"type":"response.value","cardinality":"exactly_one","display_name":"Response"}]
  }
}
```

输入 I/O、语义处理和 typed output I/O 使用不同 contract：

<!-- vibeflow-executable-example: typed-io-boundaries -->
```jsonc
{
  "pipeline": {
    "inputs":[{"key":"request.raw","type":"request.raw","display_name":"Raw Request","required":true}],
    "nodes": [
      {"id":"start","definition_id":"guide.start","display_name":"Start","description":"Starts the boundary flow."},
      {"id":"input","definition_id":"guide.input","display_name":"Input I/O","description":"Decodes the external representation."},
      {"id":"semantic","definition_id":"guide.semantic","display_name":"Semantic Process","description":"Produces a typed internal value."},
      {"id":"output","definition_id":"guide.output_number","display_name":"Output I/O","description":"Adapts the internal value."},
      {"id":"end","definition_id":"guide.end","display_name":"End","description":"Ends after the response.","similar_to":{"node":"start","relationship":"copy","reason":"Both terminal calls intentionally use the same empty lifecycle implementation."}}
    ],
    "edges":[["start","input"],["input","semantic"],["semantic","output"],["output","end"]],
    "outputs":[{"type":"response.number","cardinality":"exactly_one","display_name":"Response Number"}]
  }
}
```

## 更新配置后验证

```bash
python run.py validate --config <root>/configs/main.jsonc
```

## 相关文档

- [架构阅读与维护](architecture.md)：架构资料的阅读与更新。
- [项目治理](project-governance.md)：root 配置和资源选择。
- [Rule 与 Node](rules-and-nodes.md)：局部与图级规则、效果范围。
- [Nodeset 与 Loop](nodeset-types-and-loops.md)：子图导入和循环调用。
- [Workflow 协同](workflow-coordination.md)：命名入口与多入口设计。
- [本地预览](local-preview.md)：生成和查看审核快照。
