# VibeFlow 当前实现状态

## 当前定位

VibeFlow（包名 `vibeflow`）当前已经从“纯函数 node + 拓扑配置原型”演进为严格标准流程图内核。它面向人机协同开发，尤其是 LLM 参与长期编码和维护的场景，用机器可检查的规则限制程序结构漂移。

当前核心语义：

- 程序架构由 JSONC `pipeline` / `nodesets` 显式声明。
- `pipeline.edges` 是唯一控制流来源。
- `requires` / `provides` 是数据契约，不会被推导成控制流。
- node 必须声明标准 `flow_kind`。
- 可执行图必须有 `terminal` start/end。
- cycle 必须经过 `decision`。
- 运行时使用 `max_steps` 防止无限执行。
- 旧 `boundary`、`pipeline.loops`、edge `max_executions` 已移除，并会被配置校验拒绝。

## 已完成能力

### 包结构

核心包位于：

```text
src/vibeflow/
```

主要模块包括：

- `node.py`：`NodeInfo`、`NodeContract`、`PureNode` 和标准 `flow_kind` 常量。
- `graph_config.py`：JSONC 拓扑解析，包含 `status: planned|implemented`、`max_steps`、显式 edge `when`。
- `compiler.py`：编译显式 flow edge、数据契约诊断、cycle/decision 检查。
- `execution_plan.py`：预绑定 node 实例、参数、edge、nodeset 子计划和异步标记的执行计划。
- `runtime.py`：按显式 flow edge 调度的 runtime，支持 plan/block 执行、trace policy、对象按引用传递和显式异步 side task。
- `runtime_trace.py`、`runtime_validation.py`：运行 trace 摘要和可选输出 snapshot 校验。
- `health.py`、`health_flow.py`、`health_planned.py`：健康检查入口、flow 结构检查、planned 内容检查。
- `purity.py`、`purity_validators.py`、`purity_visitors.py`：node 纯函数、契约、源码质量检查。
- `mermaid.py`：Mermaid flowchart 源码导出。
- `ascii_flowchart.py` 及相关拆分模块：ASCII flowchart 导出。
- `mermaid_render.py`：通过项目本地 Mermaid CLI 渲染 SVG。
- `plugin.py`：policy/compiler/runtime 插件。
- `runner.py`：强制健康检查后的正式运行入口。
- `cli.py`：命令行入口。

稳定 re-export：

- `core/`
- `plugins/`
- `devtools/`
- `resources/schema/`

### 标准流程图 Node

`NodeInfo` 当前形态：

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

`flow_kind` 必填，合法值：

- `terminal`
- `process`
- `decision`
- `io`
- `predefined`
- `data_store`
- `document`
- `preparation`

`external=True` 表示该 node 包装第三方库或外部维护代码。它仍然要通过元数据、契约、拓扑、运行时 trace 检查，但跳过内部源码质量、复杂度、导入链等“我们不维护的代码”检查。

### 显式 Flow Edge

已实现：

- `pipeline.nodes`
- `pipeline.edges`
- `pipeline.inputs`
- `pipeline.max_steps`
- edge `when`，支持小型表达式，例如 `flow.route == 'again'`、`flag == true`。
- `requires/provides` 只生成 data diagnostics，不进入 `effective_edges`。
- 每个可执行图必须有 terminal start/end。
- 每个已实现节点必须从 start 可达且能到达 end。
- 每个 cycle 必须包含 `decision`。
- decision 分支值会和 output schema enum / boolean 做静态检查。
- decision 非回环出口必须能到达 terminal end。

旧配置会被拒绝：

- `boundary`
- `pipeline.loops`
- edge `max_executions`
- edge `loop`
- `max_iterations`

### Planned Architecture

现有 `pipeline + nodesets` 同时承担架构契约职责，不再另加 `architecture_flow`。

支持：

- `status: "planned" | "implemented"`，默认 `implemented`。
- planned node 可以没有真实 `type`，但必须声明 `flow_kind`。
- implemented node 不允许在 config 中伪造 `flow_kind`，真实类型来自 registry 中 `NODE_INFO.flow_kind`。
- health 对 planned 内容给 warning。
- runtime 拒绝执行 planned 内容。
- Mermaid / ASCII / SVG 都能显示 planned 节点。

### Nodeset

已实现：

- `nodesets`
- `nodeset_imports`
- `nodeset.<name>` 可作为 node 调用。
- nodeset 内部 pipeline 同样必须有 terminal start/end 和显式 edges。
- nodeset 通过 `exports` 暴露输出。
- 递归引用、契约不匹配、内部 key 泄漏会被检查。
- planned nodeset 可作为设计占位，但不能运行。

### 纯函数和源码质量检查

已实现：

- `NODE_INFO` 必填。
- `CONTRACT` 必填。
- `run_pure(inputs, params) -> outputs` 必填。
- 禁止普通 `run(context, ...)`。
- 静态检查禁止直接修改 `inputs`；runtime 为训练对象按引用传递，不再用 deepcopy 做内容级变异审计。
- 禁止动态输出 key。
- 禁止多返回/少返回 key。
- 禁止 node 之间 import/call。
- 默认禁止文件、网络、数据库、进程、环境变量等副作用能力。
- 行数、字节数、函数数量、分支数量、嵌套深度、调用链长度检查。
- duplicate AST fingerprint warning。
- `base_lib` 纯函数扫描和依赖链检查。
- `external=True` 跳过源码质量扫描，但不跳过契约/拓扑/运行时检查。

### 插件系统

已实现插件类型：

- `PolicyPlugin`
- `CompilerPlugin`
- `RuntimePlugin`

插件可扩展或收紧治理规则，但不能隐式绕过绝对规则。插件异常采用 fail-closed 语义；观测类 runtime 插件异常会进入健康报告。

`BoundaryPlugin` 已移除。

### 正式运行和产物

`run_checked(...)` 会在运行前强制执行 schema、policy、compile 和 health 检查。失败时拒绝执行 runtime。

Runtime 当前已实现训练性能导向能力：

- `Context` 按引用保存任意 Python 对象，node 间不要求 JSON serializable 或可 deepcopy。
- runtime 默认只检查输出是否为 mapping、输出 key 是否与 `provides` 一致；数据内容不做默认 snapshot 审计。
- `RuntimeOptions(trace="full"|"boundary"|"off", snapshot_outputs=False, node_hooks=True, execution="plan"|"block")` 控制 trace 粒度、可选 JSON snapshot 校验、node hook 和执行模式。
- 默认 `execution="plan"` 使用 `ExecutionPlan` / `NodeFrame` 预绑定 node、参数、edge、nodeset 子计划和 runtime plugin 列表。
- `execution="block"` 是显式 opt-in 的保守 block runner，支持线性链和条件 edge 覆盖的简单 decision loop，不做 Python 代码生成、自动并行或 context 自动 merge。
- node 调用可声明 `async: "detached"` 或 `async: "result_key"`；`detached` 在主流程外运行并在 run 结束 flush，失败记录 warning 事件；`result_key` 把 future 结果写入一个显式 key，下游 `requires` 该 key 时 join。

运行目录当前主要产物：

```text
runs/<run_id>/
  input_summary.json
  effective_policy.json
  compiled_graph.json
  health_report.json
  graph.mmd
  graph.txt
  graph.svg
  graph.svg.error.txt        # 仅 SVG 渲染失败时出现
  runtime_trace.jsonl
  output_summary.json
```

### 图形导出

已实现：

- `export_mermaid(...)` / CLI `export-mermaid`：输出 Mermaid flowchart 源码。
- `export_ascii_flowchart(...)` / CLI `export-ascii`：输出无外部依赖的 ASCII flowchart。
- `render_mermaid_svg(...)` / CLI `export-svg`：通过项目本地 Mermaid CLI 渲染 SVG。
- nodeset 折叠/展开视图。
- flow_kind 标准形状。
- `when` 条件边。
- planned/external/health finding 标记。
- registry 元数据、中文描述、契约 key 可进入图中标签。

### CLI

已实现：

```text
vibeflow validate --config ...
vibeflow validate --config ... --json
vibeflow inspect-node --type ... --module ...
vibeflow inspect-config --config ...
vibeflow run --config ...
vibeflow export-mermaid --config ... --output graph.mmd
vibeflow export-ascii --config ... --output graph.txt
vibeflow export-svg --config ... --output graph.svg
vibeflow quality-check --path ...
vibeflow quality-check --path ... --json
```

### 通用质量自检

`vibeflow quality-check --path ...` 可检查普通 Python 项目，也用于内核自检。

当前内核默认自检已达到：

```text
PASS, errors=0, warnings=0
```

### 示例和沙箱

已维护：

- `examples/minimal_project/`：最小可运行项目。
- `examples/integration_sandbox/`：综合沙箱，覆盖 flow_kind、decision cycle、nodeset、plugins、planned 内容、训练对象直通、RuntimeOptions、ExecutionPlan、block 执行、async side task、ASCII/Mermaid/SVG 输出。
- `examples/failure_cases/`：失败样本和 rule_id 覆盖。

## 当前仍可继续改进

- 更智能的图布局和大图折叠策略。
- 更丰富的语义一致性检查。
- 更细的外部依赖治理策略。
- 更完整的 side-effect 自检分层和允许清单。
