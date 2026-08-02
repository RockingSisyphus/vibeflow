# 06. Plugin 开发规范

Plugin 用于扩展策略、编译和单次运行 hook，类型固定为 `policy`、`compiler`、`runtime`。Core 只处理 descriptor、selection、依赖和 Planned 状态；Python 与 JavaScript Target 分别绑定自己的实现，不能跨 Target 复用语言对象。

Python Plugin 使用 `effect_scope=trusted`，可以执行 Python IO，并由当前 workflow 项目承担信任责任。JS/TS Plugin 使用 `vibeflow.plugin.v1` 和静态 import/Promise 审计。两者都不能绕过契约、拓扑或内核硬规则。

## Python Target：注册和启用

每个 root 的 `python_project/registry.py` 可以用 `build_plugin_registry()` 声明可用插件：

```python
from vibeflow.targets.python.project import PluginResourceRegistry

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
    registry.register(
        "future_policy",
        module="plugins.future_policy",
        class_name="FuturePolicy",
        plugin_type="policy",
        display_name="Future Policy",
        category="policy",
        description="Planned policy checks.",
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
    },
    {
      "id": "future_policy",
      "status": "planned",
      "config": {"mode": "review"}
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
- `status`：`implemented | planned`，缺省 `implemented`。
- `config` / `settings`：传给插件的设置对象。
- `conflict`：重复插件名时可设为 `replace`。
- `name`：可覆盖插件实例的 `name`。
- `scope`：默认 `project`，会出现在插件描述信息中。

`boundary` 插件类型已移除。

`module` 既可以是模块名，也可以是 `.py` 文件路径。写成路径时，相对 registry 所属 root 目录解析。模板里通常写 `plugins.policy` 或 `plugins/policy.py`。

implemented plugin 必须暴露 `PLUGIN_INFO`，用于实现自检和 inspect 信息。审查图里的资源名称、类别、版本和说明来自 `build_plugin_registry().register(...)`。未在当前 workflow config 中引用的 registered plugin 不会加载、不会注册到 active `PluginRegistry`，也不会执行任何 policy/compiler/runtime hook。workflow 可以把已登记 plugin 标为 `planned`；它会作为 planned resource 进入 Architecture JSON 和 Mermaid/SVG，使项目不再 production-ready，但不会加载实现、注册 active plugin 或执行 hook。实现完成后保留同一 ID 并把使用项改为 `implemented`。

## JavaScript Target：descriptor 与 `vibeflow.plugin.v1`

JS/TS Plugin 在 `vibeflow_project.jsonc` 的 `descriptors.plugins` 中登记，在
workflow 顶层 `plugins` 中按 ID 选择。Descriptor 示例：

```jsonc
{
  "kind": "plugin",
  "id": "project.runtime_audit",
  "type": "runtime",
  "targets": ["browser", "node"],
  "priority": 30,
  "implementations": [
    {
      "language": "typescript",
      "targets": ["browser", "node"],
      "completion": "immediate",
      "source": {
        "kind": "file",
        "ref": "plugins/runtime_audit.ts",
        "export": "createPlugin"
      }
    }
  ],
  "dependencies": [],
  "external_packages": [],
  "config": {"schema": {"type": "object"}, "defaults": {}}
}
```

实现统一导出同步工厂：

```ts
export function createPlugin(context: Readonly<{
  abiVersion: "vibeflow.plugin.v1";
  pluginId: string;
  pluginType: "policy" | "compiler" | "runtime";
  target: "browser" | "node";
  workflowId: string;
  config: Readonly<Record<string, unknown>>;
  signal: AbortSignal;
}>) {
  return {
    beforeRun() {},
    afterRun() {},
    dispose() {},
  };
}
```

- Policy Plugin 使用 `extendPolicy`、`validateNode`、`validateGraph`、`validateNodeset`。
- Compiler Plugin 使用 `beforeCompile`、`afterCompile`、`validateCompiledGraph`。
- Runtime Plugin 使用 run/node/nodeset/block 前后与失败 hook，以及 `dispose`。
- Policy/Compiler Plugin 在 AOT 构建期执行且必须 immediate；Runtime Plugin 按 invocation 创建并释放，suspend hook 只能进入异步 workflow。
- Plugin 只能导入自身、声明的 Plugin 依赖与 external package，不能导入 node、`base_lib`、Host Extension、runtime、registry 或 Capability bridge。
- Runtime Plugin 不得注册长期 listener/timer 或丢弃 Promise。需要跨 workflow 调用的宿主生命周期时使用 Host Extension。

planned Plugin 可以没有 descriptor 或源码，只进入 Architecture JSON 与图形审查；
它不绑定实现、不执行、不打包。implemented Plugin 不能依赖 planned Plugin。

## Plugin 与 Host Extension 的分工

Policy/Compiler Plugin 在构建期检查，Runtime Plugin 只覆盖一次 workflow 调用。
Host Extension 则由 `createWorkflowHost()` 创建，负责跨多次调用的 `start()` /
`stop()`、宿主事件接线和 Capability provider。Host Extension 不是 Plugin，
Runtime Plugin 也不能代替 Host Extension。

Host Extension 由 `descriptors.host_extensions` 登记并由 workflow 顶层
`host_extensions` 选择；具体 descriptor、配置和生命周期规则见
`11_JS_TS与Web_AOT构建指南.md`。

workflow 通过 registry ID 引用 plugin，不内联 `module` / `class`。

插件设置传递规则：

- 加载后实例会有 `plugin.config`。
- 如果插件实现了 `configure(config)`，内核会在注册前调用。
- `config` 和 `settings` 只能写对象。

## Python PolicyPlugin

```python
from vibeflow.targets.python.project import PluginInfo


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
from vibeflow.targets.python.project import PluginInfo


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

## Python CompilerPlugin

```python
from vibeflow.targets.python.project import PluginInfo


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

## Python RuntimePlugin

```python
from vibeflow.targets.python.project import PluginInfo


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

Runtime plugin 适合记录观测数据、附加 trace、统计耗时或上报进度。它的 `trusted` 档位允许真实 IO，但不要用 hook 隐藏本应由 `io` / `data_store` / `document` node 和显式契约表达的业务主流副作用。在 CLI 让渡模式 / `delegate-cli` 中，runtime plugin 可以抛出授权 `SystemExit`：`None` 等于 0，非 bool 整数 `0..255` 原样透传，其他值是框架错误 1。

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

## Python Finding Plugin

policy 插件也可以提供额外健康检查 hook，例如：

```python
from vibeflow.targets.python.project import PluginInfo
from vibeflow.targets.python.quality import HealthFinding


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
