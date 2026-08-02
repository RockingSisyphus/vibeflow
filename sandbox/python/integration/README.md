# 集成沙盒

这个目录模拟真实业务项目使用 `vibeflow` 的方式：业务侧只编写 node、受控 `base_lib`、插件和 JSONC 配置。运行器通过 `pyproject.toml` 与 `src/vibeflow` 自动定位仓库，不会在 Sandbox 中创建内核软链接。

运行：

```bash
PYTHONPATH=src python sandbox/python/integration/run_all.py
```

脚本会把项目复制到临时目录，并在同一临时目录执行 `npm ci` 安装 Mermaid CLI/Puppeteer，再批量运行合法配置、非法 node、非法 `base_lib`、非法配置和非法插件。默认不在源码树留下依赖、报告或运行产物；需要检查产物时使用 `--keep-artifacts`，结果会写入本目录的 `.artifacts/`。它还会使用真实 CLI 验证本工作区新增的 `review` 审核流程：

- 对已登记的嵌套 nodeset workflow，先写入陈旧架构，再确认 `review` 自动刷新 canonical `ARCHITECTURE.jsonc` 并发布 expanded `review-columns` SVG。
- 对未登记的 workflow，确认返回 `REVIEW.ARCHITECTURE.UNREGISTERED`，不修改已登记架构，也不发布 SVG。
- 确认审核结果不发布中间 `.mmd`、provenance sidecar 或嵌入式 provenance metadata。
- 对专用可视化 fixture 先执行真实 `validate` 并要求严格 `PASS`，再执行 `export-svg --expand-nodesets`：确认 external node 同时保留颜色 class、`[EXTERNAL]` 标题和 `7px` non-scaling 粗边框；同一父图中的四个 loop 调用全部连接到同一个 `end`，共享的 nodeset body 只生成一个带调用摘要的详情 fragment。
- `pass_port_math.jsonc` 通过 fake `vibeflow.port` 验证 Python `receive → base_lib 数学 Node → send`，并核对 `(5 + 2) × 3 = 21` 的输出和发送值。
- 执行模型专项用例验证普通 Python Node 留在 `MainThread`，`async: result_key` Node 确实进入 `ThreadPoolExecutor` 且 `runtime.run()` 会阻塞到 join；portable plan 同时核对 `immediate/inline/current`、`deferred/thread` 和 `detached/thread`。线程池边界覆盖三任务并行、`async_max_workers: 1` 的排队，以及 `0`、负数、布尔值和小数 worker 数被拒绝。
- `fail_async_result_key_missing.jsonc` 验证 `result_key` 未出现在 `provides` 时配置阶段失败；原有 result_key join、detached 完成和 trace 用例继续验证图内可见的异步分路。
- 在全部 case 结束后集中审计所有发布 SVG：`reports/svg` 必须逐一对应 health 无 error 的合法 case，成功运行目录必须包含 `PASS/CONCERNS` 且 errors 为空的 `health_report.json`，review SVG 必须带有各自的成功校验结果。只有 `expected_fail_*` / `expected_runtime_fail_*` 明确错误路径下的诊断 SVG 可以豁免。
- 使用真实 `delegate-cli -- --input data.yaml --verbose` 启动 graph，确认 argv 原样进入、document 节点读取文件、业务 stdout/stderr 不被内核污染，并由 `cli.exit_code` 控制进程退出。
- 使用两个真实数值 CLI graph 覆盖多种 Python IO：IO 节点从 stdin 读取数字，两个 document 节点分别从文件读取数字，process 节点求和，再由 document 节点写文件、IO 节点写 stdout/stderr。`pathlib` 用例组合 `input()`、`Path.read_text/write_text`、`open().readline()`、`print()` 和 `sys.stderr.write()`，验证 `7 + 11 + 13 = 31`；标准流用例组合 `sys.stdin.readline()`、`open().read/write()`、`Path.read_text()` 和 `sys.stdout/stderr.write()`，验证 `5 + 17 + 19 = 41`。
- 两个数值用例都按 UTF-8 字节精确检查 stdout、stderr 和输出文件，并检查退出码；同时确认 architecture/health 不会执行 effectful examples、派生 effect scope 符合节点职责、health 为 `PASS/CONCERNS`、`output_summary.json` 包含 `cli.exit_code`、关键节点各执行一次，以及 `vibeflow.log` 不泄露 stdin、文件内容、业务路径或输出内容。

使用 `--keep-artifacts` 时，脚本输出：

- `.artifacts/reports/summary.json`
- `.artifacts/reports/summary.md`
- `.artifacts/reports/mermaid/*.mmd`
- `.artifacts/reports/review/*.svg`
- `.artifacts/reports/delegate_cli_numeric/*.txt`
- `.artifacts/runs/<case_name>/...`

退出码：

- `0`：全部预期通过。
- `1`：合法 case 失败，或非法 case 未被拒绝。
- `2`：环境错误，例如无法定位仓库源码。

本目录包含故意违规的 Python 文件，用于验证内核能拒绝坏代码。仓库自检器应把这些已知反例按 fixture 精确归属，不能把它们误报为 VibeFlow 源码问题，也不能因此跳过整个 Sandbox。

## Flowchart 示例

普通 `pipeline.edges` 形成环已经被禁止；`project/configs/fail_decision_cycle_forbidden.jsonc` 验证带 decision 和 exit 的旧式 retry 环也会被 `GRAPH.CYCLE.FORBIDDEN` 拒绝。

循环示例请看 `project/configs/pass_loop_while_nodeset_retry.jsonc`、`pass_loop_stop_after_nodeset_training.jsonc` 和 nested loop fixtures：

- `vibeflow.loop.while` 调用 nodeset body。
- 固定轮数用 `loop.stop_after`。
- 条件退出用 body/state 输出的 bool `loop.stop_when`。
- 运行时仍保留 `max_steps` 作为顶层安全护栏，但不再把 decision cycle 作为循环语义。

`project/configs/pass_io_data_store.jsonc` 展示外部数据/副作用的替代建模方式：`data_store` 节点产出请求数据，`io` 节点消费外部输入结果。旧 `boundary` 配置只保留在失败用例中，验证内核会以 `CONFIG.BOUNDARY.REMOVED` 拒绝。

`project/configs/review_external_nodeset_dedup.jsonc` 是严格 health-pass 的审查渲染 fixture。它用四个 loop 节点调用同一个 `visual.reusable_worker` body，每个调用通过 `loop.outputs` 映射到唯一 provider key，并在 `join_policy: all` 的 terminal `end` 汇合；同时保留一个真实 external 主线节点。`run_all.py` 先要求 `validate` 返回 `PASS`，再检查父图中的四个调用 ID 与四条 `worker_* -> end` 连线、唯一局部详情、`calls: 4` / 前三个 ID / `+1` / 配置计数摘要，以及 external 边框 CSS。普通 nodeset 调用必须与定义保持完全相同的 provides 契约，因此同一父图中的合法重复普通调用还受 provider key 唯一性约束；异步调用的分组与摘要由单元测试覆盖。
