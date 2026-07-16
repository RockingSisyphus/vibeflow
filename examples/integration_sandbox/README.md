# 集成沙盒

这个目录模拟真实业务项目使用 `vibeflow` 的方式：业务侧只编写 node、受控 `base_lib`、插件和 JSONC 配置；内核通过 `kernel/vibeflow` 软链接进入项目。

运行：

```powershell
python examples\integration_sandbox\run_all.py
```

脚本会自动创建或刷新 `kernel/vibeflow` 软链接，批量运行合法配置、非法 node、非法 `base_lib`、非法配置和非法插件。它还会使用真实 CLI 验证本工作区新增的 `review` 审核流程：

- 对已登记的嵌套 nodeset workflow，先写入陈旧架构，再确认 `review` 自动刷新 canonical `ARCHITECTURE.jsonc` 并发布 expanded `review-columns` SVG。
- 对未登记的 workflow，确认返回 `REVIEW.ARCHITECTURE.UNREGISTERED`，不修改已登记架构，也不发布 SVG。
- 确认审核结果不发布中间 `.mmd`、provenance sidecar 或嵌入式 provenance metadata。
- 使用真实 `delegate-cli -- --input data.yaml --verbose` 启动 graph，确认 argv 原样进入、document 节点读取文件、业务 stdout/stderr 不被内核污染，并由 `cli.exit_code` 控制进程退出。
- 使用两个真实数值 CLI graph 覆盖多种 Python IO：IO 节点从 stdin 读取数字，两个 document 节点分别从文件读取数字，process 节点求和，再由 document 节点写文件、IO 节点写 stdout/stderr。`pathlib` 用例组合 `input()`、`Path.read_text/write_text`、`open().readline()`、`print()` 和 `sys.stderr.write()`，验证 `7 + 11 + 13 = 31`；标准流用例组合 `sys.stdin.readline()`、`open().read/write()`、`Path.read_text()` 和 `sys.stdout/stderr.write()`，验证 `5 + 17 + 19 = 41`。
- 两个数值用例都按 UTF-8 字节精确检查 stdout、stderr 和输出文件，并检查退出码；同时确认 architecture/health 不会执行 effectful examples、派生 effect scope 符合节点职责、health 为 `PASS/CONCERNS`、`output_summary.json` 包含 `cli.exit_code`、关键节点各执行一次，以及 `vibeflow.log` 不泄露 stdin、文件内容、业务路径或输出内容。

脚本输出：

- `reports/summary.json`
- `reports/summary.md`
- `reports/mermaid/*.mmd`
- `reports/review/pass_nodeset_nested.expanded.svg`
- `reports/delegate_cli_numeric/pathlib_sum.txt`
- `reports/delegate_cli_numeric/streams_sum.txt`
- `runs/delegate_cli/vibeflow.log`
- `runs/delegate_cli_numeric_pathlib/vibeflow.log`
- `runs/delegate_cli_numeric_streams/vibeflow.log`
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
