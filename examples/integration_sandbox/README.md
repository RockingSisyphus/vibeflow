# 集成沙盒

这个目录模拟真实业务项目使用 `vibeflow` 的方式：业务侧只编写 node、受控 `base_lib`、插件和 JSONC 配置；内核通过 `kernel/vibeflow` 软链接进入项目。

运行：

```powershell
python examples\integration_sandbox\run_all.py
```

脚本会自动创建或刷新 `kernel/vibeflow` 软链接，批量运行合法配置、非法 node、非法 `base_lib`、非法配置和非法插件，并输出：

- `reports/summary.json`
- `reports/summary.md`
- `reports/mermaid/*.mmd`
- `runs/<case_name>/...`

退出码：

- `0`：全部预期通过。
- `1`：合法 case 失败，或非法 case 未被拒绝。
- `2`：环境错误，例如无法创建软链接或 junction。

本目录包含故意违规的 Python 文件，用于验证内核能拒绝坏代码。因此仓库级通用质量自检默认排除 `integration_sandbox`，避免把反例 fixture 当成内核自身质量问题。

## Flowchart 示例

普通 `pipeline.edges` 形成环已经被禁止；`project/configs/fail_decision_cycle_forbidden.jsonc` 验证带 decision 和 exit 的旧式 retry 环也会被 `GRAPH.CYCLE.FORBIDDEN` 拒绝。

循环示例请看 `project/configs/pass_loop_while_nodeset_retry.jsonc`、`pass_loop_stop_after_nodeset_training.jsonc` 和 nested loop fixtures：

- `vibeflow.loop.while` 调用 nodeset body。
- 固定轮数用 `loop.stop_after`。
- 条件退出用 body/state 输出的 bool `loop.stop_when`。
- 运行时仍保留 `max_steps` 作为顶层安全护栏，但不再把 decision cycle 作为循环语义。

`project/configs/pass_io_data_store.jsonc` 展示外部数据/副作用的替代建模方式：`data_store` 节点产出请求数据，`io` 节点消费外部输入结果。旧 `boundary` 配置只保留在失败用例中，验证内核会以 `CONFIG.BOUNDARY.REMOVED` 拒绝。
