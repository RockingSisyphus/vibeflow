# 05. BaseLib 与外部依赖规范

## base_lib

`base_lib/` 放纯函数 helper。它可以被 node 导入，用来减少 node 内部重复逻辑。

合法示例：

```python
def add(left: float, right: float) -> float:
    return left + right
```

base_lib 应保持：

- 无文件、网络、数据库、进程等副作用。
- 无可变全局状态。
- 不导入 node、runtime。
- 依赖链不要过长。
- 函数短小、分支少、嵌套浅。

项目 policy 中可声明允许的 base_lib 路径和模块：

```jsonc
{
  "policy": {
    "base_lib": {
      "allowed_paths": ["../base_lib"],
      "allowed_modules": ["base_lib"]
    }
  }
}
```

## 外部输入输出

旧 `boundary` 模型已移除。当前推荐用标准 flowchart node 表达外部交互边界：

- `io`：输入/输出动作。
- `data_store`：数据存储请求、数据库引用、缓存请求。
- `document`：文档结构或文档内容。
- `process` + `external=True`：包装第三方库或外部维护代码。

这些 node 仍然是内核拓扑的一部分，必须声明 `CONTRACT`、`requires/provides` 和示例。

## io node

`io` 不是 start/end。推荐：

```text
terminal start -> io input -> process... -> io output -> terminal end
```

`io` node 应只做输入/输出数据整理，不应直接读写文件或网络。真实外部系统可以在内核外部准备 `pipeline.inputs`，或消费运行输出。

## data_store node

`data_store` node 用于生成结构化存储请求或引用：

```python
NODE_INFO = NodeInfo(..., flow_kind="data_store")
CONTRACT = NodeContract(
    requires=("value.final",),
    provides=("effects.request",),
    output_semantics={"effects.request": ("structured storage request",)},
)
```

它不应直接写数据库或文件。

## document node

`document` node 用于生成文档结构、报告文本或文档写入请求：

```python
NODE_INFO = NodeInfo(..., flow_kind="document")
```

它可以输出 `document.report` 这类 key，再由下游 `io` node 或外部系统消费。

## external=True

如果 node 包装第三方库或外部维护代码：

```python
NODE_INFO = NodeInfo(
    ...,
    flow_kind="process",
    external=True,
)
```

`external=True` 只跳过源码质量检查；不会跳过契约、拓扑、输出、运行时 trace 检查。如果这个外部 node 负责分支路由，必须同时声明 `flow_kind="decision"` 并满足 decision 规则。
