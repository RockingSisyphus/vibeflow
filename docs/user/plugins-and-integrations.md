# Plugin 与宿主集成

Plugin 扩展治理、编译或单次运行 hook；BaseLib 提供纯 helper；JavaScript Capability 与 Host Extension 连接宿主能力。

## Python Plugin

Plugin 使用 `PluginInfo` 描述资源，并实现对应 hook：

```python
from vibeflow.targets.python.project import PluginInfo


class Plugin:
    PLUGIN_INFO = PluginInfo(
        name="example_policy",
        plugin_type="policy",
        display_name="Example policy",
        category="policy",
        description="Adds project-specific structural findings.",
        version="1.0.0",
    )
    name = "example_policy"
    priority = 20

    def extend_policy(self, policy):
        return {"policy": {"maintainability": {"max_call_chain_length": 6}}}
```

Python 支持 `policy`、`compiler`、`runtime` 三类 Plugin。项目 Registry 登记可用资源，workflow 通过 `plugins[].id` 选择本次使用项：

```python
from vibeflow.targets.python.project import PluginResourceRegistry


def build_plugin_registry() -> PluginResourceRegistry:
    registry = PluginResourceRegistry()
    registry.register(
        "example_policy",
        module="plugins.example_policy",
        class_name="Plugin",
        plugin_type="policy",
        display_name="Example policy",
        category="policy",
        description="Adds project-specific structural findings.",
        version="1.0.0",
    )
    return registry
```

workflow 只启用显式选择的 Plugin：

```jsonc
"plugins": [{"id": "example_policy", "config": {}}]
```

Runtime Plugin 围绕一次 workflow run 执行 hook；Plugin 是 `trusted` 边界，但仍遵守 Core 不可降级规则、契约和拓扑。

## JavaScript Plugin

Descriptor 指向同步工厂 `createPlugin(context)`：

```jsonc
{
  "kind": "plugin",
  "id": "example.runtime_audit",
  "type": "runtime",
  "targets": ["browser", "node"],
  "priority": 30,
  "implementations": [{
    "language": "typescript",
    "targets": ["browser", "node"],
    "completion": "immediate",
    "source": {"kind": "file", "ref": "plugins/runtime_audit.ts", "export": "createPlugin"}
  }],
  "dependencies": [],
  "external_packages": [],
  "config": {"schema": {"type": "object"}, "defaults": {}}
}
```

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

每次 workflow 调用创建独立 Runtime Plugin 实例并在结束时释放。长期宿主生命周期使用 Host Extension。

## Capability

Capability 定义逐调用注入的宿主操作：

```jsonc
{
  "kind": "capability",
  "id": "example.clock",
  "targets": ["browser", "node"],
  "display_name": "Clock",
  "description": "Reads the host clock.",
  "operations": {
    "now": {
      "input_type": "clock.now.request",
      "output_type": "clock.now.result",
      "completion": "suspend"
    }
  }
}
```

输入输出类型需要 Data Schema。Node descriptor 同时声明 Capability ID 和 operation；宿主通过 workflow 调用 options 注入实现，或由启用的 Host Extension 提供。

## Planned 资源

workflow 可把 Plugin 或 Host Extension 标为 `planned`，使其进入 Architecture 和审核图。planned 资源不绑定源码、不执行 hook、不提供 Capability，也不进入 bundle。

验证资源：

```bash
python run.py validate --config <root>/configs/main.jsonc
python run.py quality --path <root>
python run.py build --config javascript_project/configs/main.jsonc --target node --profile esm-module --out-dir javascript_project/build/node
```
