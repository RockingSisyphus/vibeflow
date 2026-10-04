# Nodeset 与 Loop

Nodeset 把多个调用组合成一个可复用流程块。Loop 重复执行一个 Nodeset body。

## 独立 Nodeset

```jsonc
{
  "type_key": "example.prepare_text",
  "display_name": "Prepare text",
  "description": "Normalizes and validates supplied text.",
  "requires": [
    {"type": "text.raw", "cardinality": "exactly_one", "display_name": "Raw text"}
  ],
  "provides": [
    {"key": "prepared_text", "type": "text.prepared", "display_name": "Prepared text"}
  ],
  "pipeline": {
    "inputs": [
      {"key": "raw_text", "type": "text.raw", "display_name": "Raw text"}
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

在 workflow 中选择提供 `example.*` Node 的代码插件，再导入并调用 Nodeset：

```jsonc
{
  "plugins": [{"source": {"kind": "file", "ref": "plugins/text.py"}}],
  "nodeset_imports": [{"path": "nodesets/prepare_text.jsonc"}],
  "pipeline": {
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

workflow 与 Nodeset 默认选择 `vibeflow.workflow` Ruleset，其中深度上限为 4、宽度警告阈值为 10。顶层 pipeline 为 0 层，循环迭代不增加层数；深度超限报错，宽度超限产生 `NODESET.SMELL.TOO_WIDE` 警告及 `CONCERNS` 状态。Ruleset 参数与局部覆盖可以调整这些值；显式空选择取消相应审查，原生解析与执行计划仍照常生成。

Python root 的 `runtime.nodeset_max_depth` 与 JavaScript root 的 `javascript.nodeset_max_depth` 提供内置规则的默认参数，取正整数。规则的显式参数及 overrides 优先。深度诊断包含实际深度、调用链 `chain` 和逐步调用 `calls`；planned 定义和 loop body 按同一套依赖遍历计数。规则组合见[Ruleset 与局部覆盖](rules-and-nodes.md#ruleset-与局部覆盖)。

验证：

```bash
python run.py validate --config <root>/configs/main.jsonc
python run.py review --config <root>/configs/main.jsonc --output reports/workflow.svg
```
