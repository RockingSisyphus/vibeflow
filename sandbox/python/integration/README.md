# 集成沙盒

这个目录模拟真实业务项目使用 `vibeflow` 的方式：业务侧通过代码插件和 SDK 声明执行 Node、`base_lib`、Rule/Ruleset、生命周期插件，再用 JSONC 配置组织。运行器通过 `pyproject.toml` 与 `src/vibeflow` 自动定位仓库，不会在 Sandbox 中创建内核软链接。

入口目前登记 102 项，包括独立的 [综合数学应用](../comprehensive_math/README.md)。该应用合并了七个重复正例的运行；错误路径及其他专项仍单独执行，详见 [逐项替代归档](../../../docs/maintainers/history/audits/comprehensive-sandbox-20261009.md)。Python 与 JavaScript 两个 integration runner 合计 150 项（102+48）；历史 177 项清单保留当时记录。

运行：

```bash
PYTHONPATH=src python sandbox/python/integration/run_all.py
```

脚本会把项目复制到临时目录，并在同一临时目录执行 `npm ci` 安装 Mermaid CLI/Puppeteer，再批量运行合法配置、非法 Node 源码、非法独立声明、非法 `base_lib`、非法配置和 Rule 处理器错误。可以用 `VIBEFLOW_MERMAID_RENDERER_ROOT` 复用已经按锁文件安装的渲染器。默认不在源码树留下依赖、报告或运行产物；需要检查产物时使用 `--keep-artifacts`，结果会写入本目录的 `.artifacts/`。它还会使用真实 CLI 验证本工作区新增的 `review` 审核流程：

- 对已登记的嵌套 nodeset workflow，先写入陈旧架构，再确认 `review` 自动刷新 canonical `ARCHITECTURE.jsonc` 并发布 expanded `review-columns` SVG。
- 对未登记的 workflow，确认返回 `REVIEW.ARCHITECTURE.UNREGISTERED`，不修改已登记架构，也不发布 SVG。
- 确认审核结果不发布中间 `.mmd`、provenance sidecar 或嵌入式 provenance metadata。
- 对专用可视化 fixture 先执行真实 `validate` 并要求严格 `PASS`，再执行 `export-svg --expand-nodesets`：确认 external node 同时保留颜色 class、`[EXTERNAL]` 标题和 `7px` non-scaling 粗边框；同一父图中的四个 loop 调用全部连接到同一个 `end`，共享的 nodeset body 只生成一个带调用摘要的详情 fragment。
- 独立 comprehensive_math 通过注入的 `vibeflow.port` 验证 Python `receive → 两层 Nodeset/数学 Node/BaseLib/Loop → send`，同时检查计算结果、发送值、准确 warning 详情以及修正源码后的 warning 消失。
- 执行模型专项用例验证普通 Python Node 留在 `MainThread`，`async: result_key` Node 确实进入 `ThreadPoolExecutor` 且 `runtime.run()` 会阻塞到 join；portable plan 同时核对 `immediate/inline/current`、`deferred/thread` 和 `detached/thread`。线程池边界覆盖三任务并行、`async_max_workers: 1` 的排队，以及 `0`、负数、布尔值和小数 worker 数被拒绝。
- `fail_async_result_key_missing.jsonc` 验证 `result_key` 未出现在 `provides` 时配置阶段失败；原有 result_key join、detached 完成和 trace 用例继续验证图内可见的异步分路。
- 在全部 case 结束后集中审计所有发布 SVG：`reports/svg` 必须逐一对应 health 无 error 的合法 case，成功运行目录必须包含 `PASS/CONCERNS` 且 errors 为空的 `health_report.json`，review SVG 必须带有各自的成功校验结果。只有 `expected_fail_*` / `expected_runtime_fail_*` 明确错误路径下的诊断 SVG 可以豁免。
- 独立 [cli_addition](../cli_addition/README.md) 使用 YAML、pathlib、标准流三个适配配置执行 `2+3+4=9`。精确检查 stdout/stderr、文件字节、退出码、效果范围、执行次数、日志隔离和架构导出无业务副作用。
- 独立 [object_addition](../object_addition/README.md) 用 Box 和 Counter 做连续加法，检查原对象身份、非 JSON 报告、Nodeset 导出、绑定参数、固定与条件循环，以及 plan/block/compiled 执行。
- 独立 [plugin_addition](../plugin_addition/README.md) 检查多文件 Node/BaseLib/Plugin、参数覆盖、编译/运行钩子，并在临时 helper 修改、恢复后确认 `5→6→5`。
- 此前三个入口接替 11 个旧 Python 任务，完整映射见 [简单数学整合归档](../../../docs/maintainers/history/audits/addition-sandboxes-20261009.md)。
- 新增 [workflow_math](../workflow_math/README.md) 接替 13 个嵌套、循环和执行/trace 任务，五个配置共 17 组观察；[逐项迁移与验收](../../../docs/maintainers/history/audits/workflow-math-20261010.md)。
- 新增 [piecewise_math](../piecewise_math/README.md) 接替另外 11 个直线、分支、互斥汇合和数据旁路任务；四个配置共享短小加法节点，包含等号边界、24 组执行观察、真实编译块和源码、trace、运行与导出图检查。详见 [逐项迁移记录](../../../docs/maintainers/history/audits/piecewise-math-20261010.md)。

完整入口还复用独立的跨 root 质检沙箱：从发行最小项目构造 framework/project 双 root，Node 的契约与计算 helper 来自 framework BaseLib，通过真实 `run.py` 对比 `validate`、`quality` 与 `quality --path project`。用例覆盖默认及显式 workspace、直接内核 CLI、所选 root 的扫描范围、真实未声明 BaseLib 错误、workspace policy、独立 root、文件/子目录扫描、禁用 workflow 质检和混合 Target 的隔离子进程。可只运行这一组：

```bash
python tools/run_tests.py -- tests/targets/python/test_quality_workspace_sandbox.py
```

使用 `--keep-artifacts` 时，脚本输出：

- `.artifacts/reports/summary.json`
- `.artifacts/reports/summary.md`
- `.artifacts/reports/mermaid/*.mmd`
- `.artifacts/reports/review/*.svg`
- `.artifacts/{cli_addition,object_addition,plugin_addition,piecewise_math,workflow_math}/report.json`
- `.artifacts/runs/<case_name>/...`

退出码：

- `0`：全部预期通过。
- `1`：合法 case 失败，或非法 case 未被拒绝。
- `2`：环境错误，例如无法定位仓库源码。

Node 声明显式选择 `vibeflow.process`、`vibeflow.io`、`vibeflow.document` 或 `vibeflow.global_state` 等 Ruleset；这些规则的执行记录决定报告中的允许副作用范围。`rulesets: []` 的原生执行机制 fixture 不隐式补充源码审查。`project/rules/checks.py` 和独立 Rule 资源验证正常诊断、处理器异常、返回结构错误以及必需 record 缺失；compiler/runtime 插件仍只参与各自生命周期。源码预检先解析实际导入闭包，再运行选中的 import Rule，不导入业务模块。

本目录包含故意违规的 Python 文件和独立 JSONC 声明，用于验证所选规则或声明解析器能拒绝相应问题。仓库自检器应把这些已知反例按 fixture 精确归属，不能把它们误报为 VibeFlow 源码问题，也不能因此跳过整个 Sandbox。

## Flowchart 示例

普通 `pipeline.edges` 形成环已经被禁止；`project/configs/fail_decision_cycle_forbidden.jsonc` 验证带 decision 和 exit 的旧式 retry 环也会被 `GRAPH.CYCLE.FORBIDDEN` 拒绝。

循环示例请看 `project/configs/pass_loop_while_nodeset_retry.jsonc`、独立 `object_addition` 的 `fixed.jsonc` 和 nested loop fixtures：

- `vibeflow.loop.while` 调用 nodeset body。
- 固定轮数用 `loop.stop_after`。
- 条件退出用 body/state 输出的 bool `loop.stop_when`。
- 运行时仍保留 `max_steps` 作为顶层安全护栏，但不再把 decision cycle 作为循环语义。

`project/configs/pass_io_data_store.jsonc` 展示外部数据/副作用的替代建模方式：`data_store` 节点产出请求数据，`io` 节点消费外部输入结果。旧 `boundary` 配置只保留在失败用例中，验证内核会以 `CONFIG.BOUNDARY.REMOVED` 拒绝。

`project/configs/review_external_nodeset_dedup.jsonc` 是严格 health-pass 的审查渲染 fixture。它用四个 loop 节点调用同一个 `visual.reusable_worker` body，每个调用通过 `loop.outputs` 映射到唯一 provider key，并在 `join_policy: all` 的 terminal `end` 汇合；同时保留一个真实 external 主线节点。`run_all.py` 先要求 `validate` 返回 `PASS`，再检查父图中的四个调用 ID 与四条 `worker_* -> end` 连线、唯一局部详情、`calls: 4` / 前三个 ID / `+1` / 配置计数摘要，以及 external 边框 CSS。普通 nodeset 调用必须与定义保持完全相同的 provides 契约，因此同一父图中的合法重复普通调用还受 provider key 唯一性约束；异步调用的分组与摘要由单元测试覆盖。

## 目录用途与边界

仅用于：python / integration 案例，验证公开接口的综合使用、跨资源协作与错误诊断；保留真实项目输入与 runner。

- 新文件按上述用途归属；新增子目录同时写明职责，不能作为临时收纳箱。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](../../../docs/maintainers/directory-layout.md)。
