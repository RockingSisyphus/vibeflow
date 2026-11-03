# NodesetType、Nodeset 与 Loop

NodesetType 定义可复用子图，Nodeset 是对它的一次调用。Loop 重复执行所引用的 NodesetType body。

## 独立 NodesetType

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
      {"id": "start", "definition_id": "example.start", "display_name": "Start preparation", "description": "Starts text preparation."},
      {"id": "normalize", "definition_id": "example.normalize_text", "display_name": "Normalize text", "description": "Normalizes the supplied text."},
      {"id": "end", "definition_id": "example.end", "display_name": "End preparation", "description": "Ends after prepared text is available."}
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
  "nodeset_imports": [{"path": "nodeset_types/prepare_text.jsonc"}],
  "pipeline": {
    "inputs": [
      {"key": "raw_text", "type": "text.raw", "display_name": "Raw text", "required": true}
    ],
    "nodes": [
      {
        "id": "prepare",
        "definition_id": "example.prepare_text",
        "display_name": "Prepare request text",
        "description": "Runs reusable text preparation for this request."
      }
    ]
  }
}
```

调用从 NodesetType 定义继承契约。`config` 覆盖 NodesetType 的 `global_config`；`node_configs` 使用调用点 ID 组成的 dotted path 覆盖内部 Node：

```jsonc
"node_configs": {"normalize": {"collapse_newlines": false}}
```

## Planned Nodeset

planned Nodeset 保留 `type_key`、名称、说明和契约，可以暂时省略 `pipeline`，也可以带 planned body 进入静态审查。implemented Nodeset 必须有完整 pipeline。

## While Loop

`vibeflow.loop.while` 指向一个 Nodeset body，并在调用处显式声明循环契约：

```jsonc
{
  "id": "retry",
  "definition_id": "vibeflow.loop.while",
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

### 持续运行

`max_iterations` 省略时默认 **1000**；显式设为 `null` 才不限制迭代次数。没有 `stop_after` 和 `stop_when` 时，Loop 持续执行 body，直到取消或失败；静态审查会提示永久循环，但不会禁止运行。

```jsonc
"loop": {"body": "example.handle_message", "max_iterations": null}
```

消息服务的 body 可以是“等待消息 → 处理 → 回复”。等待节点采用原生异步等待，workflow 使用 `entry_mode: "async"`；整个循环属于同一次 workflow 实例。需要业务正常结束时增加 `stop_when`，也可以由应用取消运行或由另一 workflow 显式 Kill。停止操作须等待当前执行和清理完成。持续运行时按业务需要保存结果；`collect` 会逐次累积数据，适用于确实需要保留全部迭代结果的场景。

## 验证

```bash
python run.py validate --config <root>/configs/main.jsonc
python run.py review --config <root>/configs/main.jsonc
```

## 子图规则

NodesetType 的图级 `rulesets` 与 `pipeline` 并列；调用点上的 `rulesets` 控制调用局部规则。内置 `vibeflow.workflow` 按整体范围检查子图：默认深度上限 4，宽度警告阈值 10；顶层为 0 层，循环迭代不增加层数。深度超限报错，宽度超限产生 `NODESET.SMELL.TOO_WIDE` 与 `CONCERNS`。

通过 Ruleset 的 `overrides` 覆盖 `base/nodeset_types` 的 `nodeset_max_depth` 正整数参数。诊断提供实际深度与 `call_path`。完整选择和覆盖格式见[Rule 与 Node](rules-and-nodes.md)。

展示选项与调用展开方式见[本地预览](local-preview.md)。
