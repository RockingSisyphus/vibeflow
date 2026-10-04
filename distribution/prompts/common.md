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
- 运行检查或解释结果：[`kernel/docs/user/commands-and-results.md`](kernel/docs/user/commands-and-results.md)

用所属语言的插件 SDK 声明自定义资源，并在顶层 workflow 中显式选择插件。检查约束来自资源选择的 Ruleset；多文件实现逐一登记支撑源码。Host、库与插件依赖在架构图的资源区表达，业务执行关系由原生 workflow 连边表达。

多个入口承诺相同业务语义时，核对它们是否在实际执行路径上汇入共享 Node/Nodeset；边界适配保留输入和错误身份。具体设计与 Target 实现见上述文档。

完成修改后更新 Architecture，并执行任务适用的 validate、quality、build 和工作流执行探针。按本次修改对应的源码与输入，分别报告静态检查、构建、执行和业务验收结果。
