# CompiledBlock 完整代码生成计划

本文记录 `execution="compiled"` 的最终实现目标：它不应只是当前的 linear block fast path，而应名副其实地把可编译 graph 区域编译成 Python execution block。

## 目标语义

`execution="compiled"` 表示：

- 编译期把可编译 graph 区域生成 Python callable。
- runtime 调用这个 callable 执行 block。
- callable 内部直接执行 node、写 context、记录 edge。
- 不走 `_run_node()`。
- 不走 ready queue。
- 不逐步调用 `_activated_edges()` 做解释式调度。
- `trace="full"` 和 `node_hooks=True` 不应导致整体回退 `_run_steps()`，而是在 generated block 内插入对应 instrumentation。
- 只有遇到明确不可编译区域时才 fallback 到 plan runtime。

## 第一版支持范围

第一版完整 compiled block 支持：

- 线性纯 node 段。
- 单入口 CFG block。
- decision 分支。
- decision loop，只要每一步最多激活一条 edge。
- terminal start/end。
- block 内完整 edge 计数。
- block 内 `runtime.exec_order`、`runtime.node_runs`、`runtime.step_count`、`runtime.current_node` 正常更新。
- `trace="boundary"` 记录 block 边界和失败。
- `trace="full"` 记录 node 事件。
- `node_hooks=True` 时在 generated block 内调用 node hook。
- `block_hooks=True` 时调用 block hook。
- 失败时记录 `current_node`、`node_failed`、`block_failed`，然后抛出。

第一版暂不编译：

- async node。
- nodeset。
- 多个 active outgoing edge 的 fan-out。
- 需要 ready queue 合流调度的 DAG 区域。
- 动态 context merge。
- 自动并行。

这些区域应切成 plan fallback 段，不影响整体运行。

## 实现步骤

### 1. 新增 block compiler

新增 `src/vibeflow/block_compiler.py`。

核心结构：

```python
@dataclass(frozen=True)
class CompiledBlock:
    name: str
    entry: str
    exits: tuple[str, ...]
    nodes: tuple[str, ...]
    edge_routes: Mapping[str, tuple[EdgeSpec, ...]]
    callable: Callable[[PipelineRuntime, Context], CompiledBlockResult]
    source: str
    supports_full_trace: bool
    supports_node_hooks: bool

@dataclass(frozen=True)
class CompiledBlockResult:
    last_node: str
    outputs: Mapping[str, object]
```

`compile_blocks(plan, runtime_options)` 负责：

- 分析 `ExecutionPlan`。
- 切分可编译 region。
- 生成 Python source。
- 用 `exec()` 构造 callable。
- 将 node callable、params、frames、edge objects 放入 namespace，不拼接用户代码。

### 2. 生成 Python execution block

生成代码必须是内核模板，不允许拼接用户 Python 源码。

安全约束：

- node name、key、edge 条件字符串只通过 `repr()` 写入。
- node callable、params、frame、edge object 通过 namespace 注入。
- 不把用户可控字符串作为 Python 语句拼接。

线性段生成直线代码，示意：

```python
def compiled_block(runtime, context):
    frame = frames["a"]
    runtime.trace.current_node = "a"
    outputs = execute(frame, context)
    write_outputs(context, outputs)
    record_node(runtime, frame, outputs)
    record_edge(runtime, "a", "b")

    frame = frames["b"]
    ...
    return CompiledBlockResult(last_node="end", outputs=outputs)
```

decision / loop block 生成 CFG dispatch，示意：

```python
def compiled_block(runtime, context):
    current = "entry"
    for _ in range(max_steps):
        if current == "a":
            ...
            current = "decision"
            continue
        if current == "decision":
            ...
            if condition_matches("done == true", values):
                record_edge(runtime, "decision", "end")
                current = "end"
            else:
                record_edge(runtime, "decision", "loop")
                current = "loop"
            continue
    raise PipelineRuntimeError("compiled block exceeded max_steps")
```

### 3. 编译期 region 切分

在 `ExecutionPlan` 构建后分析可编译区域。

目标：

- 尽量取最大单入口纯 Python CFG region。
- 遇到 async、nodeset、复杂 fan-out、DAG 合流时切断。
- 对每个 region 生成一个 compiled block。

`ExecutionPlan` 增加：

```python
compiled_blocks: tuple[CompiledBlock, ...]
compiled_block_by_entry: Mapping[str, CompiledBlock]
compiled_node_to_block: Mapping[str, CompiledBlock]
```

### 4. runtime 调度

`execution="compiled"` 使用 compiled dispatcher：

- 当前 ready node 是 compiled block entry：调用 compiled callable。
- 否则执行现有 plan node。
- compiled callable 返回 `last_node` 和 `outputs`。
- dispatcher 从 `last_node` 继续处理 block 外 outgoing edge。
- 不再因为 `trace="full"` 或 `node_hooks=True` 整体回退。

不可编译区域仍走 plan runtime，保证功能完整。

### 5. trace / hook / edge 审计

compiled block 内必须保持流程审计语义：

- 每条真实走过的 edge 都累加到 `runtime.edge_executions`。
- 线性 edge 直接记录。
- decision edge 只记录实际命中的那条。
- loop 每次迭代都累加。
- `trace="boundary"` 记录 `block_enter` / `block_exit` / `block_failed`。
- `trace="full"` 记录 node 事件。
- `node_hooks=True` 时调用 `before_node` / `after_node` / `node_failed`。
- `block_hooks=True` 时调用 `before_block` / `after_block` / `block_failed`。
- 失败时 `runtime.current_node` 必须指向失败 node。

不要恢复不必要的热路径开销：

- `trace="boundary"` 不记录 per-node summary。
- `node_hooks=False` 不调用 node hook。
- 不在 block 内重复走 ready queue。

### 6. train preset

完整 compiled block 完成后，将训练 preset 默认改为最快路径：

```python
RuntimeOptions(
    trace="boundary",
    execution="compiled",
    run_hooks=True,
    node_hooks=False,
    nodeset_hooks=False,
    block_hooks=True,
)
```

适用位置：

- `src/vibeflow/cli.py --runtime-profile train`
- `distribution/kernel_development_pack/project_template/run.py --runtime-profile train`

显式 `--execution plan` 仍可覆盖 preset。

## 测试计划

unit tests：

- compiled linear block 确认调用 generated callable。
- compiled decision branch。
- compiled decision loop。
- `trace="full"` 不回退 plan。
- `node_hooks=True` 不回退 plan。
- compiled edge_executions 完整。
- async / nodeset / 复杂 DAG fallback。
- compiled failure 记录 `current_node`、`node_failed`、`block_failed`。
- train preset 默认使用 `execution="compiled"`，显式 `--execution plan` 可覆盖。

integration sandbox：

- `compiled_linear_training`
- `compiled_decision_loop`
- `compiled_trace_full`
- `compiled_with_node_hooks`
- `compiled_fallback_mixed_graph`

验证命令：

```bash
python3 -m compileall -q src tests examples distribution/kernel_development_pack/project_template/run.py
PYTHONPATH=src python3 -m pytest tests/unit/test/strict_runtime.py tests/unit/test/strict_mermaid_cli.py -q
PYTHONPATH=src python3 -m pytest tests/unit -q
PYTHONPATH=src python3 examples/integration_sandbox/run_all.py
PYTHONPATH=src python3 -m vibeflow quality-check --path .
git diff --check
```

## 非目标

本阶段不做：

- 用户自定义 Python 源码拼接。
- 通用 Python optimizer。
- 自动并行。
- async context merge。
- 不可证明安全的复杂 graph 强行编译。

## 完成标准

`execution="compiled"` 达成以下条件才算完成：

- 可编译区域确实由 generated Python callable 执行。
- `trace="full"` 和 `node_hooks=True` 不再导致整体回退。
- block 内 edge 审计完整。
- train preset 默认走 compiled。
- fallback 只发生在明确不可编译区域。
- docs 和分发包说明与实际行为一致。
