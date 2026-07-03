# 04. Nodeset 规范与用法

nodeset 是由多个 node 组成的可复用模块。它本身可以像 node 一样被 pipeline 调用，但内部仍由纯 node 和显式 flow edge 构成。

注意：当前内核要求 `requires`、`provides`、`exports`、`pipeline.inputs`、`pipeline.outputs` 都使用严格对象契约。旧写法 `["value.in"]` 不再支持。require 写 `{"type": "value.in", "cardinality": "exactly_one"}`，provider/export 写 `{"key": "value.out", "type": "value.out"}`。

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
      "requires": [{"type": "value.in", "cardinality": "exactly_one"}],
      "provides": [{"key": "value.out", "type": "value.out"}],
      "exports": [{"key": "value.out", "type": "value.out"}],
      "pipeline": {
        "inputs": [{"key": "value.in", "type": "value.in"}],
        "outputs": [{"type": "value.out", "cardinality": "exactly_one"}],
        "nodes": [
          {"name": "start", "type": "demo.start"},
          {
            "name": "input",
            "type": "demo.input",
            "requires": [{"type": "value.in", "cardinality": "exactly_one"}],
            "provides": [{"key": "value.in.input", "type": "value.in"}]
          },
          {
            "name": "add",
            "type": "demo.add",
            "requires": [{"type": "value.in", "cardinality": "exactly_one"}],
            "provides": [{"key": "value.out", "type": "value.out"}],
            "config": {"delta": 1}
          },
          {"name": "end", "type": "demo.end", "requires": [{"type": "value.out", "cardinality": "exactly_one"}]}
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
  "requires": [{"type": "value.in", "cardinality": "exactly_one"}],
  "provides": [{"key": "value.out", "type": "value.out"}]
}
```

## nodeset 配置覆盖内部 node

调用 nodeset 时，可以给内部 node 覆盖配置：

```jsonc
{
  "name": "flow_add_five",
  "type": "nodeset.demo.add_one",
  "requires": [{"type": "value.in", "cardinality": "exactly_one"}],
  "provides": [{"key": "value.out", "type": "value.out"}],
  "node_configs": {
    "add": {"delta": 5}
  }
}
```

这里 `add` 是 nodeset 内部 node 的 `name`。

## nodeset 全局配置

nodeset 可以声明内部 `global_config`，调用 nodeset 时也可以在调用节点上写 `config`：

```jsonc
{
  "name": "demo.add_one",
  "global_config": {"config": {"delta": 1}, "allow_config_override": false},
  "pipeline": {
    "nodes": [
      {"name": "add", "type": "demo.add", "config": {"delta": 2}}
    ]
  }
}
```

调用处：

```jsonc
{
  "name": "flow_add_five",
  "type": "nodeset.demo.add_one",
  "config": {"delta": 5},
  "allow_config_override": false
}
```

合并顺序是：调用处 `config` 覆盖 nodeset 内部 `global_config`，得到的配置再覆盖内部 node 的局部 `config`。无论 `allow_config_override` 是否为 `true`，实际覆盖都会发生；当它为 `false` 且出现同名覆盖时，健康检查给 warning。`node_configs` 仍然是精确指向内部 node 的覆盖机制，优先级高于全局配置。

## 嵌套 nodeset 的配置覆盖

如果 nodeset 内部还调用了另一个 nodeset，要用 dotted path 指向更深层 node：

```jsonc
{
  "name": "flow_nested",
  "type": "nodeset.demo.add_two",
  "requires": [{"type": "value.in", "cardinality": "exactly_one"}],
  "provides": [{"key": "value.out", "type": "value.out"}],
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

planned nodeset 可用于架构审查和图形导出，但默认不能运行。implemented nodeset 内含 `blocking` planned 子节点仍是 error；内含 `transparent` 或 `python_stub` planned 子节点会保留 warning，用于设计期连通或开发期 stub 测试。

planned nodeset 可以暂时不写 `pipeline`、`requires`、`provides`、`exports` 和元数据；implemented nodeset 必须补齐这些字段。

## nodeset_imports

大型项目建议把可复用 nodeset 拆到独立文件，再在 runnable config 中导入：

```jsonc
{
  "nodeset_imports": [
    "nodesets/math.jsonc",
    {"path": "nodesets/reporting.jsonc", "names": ["report.summary"]}
  ],
  "pipeline": {
    "nodes": [
      {
        "name": "summary",
        "type": "nodeset.report.summary",
        "requires": [{"type": "value.out", "cardinality": "exactly_one"}],
        "provides": [{"key": "document.summary", "type": "document.summary"}]
      }
    ],
    "edges": [["start", "summary"], ["summary", "end"]]
  }
}
```

规则：

- `path` 相对当前 config 文件解析。
- `names` 省略时导入目标文件里的全部 nodeset。
- 导入只带入 `nodesets`，不会导入目标文件的 `pipeline`、`plugins` 或 `policy`。
- 如果目标 nodeset 文件顶层写了 `global_config`，它会作为该文件内 nodeset 的默认内部配置。
- 导入链不能循环。
- 导入后和本文件内联 nodeset 不能重名。

## 关键限制

- nodeset 不能递归调用自己。
- nodeset 内部 pipeline 必须有 terminal start/end。
- nodeset 内部控制流必须显式写 `edges`。
- nodeset 输出必须来自 `exports`。
- 内部 key 不应泄漏到外层。
- nodeset 的 `requires` / `provides` 必须和调用处保持一致。
- 调用处的 `node_configs` 只能覆盖存在的内部 node。
- implemented nodeset 的 `display_name`、`category`、`description`、`version`、`purity` 必须是非空字符串，`purity` 只能是 `"pure"`。
- `exports` 必须是 `provides` 的子集，且必须由内部 node 生产。
- `provides` 不能暴露 `exports` 之外的内部中间 key。
- nodeset 内部需要从外层读取的 key 必须声明在 nodeset `requires` 中。
- 内部 node 数量超过 10 会给 `NODESET.SMELL.TOO_WIDE` warning，建议拆分。

nodeset 适合表达大模块，不适合绕过 node 纯度限制。外部输入输出应通过 `io`、`data_store`、`document` 或 `external=True` node 明确建模。

## 常见 nodeset 错误

- `NODESET.RECURSION`：nodeset 直接或间接调用自己。
- `NODESET.EXPORTS.MISSING`：`exports` 中的 key 没有内部 provider。
- `NODESET.INTERNAL_KEY_LEAK`：内部中间 key 暴露到了外层 `provides`。
- `NODESET.CONFIG.UNKNOWN_NODE`：`node_configs` 覆盖路径指向不存在的内部 node。
- `NODESET.CONFIG.NESTED_PATH_REQUIRED`：覆盖嵌套 nodeset 时没有使用 dotted path。
- `NODESET.CONFIG.INVALID_PATH`：dotted path 穿过了普通 node，而不是 nodeset 调用。
