# 01. Node 开发规范

Node 是业务逻辑的最小执行单元。普通 node 必须是纯函数对象：相同输入和配置必须得到相同输出，不读写外部系统。真实副作用只能放在内核根据 `flow_kind` / `external` 派生的明确 `effect_scope` 中；任何 node 都不能直接调用其他 node。

## 最小合法 node

```python
from __future__ import annotations

from vibeflow.core import DataProvider, DataRequirement
from vibeflow.targets.python.project import NodeContract, NodeInfo
from base_lib.math_tools import add


def REQ(data_type: str, display_name: str, cardinality: str = "exactly_one") -> DataRequirement:
    return DataRequirement(type=data_type, cardinality=cardinality, display_name=display_name)


def PROV(key: str, display_name: str, data_type: str | None = None) -> DataProvider:
    return DataProvider(key=key, type=data_type or key, display_name=display_name)


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
        requires=(REQ("value.in", "Input value"),),
        provides=(PROV("value.out", "Output value"),),
        input_semantics={"value.in": ("input number",)},
        output_semantics={"value.out": ("output number",)},
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
| `global_state` | Target execution domain 内的易失 ambient state 或 runtime dispatch |

`flow_kind` 与 `external` 一起决定内核派生的 `effect_scope`：

| 实现分类 | effect_scope | 允许能力 |
| --- | --- | --- |
| 其他普通 implemented（即非 `io` / `document` / `data_store` / `global_state`，且 `external=False`） | `none` | 无业务 IO |
| `flow_kind=io` | `terminal` | stdin/stdout/stderr、`print`、`input`、`argparse` |
| `flow_kind=document` / `data_store` | `python_io` | 文件、环境、网络、数据库、subprocess、终端 |
| `flow_kind=global_state` 且 `external=False` | `global_state` | 易失 ambient state，以及运行时 callback/对象方法分派 |
| 任意 `flow_kind` + `external=True` | `trusted` | 最高优先级信任边界 |
| plugin | `trusted` | 信任边界 |
| planned `python_stub` | `none` | 无业务 IO |

`effect_scope` 不是可在 config 中自由声明的字段。图形 `flow_kind=terminal` 仍属于 `none`；它与仅由 `flow_kind=io` 获得的权限档位 `effect_scope=terminal` 不是一回事。

`run_pure(inputs, params)` 是稳定 node ABI 的方法名，不单独证明实现无副作用；真正的 IO 检查边界以派生 `effect_scope` 为准。

可选字段：

- `author`：作者或维护者，可省略。
- `tags`：字符串元组，例如 `("training", "metrics")`，可省略。
- `external`：默认 `False`。仅当 node 的包装实现源码不可取得、不可解析或不可审查时设为 `True`；调用 runtime callback 本身不要求 external。

`NodeInfo.type_key` 应和 registry 中注册的 key 保持一致。config 调用时实际查找的是 registry key；二者不一致会让人类和 AI 难以定位问题，也可能触发检查 warning。

## 外部依赖 node

如果 node 的包装实现本身由外部维护且源码不能取得、不能解析或不能进入审查，使用：

```python
NODE_INFO = NodeInfo(..., flow_kind="process", external=True)
```

`external=True` 是“包装实现源码本身不可取得或不可审查”的最高优先级信任边界，使有效 `effect_scope=trusted`。它会跳过普通 node 的源码质量、导入链和副作用限制，因此确实是显式 purity/IO 绕过；不要为了让内部代码通过检查而滥用。调用从 envelope 取得的 callback/model/optimizer 方法应由受审计 `global_state` wrapper 表达，不需要 external。`external=True` 不改变 `flow_kind` 形状，不代表 decision，也不会让 cycle 合法化；契约、拓扑、输出 key、`flow_kind` 和 trace 仍然被检查。

## global_state node

`global_state` 是 Core 的语言无关流程语义，不是名为 `vibeflow.global_state` 的系统 node。项目仍自行实现、注册普通 node：

```python
NODE_INFO = NodeInfo(
    ...,
    flow_kind="global_state",
    external=False,
)
```

Target 定义自己的 execution domain。Python Target 将其实现为当前解释器进程，并容纳进程内易失 ambient state以及从 envelope、registry、cache 或其他运行时对象取得的 callback/方法分派。典型调用包括 `callback(...)`、`model(...)` 和 `optimizer.step()`；这些对象仍经 `requires`/`provides` 输入输出。它不继承 `terminal` 或 `python_io`：文件、环境变量、网络、数据库、终端、subprocess、线程/进程创建、`eval` / `exec` / `compile`、动态 import、`ctypes` / `cffi`、动态库载入、任意直接 FFI 和可识别的系统级逃逸仍禁止。

项目源码、本地 helper 与可解析的静态 import chain 都会在执行前接受 AST preflight，加载后继续现有质量与副作用检查。静态导入第三方计算库或调用运行时 callback 本身不要求 `external=True`；只有 wrapper 实现源码不可取得、不可解析或不可审查时才使用 `external=True`。Core 和审计规则不按具体第三方库名称维护白名单。

Python Target 对源码中高置信度 runtime dispatch 做建议性识别。普通 `effect_scope=none` node 会得到 `NODE.EFFECT.RUNTIME_DISPATCH.UNDECLARED` warning，但 validate/run 继续；`global_state` 以及 `io` / `document` / `data_store` 不产生该 warning。固定 builtin、Python 隐式协议、只读 Mapping 的 `get/keys/values/items`、静态 import/构造、只传递未调用的 callable 及静态第三方/native API 内部不可见行为不应误报。`print`/`input`/`argparse` 与文件、Path、网络、数据库、subprocess 继续由原有 effect scope 判断；直接越权与系统逃逸仍是硬错误。

公开 `runtime_dispatch` 事实使用三态：`true` 表示检测到，`false` 表示已分析但未检测到，`null` 表示 planned/external、源码不可分析或 Target 没有 detector。Architecture/Mermaid/SVG 对应显示 `detected` / `none` / `unknown`。

普通 Python 对象仍作为 envelope value 按引用流转，并通过 `requires` / `provides` 暴露输入输出；`global_state` 不新增隐式黑板、对象通道或 Provider 权限。其 `CONTRACT.examples` 只检查结构，不执行。

global-state 修改默认持久且非事务。成功、失败或取消后，VibeFlow 都不 snapshot、rollback 或自动恢复。若修改只应临时生效，必须在同一个 node 内用 `try/finally` 保存并恢复原值；不能依赖可能未执行的后续 node。它不自动取得锁；无有效命名锁时照常运行并产生非阻断 warning。Architecture/Mermaid/SVG 将它固定显示为 `cloud`，并展示派生 effect scope、runtime dispatch 与有效 execution lock（无锁为 `none`），不展示 Provider 信息。

## 必填契约

`CONTRACT` 必须是 `NodeContract` 实例。

- `requires`：`DataRequirement(type, cardinality)`。node 按逻辑 `type` 消费输入。
- `provides`：`DataProvider(key, type)`。`key` 是唯一输出地址，`type` 是可重复的逻辑数据类型。
- 每个输入输出端口的 `display_name` 都必须是非空字符串。
- `input_semantics`：必须覆盖所有 `requires`。
- `output_semantics`：必须覆盖所有 `provides`。
- `examples`：可选的输入和参数文档示例；内核不会自动执行。

`run_pure` 使用的配置参数 schema/defaults 只在 Registry 注册项中维护，不属于 `NodeContract`。Python 运行时继续检查实现返回的 key 是否与 `provides` 一致，但不要求节点声明 JSON 输出结构，也不验证业务值域。

`requires` 不允许重复 type；`provides` 不允许重复 key。旧的字符串契约不再支持。

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

config 中从 decision 出发的 edge 必须写非空 `when`。VibeFlow 只检查分支语法、可达性和拓扑，不从节点输出值域推断或验证业务分支集合。

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
- `_thread` / `threading` / `concurrent.futures` / `multiprocessing`
- `ctypes` / `cffi` / 动态库载入或直接 FFI

`effect_scope=terminal` 只额外开放真实 stdin/stdout/stderr、`print`、`input` 和 `argparse`，不开放文件、环境、网络、数据库或 subprocess。`python_io` 可以使用这些 Python IO 能力。`global_state` 容纳当前进程的易失 ambient state 与 runtime dispatch，但不开放上述直接 IO、并发创建、动态代码、动态 import 或 FFI。`trusted` 跳过这组实现限制，由项目承担信任责任。

node 不能导入其他 node，不能直接调用其他 node，不能读取其他 node 的 `NODE_INFO` 或 `CONTRACT`。

## 配置参数

node 自身只声明 `CONTRACT.params_schema`，注册时必须提供真实可运行的配置 schema 和默认值。运行时传入 `run_pure` 的 `params` 是“注册默认值 + 调用处覆盖”的结果。

每个 node 调用点都有独立 `id`。同一个 Python node `NodeInfo.type_key` 可以通过多个调用点的 `type_used` 重复使用，每次都可以有不同 `config`。

## 常见健康报告和修法

- `NODE.TYPE.UNKNOWN`：config 中的 `type_used` 没有在 `python_project/registry.py` 注册，也没有匹配已导入 nodeset `type_key` 或系统类型；检查 registry key / nodeset `type_key` 是否拼错。
- `NODE.METADATA.*`：`NODE_INFO` 字段缺失、为空或 `flow_kind` 非法；补全 `NodeInfo`。
- `NODE.CONTRACT.*`：`CONTRACT` 缺字段、key 重复、语义或 schema 覆盖不完整；修 `NodeContract`。
- `NODE.PURITY.*`：node 有副作用、动态导入、跨 node 调用或源码形态不合规；拆到更小纯函数，必要时移到 `base_lib/`。
- `NODE.CONFIG.INVALID`：调用处 `config` 或注册默认值不符合注册 schema；修 registry 或 config。
