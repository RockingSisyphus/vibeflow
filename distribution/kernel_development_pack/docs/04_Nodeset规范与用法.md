# 04. Nodeset 规范与用法

nodeset 是由多个 node 组成的可复用模块。它本身可以像 node 一样被 pipeline 调用，但内部仍由纯 node 和显式 flow edge 构成。

## 最小 nodeset

```jsonc
{
  "nodesets": [
    {
      "name": "demo.add_one",
      "display_name": "Add One",
      "category": "math",
      "description": "Add one to value.in.",
      "version": "0.1.0",
      "purity": "pure",
      "requires": ["value.in"],
      "provides": ["value.out"],
      "exports": ["value.out"],
      "pipeline": {
        "inputs": ["value.in"],
        "nodes": [
          {"name": "start", "type": "demo.start"},
          {"name": "input", "type": "demo.input", "requires": ["value.in"]},
          {"name": "add", "type": "demo.add", "requires": ["value.in"], "provides": ["value.out"], "config": {"delta": 1}},
          {"name": "end", "type": "demo.end", "requires": ["value.out"]}
        ],
        "edges": [["start", "input"], ["input", "add"], ["add", "end"]]
      }
    }
  ]
}
```

调用 nodeset：

```jsonc
{
  "name": "flow_add_one",
  "type": "nodeset.demo.add_one",
  "requires": ["value.in"],
  "provides": ["value.out"]
}
```

## nodeset 配置覆盖内部 node

调用 nodeset 时，可以给内部 node 覆盖配置：

```jsonc
{
  "name": "flow_add_five",
  "type": "nodeset.demo.add_one",
  "requires": ["value.in"],
  "provides": ["value.out"],
  "node_configs": {
    "add": {"delta": 5}
  }
}
```

这里 `add` 是 nodeset 内部 node 的 `name`。

## 嵌套 nodeset 的配置覆盖

如果 nodeset 内部还调用了另一个 nodeset，要用 dotted path 指向更深层 node：

```jsonc
{
  "name": "flow_nested",
  "type": "nodeset.demo.add_two",
  "requires": ["value.in"],
  "provides": ["value.out"],
  "node_configs": {
    "first.add": {"delta": 3},
    "second.add": {"delta": 4}
  }
}
```

## planned nodeset

可以先登记尚未实现的 nodeset：

```jsonc
{
  "name": "demo.future_module",
  "status": "planned",
  "flow_kind": "predefined"
}
```

planned nodeset 可用于架构审查和图形导出，但不能运行。implemented nodeset 不能包含 planned 子节点。

## 关键限制

- nodeset 不能递归调用自己。
- nodeset 内部 pipeline 必须有 terminal start/end。
- nodeset 内部控制流必须显式写 `edges`。
- nodeset 输出必须来自 `exports`。
- 内部 key 不应泄漏到外层。
- nodeset 的 `requires` / `provides` 必须和调用处保持一致。
- 调用处的 `node_configs` 只能覆盖存在的内部 node。

nodeset 适合表达大模块，不适合绕过 node 纯度限制。外部输入输出应通过 `io`、`data_store`、`document` 或 `external=True` node 明确建模。
