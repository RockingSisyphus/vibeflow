# VibeFlow 开发入口

根据任务选择 `python_project` 或 `javascript_project`。先阅读所选 root 的 README、`vibeflow_project.jsonc` 和已登记的 `ARCHITECTURE.jsonc`，沿 Architecture 的 source 定位并修改真实 Config、Nodeset、Registry、descriptor 或 Node source；生成文档只通过 VibeFlow 命令更新。

按任务阅读规范：

- 修改 workflow、Config 或 edge：[`kernel/docs/user/workflow-and-config.md`](kernel/docs/user/workflow-and-config.md)
- 开发 Python Node 或 BaseLib：[`kernel/docs/user/python-development.md`](kernel/docs/user/python-development.md)
- 开发 JavaScript/TypeScript Node：[`kernel/docs/user/javascript-development.md`](kernel/docs/user/javascript-development.md)
- 开发 Nodeset 或 Loop：[`kernel/docs/user/nodesets-and-loops.md`](kernel/docs/user/nodesets-and-loops.md)
- 开发 Plugin、Capability 或 Host Extension：[`kernel/docs/user/plugins-and-integrations.md`](kernel/docs/user/plugins-and-integrations.md)
- 运行检查或解释结果：[`kernel/docs/user/commands-and-results.md`](kernel/docs/user/commands-and-results.md)

完成修改后更新 Architecture，并执行适用的 validate、quality、build 和工作流执行探针。按结果中的实际证据报告完成状态。
