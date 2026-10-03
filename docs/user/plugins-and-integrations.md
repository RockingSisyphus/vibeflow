# Plugin 与宿主集成

Plugin 扩展治理、编译或单次运行 hook；BaseLib 提供纯 helper；JavaScript Capability 与 Host Extension 连接宿主能力。

## 领域规则与资源包

审查扩展使用 Rule/Ruleset，不再提供 policy validate hooks。插件包可以同时贡献完整 Node、Rule、Ruleset 和原生资源，Node 选中规则即按需加载；参考 [Rule、Ruleset 与 Node 声明](rules-and-nodes.md)。

## Python Plugin

生命周期插件保留 compiler/runtime 两类。使用 PluginInfo 描述资源，通过 PluginResourceRegistry 登记，workflow 的 plugins 显式选择本次生命周期实例。编译变换与运行 hook 不承担领域审查，也不会因同包 Ruleset 被选择而自动开启。

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
  abiVersion: "vibeflow.plugin.v2";
  pluginId: string;
  pluginType: "compiler" | "runtime";
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
