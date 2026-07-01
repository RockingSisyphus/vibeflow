# VibeFlow 使用者开发引导

本文面向使用 VibeFlow（包名 `vibeflow`）编写业务 node、nodeset、plugin、base_lib 和 JSONC config 的开发者。

## Node

node 只实现：

```python
def run_pure(self, inputs, params):
    ...
```

必须声明：

- `NODE_INFO: NodeInfo`
- `CONTRACT: NodeContract`

`NodeInfo.flow_kind` 必填，合法值：

- `terminal`
- `process`
- `decision`
- `io`
- `predefined`
- `data_store`
- `document`
- `preparation`

示例：

```python
NODE_INFO = NodeInfo(
    type_key="demo.add",
    display_name="Add",
    category="demo",
    description="Add a configured delta.",
    version="0.1.0",
    flow_kind="process",
)
```

规则：

- node 不读写文件、网络、数据库、浏览器、环境变量。
- node 不启动进程，不动态 import，不使用 `eval/exec`。
- node 不导入其他 node，不调用其他 node。
- node 输出 key 必须是 `CONTRACT.provides` 中声明的字符串字面量。
- node 不修改 `inputs` 或其中的可变对象。
- 简单 wrapper node 可以只取输入、调用纯 helper/base_lib 函数、返回固定输出；VibeFlow 会识别这种标准形态，避免误报 duplicate logic。

## 外部依赖 Node

如果 node 只是包装第三方库或外部维护代码，设置：

```python
NodeInfo(..., flow_kind="process", external=True)
```

`external=True` 只跳过内部源码质量检查，例如复杂度、导入链、源码规模。它不会跳过：

- 元数据检查。
- 契约检查。
- `flow_kind` 检查。
- config / topology 检查。
- decision `when` 检查。
- runtime trace 和输出 key 检查。

如果外部依赖承担路由逻辑，仍应声明 `flow_kind="decision"`，并提供 route-like output。

## Base Lib

`base_lib/` 只放纯函数 helper，可被 node 导入。

允许示例：

```python
def add(left: float, right: float) -> float:
    return left + right
```

禁止把文件、网络、数据库、浏览器、环境变量或进程副作用放进 `base_lib`。

项目可在 policy 中声明更细的 import 规则：

```jsonc
{
  "policy": {
    "imports": {
      "allowed_modules": ["urllib.parse"],
      "banned_modules": ["urllib.request"]
    }
  }
}
```

## Config / Pipeline

控制流只来自显式 `pipeline.edges`：

```jsonc
{
  "pipeline": {
    "inputs": ["value.in"],
    "nodes": [
      {"name": "start", "type": "demo.start"},
      {"name": "input", "type": "demo.input", "requires": ["value.in"]},
      {"name": "add", "type": "demo.add", "requires": ["value.in"], "provides": ["value.out"]},
      {"name": "end", "type": "demo.end", "requires": ["value.out"]}
    ],
    "edges": [
      ["start", "input"],
      ["input", "add"],
      ["add", "end"]
    ],
    "max_steps": 1000
  }
}
```

注意：

- `requires/provides` 不会自动生成控制流。
- 每个可执行 pipeline 和 nodeset 内部 pipeline 都要有 `terminal` start/end。
- 每个已实现 node 都必须从 start 可达，并能到达 end。
- 旧 `pipeline.loops`、`max_iterations`、edge `max_executions` 已移除。

## Decision / Cycle

`decision` node 用于分支和回环：

```jsonc
{"from": "route", "to": "again", "when": "flow.route == 'again'"}
```

规则：

- decision 必须提供 route-like output，例如 `flow.route`。
- decision 的 outgoing edge 必须写 `when`。
- schema enum / boolean 中声明的分支值必须被覆盖。
- 非回环分支必须能到达 terminal end。
- cycle 必须包含 decision。
- `max_steps` 只是运行时护栏，不是架构语义。

## Nodeset

复杂功能优先拆成多个 node，再用 nodeset 组合。大型项目应把可复用 nodeset 放到独立 JSONC 文件，并在 runnable config 中导入：

```jsonc
{
  "nodeset_imports": [
    {"path": "nodesets.jsonc", "names": ["paperflow.catalog"]}
  ],
  "pipeline": {
    "nodes": [
      {"name": "catalog", "type": "nodeset.paperflow.catalog", "requires": ["query.in"], "provides": ["catalog.out"]}
    ],
    "edges": [["start", "catalog"], ["catalog", "end"]]
  }
}
```

规则：

- `path` 相对当前 config 文件。
- `names` 可省略，表示导入文件中的全部 nodeset。
- 导入的 nodeset 和当前文件内联 nodeset 不允许重名。
- `nodeset_imports` 只导入 nodeset，不导入 pipeline、policy 或 plugins。
- nodeset 内部 pipeline 也必须显式写 edges。

## Planned Architecture

AI 可以先提交 planned flowchart：

```jsonc
{"name": "classify", "status": "planned", "flow_kind": "decision"}
```

planned 内容只用于架构审查：

- health 给 warning。
- runtime 拒绝执行。
- Mermaid / ASCII / SVG 会显示 planned 标记。
- implemented nodeset 不能包含 planned child。

## Plugin

plugin 可扩展治理规则，但不能绕过绝对规则。支持类型：

- `policy`
- `compiler`
- `runtime`

若 plugin 放宽可降级规则，必须声明作用域、原因和来源。项目级语义规则适合通过 policy plugin 增加。

## Registry

推荐按 namespace 分组注册：

```python
def _register_fulltext_nodes(registry):
    registry.register("fulltext.plan_provider_routes", PlanProviderRoutesNode, config_schema={}, config_defaults={})
```

如果 `_register_fulltext_nodes()` 注册了 `literature.*`，内核会给 `REGISTRY.SMELL.NAMESPACE_MISMATCH` warning。迁移期可以保留 warning，但长期应把注册移动到对应分组函数，或用项目 plugin 明确例外。

## 图形输出

推荐每次设计或修改后生成图：

```powershell
vibeflow export-mermaid --config workflow.jsonc --output graph.mmd
vibeflow export-ascii --config workflow.jsonc --output graph.txt
vibeflow export-svg --config workflow.jsonc --output graph.svg
```

正式运行也会写出 `graph.mmd`、`graph.txt`、`graph.svg`。
