# VibeFlow 开发入口

先从 `vibeflow_config.jsonc` 确定任务所属的实际 root 和 Target；`python_project`、`javascript_project` 是最小项目的示例路径。阅读所选 root 的 README、`vibeflow_project.jsonc`、已登记的 `ARCHITECTURE.jsonc`，以及目标目录中更具体的 `AGENTS.md`。沿 Architecture 的 source 定位真实 Config、Nodeset、代码插件声明和资源实现；修改 source 后通过 VibeFlow 命令更新架构产物。

按任务阅读规范：

- 修改 workflow、Config 或 edge：[`kernel/docs/user/workflow-and-config.md`](kernel/docs/user/workflow-and-config.md)
- 开发 Python Node 或 BaseLib：[`kernel/docs/user/python-development.md`](kernel/docs/user/python-development.md)
- 开发 JavaScript/TypeScript Node：[`kernel/docs/user/javascript-development.md`](kernel/docs/user/javascript-development.md)
- 开发 Nodeset 或 Loop：[`kernel/docs/user/nodesets-and-loops.md`](kernel/docs/user/nodesets-and-loops.md)
- 定义 Rule、组合 Ruleset 或选择 Node 规则：[`kernel/docs/user/rules-and-nodes.md`](kernel/docs/user/rules-and-nodes.md)
- 开发 Plugin、Capability 或 Host Extension：[`kernel/docs/user/plugins-and-integrations.md`](kernel/docs/user/plugins-and-integrations.md)
- 拆分 Node、BaseLib、Plugin 或 Host 实现，设置样式或追踪源码依赖：[`kernel/docs/user/multifile-resources.md`](kernel/docs/user/multifile-resources.md)
- 接入运行监控、保存业务输出或更新训练进度：[`kernel/docs/user/runtime-observation.md`](kernel/docs/user/runtime-observation.md)
- 运行检查或解释结果：[`kernel/docs/user/commands-and-results.md`](kernel/docs/user/commands-and-results.md)

用所属语言的插件 SDK 声明自定义资源，并在顶层 workflow 中显式选择插件。检查约束来自资源选择的 Ruleset；多文件实现逐一登记支撑源码。业务执行关系由原生 workflow 连边表达，Host、库与插件在当前配置的资源目录中展示。

每项 `pipeline.inputs` 明确填写布尔 `required`：必需输入为 true，可缺省输入为 false。顶层、Nodeset 与 Loop body 使用同一合同，未声明键不能传入，空输入声明只接受空对象。implemented Node 的 requires/provides 写入 SDK Descriptor；调用点只通过 type_used 引用，planned 与系统调用保留自己的显式契约。

直接声明 Node 或 Rule 时让 SDK 自动定位实现；显式源码定位必须与实际类、函数或资源入口一致。遇到 `RESOURCE.IMPLEMENTATION.CONFLICT`，根据报告中的声明与实际位置修正定位。需要独立延迟实现时使用源码引用声明。

多个入口承诺相同业务语义时，核对它们是否在实际执行路径上汇入共享 Node/Nodeset；边界适配保留输入和错误身份。具体设计与 Target 实现见上述文档。

完成修改后更新 Architecture，并执行任务适用的 validate、quality、build 和工作流执行探针。按本次修改对应的源码与输入，分别报告静态检查、构建、执行和业务验收结果。

正式审核图使用 `review` 生成，展示当前用户项目的主流程、所选资源目录和 Nodeset 详情。资源目录父节点分别为 `plugins`、`base_lib`、`host_extensions`，连接当前配置实际使用的资源；空目录省略。Node 显示在实际流程调用位置。主流程与嵌套父流程纵向显示，叶子 Nodeset 横向显示，子详情在父流程右侧上下排列。项目源码归属与规则证据保存在 `ARCHITECTURE.jsonc`，有效规则可通过 `review-rules --json` 查询。

Nodeset 定义可以在 `type_key` 同级设置 `"expand": false`，让展开图保留调用框并停止展示其全部内部；省略时为 `true`。同定义的重复调用和 Loop body 沿用该设置，内部源码仍接受审查并按原生流程执行。

运行排查时读取本次运行的 `vibeflow.log`（内核）和 `business.log`（业务 stdout/stderr）。自动化监控以 `status.json` 的 `state` 判断运行状态；`state/error/updated_at` 由内核维护。

业务 Node 更新进度时，Python 从 `vibeflow.targets.python.sdk` 导入 `update_run_info`，在 `run_pure` 内调用；JS/TS 在 `run(inputs, params, context)` 内调用 `context.updateInfo`。传入 JSON 对象数组，每次替换整个 `info`，需要保留的进度与指标一起提交，`[]` 清空。数值使用语言原生 JSON 类型。更新复制到当前运行缓存，默认每 60 秒及状态变化、结束时发布；Node 仍按原契约返回输出，并沿用所选 Ruleset。配置路径、刷新间隔和完整示例见上述运行日志与状态接口。

- 管理并发任务、迁移旧异步调用：[`kernel/docs/user/task-management.md`](kernel/docs/user/task-management.md)
