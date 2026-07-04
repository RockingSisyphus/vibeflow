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
- node 输出 key 必须是 `CONTRACT.provides` 中声明的 `DataProvider.key` 字符串字面量。
- `run_pure(inputs, params)` 收到的是 envelope，不是裸值。`exactly_one` 输入形如 `inputs["value.in"] == {"key": "...", "type": "value.in", "value": ..., "source_node": "..."}`，业务值在 `["value"]`。
- node 不修改 `inputs`；如果训练类场景确实需要共享对象原地更新，应让这个行为成为显式业务语义，并通过输出 key 暴露更新后的引用。
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

禁止把文件、网络、数据库、浏览器、环境变量或进程副作用放进 `base_lib`。

项目 config 顶层声明允许使用的 base_lib：

```jsonc
{
  "base_lib": {
    "paths": ["../base_lib"],
    "modules": [
      {"module": "base_lib.math_tools", "status": "implemented"},
      {"module": "base_lib.future_tools", "status": "planned", "description": "planned helper library"}
    ]
  }
}
```

只有 `implemented` base_lib 会进入 node import allowlist；`planned` base_lib 只用于规划和 Mermaid 展示。implemented base_lib 必须提供 `BASE_LIB_INFO`。

## Config / Pipeline

控制流只来自显式 `pipeline.edges`：

数据契约使用严格 key/type 结构，不支持旧字符串简写：

```jsonc
"inputs": [{"key": "value.in", "type": "value.in"}],
"outputs": [{"type": "value.out", "cardinality": "exactly_one"}],
"requires": [{"type": "value.in", "cardinality": "exactly_one"}],
"provides": [{"key": "value.out", "type": "value.out"}]
```

- `key` 是唯一数据地址，用于输出 mapping、trace 和 provenance。
- `type` 是逻辑数据类型，可以重复；下游按 `type` 消费。
- `cardinality` 必须显式写 `exactly_one`、`optional_one` 或 `all`。
- runtime 使用 node inbox / edge payload。node 只能收到直接 incoming edge 投递的数据；早期上游输出不会被跨多跳读取。
- `pipeline.outputs` 决定 run result 保留哪些 envelope；未声明的中间值不会出现在最终结果中。

```jsonc
{
  "global_config": {"config": {"tenant": "demo"}, "allow_config_override": false},
  "base_lib": {
    "paths": ["../base_lib"],
    "modules": ["base_lib.math_tools"]
  },
  "plugins": [
    {"module": "../plugins/policy.py", "class": "PolicyPlugin", "type": "policy", "config": {"level": "strict"}},
    {"name": "future_runtime_plugin", "type": "runtime", "status": "planned", "description": "planned runtime hook"}
  ],
  "pipeline": {
    "inputs": [{"key": "value.in", "type": "value.in"}],
    "outputs": [{"type": "value.out", "cardinality": "exactly_one"}],
    "nodes": [
      {"name": "start", "type": "demo.start"},
      {
        "name": "input",
        "type": "demo.input",
        "requires": [{"type": "value.in", "cardinality": "exactly_one"}],
        "provides": [{"key": "value.in.input", "type": "value.in"}]
      },
      {
        "name": "add",
        "type": "demo.add",
        "requires": [{"type": "value.in", "cardinality": "exactly_one"}],
        "provides": [{"key": "value.out", "type": "value.out"}]
      },
      {"name": "end", "type": "demo.end", "requires": [{"type": "value.out", "cardinality": "exactly_one"}]}
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

- `global_config` 会作为 `params["_global"]` 传给每个普通 node，不参与 node config schema 校验。
- `global_config` 中和 node config schema 同名的键还会覆盖 node 的实际 params；其他键只通过 `_global` 传递。
- 推荐写成 `{"config": {...}, "allow_config_override": false}`。无论 `allow_config_override` 是否为 `true`，同名键都会覆盖局部 config；当它为 `false` 且发生覆盖时，健康检查给 warning。
- `base_lib` 和 `plugins` 是资源声明，不进入主流程拓扑、execution plan 或 flow health 的孤儿/可达性检查。
- implemented plugin 必须提供 `PLUGIN_INFO`；planned plugin 不加载、不注册、不执行 hook。
- `plugins[].config` 和 `plugins[].settings` 都可传插件设置，值必须是对象；插件实例会收到 `plugin.config`，如果实现了 `configure(config)` 会在加载时被调用。
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
      {
        "name": "catalog",
        "type": "nodeset.paperflow.catalog",
        "requires": [{"type": "query.in", "cardinality": "exactly_one"}],
        "provides": [{"key": "catalog.out", "type": "catalog.out"}]
      }
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
- nodeset 可以声明自己的 `global_config`；外部 nodeset JSONC 文件的顶层 `global_config` 会作为该文件内 nodeset 的默认内部配置。
- 调用 nodeset 时可以在调用节点上写 `config`，这会覆盖 nodeset 内部 `global_config`，再覆盖内部 node 局部 config。
- 调用节点上的 `allow_config_override` 控制这些覆盖是否产生 warning：为 `false` 时仍覆盖，但同名覆盖会 warning。

## 运行时数据和性能选项

Runtime 审计流程，不默认审计数据内容：

- node 间可以按引用传递 tensor、model、optimizer、batch 等任意 Python 对象。
- 默认不要求输出值 JSON serializable，也不要求可 deepcopy。
- 默认 trace 只记录流程事件和 summary，不记录真实对象内容。
- 输出仍必须是 mapping，且 key 必须和调用点 `provides` 完全一致。
- `CONTRACT.examples` 只包含 `inputs` 和 `params`，用于证明最小输入/参数可运行并返回声明 key；不要在 examples 中写 `outputs`。

可选执行和 trace：

```python
from vibeflow import RuntimeOptions, run_checked

run_checked(..., runtime_options=RuntimeOptions(trace="boundary", node_hooks=False, execution="compiled"))
```

- `trace="full"`：默认逐 node/nodeset 事件。
- `trace="boundary"`：只保留 run/nodeset/failure 边界事件。
- `trace="off"`：只写 runtime summary。
- `execution="plan"`：默认执行计划模式。
- `execution="block"`：显式 opt-in 的保守 block 模式，仅支持线性链和简单条件 loop。
- `execution="compiled"`：显式 opt-in 的低开销线性 `CompiledBlock` 模式；遇到不满足条件的图会回退到 plan。

异步 side task 只通过 config 显式开启：

```jsonc
{
  "name": "metrics",
  "type": "demo.metrics",
  "async": "detached",
  "requires": [{"type": "batch", "cardinality": "exactly_one"}],
  "provides": [{"key": "metrics", "type": "metrics"}]
}
{
  "name": "load",
  "type": "demo.load",
  "async": "result_key",
  "result_key": "data.batch",
  "provides": [{"key": "data.batch", "type": "data.batch"}]
}
```

- `detached`：主流程不等待，run 结束时 flush；失败记录 trace warning，不自动中断主流程。
- `result_key`：下游直接 edge 上的节点按 `type` require 该异步结果时 join，结果写入 `result_key` 对应的 provider key。
- runtime 不自动 merge async context；共享对象线程安全由业务对象负责。

## Planned Architecture

AI 可以先提交 planned flowchart：

```jsonc
{"name": "classify", "status": "planned", "flow_kind": "decision"}
```

planned 内容只用于架构审查：

- health 给 warning。
- 默认 runtime 拒绝执行。
- Mermaid / ASCII / SVG 会显示 `planned blocking`、`planned transparent` 或 `planned python_stub` 标记。
- `blocking` 是默认行为，不参与主流程连通性检查。
- `transparent` 仍是 planned warning，但会参与 start/end、reachability、orphan 等 flow health，用于设计期把前后 implemented 节点连起来。
- `python_stub` 仍是 planned warning，并额外产生 `GRAPH.PLANNED.PYTHON_STUB_DEV_ONLY` warning；它参与 flow health，只能在开发测试时配合 `--allow-planned-stub` 执行。
- implemented nodeset 内含 blocking planned child 仍是 error；内含 transparent 或 python_stub planned child 会降为 warning。

`python_stub` 写法：

```jsonc
{
  "name": "runtime_control",
  "status": "planned",
  "flow_kind": "process",
  "requires": [{"type": "state.in", "cardinality": "exactly_one"}],
  "provides": [{"key": "state.out", "type": "state.out"}],
  "planned_behavior": {
    "kind": "python_stub",
    "stub_module": "project/stubs/runtime_control_stub.py"
  }
}
```

stub 模块必须位于主项目的 `project/stubs/` 下，入口固定为 `run_stub(inputs, params)`。内核会检查文件存在、签名、危险 import/call；运行时只传入该节点声明的 `requires` 输入和合并后的 params，返回 mapping 的 key 必须严格等于 `provides`。含 planned 或 python_stub 的配置始终不是 production ready。

## Plugin

plugin 可扩展治理规则，但不能绕过绝对规则。支持类型：

- `policy`
- `compiler`
- `runtime`

config 中只有显式写入 `plugins` 的插件会启用。implemented plugin 必须暴露 `PLUGIN_INFO`，planned plugin 可以只写 `name`、`type`、`status: "planned"` 和 `description`，用于 Mermaid/inspect 展示，不会加载或执行 hook。

插件配置示例：

```jsonc
{
  "plugins": [
    {"module": "../plugins/policy.py", "class": "PolicyPlugin", "type": "policy", "config": {"level": "strict"}},
    {"name": "future_runtime_plugin", "type": "runtime", "status": "planned", "description": "planned runtime hook"}
  ]
}
```

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
vibeflow export-svg --config workflow.jsonc --expand-nodesets --output graph.expanded.svg
```

正式运行也会写出 `graph.mmd`、`graph.txt`、快速图 `graph.svg` 和详细审查图 `graph.expanded.svg`。

`export-svg` 会向 Mermaid CLI 传入渲染配置。普通图默认 `maxTextSize=200000`、`maxEdges=2000`；展开 nodeset 时默认 `maxTextSize=500000`、`maxEdges=5000`。如仍遇到 Mermaid 限制，可用 `--mermaid-max-text-size` 和 `--mermaid-max-edges` 覆盖。
展开 nodeset 的 SVG 固定使用确定性 `review-columns` composer：最外层主流程在左侧纵向展示，plugins、base_lib 分列展示，展开的 nodeset 按顶层调用顺序放到右侧。nodeset 内部使用递归 detail-panel 布局：无直接子 nodeset 时横向展示；有直接子 nodeset 时父图保持 collapsed call-site 和原始连边，直接子 nodeset 作为右侧详情列按调用顺序纵向排列。审查图单个片段显示宽度默认上限为 `3200px`，可用 `--review-fragment-max-width` 覆盖。
展开 Mermaid 源码只用于调试源码，不是详细审查 SVG 的输入；不要把 expanded `.mmd` 直接交给 Mermaid CLI/mmdc 转成 SVG。
SVG 渲染不要求系统预装 Google Chrome；正常 `npm install` 后会优先使用 Puppeteer 自己安装/缓存的浏览器。如果该缓存不可用，再尝试非 snap 的系统 Chrome/Chromium。`/snap/bin/chromium` 会被跳过，因为它在 Puppeteer/mermaid-cli 下常见 profile lock 启动失败。
