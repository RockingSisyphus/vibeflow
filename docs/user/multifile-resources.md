# 多文件 Node、BaseLib、Plugin 与 Host

Node、BaseLib、Plugin 与 Host 可以将实现拆成多个明确登记的文件，同时选择各自的 Ruleset、颜色和图形。workflow 选中插件后启用这些资源。Python 使用 `vibeflow.targets.python.sdk`，JS/TS 使用完整分发包和 wheel 提供的 `@vibeflow/plugin`。

## 登记实现文件

资源入口由 SDK 自动定位。`implementation_files` 逐一列出支撑文件，路径相对调用 SDK 的声明模块。支撑文件可以包含纯工具、资源管理实现、IO 包装和类型定义；登记项必须是具体文件路径。

例如，将以下两个文件放在同一个目录。`math_support.py` 提供纯计算：

```python
def multiply(left, right):
    return left * right
```

`plugin.py` 声明使用该文件的 Node：

```python
from vibeflow.targets.python.sdk import node, Plugin
from math_support import multiply

@node(type_key="app.model", contract={
    "provides": [{"key": "result", "type": "number", "display_name": "Result"}],
    "output_semantics": {"result": ["The computed number"]},
}, implementation_files=["math_support.py"], rulesets=["vibeflow.process"],
    presentation={"fill": "#add8e6", "shape": "rounded", "icon": "M"})
class Model:
    def run_pure(self, inputs, params):
        return {"result": multiply(2, 3)}

plugin = Plugin(id="app", resources=[Model])
```

同一个文件可以定义多个资源，SDK 记录各自的实现符号和声明位置。传递依赖也逐一登记：同一资源的内部文件列入 `implementation_files`，独立库声明为 BaseLib 并通过 `base_libs` 引用。BaseLib 自己的库依赖使用 `dependencies`。源码所有权与资源引用分别记录，共享库按自己的规则检查。

跨目录文件使用明确相对路径。跨 workspace root 的文件必须处于已登记的 root；VibeFlow 使用完整 workspace 解析位置，当前命令及实现闭包决定实际检查范围。

## 一个 Host，多个实现文件

Host 使用 JS/TS Target。工厂立即返回一个具有 `capabilities/start/stop` 的对象；会话状态在工厂中创建，或传给该实例的支撑对象：

```ts
import {defineHostExtension} from "@vibeflow/plugin";
import {createSession} from "./host_support.ts";
import {library} from "./math.ts";
import type {SessionValue} from "./types.d.ts";

export const host = defineHostExtension({
  id: "app.host", targets: ["node", "browser"], provides: ["app.session"],
  base_libs: ["app.math"],
  implementation_files: ["host_support.ts", "types.d.ts"],
  rulesets: ["vibeflow.host_extension"],
  presentation: {fill: "#ffd9bb", shape: "hex", icon: "H"},
  createHost(context) {
    const session = createSession(context.signal);
    return {
      capabilities: {"app.session": {next(value: SessionValue) {
        return session.next(library.implementation(value));
      }}},
      start() { return session.start(); },
      stop() { return session.stop(); },
    };
  },
});
```

把 `host`、BaseLib 和 Capability 加入固定 `definePlugin({id, resources})` 导出，再选中插件和 Host：

```jsonc
{
  "plugins": [{"source": {"kind": "file", "ref": "plugin.ts", "export": "plugin"}}],
  "host_extensions": [{"id": "app.host", "style": {"fill": "#ffeebb"}}],
  "rulesets": ["vibeflow.workflow"],
  "pipeline": { /* 原生 Node 与连边 */ }
}
```

`Host.dependencies` 表示其他宿主实例的依赖关系。同一个 Host 的多个文件共用一个工厂和实例，Capability 调用、订阅、FIFO、取消、计时器、IO 与回执按原来的时机处理。将会话状态保存在实例中，使两次 `createWorkflowHost()` 调用创建独立状态。

## 插件声明与生命周期

`Plugin` / `definePlugin` 的 `declaration_rulesets` 检查固定资源声明；`rulesets` 检查 compiler/runtime 生命周期实现。声明入口可以导入它贡献的资源；生命周期使用自己登记的文件、`base_libs` 及生命周期依赖来表达实现关系。

纯资源插件也可以声明 `declaration_rulesets`、`implementation_files` 和 `presentation`。同一插件同时提供 compiler/runtime 时，两者分别记录入口，共用插件对象选择的支撑文件、规则和库引用。

需要不同集合时，Python 使用 `@lifecycle(id=..., type="runtime", ...)` 装饰工厂，再把该工厂加入 `Plugin.resources`；显式 `source` 支持延迟绑定。JS 使用 `defineResource` 提供完整的 `kind: "plugin"` 声明，在 `implementations` 中填写语言、执行 Target、入口和支撑文件，再加入 `definePlugin.resources`。

省略 Ruleset 和 `[]` 都表示未选择相应审查规则。常用选择如下，其中各默认规则集均包含可维护性检查：

| 检查对象 | 声明字段 | 常用 Ruleset |
| --- | --- | --- |
| Process Node | `rulesets` | `vibeflow.process` |
| BaseLib | `rulesets` | `vibeflow.base_lib` |
| compiler/runtime 生命周期 | `rulesets` | `vibeflow.plugin` |
| Host | `rulesets` | `vibeflow.host_extension` |
| 插件包声明 | `declaration_rulesets` | `vibeflow.plugin_declaration` |

## 审核与构建

所选默认规则检查入口、登记支撑文件及本地传递依赖。未登记本地导入产生 `VF_IMPORT_OWNER`，已登记但缺少资源间授权产生 `VF_IMPORT_LAYER`；修复时分别补齐文件归属或资源引用。值导入、type-only、`.d.ts` 和可静态解析的 `import()/require()` 使用同一归属资料。BaseLib 的规则按库自身声明执行。

默认可维护性规则逐文件检查：450–500 行进入警告区间，超过 500 行报错，其余大小和复杂度阈值按有效规则参数执行。多个文件分别满足限制时可以通过，文件总行数可以超过 500；支撑文件超限也会定位到该文件。入口协议检查真实工厂或执行入口，支撑函数按自己的源码职责接受检查。

插件声明加载、延迟源码及规则预览遵循[加载与检查](plugins-and-integrations.md#加载与检查)中的顺序。

```bash
vibeflow validate --workspace vibeflow_config.jsonc --config workflow.jsonc --json
vibeflow quality-check --workspace vibeflow_config.jsonc --json
vibeflow review-rules --workspace vibeflow_config.jsonc --config workflow.jsonc --json
vibeflow inspect-resources --workspace vibeflow_config.jsonc --config workflow.jsonc --json
vibeflow build --workspace vibeflow_config.jsonc --config workflow.jsonc \
  --target browser --profile single-esm --out-dir /tmp/app-workflow
```

AOT 打包实际执行需要的依赖，登记但未引用的文件作为审查资料。TS 类型在构建时擦除；浏览器产物保留运行所需代码，Rule 和 compiler 专用依赖留在检查与编译环境。生成模块提供原生宿主接口：

```js
const host = workflow.createWorkflowHost();
await host.start();
try {
  const result = host.runWorkflow({}); // 异步 workflow 使用 runWorkflowAsync
} finally {
  await host.stop();
}
```

## 图形与 Architecture

登记 Architecture 文档后，`review --output ARCHITECTURE.svg` 生成一张展开图，并更新 `ARCHITECTURE.jsonc`。JSONC 与 SVG 使用同一个 `implementation_graph`：前者便于 AI 查询声明、文件、关系和来源，后者展示工作流及资源区。Host 与实现文件位于资源区，资源依赖使用虚线，Workflow 执行连边使用原生表示。

Architecture 记录入口/支撑文件、实际导入、库依赖、插件贡献、源码归属、加载状态、有效规则和展示来源，可沿文件位置继续定位真实实现。

四类资源使用相同 `presentation` 字段：`fill/stroke/text/shape/icon`。颜色必须是六位十六进制值并遵守系统保留色；14 种形状与 Node 相同。使用处只覆盖 `fill/stroke/text`，形状和图标由资源声明选择。顺序为原生默认、资源声明、状态、使用处颜色；真实 `flow_kind`、external、planned 和诊断标记单独保留。

公开形状为 `rect/rounded/stadium/diamond/lean-r/lean-l/fr-rect/cyl/doc/hex/cloud/circle/dbl-circ/trap-b`；序列化后 `diamond` 归一化为 `diam`。实现区显示资源的默认展示，Workflow 中每次 Node 调用仍分别保存调用样式与真实执行身份。

Node 使用调用点 `style`；Host 使用 `host_extensions[].style`；插件使用 `plugins[].style`；BaseLib 使用 `base_lib.modules[].style`。插件颜色覆盖只影响插件包和它的生命周期，不改写包内 Node、Host 或库的声明。

SDK 与宿主调用约定见[Python 开发](python-development.md)、[JS/TS 开发](javascript-development.md)和[插件与宿主集成](plugins-and-integrations.md)。Host 的业务行为通过项目测试及实际宿主运行验证。
