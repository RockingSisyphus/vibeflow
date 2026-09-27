# VibeFlow 开发入口

先从 `vibeflow_config.jsonc` 确定任务所属的实际 root 和 Target；`python_project`、`javascript_project` 只是最小项目的示例路径。阅读所选 root 的 README、`vibeflow_project.jsonc`、已登记的 `ARCHITECTURE.jsonc`，以及目标目录中更具体的 `AGENTS.md`。沿 Architecture 的 source 定位并修改真实 Config、Nodeset、Registry、descriptor 或 Node source；生成文档只通过 VibeFlow 命令更新。

按任务阅读规范：

- 修改 workflow、Config 或 edge：[`kernel/docs/user/workflow-and-config.md`](kernel/docs/user/workflow-and-config.md)
- 开发 Python Node 或 BaseLib：[`kernel/docs/user/python-development.md`](kernel/docs/user/python-development.md)
- 开发 JavaScript/TypeScript Node：[`kernel/docs/user/javascript-development.md`](kernel/docs/user/javascript-development.md)
- 开发 Nodeset 或 Loop：[`kernel/docs/user/nodesets-and-loops.md`](kernel/docs/user/nodesets-and-loops.md)
- 开发 Plugin、Capability 或 Host Extension：[`kernel/docs/user/plugins-and-integrations.md`](kernel/docs/user/plugins-and-integrations.md)
- 运行检查或解释结果：[`kernel/docs/user/commands-and-results.md`](kernel/docs/user/commands-and-results.md)

多个入口承诺相同业务语义时，核对它们是否在实际执行路径上汇入共享 Node/Nodeset；边界适配保留输入和错误身份。具体设计与 Target 实现见上述文档。

完成修改后更新 Architecture，并执行任务适用的 validate、quality、build 和工作流执行探针。分别报告静态检查、构建、执行与业务验收的实际证据；历史报告或局部 PASS 不代表当前代码已完成。
