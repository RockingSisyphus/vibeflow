# VibeFlow 目标愿景

## 设计初衷

VibeFlow（包名 `vibeflow`）服务于人机协同开发，尤其是大量依赖 LLM 编写、修改和维护代码的项目。它的目标不是让程序更容易随意扩展，而是把架构纪律变成可执行的硬约束。

LLM 长期参与开发时最容易出现的问题：

- 功能越写越大，形成巨型函数或巨型模块。
- 出错后局部叠补丁，而不是定位根因。
- 多轮修改后出现隐式依赖、隐藏副作用和跨模块耦合。
- 代码还能跑，但整体结构已经不可审计。

VibeFlow 要把这些风险前移到配置、契约、编译、健康检查和运行时中处理。

## 核心目标

VibeFlow 是可迁移、可复用的严格标准流程图内核。业务开发者只写小型 node、纯 `base_lib` helper、必要插件和 JSONC 拓扑配置。

核心原则：

- node 必须足够小。
- node 默认必须是纯函数。
- node 之间不允许 Python 层面的导入、调用或隐式耦合。
- 程序控制流只能由 config 中显式 `pipeline.edges` 声明。
- `requires` / `provides` 是严格 key/type 数据契约，不是控制流推导来源。
- 每个 node 必须声明标准流程图 `flow_kind`。
- 可执行图必须有 `terminal` start/end。
- cycle 必须经过 `decision`。
- 健康检查必须能解释违反规则的原因和修复方向。

## 术语

- `node`：原子纯函数单元，只通过 `run_pure(inputs, params) -> outputs` 执行。
- `flow_kind`：标准流程图角色，决定 node 的架构语义和图形形状。
- `nodeset`：由多个 node 或其他 nodeset 组成的复合拓扑单元。
- `pipeline`：最终可运行拓扑，由 JSONC 配置声明 node、nodeset 和显式 flow edge。
- `key`：Context / run result 中的唯一数据地址，用于输出 mapping、trace 和 provenance。
- `type`：可重复的逻辑数据类型，下游按 `type` 消费，运行时通过 envelope 暴露实际来源 key。
- `base_lib`：受控纯函数基础库，可被 node 依赖，但必须接受健康检查。
- `policy`：治理规则集合，决定哪些限制硬失败、哪些限制可降级。
- `plugin`：扩展 policy、compile 或 runtime 的机制，不能隐式绕过绝对规则。

旧 `boundary` 公共模型已移除。外部输入、输出、数据存储请求、文档产物等必须通过标准 `flow_kind` 节点和显式契约表达。

## 标准 flow_kind

合法类型：

| flow_kind | 语义 |
| --- | --- |
| `terminal` | 开始 / 结束 |
| `process` | 普通处理 |
| `decision` | 判断 / 路由 |
| `io` | 输入 / 输出动作 |
| `predefined` | 预定义过程 / nodeset |
| `data_store` | 数据存储请求或引用 |
| `document` | 文档生成或文档结构 |
| `preparation` | 准备 / 初始化 |

`external_dependency` 不是流程图类型。第三方库或外部维护代码用 `NodeInfo.external=True` 标记；它不会改变图形形状、不会让 cycle 合法化，也不会自动成为 decision。

## Node 元数据目标

所有 node 必须声明：

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

`external=True` 只表示“该实现包装外部/第三方/非本项目维护代码”。内核仍验证：

- `NODE_INFO`
- `CONTRACT`
- `requires/provides`
- 配置拓扑位置
- decision route / `when` 规则
- runtime trace

但跳过源码质量、复杂度、导入链、维护性气味等对外部实现不合理的检查。

## 显式 Flow Edge

配置中的 `pipeline.edges` 是唯一控制流来源：

```jsonc
{
  "pipeline": {
    "inputs": [{"key": "value.in", "type": "value.in"}],
    "outputs": [{"type": "value.ready", "cardinality": "exactly_one"}],
    "nodes": [
      {"name": "start", "type": "demo.start"},
      {
        "name": "prepare",
        "type": "demo.prepare",
        "requires": [{"type": "value.in", "cardinality": "exactly_one"}],
        "provides": [{"key": "value.ready", "type": "value.ready"}]
      },
      {
        "name": "route",
        "type": "demo.route",
        "requires": [{"type": "value.ready", "cardinality": "exactly_one"}],
        "provides": [{"key": "flow.route", "type": "flow.route"}]
      },
      {"name": "end", "type": "demo.end", "requires": [{"type": "value.ready", "cardinality": "exactly_one"}]}
    ],
    "edges": [
      ["start", "prepare"],
      ["prepare", "route"],
      {"from": "route", "to": "end", "when": "flow.route == 'done'"}
    ],
    "max_steps": 1000
  }
}
```

规则：

- 可执行图必须至少有一个 `terminal` start 和一个 `terminal` end。
- 已实现节点不能孤立。
- 每个已实现节点必须从 start 可达。
- 每个已实现节点必须能到达 end。
- `decision` 的分支 edge 必须写 `when`。
- `decision` 输出 schema 中声明的 enum/boolean 分支必须被覆盖。
- 每个非回环 decision 分支必须能到达 end。
- 显式 cycle 必须包含 `decision`。
- 运行时用 `max_steps` 防止无限循环。

## 数据契约与 Runtime Inbox

数据契约必须使用结构化对象，不支持旧字符串简写：

```jsonc
"requires": [{"type": "value.in", "cardinality": "exactly_one"}],
"provides": [{"key": "value.ready", "type": "value.ready"}],
"inputs": [{"key": "value.in", "type": "value.in"}],
"outputs": [{"type": "value.ready", "cardinality": "exactly_one"}]
```

运行时不提供跨多跳全局黑板读取。入口输入只进入入口节点 inbox；node 输出会作为 envelope 沿实际激活的直接 outgoing edge 投递给下游。`exactly_one` / `optional_one` / `all` 由下游 require 的 `cardinality` 约束，最终 run result 只保留 `pipeline.outputs` 声明的 envelope 和 runtime 元数据。

## Planned Architecture

现有 `pipeline + nodesets` 就是架构契约。AI 可以先提交 planned 设计，再逐步实现：

```jsonc
{
  "nodesets": [
    {
      "name": "paperflow.catalog",
      "status": "planned",
      "flow_kind": "predefined"
    }
  ],
  "pipeline": {
    "nodes": [
      {"name": "start", "status": "planned", "flow_kind": "terminal"},
      {"name": "catalog", "type": "nodeset.paperflow.catalog", "status": "planned", "flow_kind": "predefined"}
    ],
    "edges": [["start", "catalog"]]
  }
}
```

规则：

- `status` 默认是 `implemented`。
- planned node 可声明 config `flow_kind`。
- implemented node 不允许在 config 中伪造 `flow_kind`。
- `planned_behavior` 默认是 `blocking`；也可写 `transparent` 让 planned 内容参与 flow 连通性检查。
- `python_stub` planned 内容只用于开发测试，必须写 `project/stubs/*.py` 下的 `run_stub(inputs, params)`，并通过显式运行开关才可执行。
- implemented nodeset 不能包含 blocking planned child；transparent/python_stub child 会保留 warning。
- health 对 planned 内容给 warning。
- runtime 默认拒绝运行 planned 内容；开启 planned stub 后也只允许 python_stub 运行。

## 副作用和外部系统

node 仍然不能直接做真实 IO。推荐表达方式：

- 外部输入：`io` 节点消费 `pipeline.inputs`。
- 外部输出：`io` 节点产生 `io.*` 输出，再由外层系统消费。
- 数据库存储请求：`data_store` 节点生成结构化请求或引用。
- 文档产物：`document` 节点生成文档结构或内容。
- 第三方库 wrapper：真实 `flow_kind` + `external=True`。

如果业务确实需要执行文件、网络、数据库、浏览器或外部进程，应在内核外部执行，再把结果作为 `pipeline.inputs` 或上游系统输入传入；内核负责纯函数拓扑和可审计契约。

## 插件目标

插件类型：

- `PolicyPlugin`
- `CompilerPlugin`
- `RuntimePlugin`

插件可以增加治理规则、收紧策略、追加健康检查或记录 runtime 事件，但不能成为绕过绝对规则的后门。

## 图形输出目标

内核应从同一份编译结果输出：

- `graph.mmd`：Mermaid flowchart 源码。
- `graph.txt`：无外部依赖的 ASCII flowchart。
- `graph.svg`：通过 Mermaid CLI 渲染的 SVG 图。

图中应显示：

- 标准 flow_kind 形状。
- planned / external 标记。
- decision `when` 条件。
- nodeset 折叠/展开。
- 契约 `key -> type`、cardinality、中文说明、健康警告/错误。

## 健康报告目标

健康报告必须稳定输出：

- `rule_id`
- `severity`
- `object_type`
- `object_id`
- `failure_layer`
- `message`
- `details`
- `suggested_fix_type`

主要 object type：`node`、`nodeset`、`pipeline`、`base_lib`、`plugin`、`policy`。

## 运行产物目标

正式运行目录：

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

trace 默认保存结构摘要，不保存原始输入输出。
