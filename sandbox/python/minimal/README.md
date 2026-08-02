# 最小拓扑内核示例项目

这个目录演示一个最小业务项目如何只通过以下元素使用内核：

- `nodes.py`：业务 node。
- `base_lib/`：纯函数 helper。
- `plugins.py`：项目策略插件。
- `config.jsonc`：拓扑、nodeset 和插件配置。
- `nodesets.jsonc`：可被其他配置导入的 nodeset 定义。
- `config_with_imports.jsonc`：使用 `nodeset_imports` 复用 `nodesets.jsonc` 的等价配置。

`config.jsonc` 演示 implemented base_lib/plugin 声明；`config_with_imports.jsonc` 额外演示 planned base_lib 占位。implemented base_lib/plugin 都提供了 `BASE_LIB_INFO` / `PLUGIN_INFO`，因此 Mermaid 图和 inspect 输出能展示资源说明。

测试会加载这里的 node，注册到测试 registry，然后用 `run_checked(...)` 运行 `config.jsonc`。
