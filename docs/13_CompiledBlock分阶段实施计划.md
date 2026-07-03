# CompiledBlock 分阶段实施计划

本文是 `12_CompiledBlock完整代码生成计划.md` 的落地拆分方案。目标是把 `execution="compiled"` 从当前的线性 block fast path，逐步实现为真正的 Python execution block，同时控制每一版的验证范围和回归风险。

建议分 4 版完成。

## V1：generated linear block

目标不是扩展控制流能力，而是先把当前线性 compiled fast path 从手写循环迁移到 `block_compiler.py` 生成 callable。

交付内容：

- 新增 `src/vibeflow/block_compiler.py`。
- 定义 `CompiledBlock`、`CompiledBlockResult` 和 `compile_blocks()`。
- 线性 block 生成 Python source，并通过 `exec()` 构造 callable。
- generated callable 内直接执行 node、写 context、记录 `runtime.exec_order`、`runtime.node_runs`、`runtime.step_count`、`runtime.current_node` 和 block 内 edge。
- generated callable 不调用 `_run_node()`，不走 ready queue。
- 第一版只保持当前已支持的保守场景：线性纯 node 段、`trace="boundary"`、`node_hooks=False`。
- 保持现有 `compiled_linear_training` 行为不变。

验收重点：

- 当前 compiled 线性训练用例通过。
- 可以证明 compiled 路径调用的是 generated callable。
- 线性 block 内 edge 计数、执行顺序和 node run 计数正确。

## V2：CFG、decision branch 和 decision loop

目标是实现完整 compiled block 的核心控制流能力。

交付内容：

- region 切分从线性链升级为单入口 CFG region。
- 支持 terminal start/end。
- 支持 decision 分支。
- 支持 decision loop，但每一步最多只能激活一条 edge。
- block 内只记录真实走过的 edge，loop 每次迭代都累计。
- 遇到不可编译区域时切成 fallback 段，不影响整体运行。
- 不编译 async node、nodeset、复杂 fan-out、需要 ready queue 合流调度的 DAG 区域。

验收重点：

- compiled decision branch 单测通过。
- compiled decision loop 单测通过。
- `edge_executions` 对分支和 loop 计数正确。
- mixed graph 中可编译区域走 compiled，不可编译区域走 plan fallback。

## V3：trace、hook 和 failure 审计

目标是消除当前 compiled 的主要语义缺口：`trace="full"` 和 `node_hooks=True` 不再导致整体回退 `_run_steps()`。

交付内容：

- generated block 内支持 `trace="full"` 的 per-node runtime event。
- generated block 内支持 `before_node`、`after_node`、`node_failed`。
- generated block 内支持 `before_block`、`after_block`、`block_failed`。
- `trace="boundary"` 只记录 run / block / failure 边界，不记录 per-node summary。
- 失败时必须保证：
  - `runtime.current_node` 指向失败 node。
  - 记录 `node_failed`。
  - 记录 `block_failed`。
  - 异常继续向上抛出。
- 更新当前“compiled + node_hooks 回退 plan”的测试预期。

验收重点：

- `trace="full"` 下 compiled 不回退 plan，并产生 node event。
- `node_hooks=True` 下 compiled 不回退 plan，并调用 node hook。
- block hook 开关仍按 `RuntimeOptions` 生效。
- compiled failure trace 和 runtime summary 能定位失败 node。

## V4：train preset、兼容和最终验收

目标是把完整 compiled block 接入默认训练路径，并完成兼容收尾。

交付内容：

- 将 `src/vibeflow/cli.py --runtime-profile train` 默认改为：

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

- 将 `distribution/kernel_development_pack/project_template/run.py --runtime-profile train` 同步改为相同默认值。
- 显式 `--execution plan` 仍可覆盖 train preset。
- 保留公开兼容入口：
  - `vibeflow.CompiledBlock`
  - `ExecutionPlan.blocks`
  - `ExecutionPlan.block_for()`
- 新增 integration sandbox 覆盖：
  - `compiled_decision_loop`
  - `compiled_trace_full`
  - `compiled_with_node_hooks`
  - `compiled_fallback_mixed_graph`

最终验证命令：

```bash
python3 -m compileall -q src tests examples distribution/kernel_development_pack/project_template/run.py
PYTHONPATH=src python3 -m pytest tests/unit/test/strict_runtime.py tests/unit/test/strict_mermaid_cli.py -q
PYTHONPATH=src python3 -m pytest tests/unit -q
PYTHONPATH=src python3 examples/integration_sandbox/run_all.py
PYTHONPATH=src python3 -m vibeflow quality-check --path .
git diff --check
```

## 版本边界

推荐不要把 V2 和 V3 合并。V2 主要处理控制流正确性，V3 主要处理审计和 hook 语义；两者混在一起容易让控制流 bug 和 instrumentation bug 互相干扰。

如果必须压缩节奏，可以合并为 3 版：

- V1：generated linear block。
- V2：CFG / decision / loop。
- V3：trace、hook、failure、train preset 和最终验收。

但默认建议保持 4 版，每一版都有清晰可测的行为边界。
