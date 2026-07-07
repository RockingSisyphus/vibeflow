# 05. BaseLib 与外部依赖规范

## base_lib

`base_lib/` 放纯函数 helper。它可以被 node 导入，用来减少 node 内部重复逻辑。

合法示例：

```python
from vibeflow import BaseLibInfo

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

workspace 模式下，每个 root 的 `vibeflow_project.jsonc` 必须声明允许使用的 base_lib 路径和模块：

```jsonc
{
  "base_lib": {
    "paths": ["../base_lib"],
    "modules": [
      {
        "module": "base_lib.math_tools",
        "status": "implemented",
        "display_name": "Math Tools",
        "category": "math",
        "description": "Pure arithmetic helpers.",
        "version": "0.1.0"
      },
      {
        "module": "base_lib.future_tools",
        "status": "planned",
        "display_name": "Future Tools",
        "category": "math",
        "description": "planned helper library",
        "version": "0.1.0"
      }
    ]
  }
}
```

workspace 模式下 `paths` 相对所属 root 目录解析；无 workspace 的旧模式下才相对 pipeline config 文件目录解析。只有 `modules` 里声明为 `implemented` 的模块会进入 node import allowlist。声明为 `planned` 的 base_lib 只用于规划和 Mermaid 展示，不会加载，也不能满足 implemented node 的 import 校验。

implemented base_lib 必须暴露 `BASE_LIB_INFO`，用于 inspect 和 Mermaid 展示模块名称、类别、版本和功能说明。config 声明本身也必须写 `display_name` 和 `description`，说明本项目为什么启用这个 helper；缺失会产生 `CONFIG.SMELL.MISSING_BASE_LIB_DISPLAY_NAME` 或 `CONFIG.SMELL.MISSING_BASE_LIB_DESCRIPTION` warning。planned base_lib 可以不存在，但也必须至少有 `module` 或 `name`，并写清 `display_name`、`description`。

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
from vibeflow import DataProvider, DataRequirement

NODE_INFO = NodeInfo(..., flow_kind="data_store")
CONTRACT = NodeContract(
    requires=(DataRequirement("value.final", "exactly_one"),),
    provides=(DataProvider("effects.request", "effects.request"),),
    input_semantics={"value.final": ("final numeric value",)},
    output_semantics={"effects.request": ("structured storage request",)},
    output_schema={"effects.request": {"type": "object"}},
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

## 真实副作用应该放在哪里

内核内的 node/base_lib 默认不直接做真实 IO。推荐模式：

1. 内核外部系统准备输入对象，作为 `run.py run --input input.json` 或自定义启动器的 `initial` 传入。
2. `io` node 把输入对象转成流程内 key。
3. `process` / `decision` / `nodeset` 做纯计算和路由。
4. `data_store` 或 `document` node 生成结构化请求或文档对象。
5. 外部系统消费运行输出，真正写文件、数据库、网络或 UI。

这样做的目的是让 VibeFlow 审计“流程和契约”，而不是把外部系统副作用藏进某个 node。
