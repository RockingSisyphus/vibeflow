# JavaScript/TypeScript 资源与 AOT

用户资源从 `@vibeflow/plugin` 的 SDK 定义。业务声明与执行代码可以放在一起，置于 nodes/；Plugin 提供类型、规则、Schema 或 Capability，须位于独立包内。JS/TS 属于同一执行族，生成物是普通 ESM。

## 业务 Node 与类型

`nodes/text.ts`：

```ts
import {defineNode} from "@vibeflow/plugin";

export const normalize = defineNode({
  id: "example.normalize_text", node_type: "vibeflow.node",
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
    return {normalized_text: normalizedText};
  },
});
```

可绑定执行代码的资源使用具名导出。SDK 自动记录原始声明、实现符号和位置；函数保留在 Target worker 中，不经过 JSON 序列化。Rule 使用 `defineRule({id, check(...) {...}})`，Ruleset 使用 `defineRuleset`。BaseLib 可用 `defineBaseLib({id, implementation(...) {...}})` 定位同文件函数，也可声明整个独立辅助模块。Capability 使用 `defineCapability`。

直接提供 `run`、`check`、`implementation` 时，实际导出的资源对象确定实现身份。若同时显式填写同语言 `source/implementations`，它必须指向同一实现；同文件导出别名可以使用。指向另一文件或另一资源的声明会返回 `RESOURCE.IMPLEMENTATION.CONFLICT`，诊断包含声明和实际实现位置。没有直接函数的延迟定义仍由 `source` 绑定，核对来源不会额外加载延迟模块。

`vibeflow_project.jsonc` 只保存项目及工具链信息：

```jsonc
{"project_target": "javascript", "javascript": {"package_root": ".", "external_packages": []}}
```

workflow 显式启用：

```jsonc
{"plugins": [{"source": {"kind": "file", "ref": "plugins/schemas/plugin.ts"}}], "pipeline": { /* definition_id 引用 nodes/ 中的业务定义 */ }}
```

DataSchema 由选中插件贡献，供公共输入输出、Node 和 Capability 查找。

## SDK 解析与运行协议

发行包和 wheel 包含 SDK 运行文件及类型声明。VibeFlow worker、分析器和构建器统一解析 `@vibeflow/plugin`。发行模板的 `tsconfig.json` 将 TypeScript 的 `paths["@vibeflow/plugin"]` 指向 `../kernel/javascript/sdk.d.ts`。这些文件由内核的同一 SDK 复制生成，受到发行清单保护。wheel 用户可以通过 `importlib.resources.files("vibeflow.targets.javascript.resources")` 定位同一文件。无需另装一个同名 npm SDK。

Node 返回普通对象，key 对应 `provides`。`completion: "immediate"` 使用同步返回；`"suspend"` 返回 Promise，并要求 workflow 的 `pipeline.entry_mode: "async"`。并发使用普通节点、显式分支边和独立的 all 汇合节点，见[普通图并发](graph-concurrency.md)。

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

Browser/Node 平台由 `build --target` 选择。Rule 始终在 Node worker 环境检查，业务平台只是规则上下文资料。浏览器产物保留执行所需的 Node、helper 和 runtime hook，不打包 Rule 或 compiler hook 的专用 Node 依赖。需要不同执行环境时可以分模块，每个资源仍可与自己的实现放在一起。

项目的 TypeScript、ESLint 和业务测试分别验证类型、编码约定和业务结果。插件入口的初始化与延迟实现的检查时机见[加载与检查](plugins-and-integrations.md#原生加载与生命周期)。

## 相关文档

- [Rule 与 Node](rules-and-nodes.md)：规则选择与自定义检查。
- [多文件资源](multifile-resources.md)：支撑文件、库依赖和样式。
- [运行观测](runtime-observation.md)：业务进度更新与日志。
- [Workflow 协同](workflow-coordination.md)：实例身份与跨工作流调用。
