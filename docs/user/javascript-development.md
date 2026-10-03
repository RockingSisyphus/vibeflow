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
  run(inputs, params) {
    return {normalized_text: inputs["text.raw"].value.trim().replace(/\s+/g, " ")};
  },
});
export const normalized = defineDataSchema({type_key: "text.normalized", schema: {type: "string"}});
export const plugin = definePlugin({id: "example.text", resources: [normalize, normalized]});
```

可绑定执行代码的资源使用具名导出。SDK 自动记录原始声明、实现符号和位置；函数保留在 Target worker 中，不经过 JSON 序列化。Rule 使用 `defineRule({id, check(...) {...}})`，Ruleset 使用 `defineRuleset`。BaseLib 可用 `defineBaseLib({id, implementation(...) {...}})` 定位同文件函数，也可声明整个独立辅助模块。HostExtension 使用 `defineHostExtension({id, targets, provides, createHost(context) {...}})`，Capability 使用 `defineCapability`。

`vibeflow_project.jsonc` 只保存项目及工具链信息：

```jsonc
{"project_target": "javascript", "javascript": {"package_root": ".", "external_packages": []}}
```

workflow 显式启用：

```jsonc
{"plugins": [{"source": {"kind": "file", "ref": "plugins/text.ts"}}], "pipeline": { /* 原生 type_used 与连边 */ }}
```

支持已安装模块/包、显式导出和已登记的 workspace `root`，不自动安装或发现。Node 自己选择 `rulesets` 和默认 `presentation`；省略或 `[]` 表示未选择 Node 审查规则。Data Schema 也必须由选中插件贡献，供公共输入输出、Node 和 Capability 查找。

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

项目自己的 TypeScript、ESLint 与业务测试仍需显式运行。健康审查不代替业务正确性检查。插件受信入口先初始化，已发生的初始化不能由规则提前阻断或撤销。
