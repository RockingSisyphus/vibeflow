# VibeFlow 严格标准流程图设计

## 目标

VibeFlow（包名 `vibeflow`）是面向人机协同开发的严格流程图运行内核。它要求业务程序由小型纯函数 node 和显式 JSONC flow edge 组成，并在运行前通过 schema、编译、健康检查和策略系统验证。

核心目标：

- VibeFlow 与业务彻底解耦。
- node 默认必须是纯函数。
- node 必须完整声明元数据、契约、输入、输出和标准 `flow_kind`。
- node 之间禁止互相导入、依赖或直接调用。
- 控制流只由配置中的显式 `pipeline.edges` 表达。
- 复杂功能通过 nodeset 组合，而不是写巨型 node。
- 插件可以扩展 policy / compiler / runtime，但不能绕过绝对规则。
- VibeFlow 能生成 Mermaid、ASCII 和 SVG 流程图，供人审查整体结构。

## 核心概念

- `node`：原子纯函数单元，只暴露 `run_pure(inputs, params) -> outputs`。
- `flow_kind`：node 的标准流程图角色。
- `nodeset`：复合拓扑单元，可被当作 `nodeset.<name>` 调用。
- `pipeline`：可运行图，由显式 edge 连接 node 和 nodeset。
- `base_lib`：受控纯函数 helper。
- `policy`：治理规则集合。
- `plugin`：policy/compiler/runtime 扩展点。

旧 `boundary` 公共模型、`pipeline.loops`、edge `max_executions` 已移除。

## Node 接口

```python
class PureNode(Protocol):
    NODE_INFO: NodeInfo
    CONTRACT: NodeContract

    def run_pure(self, inputs: Mapping[str, object], params: Mapping[str, object]) -> Mapping[str, object]:
        ...
```

`NodeInfo` 必须包含：

```python
NodeInfo(
    type_key="demo.add",
    display_name="Add",
    category="demo",
    description="Add a configured delta.",
    version="0.1.0",
    flow_kind="process",
    external=False,
)
```

`flow_kind` 合法值：

- `terminal`
- `process`
- `decision`
- `io`
- `predefined`
- `data_store`
- `document`
- `preparation`

`external=True` 代表该 node 包装第三方或外部维护代码。它不改变流程图语义，只跳过源码质量/复杂度/导入链扫描；契约、拓扑、route、runtime trace 仍然被检查。

## 纯函数限制

node 禁止：

- 直接读写 `Context`。
- 直接读写文件、网络、数据库、浏览器、环境变量。
- 启动进程或动态执行代码。
- 调用其他 node。
- 导入其他 node 的 Python 模块。
- 动态生成 output key。
- 修改 `inputs` 或从 `inputs` 中取出的可变对象。

真实外部能力应放在内核外部系统中执行，并通过 `io` / `data_store` / `document` 节点的结构化契约衔接。

## Config 与 Pipeline

标准结构：

```jsonc
{
  "pipeline": {
    "inputs": ["value.in"],
    "max_steps": 1000,
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
    ]
  }
}
```

规则：

- `pipeline.edges` 是唯一控制流来源。
- `requires/provides` 不推导控制流。
- 每个已实现图必须有 `terminal` start/end。
- 每个已实现 node 必须从 start 可达并能到达 end。
- 已实现 node 不能孤立。
- `max_steps` 是 runtime 安全护栏。

## Decision 与 Cycle

`decision` node 必须提供 route-like output，例如：

- `flow.route`
- `route`
- `decision`
- `branch`
- `selected_branch`

分支 edge 必须写 `when`：

```jsonc
{"from": "route", "to": "retry", "when": "flow.route == 'again'"}
```

当前支持的小表达式：

- `key == 'literal'`
- `key != 'literal'`
- `key == true`
- `key == false`

Cycle 规则：

- 显式 flow cycle 必须包含 `decision`。
- `external=True` 不会让 cycle 合法化。
- decision 非回环出口必须能到达 terminal end。
- decision schema enum / boolean 分支值必须被 edge 条件覆盖。

## Nodeset

nodeset 是可复用复合拓扑。它本身必须表现为纯函数：

- 有 metadata 和契约。
- 内部 pipeline 也必须有 terminal start/end 和显式 edges。
- 内部中间 key 默认不能泄漏。
- 只通过 `exports` 暴露输出。
- 禁止递归引用。
- 调用处的 `requires/provides` 必须和 nodeset 契约一致。

调用：

```jsonc
{"name": "flow", "type": "nodeset.demo.add_one", "requires": ["value.in"], "provides": ["value.out"]}
```

## Planned / Implemented

`pipeline + nodesets` 也是架构契约。AI 可以先写 planned flowchart，再逐步实现：

```jsonc
{"name": "classify", "status": "planned", "flow_kind": "decision"}
```

规则：

- `status` 默认 `implemented`。
- planned node 可以没有真实 `type`，但必须有 config `flow_kind`。
- implemented node 的 `flow_kind` 只能来自 registry 中的 `NODE_INFO`。
- implemented nodeset 不能包含 planned 子节点。
- health 对 planned 内容给 warning。
- runtime 拒绝运行 planned 内容。

## Plugin

插件类型：

- `policy`
- `compiler`
- `runtime`

插件异常默认 fail-closed。插件可收紧策略或追加健康检查；放宽可降级规则时必须声明 relaxation、scope、reason 和来源。

## 图形输出

同一份拓扑可输出：

- Mermaid：`export-mermaid` / `graph.mmd`
- ASCII：`export-ascii` / `graph.txt`
- SVG：`export-svg` / `graph.svg`

图形应显示：

- 标准流程图形状。
- `when` 条件。
- nodeset 折叠/展开。
- planned / external 标记。
- 中文说明、契约 key 和健康 finding。

## 正式运行

`run_checked(...)` 是正式入口：

1. 加载 JSONC。
2. 加载插件。
3. 合并 policy。
4. 执行 schema 检查。
5. 编译图。
6. 执行完整健康检查。
7. 健康失败则拒绝运行。
8. 运行 step runtime。
9. 写出报告、trace 和图形产物。

运行产物：

```text
runs/<run_id>/
  input_summary.json
  effective_policy.json
  compiled_graph.json
  health_report.json
  graph.mmd
  graph.txt
  graph.svg
  graph.svg.error.txt
  runtime_trace.jsonl
  output_summary.json
```

## CLI

```text
vibeflow validate --config workflow.jsonc
vibeflow inspect-node --type demo.add --module nodes.py --class AddNode
vibeflow inspect-config --config workflow.jsonc
vibeflow run --config workflow.jsonc
vibeflow export-mermaid --config workflow.jsonc --output graph.mmd
vibeflow export-ascii --config workflow.jsonc --output graph.txt
vibeflow export-svg --config workflow.jsonc --output graph.svg
vibeflow quality-check --path .
```

## 绝对规则摘要

1. node 必须是纯函数，除 `external=True` 只跳过源码质量扫描外，不允许破坏契约。
2. node 不允许调用或导入其他 node。
3. 控制流必须显式写在 config edge 中。
4. 可执行图必须有 terminal start/end。
5. cycle 必须包含 decision。
6. implemented node 的 `flow_kind` 只能来自 `NODE_INFO`。
7. planned 内容不能运行。
8. 旧 `boundary` / `pipeline.loops` / `max_executions` 配置必须失败。
