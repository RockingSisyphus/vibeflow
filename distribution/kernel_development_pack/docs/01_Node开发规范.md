# 01. Node 开发规范

Node 是业务逻辑的最小执行单元。普通 node 必须是纯函数对象：相同输入和配置必须得到相同输出，不读写外部系统。真实副作用只能放在内核根据 `flow_kind` / `external` 派生的明确 `effect_scope` 中；任何 node 都不能直接调用其他 node。

## 最小合法 node

```python
from __future__ import annotations

from vibeflow import DataProvider, DataRequirement, NodeContract, NodeInfo
from base_lib.math_tools import add


def REQ(data_type: str, cardinality: str = "exactly_one") -> DataRequirement:
    return DataRequirement(type=data_type, cardinality=cardinality)


def PROV(key: str, data_type: str | None = None) -> DataProvider:
    return DataProvider(key=key, type=data_type or key)


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
        requires=(REQ("value.in"),),
        provides=(PROV("value.out"),),
        input_semantics={"value.in": ("input number",)},
        output_semantics={"value.out": ("output number",)},
        params_schema={"delta": {"type": "number"}},
        output_schema={"value.out": {"type": "number"}},
        examples=(
            {
                "inputs": {"value.in": {"key": "value.in", "type": "value.in", "value": 2, "source_node": "example"}},
                "params": {"delta": 3},
            },
        ),
    )

    def run_pure(self, inputs, params):
        return {"value.out": add(inputs["value.in"]["value"], params["delta"])}
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
| `io` | 交互式输入 / 输出，可使用真实标准流 |
| `predefined` | 预定义过程 / nodeset |
| `data_store` | 数据存储交互 |
| `document` | 文档、文件或外部资源交互 |
| `preparation` | 准备 / 初始化 |

`flow_kind` 与 `external` 一起决定内核派生的 `effect_scope`：

| 实现分类 | effect_scope | 允许能力 |
| --- | --- | --- |
| 其他普通 implemented（即非 `io` / `document` / `data_store`，且 `external=False`） | `none` | 无业务 IO |
| `flow_kind=io` | `terminal` | stdin/stdout/stderr、`print`、`input`、`argparse` |
| `flow_kind=document` / `data_store` | `python_io` | 文件、环境、网络、数据库、subprocess、终端 |
| 任意 `flow_kind` + `external=True` | `trusted` | 最高优先级信任边界 |
| plugin | `trusted` | 信任边界 |
| planned `python_stub` | `none` | 无业务 IO |

`effect_scope` 不是可在 config 中自由声明的字段。图形 `flow_kind=terminal` 仍属于 `none`；它与仅由 `flow_kind=io` 获得的权限档位 `effect_scope=terminal` 不是一回事。

`run_pure(inputs, params)` 是稳定 node ABI 的方法名，不单独证明实现无副作用；真正的 IO 检查边界以派生 `effect_scope` 为准。

`purity` 为了 ABI 兼容仍默认是 `"pure"`，不要改成其他值。它不会覆盖派生的 `effect_scope`，也不能用来申请副作用能力。

可选字段：

- `author`：作者或维护者，可省略。
- `tags`：字符串元组，例如 `("training", "metrics")`，可省略。
- `external`：默认 `False`。仅当 node 包装第三方库或外部维护代码时设为 `True`。

`NodeInfo.type_key` 应和 registry 中注册的 key 保持一致。config 调用时实际查找的是 registry key；二者不一致会让人类和 AI 难以定位问题，也可能触发检查 warning。

## 外部依赖 node

如果 node 包装第三方库或外部维护代码，使用：

```python
NODE_INFO = NodeInfo(..., flow_kind="process", external=True)
```

`external=True` 是“实现由第三方或外部维护”的最高优先级信任边界，使有效 `effect_scope=trusted`。它会跳过普通 node 的源码质量、导入链和副作用限制，因此确实是显式 purity/IO 绕过；不要为了让内部代码通过检查而滥用。它不改变流程图形状，不代表 decision，也不会让 cycle 合法化；契约、拓扑、输出 key、`flow_kind` 和 trace 仍然被检查。

## 必填契约

`CONTRACT` 必须是 `NodeContract` 实例。

- `requires`：`DataRequirement(type, cardinality)`。node 按逻辑 `type` 消费输入。
- `provides`：`DataProvider(key, type)`。`key` 是唯一输出地址，`type` 是可重复的逻辑数据类型。
- `input_semantics`：必须覆盖所有 `requires`。
- `output_semantics`：必须覆盖所有 `provides`。
- `params_schema`：必须声明 `run_pure` 读取的每个配置参数。
- `output_schema`：必须覆盖所有 `provides`。
- `examples`：建议提供输入和参数示例，方便人和 AI 理解。对 `effect_scope=none` 的普通 node，它还用于证明最小输入/参数可运行并返回声明 key；effectful/external examples 不执行。

`requires` 不允许重复 type；`provides` 不允许重复 key。旧的字符串契约不再支持。

`effect_scope=none` 的普通 node 会执行 examples 以验证最小样例。`terminal` / `python_io` 或 `external=True` node 的 examples 可能触发真实副作用，内核只检查其结构，不执行。

`examples` 只写：

```python
examples=({"inputs": {"value.in": {"key": "value.in", "type": "value.in", "value": 2, "source_node": "example"}}, "params": {"delta": 3}},)
```

不要在 `examples` 中写 `outputs`。运行结果由 `run_pure` 和 `provides` 校验，不通过示例输出声明。

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

Runtime 允许输出任意 Python 对象，并按引用传给下游；不要求输出 JSON serializable，也不要求可 deepcopy。输出仍必须是 mapping，且 key 必须和 `provides` 完全一致。`CONTRACT.examples` 只包含 `inputs` 和 `params`；对 `none` 范围普通 node，它用于证明最小输入/参数可运行并返回声明 key，effectful/external node 则只检查结构。不要在 examples 中写 `outputs`。

`terminal` start/end node 也使用同一接口。start node 通常 `requires=()`、`provides=()` 并返回 `{}`；end node 通常只声明 `requires`，返回 `{}`。

## 导入和副作用限制

`effect_scope=none` 的普通 node 和 planned `python_stub` 禁止常见副作用和外部耦合能力，包括但不限于：

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

`effect_scope=terminal` 只额外开放真实 stdin/stdout/stderr、`print`、`input` 和 `argparse`，不开放文件、环境、网络、数据库或 subprocess。`python_io` 可以使用这些 Python IO 能力。`trusted` 跳过这组实现限制，由项目承担信任责任。

node 不能导入其他 node，不能直接调用其他 node，不能读取其他 node 的 `NODE_INFO` 或 `CONTRACT`。

## 配置参数

node 自身只声明 `CONTRACT.params_schema`，注册时必须提供真实可运行的配置 schema 和默认值。运行时传入 `run_pure` 的 `params` 是“注册默认值 + 调用处覆盖”的结果。

每个 node 调用点都有独立 `id`。同一个 Python node `NodeInfo.type_key` 可以通过多个调用点的 `type_used` 重复使用，每次都可以有不同 `config`。

## 常见健康报告和修法

- `NODE.TYPE.UNKNOWN`：config 中的 `type_used` 没有在 `project/registry.py` 注册，也没有匹配已导入 nodeset `type_key` 或系统类型；检查 registry key / nodeset `type_key` 是否拼错。
- `NODE.METADATA.*`：`NODE_INFO` 字段缺失、为空或 `flow_kind` 非法；补全 `NodeInfo`。
- `NODE.CONTRACT.*`：`CONTRACT` 缺字段、key 重复、语义或 schema 覆盖不完整；修 `NodeContract`。
- `NODE.PURITY.*`：node 有副作用、动态导入、跨 node 调用或源码形态不合规；拆到更小纯函数，必要时移到 `base_lib/`。
- `NODE.CONFIG.INVALID`：调用处 `config` 或注册默认值不符合注册 schema；修 registry 或 config。
