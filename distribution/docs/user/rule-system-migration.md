# 配置与接口迁移

当前格式如下。升级时迁移源码与配置，再重新生成计划、AOT 和预览快照；架构资料按[架构指南](architecture.md)更新。

| 接口／产物 | 当前版本 |
| --- | --- |
| Workflow ABI | `vibeflow.workflow.v12` |
| Plugin ABI | `vibeflow.plugin.v5` |
| Rule ABI | `vibeflow.rule.v3` |
| AOT manifest | `vibeflow.aot-build.v6` |
| Workflow 启动清单 | `vibeflow.workflow-launches.v2` |
| 预览快照 | v5 |

旧计划、manifest、启动清单和预览格式通过重新生成升级；当前工具读取当前格式。业务输出、日志、trace 和发布归档按原用途保留。

## 项目与资源

| 旧机制 | 迁移操作 |
| --- | --- |
| 无项目、单层 root 或 root path 为点目录 | 在项目配置中注册独立子目录 root |
| `policy`、`quality_enabled`、`quality_structure` | 在 `project_rules.jsonc` / `root_rules.jsonc` 中选择规则及参数 |
| `structure_roles` / `enforce_role_imports` | 用资源引用 Rule 配置源码依赖政策 |
| 独立扫描、`--exclude-dir` / `--exclude-path` 与全局质量阈值 | 按对应 layout／源码 Rule 设置目录用途与质量参数 |
| Plugin 导出业务 Node | Node 移入 `nodes/`，以 `id` 声明、`node_type` 引用类型；Plugin 提供 NodeType |
| 调用点 `type_used` | 使用 `definition_id` 引用业务定义，保留调用自身的 `id` |
| Nodeset 定义与调用混用 | 用 `type_key` 标识 NodesetType，调用通过 `definition_id` 引用 |
| Plugin 实现分散 | 将入口、贡献和支撑源码放入 `plugins/<包名>/`，按整包选择 |
| 跨 root 私有实现复用 | 提取为项目共享资源，或按明确用途配置对应跨 root 规则 |
| 隐式独立库引入 | 在 workflow 的 `base_lib.modules` 中列全直接与间接依赖；Plugin 私有库随整包选择 |

先建立 root 并登记用途、Target 与工具链，再整理资源归属，最后更新类型、调用和规则选择。配置示例见[项目治理](project-governance.md)，规则数据接口见[Rule 与 Node](rules-and-nodes.md)。

## 输入与宿主边界

端口与宿主接入代码见[Workflow 协同](workflow-coordination.md)。

## 并发与异步

旧 `task_manager`、`vibeflow.task_manager`、`task_targets`、TaskRef/TaskController/TaskOutcome、`context.tasks` 和 `async_max_workers` 改为普通图并发：将工作节点放入 `pipeline.nodes`，补齐“分发 → 工作 → all 汇合 → 结束”的调度边，以分发调用的 `config.max_concurrency` 配置额度。节点内部保留本节点业务任务的清理，其他节点的启动与等待由图表达。运行配置见[普通图并发](graph-concurrency.md)。

等待消息、等待独立实例的 Python workflow 声明 `entry_mode: "async"`；等待 Node 改为 `async def run_pure` 并 await，SDK 使用 `run_async()`。普通值立即返回的计算流程保持 sync，跨 workflow 同步调用使用 InvokeSync。

进程启动配置使用 `launch.kind: "process"`；同进程使用 `"in_process"` 并显式绑定目标描述与执行方法。底层 Python HTTP Client 使用 `await WorkflowClient.open(...)` 或 `await WorkflowClient.from_environment(...)`；call/wait/receive/kill/flush/finish 均 await，send 立即交接，再由 flush/finish 等待完成。

`runtime_dispatch` 推断字段及展示已退役；执行锁、调度、异步所有权与清理继续使用各自接口。

## 重新构建与审阅

迁移后执行适用的 validate、quality 和 build，并运行工作流执行探针。审核材料使用 review 的 HTML 快照，交付方式见[本地预览](local-preview.md#生成与交付审核材料)。
