# JavaScript/TypeScript 资源与 AOT

用户资源从 `@vibeflow/plugin` 的 SDK 定义。声明与执行代码可以放在一起；workflow 显式选择固定插件对象。JS/TS 属于同一执行族，生成物继续是普通 ESM，使用原生 Workflow ABI v4。

## Node 与固定插件

`plugins/text.ts`：

```ts
import {definePlugin, defineNode, defineDataSchema} from "@vibeflow/plugin";

export const normalize = defineNode({
  type_key: "example.normalize_text",
  display_name: "Normalize text", description: "Normalizes supplied text.",
  rulesets: ["vibeflow.process"],
  contract: {
    requires: [{type: "text.raw", cardinality: "exactly_one", display_name: "Raw text"}],
    provides: [{key: "normalized_text", type: "text.normalized", display_name: "Normalized text"}],
    input_semantics: {"text.raw": ["Text before normalization."]},
    output_semantics: {normalized_text: ["Normalized whitespace."]},
  },
  run(inputs, params, context) {
    const normalizedText = inputs["text.raw"].value.trim().replace(/\s+/g, " ");
    context.updateInfo([{
      id: "normalize", characters: normalizedText.length,
      message: "文本规范化完成",
    }]);
    return {normalized_text: normalizedText};
  },
});
export const normalized = defineDataSchema({type_key: "text.normalized", schema: {type: "string"}});
export const raw = defineDataSchema({type_key: "text.raw", schema: {type: "string"}});
export const plugin = definePlugin({id: "example.text", resources: [normalize, raw, normalized],
  declaration_rulesets: ["vibeflow.plugin_declaration"]});
```

可绑定执行代码的资源使用具名导出。SDK 自动记录原始声明、实现符号和位置；函数保留在 Target worker 中，不经过 JSON 序列化。Rule 使用 `defineRule({id, check(...) {...}})`，Ruleset 使用 `defineRuleset`。BaseLib 可用 `defineBaseLib({id, implementation(...) {...}})` 定位同文件函数，也可声明整个独立辅助模块。HostExtension 使用 `defineHostExtension({id, targets, provides, createHost(context) {...}})`，Capability 使用 `defineCapability`。

直接提供 `run`、`check`、`implementation` 或 `createHost` 时，实际导出的资源对象确定实现身份。若同时显式填写同语言 `source/implementations`，它必须指向同一实现；同文件导出别名可以使用。指向另一文件或另一资源的声明会返回 `RESOURCE.IMPLEMENTATION.CONFLICT`，诊断包含声明和实际实现位置。没有直接函数的延迟定义仍由 `source` 绑定，核对来源不会额外加载延迟模块。

`vibeflow_project.jsonc` 只保存项目及工具链信息：

```jsonc
{"project_target": "javascript", "javascript": {"package_root": ".", "external_packages": []}}
```

workflow 显式启用：

```jsonc
{"plugins": [{"source": {"kind": "file", "ref": "plugins/text.ts"}}], "pipeline": { /* 原生 type_used 与连边 */ }}
```

支持已安装模块/包、显式导出和已登记的 workspace `root`。Node 自己选择 `rulesets` 和默认 `presentation`；省略或 `[]` 表示未选择 Node 审查规则。DataSchema 由选中插件贡献，供公共输入输出、Node 和 Capability 查找。

## 多文件资源

`defineNode`、`defineBaseLib`、`defineHostExtension` 和 `definePlugin` 接受 `implementation_files`，逐一登记支撑文件；路径相对调用 SDK 的声明模块。支撑文件可以包含运行实现、纯工具或类型。共享库使用 BaseLib，并由使用它的资源明确填写 `base_libs`。

`presentation` 为四类资源设置颜色、形状和图标，正式 Architecture 与 SVG 保存有效值及来源。默认可维护性规则逐文件检查 500 行上限。Host 保留一个工厂和实例，支撑对象共享该实例持有的状态。type-only 导入、生命周期分文件及使用处颜色覆盖见[多文件资源](multifile-resources.md)。

## SDK 解析与运行协议

发行包和 wheel 包含 SDK 运行文件及类型声明。VibeFlow worker、分析器和构建器统一解析 `@vibeflow/plugin`。发行模板的 `tsconfig.json` 将 TypeScript 的 `paths["@vibeflow/plugin"]` 指向 `../kernel/javascript/sdk.d.ts`。这些文件由内核的同一 SDK 复制生成，受到发行清单保护。源码沙箱的 tsconfig 直接引用内核资源目录；wheel 用户可以通过 `importlib.resources.files("vibeflow.targets.javascript.resources")` 定位同一文件。无需另装一个同名 npm SDK。

Node 返回普通对象，key 对应 `provides`。`completion: "immediate"` 使用同步返回；`"suspend"` 返回 Promise，并要求 workflow 的 `pipeline.entry_mode: "async"`。调度、TaskPlan、Capability 和 Host 协议保持原有机制。

```bash
npm ci --prefix javascript_project
python run.py validate --config javascript_project/configs/main.jsonc
python run.py build --config javascript_project/configs/main.jsonc --target node --profile esm-module --out-dir javascript_project/build/node
```

同步 workflow 导出 `runWorkflow(inputs, options)`；异步导出 `runWorkflowAsync(inputs, options)`。例如：

```js
import {runWorkflow} from "./build/node/workflow.js";
const result = runWorkflow({request: {message: "hello"}});
```

Browser/Node 平台由 `build --target` 选择。Rule 始终在 Node worker 环境检查，业务平台只是规则上下文资料。浏览器产物保留执行所需的 Node、helper、Host 和 runtime hook，不打包 Rule 或 compiler hook 的专用 Node 依赖。需要不同执行环境时可以分模块，每个资源仍可与自己的实现放在一起。

项目的 TypeScript、ESLint 和业务测试分别验证类型、编码约定和业务结果。插件入口的初始化与延迟实现的检查时机见[加载与检查](plugins-and-integrations.md#加载与检查)。

## 在业务 Node 中更新进度

上例使用运行器提供的第三个参数 `context`，通过 `context.updateInfo` 提交信息，并照常返回 Node 输出。异步 Node 在 `await` 业务操作后使用同一接口；训练循环可逐轮更新。Node 的规则选择与原生执行协议沿用已有声明。

传入普通 JSON 对象数组，每次调用替换全部 `info`；`[]` 清空信息。缓存会在下次刷新、状态变化或结束时发布，默认间隔为 60000 毫秒，运行选项 `statusIntervalMs` 可调整。Node.js 写入状态文件，浏览器通过 `onStatus` 向宿主提供快照。文件路径、Host 会话及完整格式见[运行日志与状态接口](runtime-observation.md)。
