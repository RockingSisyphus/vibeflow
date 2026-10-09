# 统一插件与宿主集成

固定插件贡献自定义 Node、Rule、Ruleset、DataSchema、BaseLib、Capability 和 HostExtension。Python 用 `Plugin`，JS/TS 用 `definePlugin`；workflow 的 `plugins` 显式选择本次使用的插件及资源。

默认规则和资源由内置插件自动接入，Config 无需声明。它们与外部插件共用 Catalog、冲突诊断和实现绑定；报告记录实际声明及实现来源。资源存在与规则选择是独立的，`rulesets=[]` 不触发默认检查。

## 选择与配置

```jsonc
{
  "plugins": [{
    "id": "example.model",
    "root": "python-project",
    "source": {"kind": "file", "ref": "plugins/model.py", "export": "plugin"},
    "config": {"mode": "review"}
  }]
}
```

`id` 可选，用来核对插件导出身份。`root` 可选，取已登记的 workspace root ID。文件相对该 root；`module/package` 显式定位 Target 已安装的模块。插件导出固定资源列表、契约和规则组合；`config` 按插件 schema/defaults 合并，提供给 Rule 的只读 `context.facts["plugins"]` 及生命周期工厂。Node 调用 `params` 和 Ruleset 参数分别配置。

不同 workflow 拥有独立的资源集合、插件配置和生命周期实例。`enabled: false` 跳过加载；`status: "planned"` 保存规划记录。Nodeset 的结构由导入文件提供，所需插件统一在顶层 workflow 选择。

## 加载与检查

VibeFlow 按以下顺序装配当前 workflow：

1. 读取插件选择，加载受信入口及其直接导入，取得固定定义。
2. 校验资源、配置和冲突，冻结本次资源集合。
3. 解析工作流引用和有效 Ruleset，再执行对应阶段的检查。
4. 绑定延迟实现，进入原生构建或运行；生命周期工厂在各自阶段创建实例。

加载或声明失败时，报告该根因并停止后续装配。已初始化源码仍接受所选规则审查，诊断描述已经发生的行为；它不会撤销初始化。尚未加载的延迟实现及闭包在所选 import 检查失败后保持未加载。规则与插件是受信扩展代码；只读上下文保证公共分析资料的使用约定，执行进程仍具有普通代码的文件系统能力。

资源查询与 `review-rules` 取得声明并展示选择，框架不调用检查函数、业务执行入口或生命周期工厂。

## 生命周期

一个插件可以同时贡献资源并提供 compiler/runtime 工厂。`declaration_rulesets` 检查插件声明源码，`rulesets` 检查生命周期实现；两者分别明确选择。常用选择是 `vibeflow.plugin_declaration` 与 `vibeflow.plugin`。

```python
from vibeflow.targets.python.sdk import Plugin

class Audit:
    def before_run(self, payload):
        pass
    def dispose(self):
        pass

def create_runtime(context):
    return Audit()  # context["config"] 为本次 workflow 的只读参数

plugin = Plugin(id="example.audit", resources=[], runtime=create_runtime,
                rulesets=["vibeflow.plugin"],
                declaration_rulesets=["vibeflow.plugin_declaration"])
```

Python 实例使用 snake_case hooks，如 `before_run(inputs)`、`after_run(result, trace)`、`before_compile(graph)` 和 `after_compile(graph, compiled)`，通过 `dispose()` 释放资源。JS/TS 采用 Plugin ABI v3，使用 camelCase hooks：

```ts
import {definePlugin} from "@vibeflow/plugin";
export const plugin = definePlugin({
  id: "example.audit", resources: [], priority: 30,
  rulesets: ["vibeflow.plugin"], declaration_rulesets: ["vibeflow.plugin_declaration"],
  runtime(context) {
    return {beforeRun() {}, afterRun() {}, dispose() {}};
  },
});
```

JS 工厂同步返回实例，runtime hooks 可以按原协议异步完成。每次 workflow 调用创建并释放独立实例；长期宿主职责由原生 HostExtension 承担。compiler 的 beforeCompile/afterCompile 保留原来的编译变换职责。

Plugin 可以通过 `implementation_files` 登记支撑源码，通过 `base_libs` 引用独立库，并设置默认 `presentation`。独立生命周期工厂可以各自声明这些字段。具体代码形式见[插件声明与生命周期](multifile-resources.md#插件声明与生命周期)。

## Capability 与 Host

```ts
import {defineCapability} from "@vibeflow/plugin";
export const clock = defineCapability({
  id: "example.clock", targets: ["browser", "node"],
  operations: {now: {input_type: "clock.now.request", output_type: "clock.now.result", completion: "suspend"}},
});
```

把此资源放入插件，并贡献其输入输出 DataSchema。Node 显式声明使用的 Capability，宿主通过 options 注入实现，或由启用的 JS HostExtension 提供。`defineHostExtension` 使用 `createHost` 回调或显式延迟源码；固定声明不改变原生 Host 协议。

Host 在 `host_extensions` 中选择，通常明确使用 `vibeflow.host_extension` Ruleset。入口及支撑文件共同实现一个 Host；每次创建时持有独立会话状态。`implementation_files` 登记内部文件，`base_libs` 引用共享库，`dependencies` 表达其他 Host 实例依赖。多文件示例、逐文件检查和架构资源区见[一个 Host，多个实现文件](multifile-resources.md#一个-host多个实现文件)。

选择统一写在 workflow.host_extensions；旧项目级 Host 字段会返回迁移错误。

```bash
python run.py inspect-resources --config <root>/configs/main.jsonc --json
python run.py review-rules --config <root>/configs/main.jsonc --json
```

升级已有项目时，按[一次迁移说明](rule-system-migration.md)把旧登记改为代码插件与显式选择。
