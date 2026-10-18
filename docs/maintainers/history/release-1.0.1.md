# VibeFlow 1.0.1

## 中文更新日志

本版以正式版本 v1.0.0 为基线。**虽然版本号为 1.0.1，本版包含不兼容的并发接口迁移；已有项目须修改旧任务管理配置并重建产物。**

- 普通 Node、Nodeset、Loop 和显式调度边统一承载并发。删除旧任务图、task_manager、TaskRef/TaskController/TaskOutcome、`context.tasks`、`task_targets` 与全局 `async_max_workers`，不保留兼容执行器。分发与统一回收使用不同节点，每条执行分支都须显式到达结束节点。
- 分发调用通过 `config.max_concurrency` 设置局部容量，默认 8，只接受正整数。超出部分排队；任意调用实际完成清理即补入下一项，不等待整批结束。额度按这次分发的直接调用计算，Nodeset/Loop 保持名额到完整返回，不同和嵌套分发独立计数；共享目标同时满足各来源额度。
- 统一规则拒绝断路分支与同节点回收兼分发。后者从仅作提示的旧路径移入共用 join 错误检查，公开 `validate` 和 `build` 必须失败。取消与失败等待已启动节点真实退出；JS 保留尚未完成的 SDK 操作归属，Python 保留线程清理、执行锁和 trace 一致性。
- 永久沙箱覆盖显式容量 12、容量 4、默认 8、实际清理后补位、单次收集、按声明顺序交付和重复 AOT 调用；非法图同时验证 CLI 诊断、退出码与未发布构建产物。JS 使用 Node 和真实 Chromium。
- HTTP 渲染只服务登记的 loopback 资源，子进程监督覆盖渲染和验证后代；失败诊断与部分观察记录保留。修复 CLI stdout/stderr 收尾竞争，结束信号到达后继续排空已产生的数据。
- 更新开发者设计、维护流程、用户配置与迁移指南，以及中英文入口文档。

### 迁移与资产

Workflow ABI 从 v7 升为 `vibeflow.workflow.v8`；AOT manifest 仍为 `vibeflow.aot-build.v3`，不表示旧计划兼容。升级步骤见[用户并发迁移](../../../distribution/docs/user/graph-concurrency.md#从旧任务接口迁移)。删除业务管理器的启动、回收和补位循环，用显式普通节点及下游 all 汇合表达，再重新构建计划、Architecture 和 AOT 目录。

资产包括 `vibeflow-distribution-1.0.1.zip`（collaborative）、`vibeflow-distribution-autonomous-1.0.1.zip` 与 `SHA256SUMS-1.0.1.txt`。两个 profile 使用相同内核、机器 policy 和最小项目，只改变开发协议及文档选择。历史 Release 资产保持原样。

### 验证范围

并发实现的最近专项验收通过 Python 沙箱 16 项、Node／Chromium 沙箱 10 项和 132 项相关回归；这是功能验收，不能替代本次发行包验证，也不表述为重新通过原 18 阶段全量。早先 pytest 的失败和补验记录保留，不改写原始成绩。

2026-10-18 发行专项 44 项已通过：首轮 43 项通过，渲染项因尝试下载浏览器受阻，改用预装 Chromium 后补验通过。双 profile ZIP 的版本、内核哈希、用户文档字节和共享内核已核对，正式 ZIP 与隔离构建及解压部署验证所用 ZIP 逐字节一致。两包验证 kernel、Python AOT API/无源码 CLI，以及 Node 构建运行；1.0.1 wheel 隔离安装、资源导入和 AOT 运行通过。实际解压发行包还验证两 Target 的容量 4 补位及两类非法图拒绝。仓库检查零错误、零警告。最初并行构建的自检看到另一构建的暂存目录而中止，其原始日志保留，改在正式构建结束后复验通过。证据位于工作区外 `vibeflow-release-1.0.1-20261018`，不写入发行包或用户桌面。

## English release notes

Changes since v1.0.0. **This patch-numbered release includes a breaking concurrency migration. Update task-management configurations and rebuild generated artifacts before upgrading.**

- Ordinary nodes, Nodesets, Loops and explicit scheduled edges replace the task graph and controller API. Dispatch and collection are separate calls; every execution branch must reach an end node. Removed task interfaces have no compatibility executor.
- `config.max_concurrency` limits the direct calls of each dispatch invocation, defaulting to 8. Queued calls refill after any active call actually exits and finishes cleanup. Independent and nested dispatches retain separate budgets; shared targets must satisfy all their dispatch budgets.
- Standard workflow rules reject disconnected workers and combined collectors/dispatchers in both validation and builds. The latter is now a shared join error, replacing the former warning-only path. Failure and cancellation retain ownership until running calls and SDK operations really finish.
- Permanent Python, Node and real Chromium sandboxes check exact capacities, incremental refill, ordered results, one collector invocation, repeated AOT execution and CLI rejection with no published build artifacts.
- Loopback HTTP rendering boundaries, descendant process cleanup, partial observation records and final stdout/stderr draining are corrected. Developer and user documentation describe the new behavior and migration.

Workflow ABI is v8; the AOT manifest remains v3. Rebuild old plans and bundles. Assets contain collaborative and autonomous ZIPs plus a SHA256 list. The latest focused feature validation passed 16 Python sandbox observations, 10 Node/Chromium observations and 132 regressions. Release-specific package verification is separate; these results are not a new full 18-stage acceptance batch.

Release verification on 2026-10-18 passed all 44 selected tests after rechecking the browser test with installed Chromium. Both formal ZIPs are byte-identical to the archives exercised by isolated dual-profile deployment, Python AOT API/source-free CLI and Node checks. The 1.0.1 wheel passed isolated installation and execution. The extracted release also passed capacity-4 refill and invalid-graph rejection probes in both Targets. Repository checks report zero errors and warnings; initial setup/build failures remain in the evidence logs.

[完整比较 / Full comparison: v1.0.0 → v1.0.1](https://github.com/RockingSisyphus/vibeflow/compare/v1.0.0...v1.0.1)
