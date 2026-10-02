# Python 最小示例

`manifests/nodes/` 声明 Node 的业务说明、契约、参数和 Ruleset；`nodes.py` 只实现执行方法。项目通过 `vibeflow_project.jsonc` 装配资源，再通过 `config.jsonc` 组合原生 Node 和 Nodeset。

`base_lib/` 提供纯算术辅助函数。源码由所选 `vibeflow.process` Ruleset 检查；`nodesets.jsonc` 与 `config_with_imports.jsonc` 演示原生组合和导入。检查不执行契约中的示例输入。
