# Workflow 与 Config

Config 描述工作流中的调用实例、公共输入输出、资源选择和显式连接。Node 类型或 Nodeset 定义提供已实现调用的端口契约。

## Config 与正式审核图

Config 是实际构建和执行的来源，不是绘图用的描述语言。修改已有环节时，应沿已登记 Architecture 的 source 在原工作流的实际位置表达 planned Node 或 Nodeset，并对完整工作流生成正式审核图。不得用独立的局部、概念性或单纯表意配置代替原流程；通过结构检查也不能代替真实调用和接入依据。

协同模式对新增独立工作流、共享资源变更，以及 planned 与已执行状态的具体要求见其 profile 文档。

## 多入口与业务语义

若 CLI、浏览器事件或其他入口承诺相同业务判断，应检查它们的真实调用路径是否汇入同一套执行中的 Node/Nodeset。两个入口分别调用相似的 helper、复制相同代码或使用相同名称，不等于共享工作流语义。入口边界负责读取和格式适配，业务分类、合并和领域校验由拥有该职责的节点处理；输出边界只适配结果，不从原始输入重新计算。

边界适配应保留未知字段、字段缺失与错误类别，直到负责判断的节点处理它们。入口特有的词法错误可以由入口识别，但不应在 guard 或错误输出中把不同错误改写成同一种默认结果。辅助数据的 `data bypass` 不应成为绕过共享业务处理的主线。用工作流的实际边和调用点核对这些关系，不凭图形外观推断执行行为。

## 最小 pipeline

```jsonc
{
  "pipeline": {
    "inputs": [
      {"key": "request", "type": "payload.request", "display_name": "Public request"}
    ],
    "nodes": [
      {
        "id": "start",
        "type_used": "example.start",
        "display_name": "Start request",
        "description": "Starts this request workflow."
      },
      {
        "id": "process",
        "type_used": "example.process",
        "display_name": "Process request",
        "description": "Applies the business transformation."
      },
      {
        "id": "end",
        "type_used": "example.end",
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

每个调用实例必须有非空 `display_name` 和 `description`。`id` 在当前作用域唯一，`type_used` 指向 Node `type_key`、Nodeset `type_key` 或系统类型。

已实现普通 Node 和 Nodeset 调用不在 Config 重复写 `requires` / `provides`。planned Node、`vibeflow.io`、`vibeflow.loop.while` 以及 pipeline 公共输入输出继续显式声明其结构。

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

## Decision

Decision Node 使用 `flow_kind="decision"`，提供 route-like 输出，例如 `flow.route`。从 Decision 发出的分支 edge 写明 `when`：

```jsonc
{"from": "route", "to": "accept", "when": "flow.route == 'accept'"}
```

分支值由业务实现与项目测试负责；VibeFlow 检查条件语法、分支拓扑和可达性。

## I/O 与副作用边界

| `flow_kind` 或实现 | 使用者可见边界 |
| --- | --- |
| `vibeflow.process` Ruleset | 默认禁止副作用 |
| `vibeflow.io` Ruleset | 允许真实终端输入输出 |
| `vibeflow.document` / `vibeflow.data_store` Ruleset | 允许文件、网络、数据库等 Python I/O |
| `vibeflow.global_state` Ruleset | 允许易失状态与源码可见 runtime dispatch |

Node 声明显式选择 Ruleset；分类可以提供默认选择。`flow_kind` 继续表示执行身份，`external` 继续表示外部边界，它们不授予副作用权限。报告中的 `effect_scope` 来自有效规则记录；显式空选择表示未约束。详见[规则与分类](rules-and-nodes.md)。需要协调 `global_state` 冲突资源时使用静态命名 `execution_lock`；相同 key 互斥，不同 key 可并行。

## 可执行结构示例

以下三个任务无关配置由测试直接提取、验证并运行。顺序主线可以用额外 transfer edge 把早期数据送到后续调用：

<!-- vibeflow-executable-example: sequential-bypass -->
```jsonc
{
  "pipeline": {
    "nodes": [
      {"id":"start","type_used":"guide.start","display_name":"Start","description":"Starts the flow."},
      {"id":"source","type_used":"guide.source","display_name":"Source","description":"Produces original and current values."},
      {"id":"normalize","type_used":"guide.normalize","display_name":"Normalize","description":"Normalizes the current value."},
      {"id":"combine","type_used":"guide.combine","display_name":"Combine","description":"Combines both values."},
      {"id":"output","type_used":"guide.output_value","display_name":"Output I/O","description":"Adapts the semantic result."},
      {"id":"end","type_used":"guide.end","display_name":"End","description":"Ends after the response.","similar_to":{"node":"start","relationship":"copy","reason":"Both terminal calls intentionally use the same empty lifecycle implementation."}}
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
      {"id":"start","type_used":"guide.start","display_name":"Start","description":"Starts both branches."},
      {"id":"left","type_used":"guide.left","display_name":"Left","description":"Produces the left value."},
      {"id":"right","type_used":"guide.right","display_name":"Right","description":"Produces the right value.","similar_to":{"node":"left","relationship":"variant","reason":"The parallel branches intentionally share the same pure constant-source shape."}},
      {"id":"merge","type_used":"guide.merge","display_name":"Merge","description":"Waits for both branches.","join_policy":"all"},
      {"id":"output","type_used":"guide.output_merged","display_name":"Output I/O","description":"Adapts the merged value."},
      {"id":"end","type_used":"guide.end","display_name":"End","description":"Ends after the response.","similar_to":{"node":"start","relationship":"copy","reason":"Both terminal calls intentionally use the same empty lifecycle implementation."}}
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
    "inputs":[{"key":"request.raw","type":"request.raw","display_name":"Raw Request"}],
    "nodes": [
      {"id":"start","type_used":"guide.start","display_name":"Start","description":"Starts the boundary flow."},
      {"id":"input","type_used":"guide.input","display_name":"Input I/O","description":"Decodes the external representation."},
      {"id":"semantic","type_used":"guide.semantic","display_name":"Semantic Process","description":"Produces a typed internal value."},
      {"id":"output","type_used":"guide.output_number","display_name":"Output I/O","description":"Adapts the internal value."},
      {"id":"end","type_used":"guide.end","display_name":"End","description":"Ends after the response.","similar_to":{"node":"start","relationship":"copy","reason":"Both terminal calls intentionally use the same empty lifecycle implementation."}}
    ],
    "edges":[["start","input"],["input","semantic"],["semantic","output"],["output","end"]],
    "outputs":[{"type":"response.number","cardinality":"exactly_one","display_name":"Response Number"}]
  }
}
```

## 项目配置

workspace 根的 `vibeflow_config.jsonc` 登记项目 root。每个 root 的 `vibeflow_project.jsonc` 必须声明 `project_target: "python" | "javascript"`，并登记 Registry 或 descriptor 目录、Architecture 文档及 Target 配置。

验证修改：

```bash
python run.py architecture --config <root>/configs/main.jsonc --output <root>/ARCHITECTURE.jsonc
python run.py validate --config <root>/configs/main.jsonc
```
