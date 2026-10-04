# 多文件 Node、BaseLib、Plugin 与 Host

从 0.15.0 开发版本开始，四类资源共用显式源码登记、Ruleset 和展示声明。自定义资源仍只通过 workflow 选中的插件启用。Python 使用 `vibeflow.targets.python.sdk`；JS/TS 使用随完整分发包和 wheel 提供的 `@vibeflow/plugin`。Plugin ABI v3、Rule ABI v1、Workflow ABI v4 保持不变。

## 登记实现文件

资源的入口由 SDK 自动定位。`implementation_files` 是支撑文件的明确列表，路径相对调用 SDK 的声明模块，不相对 workflow 配置。它可以包含纯工具、资源管理实现、IO 包装和类型文件；不接受目录或通配符。

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

同一个文件可以定义多个资源。SDK 记录各自的实现符号和声明位置；引用另一个资源不会取得它的源码所有权或权限。传递依赖也必须被登记：同一资源的内部文件列入 `implementation_files`，独立库声明为 BaseLib 并通过 `base_libs` 引用。BaseLib 自己的库依赖使用 `dependencies`。

跨目录文件使用明确相对路径。跨 workspace root 的文件必须处于已经登记的 root；VibeFlow 保留完整 workspace 用于解析，实际检查范围仍由当前命令和实现闭包决定。文件存在本身不会注册任何资源。

## 一个 Host，多个实现文件

Host 本轮由 JS/TS Target 执行。工厂仍立即返回一个具有 `capabilities/start/stop` 的对象。会话状态在工厂中创建，或传给该实例的支撑对象：

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

`Host.dependencies` 继续表示其他宿主实例的依赖关系。同一个 Host 的多个文件不会新增 Host 实例，不改变 Capability 调用、订阅、FIFO、取消、计时器、IO 或回执的调度机制。支撑模块不要保存模块级共享会话状态；两个 `createWorkflowHost()` 调用应创建独立状态。

## 插件声明与生命周期

`Plugin` / `definePlugin` 的 `declaration_rulesets` 检查固定资源声明；`rulesets` 检查 compiler/runtime 生命周期实现。声明入口可以导入它贡献的资源。生命周期只能通过自己的实现文件、明确 `base_libs` 和既有生命周期依赖使用其他实现，不因为包内存在某个 Node 就获得调用该 Node 的权限。

纯资源插件也可以声明 `declaration_rulesets`、`implementation_files` 和 `presentation`。同一插件同时提供 compiler/runtime 时，两者分别记录真实入口，共用它在插件对象上明确选择的支撑文件、规则和库引用。需要不同集合时，Python 使用 `@lifecycle(id=..., type="runtime", ...)` 装饰工厂，再把该工厂加入 `Plugin.resources`；显式 `source` 可延迟绑定。JS 使用 `defineResource` 提供完整的 `kind: "plugin"` Descriptor，其中的 `implementations` 明确填写语言、执行 Target、入口和支撑文件，再加入 `definePlugin.resources`。这个底层构造器不接受 `defineNode` 等高级接口的 `run/source` 简写。

省略 Ruleset 和 `[]` 都表示未选择相应审查规则。常用默认选择为 `vibeflow.process`、`vibeflow.base_lib`、`vibeflow.plugin`、`vibeflow.host_extension` 和 `vibeflow.plugin_declaration`；后两种生命周期默认规则集包含可维护性检查。新建资源应按需要明确填写规则选择。

## 审核与构建

默认规则检查入口、已登记支撑文件及本地传递依赖；未登记本地导入产生 `VF_IMPORT_OWNER`，已登记但缺少资源间授权产生 `VF_IMPORT_LAYER`。值导入、type-only、`.d.ts` 和可静态解析的 `import()/require()` 共用归属资料。BaseLib 保留自己的规则，不继承 Host 的 IO 权限。

每个文件沿用现有默认 500 行及其他可维护性阈值。多个文件合计超过 500 行，只要各文件满足所选规则仍可通过；仅支撑文件超限也会报告。入口协议检查针对真实入口，支撑函数不被要求返回 Host 或 Plugin 工厂对象。

插件入口及其直接导入是受信代码，加载后才能取得固定定义。审核可以诊断已经发生的初始化，不能撤销它。明确延迟的实现仍可在绑定前接受所选导入规则检查。禁用、planned 和未选择插件不会由框架加载；规则预览不调用检查函数、业务入口或生命周期工厂。

```bash
vibeflow validate --workspace vibeflow_config.jsonc --config workflow.jsonc --json
vibeflow quality-check --workspace vibeflow_config.jsonc --json
vibeflow review-rules --workspace vibeflow_config.jsonc --config workflow.jsonc --json
vibeflow inspect-resources --workspace vibeflow_config.jsonc --config workflow.jsonc --json
vibeflow build --workspace vibeflow_config.jsonc --config workflow.jsonc \
  --target browser --profile single-esm --out-dir /tmp/app-workflow
```

AOT 只打包实际执行需要的依赖；登记未引用文件用于审查，不会强制执行它。类型代码按 TS 规则擦除；Rule 和 compiler 专用依赖不会因登记而自动进入浏览器产物。运行仍使用生成模块的原生接口：

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

注册正式架构文档后，`review --output ARCHITECTURE.svg` 生成一张展开图，并更新 `ARCHITECTURE.jsonc`。失败审查不发布新正式图。JSONC 与 SVG 使用同一个 `implementation_graph`，包括资源、入口/支撑文件、实际导入、库依赖、贡献关系、源码归属、加载状态、有效规则及展示来源。Host 和文件位于资源区；资源依赖使用虚线，Workflow 执行连边保持原生表示。

四类资源使用相同 `presentation` 字段：`fill/stroke/text/shape/icon`。颜色必须是六位十六进制值并遵守系统保留色；14 种形状与 Node 相同。使用处只覆盖 `fill/stroke/text`，形状和图标由资源声明选择。顺序为原生默认、资源声明、状态、使用处颜色；真实 `flow_kind`、external、planned 和诊断标记单独保留。

公开形状为 `rect/rounded/stadium/diamond/lean-r/lean-l/fr-rect/cyl/doc/hex/cloud/circle/dbl-circ/trap-b`；序列化后 `diamond` 归一化为 `diam`。实现区显示资源的默认展示，Workflow 中每次 Node 调用仍分别保存调用样式与真实执行身份。

Node 使用调用点 `style`；Host 使用 `host_extensions[].style`；插件使用 `plugins[].style`；BaseLib 使用 `base_lib.modules[].style`。插件颜色覆盖只影响插件包和它的生命周期，不改写包内 Node、Host 或库的声明。

更多 SDK 和宿主调用约定见 [Python 开发](python-development.md)、[JS/TS 开发](javascript-development.md) 和 [插件与宿主集成](plugins-and-integrations.md)。通用 Host 测试不替代业务项目在其生产宿主中的验收。
