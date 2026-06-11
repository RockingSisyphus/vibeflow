# 最小拓扑内核示例项目

这个目录演示一个最小业务项目如何只通过以下元素使用内核：

- `nodes.py`：业务 node。
- `base_lib/`：纯函数 helper。
- `plugins.py`：项目策略插件。
- `config.jsonc`：拓扑、nodeset 和插件配置。
- `nodesets.jsonc`：可被其他配置导入的 nodeset 定义。
- `config_with_imports.jsonc`：使用 `nodeset_imports` 复用 `nodesets.jsonc` 的等价配置。

测试会加载这里的 node，注册到测试 registry，然后用 `run_checked(...)` 运行 `config.jsonc`。
