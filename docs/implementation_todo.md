# VibeFlow 当前实现清单

本文件记录当前实现基线和后续仍值得推进的工作。旧 `boundary`、`pipeline.loops`、edge `max_executions` 设计已废弃，不再作为待办或完成项维护。

## 当前已完成

### 标准流程图核心

- [x] `NodeInfo.flow_kind` 必填。
- [x] 支持标准 flow_kind：`terminal`、`process`、`decision`、`io`、`predefined`、`data_store`、`document`、`preparation`。
- [x] 移除 `external_dependency` 作为 flow kind。
- [x] 增加 `NodeInfo.external: bool`，用于外部/第三方实现的源码质量检查跳过。
- [x] implemented node 的 `flow_kind` 只能来自 registry 中的 `NODE_INFO`。
- [x] planned node/nodeset 可在 config 中声明设计期 `flow_kind`。

### 显式 flow edge

- [x] `pipeline.edges` 是唯一控制流来源。
- [x] `requires/provides` 保留为数据契约和诊断来源，不推导控制流。
- [x] `CompiledGraph.effective_edges` 表示显式 flow edge。
- [x] 保留 `data_edges` 作为诊断信息。
- [x] 拒绝旧 `pipeline.loops`。
- [x] 拒绝旧 edge `max_executions` / `loop`。
- [x] 使用 `pipeline.max_steps` 作为运行时安全护栏。

### Flowchart 健康检查

- [x] 可执行图必须有 terminal start/end。
- [x] 已实现节点不能孤立。
- [x] 已实现节点必须从 start 可达。
- [x] 已实现节点必须能到达 end。
- [x] 显式 cycle 必须经过 decision。
- [x] decision outgoing edge 必须写 `when`。
- [x] decision output schema enum/boolean 和 branch condition 做一致性检查。
- [x] decision 非回环分支必须能到达 terminal end。
- [x] 数据契约缺失 upstream provider 输出 warning。
- [x] 未消费 output 输出 warning，但 `when` 中使用的 route key 视为已消费。

### Planned Architecture

- [x] 支持 `status: planned | implemented`。
- [x] planned node 可作为设计占位。
- [x] planned nodeset 可作为设计占位。
- [x] health 对 planned 内容给 warning。
- [x] runtime 拒绝 planned 内容。
- [x] implemented nodeset 不能包含 planned child。
- [x] Mermaid / ASCII / SVG 能显示 planned 标记。

### Runtime

- [x] step runtime 从 terminal start 节点开始。
- [x] runtime 只沿显式 flow edge 调度。
- [x] runtime 执行 edge `when` 条件。
- [x] runtime 记录 `exec_order`、`edge_executions`、`step_count`、`node_runs`、`stop_reason`、events，并可通过 `RuntimeOptions.trace` 降低 trace 粒度。
- [x] runtime 到达无 outgoing edge 的 terminal end 后停止。
- [x] runtime 默认按引用传递任意 Python 对象，不要求输出 JSON serializable 或可 deepcopy。
- [x] runtime 使用 `ExecutionPlan` / `NodeFrame` 预绑定 node、参数、edge 和 nodeset 子计划。
- [x] runtime 可选 `execution="block"` 执行线性链和简单 decision loop。
- [x] runtime 支持显式 `async: "detached"` 和 `async: "result_key"` side task。

### 图形输出

- [x] `export-mermaid` 输出 `graph.mmd`。
- [x] `export-ascii` 输出 `graph.txt`。
- [x] `export-svg` 通过项目本地 Mermaid CLI 输出 `graph.svg`。
- [x] 正式运行写出 `graph.mmd`、`graph.txt`、`graph.svg`。
- [x] SVG 渲染失败不改变拓扑运行结果，会写出 error sidecar。
- [x] 图中显示 flow_kind 标准形状、`when`、planned、external、health finding、中文描述和契约 key。

### Node / base_lib / plugin 治理

- [x] `NODE_INFO` / `CONTRACT` 完整性检查。
- [x] `run_pure(inputs, params)` 接口检查。
- [x] 禁止 node 间 import/call。
- [x] 禁止常见副作用能力。
- [x] 静态检查输入变异、输出 key 和 CONTRACT example JSON snapshot；runtime 默认检查输出 key，可选恢复输出 JSON snapshot。
- [x] 检查源码行数、字节数、函数数量、分支、嵌套、调用链。
- [x] 检查 `base_lib` 纯度和依赖链。
- [x] 支持 `PolicyPlugin`、`CompilerPlugin`、`RuntimePlugin`。
- [x] 移除 `BoundaryPlugin`。

### 分发和自检

- [x] 提供 `distribution/kernel_development_pack/`。
- [x] 提供最小项目和集成沙箱。
- [x] 默认质量自检 `quality-check --path .` 达到 `PASS`。

## 后续可改进

- [ ] 更大图的 SVG/ASCII 自动布局优化。
- [ ] 更细的外部依赖治理策略，例如按 node type 声明可信外部库清单。
- [ ] 更智能的契约语义一致性检查。
- [ ] 更细的 side-effect 自检允许清单，降低测试/脚本侧误报。
- [ ] 为 planned architecture 增加设计审查报告视图。
- [ ] 为多项目分发包增加自动 smoke test。

## 当前完成判定

当前主线应满足：

```powershell
python -m compileall src/vibeflow tests/unit examples/integration_sandbox/project examples/integration_sandbox/run_all.py distribution/kernel_development_pack/project_template/run.py
pytest -q
python examples/integration_sandbox/run_all.py
$env:PYTHONPATH='src'; python -m vibeflow quality-check --path .
```

预期：测试通过，集成沙箱通过，默认质量自检 `PASS` 且 `errors=0, warnings=0`。
