# 05. BaseLib 与外部依赖规范

## base_lib

`base_lib/` 放纯函数 helper。它可以被 node 导入，用来减少 node 内部重复逻辑。

合法示例：

```python
from vibeflow.targets.python.project import BaseLibInfo

BASE_LIB_INFO = BaseLibInfo(
    module="base_lib.math_tools",
    display_name="Math Tools",
    category="math",
    description="Pure arithmetic helpers.",
    version="0.1.0",
)

def add(left: float, right: float) -> float:
    return left + right
```

base_lib 应保持：

- 无文件、网络、数据库、进程等副作用。
- 无可变全局状态。
- 不导入 node、plugin、runtime。
- 不导入 `nodes`、`task_nodes`、`plugins` 或业务 registry。
- 依赖链不要过长。
- 函数短小、分支少、嵌套浅。

`NODE_INFO`、`CONTRACT`、`BASE_LIB_INFO` 和 `PLUGIN_INFO` 可以调用项目本地的声明 helper。例如可以在 `base_lib.node_contracts` 中定义 `REQ(...)` / `PROV(...)`，再由 node 模块导入并构造 `DataRequirement` / `DataProvider`。Python Target 会先读取完整本地 import graph，只有当 helper 本身以及它继续调用的本地函数都能被证明为有限、无副作用的声明构造时才允许导入执行；规则根据源码和调用链判断，不根据 `REQ` 等函数名开白名单。

声明 helper 不得包含文件、环境、网络、subprocess、线程/进程、动态代码、动态 import、FFI、模块全局修改或无法解析的 callback，也不得用顶层循环或递归参与导入期构造。普通、可解析且没有 metaclass / `__init_subclass__` hook 的本地 mixin 继承可以使用；无法审计的外部基类仍须进入明确的 `external=True` 信任边界。

每个 root 的 `python_project/registry.py` 可以用 `build_base_lib_registry()` 声明该 root 下可用的 base_lib：

```python
from vibeflow.targets.python.project import BaseLibRegistry

def build_base_lib_registry() -> BaseLibRegistry:
    registry = BaseLibRegistry()
    registry.register(
        "math_tools",
        module="base_lib.math_tools",
        display_name="Math Tools",
        category="math",
        description="Pure arithmetic helpers.",
        version="0.1.0",
    )
    return registry
```

workflow config 再声明本流程实际使用的 base_lib id：

```jsonc
{
  "base_lib": {
    "modules": [{"id": "math_tools"}]
  }
}
```

registry 中的 `module` 相对所属 root 解析。只有当前 workflow config 引用的 base_lib 会进入 node import allowlist；即使某个 helper 已注册为可用，当前 config 未引用时，implemented node 导入它仍会被健康检查拒绝。

implemented base_lib 必须暴露 `BASE_LIB_INFO`，用于实现自检和 inspect 信息。审查图里的资源名称、类别、版本和说明来自 `build_base_lib_registry().register(...)`。planned base_lib 不进入 resource registry；需要计划占位时，用 planned node 或 planned nodeset 表达。

## base_lib 适合放什么

适合：

- 纯计算函数。
- 数据结构转换函数。
- 无副作用的验证、归一化、打分、格式化函数。
- 多个 node 共享的领域公式或小算法。

不适合：

- 读取配置、环境变量或文件。
- 创建网络、数据库、浏览器、模型加载等资源。
- 存放 node class、plugin class 或 registry 逻辑。
- 用全局变量缓存可变业务状态。

如果 helper 依赖链过深，健康检查会报告 dependency chain warning/error。修法是把 helper 合并到更小的局部函数，或拆成更清晰的业务 node/nodeset。

## 外部输入输出

旧 `boundary` 模型已移除。当前推荐用标准 flowchart node 表达外部交互边界：

- `io`：交互式终端边界，可使用真实 stdin/stdout/stderr、`print`、`input` 和 `argparse`。
- `data_store`：存储语义，可执行文件、环境、网络、数据库、subprocess 和终端 IO。
- `document`：文档/文件语义，可执行同一组 Python IO。
- `global_state`：语言无关的运行域边界；Python Target 中容纳当前解释器进程的 RNG、默认选项、backend flag、全局 cache/registry 等 ambient state，以及从 envelope/registry/cache 取得的 runtime callback/对象方法分派。
- 任意真实 `flow_kind` + `external=True`：包装实现源码本身不可取得、不可解析或不可审查，使用最高优先级的 trusted 边界。

内核从实现分类派生固定 `effect_scope`：

| 分类 | effect_scope |
| --- | --- |
| 其他普通 implemented node（即非 `io` / `document` / `data_store` / `global_state`，且 `external=False`） | `none` |
| `flow_kind=io` | `terminal` |
| `flow_kind=document` / `data_store` | `python_io` |
| `flow_kind=global_state` 且 `external=False` | `global_state` |
| 任意 `external=True` node | `trusted`（最高优先级） |
| plugin | `trusted` |
| planned `python_stub` | `none` |

`effect_scope` 不是 config 可调的权限字段。图形 `flow_kind=terminal` 仍是 `none`，不等于权限档位 `terminal`。`global_state` 不继承 `terminal` 或 `python_io`，仍禁止文件、环境变量、网络、数据库、终端、subprocess、线程/进程创建、动态代码、动态 import、直接 FFI 和可识别的系统级逃逸。选择 `flow_kind` 必须先符合业务语义，不得仅为获得更宽能力而伪造语义。

这些 node 仍然是内核拓扑的一部分，必须声明 `CONTRACT`、`requires/provides` 和 examples，并遵守契约、拓扑、输出 key 和 trace 检查。`terminal` / `python_io` / `global_state` 或 `external=True` node 的 examples 可能触发真实副作用，内核只验证结构，不执行。

## io node

`io` 不是 start/end。推荐：

```text
terminal start -> io input -> process... -> io output -> terminal end
```

`io` node 的 `effect_scope=terminal`。它可以直接使用真实 stdin/stdout/stderr、`print`、`input` 和 `argparse`，适合 CLI 让渡模式 / `delegate-cli` 中的参数解析、交互提示和业务输出。它不获得文件、环境、网络、数据库或 subprocess 能力；这些工作应按真实语义交给 `document` / `data_store` 或受信任外部实现。

## data_store node

`data_store` node 用于执行或编排数据存储语义：

```python
from vibeflow.core import DataProvider, DataRequirement

NODE_INFO = NodeInfo(..., flow_kind="data_store")
CONTRACT = NodeContract(
    requires=(DataRequirement("value.final", "exactly_one", "Final value"),),
    provides=(DataProvider("effects.request", "effects.request", "Storage request"),),
    input_semantics={"value.final": ("final numeric value",)},
    output_semantics={"effects.request": ("structured storage request",)},
)
```

其 `effect_scope=python_io`，可以读写文件、环境、网络、数据库、subprocess 和终端。契约应输出可审计的结果/回执或引用，不要把与存储无关的业务逻辑塞进来。

## document node

`document` node 用于生成、读取或写入文档/文件产物：

```python
NODE_INFO = NodeInfo(..., flow_kind="document")
```

其 `effect_scope=python_io`，可以使用文件、环境、网络、数据库、subprocess 和终端。它可输出 `document.report` 这类文档内容、路径、句柄或写入回执；仍应把与文档无关的语义判断留在正确的 process/decision node。

## external=True

如果 node 的包装实现源码本身由外部维护且不可取得、不可解析或不可审查：

```python
NODE_INFO = NodeInfo(
    ...,
    flow_kind="process",
    external=True,
)
```

`external=True` 表示包装实现源码本身无法进入项目审查，并以最高优先级把有效 `effect_scope` 设为 `trusted`。它会跳过普通 node 的源码质量、导入链和副作用限制，因此确实是显式 IO/purity 绕过，由项目承担信任责任。它不会跳过契约、`flow_kind`、拓扑、输出或 trace 检查，也不改变 `flow_kind` 形状；审查图会叠加 `[EXTERNAL]` 标题和 `7px` non-scaling 粗边框。如果这个外部 node 负责分支路由，必须同时声明 `flow_kind="decision"` 并满足 decision 规则。

静态导入第三方计算库，或在受审计 `global_state` wrapper 中调用 envelope 提供的 callback/model/optimizer，本身都不要求 `external=True`。Python Target 只对源码可见、高置信度的 runtime dispatch 给出建议性事实，不推断静态第三方/native API 内部行为。只有 wrapper 实现源码本身不可取得、不可解析或不可审查时才使用 `external=True` / `trusted`。VibeFlow 不维护任何具体工具或厂商 API 白名单。

## 真实副作用应该放在哪里

推荐模式：

1. 交互式 CLI 的参数解析、提示和输出放在 `flow_kind=io` node；CLI 让渡模式 / `delegate-cli` 传入 `cli.argv`，业务代码直接使用真实标准流。
2. 文件/文档操作放在 `document`，存储/数据系统操作放在 `data_store`；二者均由 `python_io` 档位审计。
3. `process` / `decision` / 图形 `terminal` 等普通 node 保持 `none`，只做纯计算、路由和生命周期表达。
4. 进程内易失 ambient state 或源码可见 runtime dispatch 使用 `global_state`；普通 model/optimizer 等对象仍经 envelope / contract 按引用流转。
5. wrapper 实现源码本身不可取得或不可审查时才使用 `external=True`；plugin 同样属于 `trusted`。对这两类实现做项目级审计。
6. 所有真实副作用仍通过显式 node/plugin、契约和图上路径呈现；不要藏在 `base_lib`、普通 node 或未声明资源中。
