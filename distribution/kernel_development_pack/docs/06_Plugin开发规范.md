# 06. Plugin 开发规范

插件用于扩展策略、编译和运行 hook。插件不能绕过内核硬规则；如果插件放宽策略，必须按内核要求声明 relaxation。

## 配置插件

```jsonc
{
  "plugins": [
    {"module": "plugins/policy.py", "class": "PolicyPlugin", "type": "policy"},
    {"module": "plugins/runtime.py", "class": "RuntimePlugin", "type": "runtime"}
  ]
}
```

字段说明：

- `module`：Python 模块路径或 `.py` 文件路径，相对 config 所在目录解析。
- `class`：插件类名，默认 `Plugin`。
- `type`：`policy`、`compiler`、`runtime` 之一。
- `priority`：数字越小越先执行。
- `enabled`：设为 `false` 时跳过。
- `conflict`：重复插件名时可设为 `replace`。

`boundary` 插件类型已移除。

## PolicyPlugin

```python
class PolicyPlugin:
    name = "project_policy"
    priority = 10

    def extend_policy(self, policy):
        return {
            "policy": {
                "base_lib": {
                    "allowed_paths": ["../base_lib"],
                    "allowed_modules": ["base_lib"]
                }
            }
        }
```

放宽限制时必须带 `relaxations`，否则会被拒绝。

Policy plugin 也可以追加健康 finding，例如项目级命名规范、领域语义检查、特殊 nodeset 宽度限制等。

## CompilerPlugin

```python
class CompilerPlugin:
    name = "compile_hook"
    priority = 10

    def before_compile(self, graph):
        return None

    def after_compile(self, graph, compiled):
        return None
```

Compiler plugin 可观察或追加编译期检查，但不能把非法 graph 改成合法 graph 后绕过内核规则。

## RuntimePlugin

```python
class RuntimePlugin:
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

## Finding plugin

policy 插件也可以提供额外健康检查 hook，例如：

```python
from topology_kernel import HealthFinding


class ProjectFindingPlugin:
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
