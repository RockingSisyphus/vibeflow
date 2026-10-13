# Nodeset 与 Loop

Nodeset 把多个调用组合成一个可复用流程块。Loop 重复执行一个 Nodeset body。

## 独立 Nodeset

```jsonc
{
  "type_key": "example.prepare_text",
  "display_name": "Prepare text",
  "description": "Normalizes and validates supplied text.",
  "expand": true,
  "requires": [
    {"type": "text.raw", "cardinality": "exactly_one", "display_name": "Raw text"}
  ],
  "provides": [
    {"key": "prepared_text", "type": "text.prepared", "display_name": "Prepared text"}
  ],
  "pipeline": {
    "inputs": [
      {"key": "raw_text", "type": "text.raw", "display_name": "Raw text", "required": true}
    ],
    "nodes": [
      {"id": "start", "type_used": "example.start", "display_name": "Start preparation", "description": "Starts text preparation."},
      {"id": "normalize", "type_used": "example.normalize_text", "display_name": "Normalize text", "description": "Normalizes the supplied text."},
      {"id": "end", "type_used": "example.end", "display_name": "End preparation", "description": "Ends after prepared text is available."}
    ],
    "edges": [["start", "normalize"], ["normalize", "end"]],
    "outputs": [
      {"type": "text.prepared", "cardinality": "exactly_one", "display_name": "Prepared text"}
    ]
  }
}
```

Nodeset 内部的 `pipeline.inputs` 同样显式声明 `required`。这里原始文本是必填输入，所以使用 `true`；可选输入使用 `false`，公共输入的完整规则见 [Workflow 与 Config](workflow-and-config.md#最小-pipeline)。

在 workflow 中选择提供 `example.*` Node 的代码插件，再导入并调用 Nodeset：

```jsonc
{
  "plugins": [{"source": {"kind": "file", "ref": "plugins/text.py"}}],
  "nodeset_imports": [{"path": "nodesets/prepare_text.jsonc"}],
  "pipeline": {
    "inputs": [
      {"key": "raw_text", "type": "text.raw", "display_name": "Raw text", "required": true}
    ],
    "nodes": [
      {
        "id": "prepare",
        "type_used": "example.prepare_text",
        "display_name": "Prepare request text",
        "description": "Runs reusable text preparation for this request."
      }
    ]
  }
}
```

调用从 Nodeset 定义继承契约。`config` 覆盖 Nodeset 的 `global_config`；`node_configs` 使用调用点 ID 组成的 dotted path 覆盖内部 Node：

```jsonc
"node_configs": {"normalize": {"collapse_newlines": false}}
```

## 架构图展开选择

Nodeset 定义的 `expand` 控制展开视图是否显示内部流程。省略时默认为 `true`；设置为 `false` 后，图中保留该 Nodeset 的调用框和对外连边，其内部 Node、连边及嵌套 Nodeset 的内容不再展开。

例如，在上面的 `example.prepare_text` 定义中，将该字段改为：

```jsonc
"expand": false
```

`expand` 与 `type_key`、`requires`、`provides` 放在同一层，取值只能是 JSON 布尔值 `true` 或 `false`。同一 Nodeset 定义的多个调用共用这个设置；从独立文件导入的定义和 Loop 的 `body` 引用也遵循它。展开视图在折叠的调用处停止递归，因此内部子 Nodeset 即使选择了 `expand: true`，也不会通过这个调用展示。

检查和运行继续使用完整流程，包括内部源码健康规则、契约、递归与深度检查以及原生执行。`ARCHITECTURE.jsonc` 记录 `expand` 的实际值，并保存完整的内部定义、契约、来源及规则资料，供审查工具读取。

## Planned Nodeset

planned Nodeset 保留 `type_key`、名称、说明和契约，可以暂时省略 `pipeline`，也可以带 planned body 进入 Architecture 与静态检查。implemented Nodeset 必须有完整 pipeline。

## While Loop

`vibeflow.loop.while` 指向一个 Nodeset body，并在调用处显式声明循环契约：

```jsonc
{
  "id": "retry",
  "type_used": "vibeflow.loop.while",
  "display_name": "Retry operation",
  "description": "Repeats the retry body until it succeeds or reaches the limit.",
  "requires": [
    {"type": "retry.state", "cardinality": "exactly_one", "display_name": "Retry state"}
  ],
  "provides": [
    {"key": "retry_result", "type": "retry.result", "display_name": "Retry result"}
  ],
  "loop": {
    "body": "example.retry_step",
    "max_iterations": 5,
    "stop_when": {"from": "retry.done", "equals": true},
    "carry": [{"from": "retry.state", "as": "retry.state", "update": "retry.next_state"}],
    "collect": [{"from": "retry.metric", "as": "retry.metrics"}]
  }
}
```

普通 graph 和 Nodeset body 保持无环；重复执行由 Loop 表达。Nodeset 调用和 `loop.body` 都参与递归与最大嵌套深度检查。

Workflow 的静态默认包含 `vibeflow.workflow`；Nodeset 缺省继承上级有效选择。该 Ruleset 使用整体范围，其中深度上限为 4、宽度警告阈值为 10。顶层 pipeline 为 0 层，循环迭代不增加层数；深度超限报错，宽度超限产生 `NODESET.SMELL.TOO_WIDE` 警告及 `CONCERNS` 状态。Ruleset 参数与局部覆盖可以调整这些值；显式空选择取消相应审查，原生解析与执行计划仍照常生成。

Python root 的 `runtime.nodeset_max_depth` 与 JavaScript root 的 `javascript.nodeset_max_depth` 提供内置规则的默认参数，取正整数。规则的显式参数及 overrides 优先。深度诊断包含实际深度和完整 `call_path`；循环体按静态调用结构计数，显式子选择划定新的负责范围。规则组合见[Ruleset 与局部覆盖](rules-and-nodes.md#ruleset-与局部覆盖)。

验证：

```bash
python run.py validate --config <root>/configs/main.jsonc
python run.py review --config <root>/configs/main.jsonc --output reports/workflow.svg
```

## Nodeset 的规则接管

图级 `rulesets` 写在 Nodeset 定义文件顶层，与 `pipeline` 并列。未填写则继承上级；显式列表替代继承规则、接管内部；`[]` 停止内部继承。上级仍可检查该 Nodeset 调用的外部连接，内部 Node 自己的局部规则继续执行。Node 调用上的 `rulesets` 是局部选择，不能代替 Nodeset 定义上的图级选择。完整写法见 [Nodeset 接管的配置位置](rules-and-nodes.md#nodeset-接管的配置位置)。

并发启动、任务引用、停止与实际收尾合同见[原生任务管理](task-management.md)。
