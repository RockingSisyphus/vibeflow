# VibeFlow 开发入口

先从 `vibeflow_config.jsonc` 确定任务所属的实际 root 和 Target；`python_project`、`javascript_project` 是最小项目的示例路径。阅读所选 root 的 README、`vibeflow_project.jsonc`、已登记的 `ARCHITECTURE.jsonc`，以及目标目录中更具体的 `AGENTS.md`。沿 Architecture 的 source 定位真实 Config、Nodeset、代码插件声明和资源实现；修改 source 后通过 VibeFlow 命令更新架构产物。

按任务阅读规范：

- 多入口、跨 workflow 调用/消息、端口节点或原生 IO 迁移：[`kernel/docs/user/workflow-coordination.md`](kernel/docs/user/workflow-coordination.md)；功能来自 Capability 与显式 Rule，不按节点名称或外观赋权。
- 修改 workflow、Config 或 edge：[`kernel/docs/user/workflow-and-config.md`](kernel/docs/user/workflow-and-config.md)
- 开发 Python Node 或 BaseLib：[`kernel/docs/user/python-development.md`](kernel/docs/user/python-development.md)
- 开发 JavaScript/TypeScript Node：[`kernel/docs/user/javascript-development.md`](kernel/docs/user/javascript-development.md)
- 开发 Nodeset 或 Loop：[`kernel/docs/user/nodeset-types-and-loops.md`](kernel/docs/user/nodeset-types-and-loops.md)
- 定义 Rule、组合 Ruleset 或选择 Node 规则：[`kernel/docs/user/rules-and-nodes.md`](kernel/docs/user/rules-and-nodes.md)
- 开发 Plugin、Capability 或 workflow 协同：[`kernel/docs/user/plugins-and-integrations.md`](kernel/docs/user/plugins-and-integrations.md)
- 拆分 Node、BaseLib 或 Plugin 实现，设置样式或追踪源码依赖：[`kernel/docs/user/multifile-resources.md`](kernel/docs/user/multifile-resources.md)
- 接入运行监控、保存业务输出或更新训练进度：[`kernel/docs/user/runtime-observation.md`](kernel/docs/user/runtime-observation.md)
- 运行检查或解释结果：[`kernel/docs/user/commands-and-results.md`](kernel/docs/user/commands-and-results.md)

项目必须注册独立子目录 root。业务 Node/独立 BaseLib 从标准目录发现，Plugin 整包提供 NodeType、Rule 等贡献并在 workflow 显式选择；项目/root 治理分别配置于 project_rules.jsonc/root_rules.jsonc。参阅 kernel/docs/user/project-governance.md。检查约束来自资源选择的 Ruleset；多文件实现逐一登记支撑源码。业务执行关系由原生 workflow 连边表达，库与插件在当前配置的资源目录中展示。

每项 `pipeline.inputs` 明确填写布尔 `required`：必需输入为 true，可缺省输入为 false。顶层、Nodeset 与 Loop body 使用同一合同，未声明键不能传入，空输入声明只接受空对象。implemented Node 的 requires/provides 写入 SDK Descriptor；调用点只通过 definition_id 引用，planned 与系统调用保留自己的显式契约。

直接声明 Node 或 Rule 时让 SDK 自动定位实现；显式源码定位必须与实际类、函数或资源入口一致。遇到 `RESOURCE.IMPLEMENTATION.CONFLICT`，根据报告中的声明与实际位置修正定位。需要独立延迟实现时使用源码引用声明。

多个入口承诺相同业务语义时，核对它们是否在实际执行路径上汇入共享 Node/Nodeset；边界适配保留输入和错误身份。具体设计与 Target 实现见上述文档。

完成修改后更新 Architecture，并执行任务适用的 validate、quality、build 和工作流执行探针。按本次修改对应的源码与输入，分别报告静态检查、构建、执行和业务验收结果。

正式审核材料使用 `review` 生成：交付 JSON 结果中的 `preview` 完整路径、`preview_id` 和定位到当次快照的 HTML 链接（`#snapshot=<preview_id>&view=flow`），说明对应的 Config 与需查看的变化。请用户通过 HTML 查看该快照的 workflow，不能只报告生成成功或提供一张 SVG。HTML 入口加载当次结构化快照，提供流程、BaseLib、Plugin 和 workflow 关联视图。资源来自当前 workflow 的实际选择；Node 显示在真实调用位置。Nodeset 与 Loop 默认折叠，在具体调用上右键展开或收起，手动状态不修改源配置。项目源码归属与规则证据保存在 `ARCHITECTURE.jsonc`，有效规则可通过 `review-rules --json` 查询。

需要静态 SVG 对照时使用 `review --with-svg` 或 `review --output FILE.svg`。SVG 的主流程与嵌套父流程纵向显示、叶子 Nodeset 横向显示；Nodeset 定义的 `"expand": false` 控制 SVG 详情展开，省略时为 `true`。该配置不改变 HTML 的手动展开，也不影响源码审查及原生执行。

运行排查时读取本次运行的 `vibeflow.log`（内核）和 `business.log`（业务 stdout/stderr）。自动化监控以 `status.json` 的 `state` 判断运行状态；`state/error/updated_at` 由内核维护。

业务 Node 更新进度时，Python 从 `vibeflow.targets.python.sdk` 导入 `update_run_info`，在 `run_pure` 内调用；JS/TS 在 `run(inputs, params, context)` 内调用 `context.updateInfo`。传入 JSON 对象数组，每次替换整个 `info`，需要保留的进度与指标一起提交，`[]` 清空。数值使用语言原生 JSON 类型。更新复制到当前运行缓存，默认每 60 秒及状态变化、结束时发布；Node 仍按原契约返回输出，并沿用所选 Ruleset。配置路径、刷新间隔和完整示例见上述运行日志与状态接口。

- 管理并发任务、迁移旧异步调用：[`kernel/docs/user/graph-concurrency.md`](kernel/docs/user/graph-concurrency.md)
