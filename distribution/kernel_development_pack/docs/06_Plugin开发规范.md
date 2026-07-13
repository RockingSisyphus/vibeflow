# 06. Plugin 开发规范

插件用于扩展策略、编译和运行 hook。插件不能绕过内核硬规则；如果插件放宽策略，必须按内核要求声明 relaxation。

## 注册和启用插件

每个 root 的 `project/registry.py` 可以用 `build_plugin_registry()` 声明可用插件：

```python
from vibeflow import PluginResourceRegistry

def build_plugin_registry() -> PluginResourceRegistry:
    registry = PluginResourceRegistry()
    registry.register(
        "project_policy",
        module="plugins.policy",
        class_name="PolicyPlugin",
        plugin_type="policy",
        display_name="Project Policy",
        category="policy",
        description="Project policy checks.",
        version="0.1.0",
    )
    registry.register(
        "runtime_hook",
        module="plugins.runtime",
        class_name="RuntimePlugin",
        plugin_type="runtime",
        display_name="Runtime Hook",
        category="runtime",
        description="Runtime hook used by selected workflows.",
        version="0.1.0",
    )
    return registry
```

workflow config 再按 id 启用本流程实际使用的插件：

```jsonc
{
  "plugins": [
    {
      "id": "project_policy",
      "config": {"level": "strict"}
    },
    {
      "id": "runtime_hook"
    }
  ]
}
```

registry 字段说明：

- `id`：workflow config 引用的资源 id。
- `module`：Python 模块路径或 `.py` 文件路径，相对所属 root 解析。
- `class`：插件类名，默认 `Plugin`。
- `plugin_type`：`policy`、`compiler`、`runtime` 之一。
- `display_name` / `description`：审查图和报告中的可读资源说明。

config 字段说明：

- `id`：必须引用当前 root `build_plugin_registry()` 中已注册的插件。
- `priority`：数字越小越先执行。
- `enabled`：设为 `false` 时跳过。
- `config` / `settings`：传给插件的设置对象。
- `conflict`：重复插件名时可设为 `replace`。
- `name`：可覆盖插件实例的 `name`。
- `scope`：默认 `project`，会出现在插件描述信息中。

`boundary` 插件类型已移除。

`module` 既可以是模块名，也可以是 `.py` 文件路径。写成路径时，相对 registry 所属 root 目录解析。模板里通常写 `plugins.policy` 或 `plugins/policy.py`。

implemented plugin 必须暴露 `PLUGIN_INFO`，用于实现自检和 inspect 信息。审查图里的资源名称、类别、版本和说明来自 `build_plugin_registry().register(...)`。未在当前 workflow config 中引用的 registered plugin 不会加载、不会注册到 active `PluginRegistry`，也不会执行任何 policy/compiler/runtime hook。planned plugin 不进入 resource registry；需要计划占位时，用 planned node 或 planned nodeset 表达。

旧 inline `module` / `class` 写法短期兼容，但在 registry-backed config 中会产生 legacy warning；新项目不要使用。

插件设置传递规则：

- 加载后实例会有 `plugin.config`。
- 如果插件实现了 `configure(config)`，内核会在注册前调用。
- `config` 和 `settings` 只能写对象。

## PolicyPlugin

```python
from vibeflow import PluginInfo


class PolicyPlugin:
    PLUGIN_INFO = PluginInfo(
        name="project_policy",
        plugin_type="policy",
        display_name="Project Policy",
        category="policy",
        description="Project policy extension point.",
        version="0.1.0",
    )
    name = "project_policy"
    priority = 10

    def extend_policy(self, policy):
        return None
```

放宽限制时必须带 `relaxations`，否则会被拒绝。

示例：

```python
from vibeflow import PluginInfo


class PolicyPlugin:
    PLUGIN_INFO = PluginInfo("temporary_policy", "policy", "Temporary Policy", "policy", "Temporary audited downgrade.", "0.1.0")
    name = "temporary_policy"
    priority = 20

    def extend_policy(self, policy):
        return {
            "policy": {
                "rules": {
                    "downgrades": [
                        {
                            "rule_id": "GRAPH.SMELL.DUPLICATE_LOGIC",
                            "scope": {"object_type": "node"},
                            "to": "warning",
                            "reason": "terminal start/end both return empty mapping",
                            "expires": "2026-12-31"
                        }
                    ]
                }
            },
            "relaxations": [
                {
                    "rule_id": "GRAPH.SMELL.DUPLICATE_LOGIC",
                    "scope": {"object_type": "node"},
                    "reason": "demo terminal nodes intentionally share empty logic",
                    "source": "project policy"
                }
            ]
        }
```

只能放宽 `rules.downgradeable` 中列出的规则。不能通过 plugin 放宽硬错误。

Policy plugin 也可以追加健康 finding，例如项目级命名规范、领域语义检查、特殊 nodeset 宽度限制等。

## CompilerPlugin

```python
from vibeflow import PluginInfo


class CompilerPlugin:
    PLUGIN_INFO = PluginInfo("compile_hook", "compiler", "Compile Hook", "compiler", "Observes compiler hooks.", "0.1.0")
    name = "compile_hook"
    priority = 10

    def before_compile(self, graph):
        return None

    def after_compile(self, graph, compiled):
        return None
```

Compiler plugin 可观察或追加编译期检查，但不能把非法 graph 改成合法 graph 后绕过内核规则。

实际 hook 签名：

- `before_compile(graph)`
- `after_compile(graph, compiled)`

如果 compiler plugin 抛异常，编译失败，健康报告会显示 `GRAPH.COMPILE` 相关错误。

## RuntimePlugin

```python
from vibeflow import PluginInfo


class RuntimePlugin:
    PLUGIN_INFO = PluginInfo("runtime_hook", "runtime", "Runtime Hook", "runtime", "Observes runtime hooks.", "0.1.0")
    name = "runtime_hook"
    priority = 10

    def before_run(self, state):
        return None

    def before_node(self, name, node_type, input_summary):
        return None

    def after_node(self, name, node_type, output_summary):
        return None

    def before_nodeset(self, name, node_type):
        return None

    def after_nodeset(self, name, node_type):
        return None

    def after_run(self, state, trace):
        return None
```

Runtime plugin 适合记录观测数据、附加 trace、统计耗时或上报进度。它不应执行业务副作用来替代 `io` / `data_store` / `document` 节点的显式契约。

实际 runtime hook 签名：

- `before_run(context_dict)`
- `after_run(context_dict, trace_dict)`
- `run_failed(context_dict, trace_dict, message)`
- `before_node(name, node_type, input_summary)`
- `after_node(name, node_type, output_summary)`
- `node_failed(name, node_type, message)`
- `before_nodeset(name, node_type)`
- `after_nodeset(name, node_type)`
- `nodeset_failed(name, node_type, message)`
- `before_block(block_name, block_nodes)`
- `after_block(block_name, block_nodes)`
- `block_failed(block_name, block_nodes, message)`

`after_run` / `run_failed` 收到的 `trace_dict` 是运行摘要，包含 `event_count`、`trace_path` 和 `events_streamed=true`；完整事件流请从 `runtime_trace.jsonl` 逐行读取，不要读取 `trace_dict["events"]`。

这些 hook 是否执行受 `RuntimeOptions` 和 CLI runtime flags 控制，例如 `--node-hooks/--no-node-hooks`。

## Finding plugin

policy 插件也可以提供额外健康检查 hook，例如：

```python
from vibeflow import HealthFinding, PluginInfo


class ProjectFindingPlugin:
    PLUGIN_INFO = PluginInfo("project_findings", "policy", "Project Findings", "policy", "Adds project-specific health findings.", "0.1.0")
    name = "project_findings"
    priority = 20

    def validate_graph(self, graph, compiled):
        return [
            HealthFinding(
                rule_id="PROJECT.GRAPH.WARNING",
                severity="warning",
                object_type="pipeline",
                object_id="pipeline",
                failure_layer="plugin",
                message="project-specific warning",
                suggested_fix_type="fix_config",
            )
        ]
```

插件异常会导致运行拒绝。插件应保持小而明确。

实际健康检查 hook：

- `validate_node(spec, node_cls, metrics_dict)`
- `validate_graph(graph, compiled)`
- `validate_nodeset(nodeset)`

这些 hook 必须返回 `list[HealthFinding]` 或 `tuple[HealthFinding, ...]`；返回其他类型或非 `HealthFinding` 项会产生 plugin error。

## 插件错误排查

- `PLUGIN.LOAD`：模块路径、类名或工厂返回值错误；检查 `module`、`class`、相对路径。
- `PLUGIN.CONFIG.SCHEMA`：`plugins` 字段不是 list，或某一项不是字符串/对象。
- `PLUGIN.POLICY.SHAPE`：`extend_policy` 返回值不是对象，或 `policy` 字段不是对象。
- `PLUGIN.POLICY.RELAXATION_REQUIRED`：插件放宽了限制但没声明完整 `relaxations`。
- `PLUGIN.POLICY.ABSOLUTE_RULE`：试图放宽不可降级规则。
- `PLUGIN.EXECUTION`：插件 hook 抛异常。优先修插件，不要绕过内核校验。
