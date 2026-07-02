# 01. Node 开发规范

Node 是业务逻辑的最小执行单元。它必须是纯函数对象：相同输入和配置必须得到相同输出，不允许读写文件、访问网络、访问数据库、读取环境变量、启动进程、持有外部资源、调用其他 node。

## 最小合法 node

```python
from __future__ import annotations

from vibeflow import NodeContract, NodeInfo
from base_lib.math_tools import add


class AddNode:
    NODE_INFO = NodeInfo(
        type_key="demo.add",
        display_name="Add",
        category="math",
        description="Add a configured delta to value.in.",
        version="0.1.0",
        flow_kind="process",
    )
    CONTRACT = NodeContract(
        requires=("value.in",),
        provides=("value.out",),
        input_semantics={"value.in": ("input number",)},
        output_semantics={"value.out": ("output number",)},
        params_schema={"delta": {"type": "number"}},
        output_schema={"value.out": {"type": "number"}},
        examples=(
            {
                "inputs": {"value.in": 2},
                "params": {"delta": 3},
                "outputs": {"value.out": 5},
            },
        ),
    )

    def run_pure(self, inputs, params):
        return {"value.out": add(inputs["value.in"], params["delta"])}
```

## 必填元数据

`NODE_INFO` 必须是 `NodeInfo` 实例，并且这些字段必须是非空：

- `type_key`
- `display_name`
- `category`
- `description`
- `version`
- `flow_kind`

`flow_kind` 合法值：

| flow_kind | 用途 |
| --- | --- |
| `terminal` | 开始 / 结束 |
| `process` | 普通处理 |
| `decision` | 判断 / 路由 |
| `io` | 输入 / 输出动作 |
| `predefined` | 预定义过程 / nodeset |
| `data_store` | 数据存储请求或引用 |
| `document` | 文档生成或文档结构 |
| `preparation` | 准备 / 初始化 |

`purity` 默认是 `"pure"`，不要改成其他值。

## 外部依赖 node

如果 node 包装第三方库或外部维护代码，使用：

```python
NODE_INFO = NodeInfo(..., flow_kind="process", external=True)
```

`external=True` 不改变流程图形状，不代表 decision，也不会让 cycle 合法化。它只跳过源码质量、复杂度、导入链等内部实现检查。契约、拓扑、输出 key、运行 trace 仍然被检查。

## 必填契约

`CONTRACT` 必须是 `NodeContract` 实例。

- `requires`：node 读取的输入 key。
- `provides`：node 输出的 key。
- `input_semantics`：必须覆盖所有 `requires`。
- `output_semantics`：必须覆盖所有 `provides`。
- `params_schema`：必须声明 `run_pure` 读取的每个配置参数。
- `output_schema`：必须覆盖所有 `provides`。
- `examples`：建议提供输入、参数、输出示例，方便人和 AI 理解。

`requires` 和 `provides` 不允许重复，不允许交叉。

## decision node

`flow_kind="decision"` 的 node 必须提供 route-like output，例如：

- `flow.route`
- `route`
- `decision`
- `branch`
- `selected_branch`

建议在 `output_schema` 中用 enum 或 boolean 明确分支：

```python
output_schema={"flow.route": {"type": "string", "enum": ["again", "done"]}}
```

config 中从 decision 出发的 edge 必须写 `when`。

## run_pure 规则

`run_pure` 必须精确使用这个签名：

```python
def run_pure(self, inputs, params):
    ...
```

禁止：

- `async def run_pure(...)`
- generator
- `*args` / `**kwargs`
- 多余参数或缺少参数
- 普通 `run(...)`
- public helper 方法
- 直接修改 `inputs`
- 返回动态 output key
- 少返回或多返回 key

Runtime 允许输出任意 Python 对象，并按引用传给下游；不要求输出 JSON serializable，也不要求可 deepcopy。输出仍必须是 mapping，且 key 必须和 `provides` 完全一致。`CONTRACT.examples` 只包含 `inputs` 和 `params`，用于证明最小输入/参数可运行并返回声明 key；不要在 examples 中写 `outputs`。

## 导入和副作用限制

node 中禁止常见副作用和外部耦合能力，包括但不限于：

- `open`
- `os.getenv` / `os.environ` / `os.system`
- `pathlib.Path.read_text` / `write_text`
- `subprocess`
- `socket`
- `requests` / `httpx` / `urllib.request`
- `sqlite3` / `sqlalchemy`
- `playwright` / `selenium`
- `eval` / `exec` / `compile` / `__import__`
- `importlib.import_module`

node 不能导入其他 node，不能直接调用其他 node，不能读取其他 node 的 `NODE_INFO` 或 `CONTRACT`。

## 配置参数

node 自身只声明 `CONTRACT.params_schema`，注册时必须提供真实可运行的配置 schema 和默认值。运行时传入 `run_pure` 的 `params` 是“注册默认值 + 调用处覆盖”的结果。

每个 node 调用点都有独立 `name`，也就是独立 node_id。同一个 node_type 可以被多次调用，每次都可以有不同 `config`。
