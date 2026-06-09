# 03. Config 与 Pipeline 规范

配置文件使用 `.jsonc`，支持 `//` 行注释和 `/* ... */` 块注释。不支持 trailing comma。

## 标准结构

```jsonc
{
  "pipeline": {
    "inputs": [],
    "nodes": [],
    "edges": [],
    "loops": []
  },
  "nodesets": [],
  "boundary": null,
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
  "name": "seed",
  "type": "demo.seed",
  "provides": ["value.in"],
  "config": {"value": 2}
}
```

字段说明：

- `name`：本次调用的 node_id，在当前 pipeline 内必须唯一。
- `type`：注册表中的 node_type。
- `requires`：本次调用需要从上下文读取的 key。
- `provides`：本次调用写入上下文的 key。
- `config`：本次调用覆盖注册默认值的配置。
- `node_configs`：调用 nodeset 时，用来覆盖内部 node 配置。

内核会根据 `requires` / `provides` 自动推导数据依赖边，也允许显式写 `edges`。

## edge

二元数组形式：

```jsonc
["seed", "add"]
```

对象形式：

```jsonc
{"from": "seed", "to": "add", "max_executions": 1}
```

`max_executions` 必须是大于等于 1 的整数。

## loop

所有环路都必须显式声明，并必须有执行上限。

```jsonc
{
  "name": "count_loop",
  "nodes": ["inc", "done", "copy_back"],
  "edges": [
    ["copy_back", "inc"]
  ],
  "max_iterations": 5,
  "until": "loop.done"
}
```

字段说明：

- `name`：loop 名称。
- `nodes`：loop 内节点，建议显式写出。
- `edges`：形成环路的边。
- `max_iterations`：最大迭代次数。
- `until`：可选，某个上下文 key 为真时停止。

未声明的 cycle 会被拒绝。

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
    },
    "maintainability": {
      "warn_call_chain_length": 4,
      "max_call_chain_length": 4
    }
  }
}
```

通常不要放宽硬规则。确实需要临时放宽时，应写明 reason 和 expires。

