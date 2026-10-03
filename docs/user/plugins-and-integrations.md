# 统一插件与宿主集成

所有自定义 Node、Rule、Ruleset、DataSchema、BaseLib、Capability、HostExtension 都由固定插件贡献。Python 用 `Plugin`，JS/TS 用 `definePlugin`；workflow 的 `plugins` 是唯一启用入口。普通模块导入、项目中的声明文件和资源 ID 本身不产生注册效果。

## 选择与配置

```jsonc
{
  "plugins": [{
    "id": "example.model",
    "root": "python_project",
    "source": {"kind": "file", "ref": "plugins/model.py", "export": "plugin"},
    "config": {"mode": "review"}
  }]
}
```

`id` 可选，用来核对插件导出身份。`root` 可选，必须是已登记 workspace root。文件相对该 root；`module/package` 显式定位 Target 已安装的模块。资源列表、契约、规则组合固定，插件配置不生成资源。配置按插件 schema/defaults 校验与合并，并以只读 `context.facts["plugins"]` 提供给 Rule，提供给生命周期工厂；Node 调用 `params` 与 Ruleset 参数独立。

先加载选中插件，再冻结资源集合，之后解析工作流资源引用和有效规则。不同 workflow 的 Catalog、配置与生命周期实例隔离。加载或声明失败直接报告根因，不继续装配未知 Node。禁用项 `enabled: false` 完全不加载；`status: "planned"` 只提供规划记录，不贡献可执行资源。Nodeset 导入文件不能隐式启用插件，所需插件由顶层 workflow 选择。

插件入口及其直接导入模块是受信初始化；规则可诊断已发生的顶层副作用，不能提前阻断或撤销。延迟源码引用的尚未加载实现仍可先检查。只读上下文是维护契约，不是操作系统沙箱。

## 生命周期

一个插件可以同时贡献资源并提供 compiler/runtime 工厂。审查使用 Rule，不恢复 policy hooks。声明、查询和 `review-rules` 不由框架调用生命周期工厂。

```python
from vibeflow.targets.python.sdk import Plugin

class Audit:
    def before_run(self, payload):
        pass
    def dispose(self):
        pass

def create_runtime(context):
    return Audit()  # context["config"] 为本次 workflow 的只读参数

plugin = Plugin(id="example.audit", resources=[], runtime=create_runtime)
```

Python hooks 的名称和参数沿用原生 PluginRegistry 协议。JS/TS 采用 Plugin ABI v3：

```ts
import {definePlugin} from "@vibeflow/plugin";
export const plugin = definePlugin({
  id: "example.audit", resources: [], priority: 30,
  runtime(context) {
    return {beforeRun() {}, afterRun() {}, dispose() {}};
  },
});
```

JS 工厂同步返回实例，runtime hooks 可以按原协议异步完成。每次 workflow 调用创建并释放独立实例；长期宿主职责由原生 HostExtension 承担。compiler 的 beforeCompile/afterCompile 保留原来的编译变换职责。

## Capability 与 Host

```ts
import {defineCapability} from "@vibeflow/plugin";
export const clock = defineCapability({
  id: "example.clock", targets: ["browser", "node"],
  operations: {now: {input_type: "clock.now.request", output_type: "clock.now.result", completion: "suspend"}},
});
```

把此资源放入插件，并贡献其输入输出 DataSchema。Node 显式声明使用的 Capability，宿主通过 options 注入实现，或由启用的 JS HostExtension 提供。`defineHostExtension` 使用 `createHost` 回调或显式延迟源码；固定声明不改变原生 Host 协议。

```bash
python run.py inspect-resources --config <root>/configs/main.jsonc --json
python run.py review-rules --config <root>/configs/main.jsonc --json
```

旧 JSONC 声明扫描、bundle、registry 和生命周期的 module/class 选择不再加载；参见 [一次迁移说明](rule-system-migration.md)。
