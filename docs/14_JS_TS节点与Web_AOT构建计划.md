# VibeFlow JavaScript/TypeScript 节点与跨运行时 AOT 构建计划

本文记录 VibeFlow 面向 JavaScript、TypeScript、浏览器和 Node.js 的通用扩展方案。

> 状态：基础设计已在 JavaScript Target 中落实。0.9 的 Plugin 与 Target 隔离以 [JavaScript/TypeScript 节点与 Web AOT 构建指南](js_aot_build.md) 为准；本文只记录方案形成过程。

VibeFlow 将从主要管理 Python 程序的框架，扩展为能够管理多语言节点、检查统一流程，并为不同运行目标生成普通程序的流程编译框架。

## 一句话方案

把 VibeFlow 的节点描述、流程规划、代码生成和产物打包分开：

- node 和 `base_lib` 可以分别提供 Python、JavaScript 或 TypeScript 实现。
- 流程图先编译成与语言无关的 `BlockPlan`。
- Python emitter 生成 Python execution block。
- JavaScript emitter 生成普通 ESM 模块和直接控制流。
- 独立的 packager 再按需要生成多文件模块、单文件 JS 或 HTML 应用。
- 最终程序是独立生成代码，只包含运行所需的静态控制流和 helper。

## 三个不能混淆的概念

计划中的语言、运行目标和产物形式必须分别表达：

- `language`：实现源码使用 `python`、`javascript` 或 `typescript`。
- `target`：程序最终运行在 `cpython`、`browser` 或 `node`。
- `profile`：构建结果是 `esm-module`、`single-esm`、`web-app` 等形式。

TypeScript 是源码语言，browser 是运行目标，single ESM 是打包形式。三者不能放进同一个字段，也不能由某个构建器的参数替代。

## 目标使用方式

统一使用通用 `build` 入口：

```bash
python run.py build \
  --config project/configs/main.jsonc \
  --target browser \
  --profile esm-module \
  --out-dir dist/
```

需要单文件浏览器模块时：

```bash
python run.py build \
  --config project/configs/main.jsonc \
  --target browser \
  --profile single-esm \
  --out-dir dist/ \
  --entry-name workflow.js
```

需要普通网页时：

```bash
python run.py build \
  --config project/configs/main.jsonc \
  --target browser \
  --profile web-app \
  --html project/web/index.html \
  --out-dir dist/
```

`build-web` 可以保留为 browser target 的便捷别名，但不作为核心架构名称。

## 总体结构

```text
node/base_lib 描述 + 流程图 + 配置 + data schema
                         │
                         ▼
                   校验与契约检查
                         │
                         ▼
                语言无关的 BlockPlan
                         │
              ┌──────────┴───────────┐
              ▼                      ▼
     PythonBlockEmitter     JavaScriptBlockEmitter
              │                      │
              ▼                      ▼
       Python callable        ESM ModuleGraph
                                     │
                                     ▼
                            ArtifactPackager
                                     │
              ┌──────────────────────┼──────────────────┐
              ▼                      ▼                  ▼
         esm-module             single-esm          web-app
```

`BlockPlan` 只在构建期存在。JS 产物中不发布原始流程图，也不要求目标环境解释 `BlockPlan`。

## 需要修改的核心部分

### 1. 将 node、base_lib 和数据类型描述改成与语言无关

统一 descriptor 至少需要描述：

- 逻辑 ID 或 `type_key`。
- `flow_kind`。
- `requires` / `provides`。
- params、输入值和输出值的 schema 或 schema reference。
- 可用实现的源码语言和入口。
- 每个实现支持的运行 target。
- 显式资源依赖和允许的外部包。
- 源文件位置和版本信息。

node 示例：

```json
{
  "type_key": "prompt.compose",
  "flow_kind": "process",
  "requires": [{"type": "chat.messages", "cardinality": "exactly_one"}],
  "provides": [{"key": "prompt.text", "type": "prompt.text"}],
  "implementations": [
    {
      "language": "python",
      "entry": "nodes.prompt_compose",
      "targets": ["cpython"]
    },
    {
      "language": "typescript",
      "entry": "project/nodes/prompt_compose.ts",
      "targets": ["browser", "node"]
    }
  ]
}
```

Python Target 将 `NODE_INFO`、`CONTRACT` 和 registry 事实转换成统一 descriptor；同时存在静态 descriptor 时必须一致。

不能把逻辑数据类型名称直接当作 TypeScript 类型。只有存在 value schema 时，才能生成具体的 TypeScript value type；缺少 schema 时必须生成 `unknown`。如果首版要求完整强类型 `.d.ts`，应先增加通用 data schema registry 或 pipeline boundary schema。

### 2. 为 JavaScript/TypeScript 增加标准节点 ABI

基础调用语义保持为：

```text
run(inputs, params, context?) -> outputs | Promise<outputs>
```

`context` 是可选的运行控制信息，不是业务输入：

```ts
export interface NodeRunContext {
  readonly signal: AbortSignal;
}

export function run(
  inputs: Inputs,
  params: Params,
  context?: NodeRunContext,
): Outputs | Promise<Outputs> {
  context?.signal.throwIfAborted();
  return createOutputs(inputs, params);
}
```

原有二参数 JS/TS 节点仍然合法。

VibeFlow 负责检查：

- TypeScript 类型是否通过。
- 声明的输入输出是否与节点契约一致。
- 是否返回缺失或多余的 output key。
- 节点之间是否出现绕过流程图的直接 import。
- 是否使用目标环境不支持的 API。
- 是否引入隐藏 IO、可变模块级业务状态或其他不允许的副作用。
- 文件大小、复杂度和现有项目质量规则是否满足要求。
- alias、相对路径、重导出和 symlink 是否试图绕过依赖边界。

静态检查是保守的工程门禁，不是安全沙箱。

### 3. 将现有 base_lib 模型语言无关化

JS/TS node 需要共享纯 helper、不可变常量、领域类型和验证器。这些能力应扩展现有 `base_lib`，不能另建一套 Web 专用共享依赖机制。

一个 `base_lib` 是逻辑资源，可以提供多个实现：

```json
{
  "id": "domain_helpers",
  "implementations": [
    {
      "language": "typescript",
      "entry": "project/base_lib/domain_helpers.ts",
      "module_specifier": "@project/base/domain_helpers",
      "targets": ["browser", "node"],
      "dependencies": []
    },
    {
      "language": "python",
      "entry": "base_lib.domain_helpers",
      "targets": ["cpython"],
      "dependencies": []
    }
  ]
}
```

规则如下：

- workflow 启用逻辑 `base_lib id`，而不是随意启用磁盘路径。
- 构建时根据 target 选择唯一匹配实现；缺失或歧义时构建失败。
- node 只能导入当前 workflow 已启用的 `base_lib`。
- `base_lib` 可以依赖其他 `base_lib`，但跨资源依赖必须显式声明。
- 构建只打包 workflow 直接启用的资源及其已声明传递依赖。
- node 不能导入其他 node。
- `base_lib` 不能反向导入 node、plugin、runtime、resource registry 或 host bridge。
- `base_lib` 不能隐藏 IO、宿主调用和可变全局业务状态。
- `import type` 和运行时依赖分别记录和检查。
- browser target 不允许 Node-only API，node target 不允许未适配的 DOM API。

Python Target 负责把 registry 资源转换成 descriptor 事实。JS/TS descriptor 元数据必须静态读取，不执行业务模块。

共享 schema 不能成为第二套 workflow contract。`requires` / `provides` 和 data schema registry 仍是契约真源，TS `base_lib` 只能提供与其一致的类型、验证器和纯 helper。

HTML、CSS 和图片属于入口或静态资产，不是 `base_lib`。宿主桥属于 capability 或 effectful node。构建扩展属于 plugin。

### 4. 把 CompiledBlock 拆成规划与语言代码生成

当前 CompiledBlock 的长期改造方向是：

```text
BlockPlanner
├── PythonBlockEmitter
└── JavaScriptBlockEmitter
```

`BlockPlanner` 负责：

- 分析流程图和执行顺序。
- 划分可编译 region。
- 表达顺序、分支、循环、合流和 nodeset。
- 生成语言无关的 `BlockPlan`。
- 在构建期拒绝目标 emitter 尚不支持的流程结构。

`PythonBlockEmitter` 负责 Python Target 的 compiled execution。

`JavaScriptBlockEmitter` 把 `BlockPlan` 直接生成普通 JavaScript，例如函数调用、`if/else`、有限循环和 `await`。它应生成多个可定位的 block 函数，而不是一个难以调试的巨大函数。

生成代码可以带少量内联 helper，例如：

- envelope 和输出 key 检查。
- 每次调用的 invocation state。
- 错误上下文和可选 trace。
- 取消检查。

这些 helper 是生成程序的一部分，不是通用 graph interpreter。

### 5. 定义顶层 AOT Workflow 调用 ABI

JavaScript emitter 根据 `pipeline.entry_mode` 生成一个入口：

```ts
export interface WorkflowRunOptions {
  signal?: AbortSignal;
}

// entry_mode: "sync"
export function runWorkflow(
  inputs: WorkflowInputs,
  options?: WorkflowRunOptions,
): WorkflowOutputs;

// entry_mode: "async"
export async function runWorkflowAsync(
  inputs: WorkflowInputs,
  options?: WorkflowRunOptions,
): Promise<WorkflowOutputs>;
```

`entry_mode` 缺省为 `sync`。同步计划只包含
`completion: immediate + schedule: inline + executor: current`；包含 suspend、
deferred 或 detached 的 JS 计划必须显式使用异步入口。

公共 ABI 保证：

- import 模块不会自动执行 workflow 或产生业务副作用。
- 模块级只保存不可变定义、节点函数和静态常量。
- 每次调用新建独立的 context、inbox、result、trace、错误状态和异步任务集合。
- 同一模块可以顺序重复调用，也可以并发调用。
- VibeFlow 调度状态按调用隔离；外部依赖和宿主副作用由 Capability 实现管理。
- workflow 完成或失败后，不残留会影响下一次调用的可变状态。
- ABI 和构建 manifest 记录版本。

错误语义统一为：

- 同步入口成功时直接返回 `WorkflowOutputs`，失败时抛出错误。
- 异步入口成功时 Promise 返回 `WorkflowOutputs`，失败时 Promise reject。
- 公共错误提供稳定的 `code`、workflow ID、node/block path 和 `cause`。

取消是协作式取消：

- 调用前 signal 已取消时，不调度任何节点。
- 执行中取消时，停止调度后续节点。
- signal 传给正在等待的异步 node 或 host operation。
- 忽略 signal 的 Promise 和同步死循环无法在同一 JS realm 中被强制终止。
- 取消不等于事务回滚，也不能撤销已经发生的外部副作用。

首版支持 detached 异步任务，但任务必须归属于发起它的单次 `runWorkflow()` 调用，并在该调用返回前完成跟踪和清理。清理失败或超时统一 reject，`AbortSignal` 继续协作式传播；忽略 signal 的 Promise 仍无法在同一 JS realm 中被强制终止。detached 任务不能越过 Workflow ABI 返回继续持有 VibeFlow 调用状态。

顶层 workflow 的公共输出形状必须在语言无关层定义，不能由 JS emitter 自行决定。内部仍使用 envelope 保存 provenance、key 和 cardinality，但公共 `WorkflowOutputs` 只返回按 output `as` 命名的普通业务值：`exactly_one` 返回单值，`optional_one` 无值时省略字段，`all` 返回数组且无结果时为 `[]`。value 有 schema 时生成具体类型，没有 schema 时为 `unknown`。

### 6. 增加通用构建入口和独立打包层

`build` 执行以下流程：

1. 读取项目配置、资源 descriptor 和流程图。
2. 执行 schema、契约、健康度和代码规则检查。
3. 根据 target 选择 node 和 `base_lib` 实现。
4. 检查依赖图、TypeScript 类型和目标环境 API。
5. 将流程图编译成 `BlockPlan`。
6. 用目标 emitter 生成语言模块。
7. 将 emitter 产物交给对应 `ArtifactPackager`。
8. 在 staging 目录完成检查后，原子发布到输出目录。

packager profile：

- `esm-module`：完整、可搬运的 ESM module graph。入口为 `workflow.js`，允许包含内部 block、node 和 `base_lib` 模块；不要求 HTML，不自动启动。
- `single-esm`：将所有内部模块合并成一个本地 JS 文件，不产生隐式本地 JS chunk；source map 可以是单独开发产物，严格单文件发行时可以内联。
- `web-app`：普通 `HTML + JS + assets` 应用。
- `single-html`：把允许内联的 JS、CSS 和小型资源放进一个 HTML，作为后续能力，不阻塞首版。

esbuild 可以作为首个锁定版本的参考 packager，但不能把 esbuild 专用选项写进 `BlockPlan`、node descriptor 或稳定 ABI。

ESM external dependency 表示保留或重写 import specifier。宿主 global 映射属于 classic script、IIFE 或 host adapter 的能力，不属于 `single-esm` 的默认语义。“没有本地 companion chunk”和“没有任何外部依赖”也必须作为两个不同保证。

构建过程必须 fail closed：不支持的节点、控制流、target API、动态 import、worker、WASM 或资源模式，应在构建期给出带源位置的错误，不能生成运行到目标环境才失败的半成品。

### 7. HTML 只是可选的应用入口

只有 `web-app` 和未来的 `single-html` profile 需要 HTML。HTML 负责页面结构、样式入口和加载 bootstrap，不进入 `BlockPlan`，也不是 workflow node。

业务流程由节点图表达；DOM 结构和 HTML 页面保留在 Web 应用层。

### 8. 保持通用 Host Capability 边界

流程逻辑通过明确声明的 Host Capability 使用浏览器、桌面容器或第三方应用能力，例如：

- 存储。
- 网络请求。
- DOM 事件或 UI 通知。
- 文件选择。
- 宿主消息桥。

Host Capability 应按每次 `runWorkflow()` 调用注入，不能使用会污染并发调用的模块级全局 setter。能力声明用于依赖管理、检查和宿主适配，不是安全沙箱。

普通的有限请求采用：

```text
宿主读取并冻结输入
→ 调用 AOT workflow 做有限纯计算
→ 宿主复核并提交结果
```

需要审计宿主副作用时，将调用建模为显式 effectful node 和 Capability。长期程序可以由 Host Extension 驱动重复调用，也可以使用
`entry_mode: async + max_iterations: null + vibeflow.io.receive/send` 表达。

## 首版支持范围

首版 JavaScript emitter 建议支持：

- 同步 JS/TS 节点。
- 返回 Promise 的协作式异步节点。
- 线性流程和 DAG。
- decision 分支。
- 基础合流和 nodeset。
- 标准内部 envelope、公共裸业务值、cardinality 和错误语义。
- 浏览器与 Node 均可使用的纯计算节点。
- 每次调用状态隔离。
- `AbortSignal` 传播和停止后续调度。
- `esm-module` 产物。
- 构建期错误定位、`.d.ts` 和 source map。

如果首个迁移项目必须单文件发行，可以在同一可用里程碑加入 `single-esm`。`web-app` 可在同一阶段随后接入，`single-html` 后置。

Worker 硬中止、事务回滚或只有 Python runtime 才具备的语义，可以分阶段支持。在支持之前必须构建失败并指出具体位置。detached async 则按单次调用跟踪，并在 Workflow ABI 返回前完成清理。

## 实施顺序

### V1：统一 descriptor 和资源模型

- 定义语言无关的 node、`base_lib` 和 data schema descriptor。
- 区分 language、target 和 profile。
- 由 Python Target 把 node、`BaseLibRegistry` 和 registry 资源转换成统一事实。
- 用 Python Target 测试固定现有执行语义。

### V2：抽出语言无关的 BlockPlan

- 将控制流分析从 Python source emitter 中拆出。
- 引入 `BlockPlanner` 和 `BlockPlan`。
- 让现有 Python compiled 路径改用新 planner，但不改变运行行为。

### V3：JS/TS SDK、base_lib 与检查器

- 定义 JS/TS node、`NodeRunContext` 和 `base_lib` 导出规范。
- 增加契约、类型、import、依赖图、目标环境和副作用规则检查。
- 增加 data schema 到 TypeScript 类型的生成规则。
- 建立 Python 与 JS emitter 的语义一致性测试。

### V4a：JavaScript emitter、调用 ABI 与 esm-module

- 生成普通 ESM block 和顶层 `runWorkflow()`。
- 实现每次调用状态隔离、协作式取消、统一错误、内部 envelope 和公共裸业务值输出。
- 输出完整 `esm-module`、`.d.ts`、source map 和 build manifest。
- 不要求 HTML，也不依赖 Python 或浏览器端 VibeFlow runtime。

### V4b：ArtifactPackager

- 接入锁版本的参考 packager backend。
- 支持 `single-esm` 和 `web-app`。
- 明确 external、chunk、动态 import、资源和固定文件名规则。
- staging 构建成功后原子发布。

### V5：通用 Host Capability 与后续发行能力

- 定义按 invocation 注入的 host capability 接口。
- 完善 browser、Node 和宿主容器的目标检查。
- 完善 Host Extension 的依赖、打包和生命周期管理。
- 评估 `single-html`、Worker 隔离和 TS plugin。

## 当前公共边界

必须保持：

- Python Runtime 与 JavaScript AOT 使用同一公共工作流语义。
- Python 与 JS emitter 对共同支持的流程语义保持一致。
- 构建产物可以脱离 Python 和 VibeFlow 安装环境运行。
- 生成代码和 source map 能定位回 workflow、block、node 和 `base_lib`。
- 核心 descriptor 和 BlockPlan 不依赖特定 bundler。

职责边界：

- Python node 的 JavaScript 实现由项目显式提供。
- 浏览器执行 emitter 生成的静态程序，不解释原始 workflow 或通用 Deployment IR。
- Python Runtime 内部值保持现有对象语义；跨语言 ABI 使用可移植数据。
- DOM 结构保留在 Web 应用层，流程节点表达业务行为。
- Capability 和静态检查用于依赖审计，不构成安全沙箱。
- 不协作的 JavaScript、事务回滚和 exactly-once 由宿主执行环境解决。

## 验收标准

### Python Target

- Python Target 的 node、base_lib、Plugin 和 Runtime 测试全部通过。
- registry 事实与静态 descriptor 一致。
- Python compiled execution 保持既定语义。

### Workflow 调用 ABI

- 单纯 import 构建模块不会产生业务副作用。
- 同一模块连续调用两次，两次输出和状态互不污染。
- 两个并发调用的 context、trace、错误和异步任务互不覆盖。
- 调用前已取消时不调度节点。
- 执行中取消时不再调度后续节点，并向异步节点传播 signal。
- workflow 完成、失败或取消后仍可再次调用。
- detached async 按调用隔离，并在返回前完成、失败或以清理超时 reject。

### 构建 profile

- `esm-module` 不要求 HTML，并输出完整可搬运的内部 module graph。
- `esm-module` 可以被 Vite、Webpack 或 esbuild 等下游工具导入。
- `single-esm` 没有隐式本地 JS chunk，并支持固定入口文件名。
- `web-app` 正常输出 HTML、JS 和 assets。
- `single-html` 不阻塞首版。
- profile 之间复用同一个 BlockPlan 和 workflow ABI。
- 构建失败不会在正式输出目录留下半套产物。
- manifest 记录 target、profile、ABI、emitter 和 packager 版本。

### base_lib 和依赖

- 同一逻辑 `base_lib` 的 Python/TS 实现能按 target 正确选择。
- target 不匹配或存在多个歧义实现时构建失败。
- node 导入已启用的 `base_lib` 时成功。
- 导入未启用的 `base_lib` 或直接导入其他 node 时失败。
- 已声明的传递 `base_lib` 依赖会被检查和打包，未声明依赖失败。
- `base_lib` 反向导入 node、plugin、runtime、registry 或 host bridge 时失败。
- source map 能定位回 node 和 `base_lib` 源文件。

### 语义一致性

- 同一组契约、分支、合流、nodeset、有限循环、输出、取消和错误规则用于 emitter 一致性测试。
- pipeline output 的 alias、cardinality 和 value schema 在 Python/JS 中一致；内部 envelope 不泄漏到公共输出。
- 构建产物不读取原始流程图，也不包含通用 VibeFlow 执行器。
- 不支持的 target 特性在构建期给出带源位置的错误。

## 最终结论

VibeFlow 作为多语言流程编译器，在开发期管理 node、`base_lib`、契约、流程结构和质量检查；构建时把同一份流程编译成 Python execution block 或普通 ESM；packager 再生成多文件模块、单文件 JS 或网页。生成程序通过稳定 ABI 接入网页、Node.js、插件、WebView、Worker 和桌面容器。
