# JavaScript/TypeScript 节点与 Web AOT 构建指南

VibeFlow 可以把同一份 workflow 编译为普通 JavaScript ESM。生成物在运行时不需要 Python，也不需要浏览器或 Node.js 安装 VibeFlow。同步 workflow 导出 `runWorkflow()`，显式异步 workflow 导出 `runWorkflowAsync()`。

本文描述当前已经实现的公开配置、节点 ABI、Workflow ABI 和构建命令。早期方案和取舍记录见 [JavaScript/TypeScript 节点与跨运行时 AOT 构建设计记录](14_JS_TS节点与Web_AOT构建计划.md)，实际使用应以本文和 CLI 为准。

可运行的完整工程见源码仓库中的
[`examples/js_aot_minimal`](https://github.com/RockingSisyphus/vibeflow/tree/main/examples/js_aot_minimal)。
需要检查真实 TypeScript node、`base_lib`、分支/合流、nodeset、有限循环、
同步/异步入口、Capability、Port、调用隔离、取消、构建 profile 和非法依赖时，可运行
[`examples/typescript_sandbox`](https://github.com/RockingSisyphus/vibeflow/tree/main/examples/typescript_sandbox)。

## 1. 适用范围

当前 AOT 构建支持：

- JavaScript 和 TypeScript node；
- JavaScript 和 TypeScript `base_lib`；
- `browser` 和 `node` target；
- `esm-module`、`single-esm` 和 `web-app` profile；
- 顶层输入输出 Schema、Capability 注入、Host Extension、trace、取消和调用级异步任务清理；
- 条件、合流、nodeset、有限或永久循环、原生 Port 及其他可移植的 VibeFlow 执行语义。

AOT 是构建过程，不是把 VibeFlow 解释器搬进浏览器。emitter 会把每个
workflow、nodeset 和 loop 展开成具体函数，把节点调用、路由、条件和合流
写成该流程专用的静态控制流；产物只保留 ABI、Schema、错误、trace、取消和
Capability 等通用 helper，不携带原始流程图或通用 graph walker。构建后的
模块不会读取原始 workflow，也不会自动开始执行。

## 2. 工程结构与项目配置

一种推荐目录如下：

```text
vibeflow_config.jsonc
project/
├── vibeflow_project.jsonc
├── package.json
├── package-lock.json
├── configs/
├── nodes/
├── base_lib/
├── manifests/
│   ├── nodes/
│   ├── base_lib/
│   ├── data/
│   ├── capabilities/
│   └── host_extensions/
├── host_extensions/
└── web/
```

在 `project/vibeflow_project.jsonc` 中登记五类 descriptor 和项目自己的 JavaScript 工具链：

```jsonc
{
  "descriptors": {
    "nodes": ["manifests/nodes"],
    "base_lib": ["manifests/base_lib"],
    "data_schemas": ["manifests/data"],
    "capabilities": ["manifests/capabilities"],
    "host_extensions": ["manifests/host_extensions"]
  },
  "javascript": {
    "package_root": ".",
    "external_packages": []
  }
}
```

路径相对于 VibeFlow project root。每个目录会递归读取 `*.jsonc`；每个文件只能描述一个资源。配置过但不存在的目录、越出 project root 的路径和符号链接都会使构建失败。

`javascript.package_root` 是包含 `package.json`、lockfile 和项目本地 `node_modules` 的目录。`external_packages` 中的包不会进入 bundle，而是保留给下游 bundler 或实际宿主解析。

`descriptors.host_extensions` 只登记当前 project 可用的 Host Extension
descriptor。具体 workflow 在自己的顶层 `host_extensions` 中选择实际使用的
扩展；没有被当前 workflow 引用的扩展不会进入构建。旧项目仍可用
`javascript.host_extensions` 提供默认选择，但这是兼容字段；只要 workflow
显式写了 `host_extensions`，即使值是空列表，也会完全覆盖该默认值。

## 3. 五类 JSONC descriptor

### 3.1 Node descriptor

```jsonc
{
  "kind": "node",
  "type_key": "example.greet",
  "display_name": "Build greeting",
  "category": "example",
  "description": "Builds a greeting.",
  "version": "1.0.0",
  "flow_kind": "process",
  "purity": "pure",
  "external": false,
  "tags": [],
  "contract": {
    "requires": [
      {
        "type": "name.text",
        "cardinality": "exactly_one",
        "display_name": "Name"
      }
    ],
    "provides": [
      {
        "key": "greeting",
        "type": "greeting.text",
        "display_name": "Greeting"
      }
    ],
    "input_semantics": {},
    "output_semantics": {},
    "params_schema": {
      "prefix": {
        "type": "string"
      }
    },
    "params_defaults": {
      "prefix": "Hello"
    },
    "output_schema": {
      "greeting": {
        "type": "string"
      }
    },
    "examples": []
  },
  "implementations": [
    {
      "language": "typescript",
      "targets": ["browser", "node"],
      "completion": "suspend",
      "source": {
        "kind": "file",
        "ref": "nodes/greet.ts",
        "export": "run"
      }
    }
  ],
  "base_libs": ["example.text"],
  "capabilities": [
    {
      "id": "example.clock",
      "operations": ["now"]
    }
  ]
}
```

关键规则：

- `type_key` 是稳定的 node ID。
- `requires` 按数据 `type` 声明输入，cardinality 为 `exactly_one`、`optional_one` 或 `all`。
- `provides` 的 `key` 是实现返回对象中的 key，`type` 是流程中传递的数据类型。
- `params_schema` 和 `params_defaults` 描述 workflow 中 node `config` 的合法形状。
- `output_schema` 按 provider key 检查 node 返回值。
- AOT 构建会为当前 target 选择唯一一个 JavaScript/TypeScript 实现；不存在或存在歧义都会失败。
- `completion` 为 `immediate` 或 `suspend`，缺省为 `immediate`；它是实现能否立即返回的静态契约。
- `source.ref` 相对于 project root。JS/TS AOT 工程构建当前使用文件源码；没有配套生成器的 `generated` source 不可用。
- node 只能使用自己声明的 `base_libs` 和 Capability operation。

### 3.2 `base_lib` descriptor

```jsonc
{
  "kind": "base_lib",
  "id": "example.text",
  "display_name": "Text helpers",
  "description": "Pure text normalization helpers.",
  "category": "example",
  "version": "1.0.0",
  "implementations": [
    {
      "language": "typescript",
      "targets": ["browser", "node"],
      "source": {
        "kind": "file",
        "ref": "base_lib/text.ts"
      }
    }
  ],
  "dependencies": [],
  "external_packages": []
}
```

`dependencies` 必须列出该库使用的其他 `base_lib` ID；`external_packages` 必须列出该库使用的纯工具包。构建只纳入当前 workflow 实际启用的依赖闭包。

依赖边界会在 TypeScript 检查前和 bundling 后各检查一次：

- node 不得直接导入另一个 node；
- node 不得导入未声明的 `base_lib`；
- `base_lib` 不得导入 node、runtime、plugin、registry 或 Capability bridge；
- `base_lib` 之间的依赖必须显式声明；
- `base_lib` 不得直接读取时间、随机数、熵或宿主环境；这类输入必须经 node
  声明并调用 Capability；
- 无法静态解析的动态 `import()` 或 `require()` 会失败；
- alias、barrel、symlink 不能绕过资源归属和依赖规则；
- node 和 `base_lib` 的模块顶层不得保留可变业务状态，也不得修改内建对象、
  prototype 或使用带 `g`/`y` 状态的模块级正则；
- browser target 不允许未经适配的 Node API，node target 不允许未经适配的 DOM 全局。

HTML 不是 node 或 `base_lib` 的实现语言，只能作为 `web-app` 的页面模板。

### 3.3 Data Schema descriptor

```jsonc
{
  "kind": "data_schema",
  "type_key": "greeting.text",
  "representation": "json",
  "display_name": "Greeting",
  "description": "A rendered greeting.",
  "schema": {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "string"
  }
}
```

当前只支持 `representation: "json"` 和 JSON Schema draft 2020-12。首版运行时采用一个可移植、无额外依赖的严格子集：类型、`enum`/`const`、`allOf`/`anyOf`/`oneOf`、字符串长度与正则、数值上下界、数组长度与 `items`，以及对象的 `properties`/`required`/`additionalProperties`。字符串长度按 Unicode code point 计算；`pattern` 只接受 Python 与无 flags ECMAScript `RegExp` 的保守公共子集，非法或有方言差异的写法会在构建期失败。所有进入 JS 计划的整数还必须位于 JavaScript 安全整数范围 `[-(2^53-1), 2^53-1]`，避免构建后静默改变配置或 Schema 常量。`$ref`、`not`、`multipleOf`、`dependentRequired` 等尚未实现的断言会在构建期明确失败，不会被静默忽略。`id` 可以作为 `type_key` 的别名；如果两者同时出现，值必须一致。

Data Schema 用于：

- 构建前校验 pipeline、node 和 Capability 的类型引用；
- 在任何 node 执行前校验公共输入；
- 校验 node、Capability 和公共输出；
- 生成 `workflow.d.ts` 中的 TypeScript 类型。

### 3.4 Capability descriptor

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

`input_type` 和 `output_type` 应各有对应的 Data Schema。node 还必须在自己的 descriptor 中显式声明使用的 Capability ID 和 operation。

Capability descriptor 只定义契约。`completion` 缺省为 `immediate`；需要等待 Promise 的 operation 必须声明 `suspend`，而且只能用于异步 workflow。VibeFlow 不提供宿主实现，也不保存模块级宿主对象；实现由宿主在每次调用 workflow 时注入，或由显式启用的 Host Extension 提供。

### 3.5 Host Extension descriptor

Host Extension 是 JS/TS AOT 的宿主接线资源，不是普通流程 node，也不同于 Python `RuntimePlugin`：

```jsonc
{
  "kind": "host_extension",
  "id": "example.browser_host",
  "targets": ["browser"],
  "implementations": [
    {
      "language": "typescript",
      "targets": ["browser"],
      "source": {
        "kind": "file",
        "ref": "host_extensions/browser_host.ts",
        "export": "createHostExtension"
      }
    }
  ],
  "provides": ["example.clock"],
  "dependencies": [],
  "external_packages": []
}
```

扩展工厂返回 `{ capabilities?, start(), stop() }`。VibeFlow 会静态检查 target、依赖、Capability 和 import 边界，将源码打入 AOT 产物，并生成显式的 `createWorkflowHost()`。每个 host 拥有独立的 extension instance；`start()` 按依赖顺序执行，`stop()` 反向、幂等执行，部分启动失败时会清理已启动扩展。import、创建 host 和 `web-app` 本身都不会自动 start。

普通 node 不得注册长期监听器；这类宿主事件接线应放在 Host Extension 中。Host Extension 不能导入 node、`base_lib` 私有实现、Python runtime/plugin 或业务 registry，也不能绕过 workflow 的 Capability 契约。

### 3.6 在 workflow 中使用 Host Extension

顶层 `host_extensions` 接受字符串 ID 或对象：

```jsonc
{
  "host_extensions": [
    "example.browser_host",
    {
      "id": "example.configured_host",
      "status": "implemented",
      "enabled": true,
      "config": {"channel": "primary"}
    },
    {
      "id": "example.future_host",
      "status": "planned",
      "display_name": "Future Host",
      "description": "Connects a future host environment.",
      "category": "host",
      "version": "0.1.0",
      "targets": ["browser"],
      "provides": ["example.clock"],
      "dependencies": []
    }
  ],
  "pipeline": {
    "entry_mode": "sync",
    "nodes": []
  }
}
```

字符串等价于 `{"id": "...", "status": "implemented"}`。对象支持：

- `id`：稳定资源 ID；
- `status`：`implemented | planned`，缺省 `implemented`；
- `enabled`：`false` 时忽略该项；
- `config` / `settings`：扩展实例配置，两者均要求对象；
- `display_name`、`description`、`category`、`version`：审查元数据；
- `targets`、`provides`、`dependencies`：资源契约。

implemented 扩展必须能从 `descriptors.host_extensions` 登记的 catalog 中解析。
workflow 若填写 `targets`、`provides` 或 `dependencies`，内容必须与 descriptor
一致。构建只解析、检查和打包 implemented 扩展及其 implemented 依赖；其
`config` 会为每个 host 深拷贝、递归冻结后作为 `context.config` 传给
`createHostExtension(context)`。工厂本身必须同步返回实例；`async` 工厂或
Promise 返回类型会在构建期失败，但实例的 `start()` / `stop()` 可以异步。

planned 扩展可以暂时没有 descriptor 或源码，但应填写足够的显示信息和资源
契约，以便 Architecture JSON、Mermaid 和 SVG 审查。它不会被打包，不会创建
实例或执行 `start()`/`stop()`，也不算作已经提供 Capability。implemented
扩展不能依赖 planned 扩展；这种依赖在 AOT 构建期失败。把资源实现后，登记
descriptor 并将 workflow 中同一 ID 的 `status` 改为 `implemented`。

## 4. Node 调用 ABI

JS/TS node 导出的函数名通常为 `run`，也可以通过 `source.export` 指定：

```ts
interface Envelope<T> {
  readonly key: string;
  readonly type: string;
  readonly value: T;
  readonly source_node: string;
}

export function run(
  inputs: Readonly<Record<string, Envelope<unknown> | null | readonly Envelope<unknown>[]>>,
  params: Readonly<Record<string, unknown>>,
  context: Readonly<{
    readonly signal?: AbortSignal;
    readonly capabilities: Readonly<Record<string, unknown>>;
    trace(kind: string, details?: Readonly<Record<string, unknown>>): void;
  }>,
): Readonly<Record<string, unknown>>;
```

声明 `completion: "suspend"` 的实现必须返回
`Promise<Readonly<Record<string, unknown>>>`，并且只能进入
`pipeline.entry_mode: "async"`。VibeFlow 不会把同步 workflow 自动升级成异步。

实际 TypeScript 可以把这个宽泛签名收窄成具体类型。例如：

```ts
import { normalizeName } from "../base_lib/text.ts";

interface Envelope<T> {
  readonly key: string;
  readonly type: string;
  readonly value: T;
  readonly source_node: string;
}

interface Inputs {
  readonly "name.text": Envelope<string>;
}

interface Params {
  readonly prefix: string;
}

interface Context {
  readonly signal?: AbortSignal;
  readonly capabilities: {
    readonly "example.clock": {
      readonly now: (input: null) => Promise<number>;
    };
  };
  trace(kind: string, details?: Readonly<Record<string, unknown>>): void;
}

export async function run(
  inputs: Inputs,
  params: Params,
  context: Context,
): Promise<{ readonly greeting: string }> {
  const name = normalizeName(inputs["name.text"].value);
  const timestamp = await context.capabilities["example.clock"].now(null);
  context.trace("greeting_built", { timestamp });
  return { greeting: `${params.prefix}, ${name}!` };
}
```

上面的异步示例要求 node implementation 写出
`"completion": "suspend"`，Capability `now` 也声明
`"completion": "suspend"`，同时 pipeline 使用 `"entry_mode": "async"`。
声明与 TypeScript 源码不一致会在构建期失败。

输入对象按 requirement 的数据 `type` 索引：

- `exactly_one` 得到一个 `Envelope`；
- `optional_one` 得到 `Envelope | null`；
- `all` 得到只读 `Envelope[]`。

返回对象保存普通业务值，key 必须与 `provides[].key` 完全一致。node 不应自行构造输出 envelope；VibeFlow 只在生成代码内部用 envelope 传递 provenance 和 cardinality。

## 5. Pipeline 的公共输入输出

JS/Web AOT 要求每个 pipeline input 都显式写出 `required`。output 支持用 `as` 指定稳定的公共字段名，建议明确写出；省略时默认使用 output 的数据 `type`：

```jsonc
{
  "pipeline": {
    "entry_mode": "sync",
    "inputs": [
      {
        "key": "name",
        "type": "name.text",
        "display_name": "Name",
        "required": true
      }
    ],
    "nodes": [],
    "edges": [],
    "outputs": [
      {
        "type": "greeting.text",
        "cardinality": "exactly_one",
        "display_name": "Greeting",
        "as": "greeting"
      }
    ]
  }
}
```

调用开始时，在任何 node 执行前会拒绝未知输入、缺少的必需输入和 Schema 不匹配的输入。

公共输出不暴露内部 envelope：

- `exactly_one` 返回一个普通业务值；
- `optional_one` 没有值时省略对应字段；
- `all` 总是返回普通业务值数组，没有结果时为 `[]`。

例如上面的 output 对应：

```ts
const result = runWorkflow({ name: "VibeFlow" });
console.log(result.greeting);
```

## 6. 顶层 Workflow ABI

JS AOT 使用 `vibeflow.workflow.v2`。`entry_mode` 缺省为 `sync`，两种模式导出不同入口，不保留旧的 Promise 兼容入口：

```ts
export type WorkflowTraceMode = "off" | "boundary" | "full";

export interface WorkflowRunOptions {
  readonly signal?: AbortSignal;
  readonly trace?: WorkflowTraceMode;
  readonly onTrace?: (event: WorkflowTraceEvent) => void;
  readonly capabilities?: WorkflowCapabilities;
  readonly detachedTimeoutMs?: number;
}

// pipeline.entry_mode: "sync"
export function runWorkflow(
  inputs: WorkflowInputs,
  options?: WorkflowRunOptions,
): WorkflowOutputs;

// pipeline.entry_mode: "async"
export function runWorkflowAsync(
  inputs: WorkflowInputs,
  options?: WorkflowRunOptions,
): Promise<WorkflowOutputs>;
```

调用语义：

- 单纯 `import` 不会执行 workflow；
- 每次调用都有独立的状态、trace、错误、Capability 包装和异步任务集合；
- 同一模块可连续调用，也可并发调用；
- 同步入口直接返回普通 `WorkflowOutputs`，失败直接抛出 `VibeFlowWorkflowError`；
- 异步入口 resolve 为普通 `WorkflowOutputs`，失败通过 Promise reject；
- `AbortSignal` 在调用前取消时阻止所有 node，在执行中取消时停止后续调度，并传给异步 Capability；
- 取消是协作式的，不能强制终止忽略 signal 的 Promise 或同步死循环；
- detached 任务属于发起它的异步调用，入口会在返回前等待并清理；超出 `detachedTimeoutMs` 会 reject。

默认 trace 模式是 `boundary`，默认 detached 清理超时为 5000 ms。`onTrace` 抛错时，workflow 会以 trace sink 错误 reject。

生成模块还导出 `VibeFlowWorkflowError`。稳定错误码覆盖输入、Schema、Capability、node、输出、取消、最大执行步数、异步清理超时、trace 回调和生成程序内部错误。错误包含 `code`、`workflowId`、`nodePath` 或 `blockPath`，并保留原始 `cause`。

### Capability 注入示例

生成的 `.d.ts` 会按实际使用的 Capability 生成 `WorkflowCapabilities`：

```ts
import { runWorkflow } from "./workflow.js";

const controller = new AbortController();

const outputs = runWorkflow(
  { name: "VibeFlow" },
  {
    signal: controller.signal,
    trace: "boundary",
    onTrace(event) {
      console.debug(event.kind, event.nodePath);
    },
    capabilities: {
      "example.clock": {
        now(input, { signal }) {
          signal?.throwIfAborted();
          return Date.now();
        },
      },
    },
  },
);
```

执行前会检查所有必需 Capability 和 operation 是否齐全。VibeFlow 会校验 operation 的输入输出 Schema，并以第二个参数 `{ signal }` 调用宿主实现。每个 node 只能看到自己声明的能力。

Capability 是依赖契约和调用边界，不是安全沙箱。外部副作用是否可重试、可回滚和并发安全，仍由宿主实现负责。

### 完成方式、任务分路和 Promise 审计

VibeFlow 将三件事分开记录：

- `completion: immediate | suspend`：实现是否返回 Promise；
- `schedule: inline | deferred | detached`：是否形成流程图可见的任务分路；
- `executor: current | event_loop | thread`：实际执行位置。

同步 JS workflow 不得包含 suspend、deferred 或 detached。异步 workflow 可以串行等待 suspend node，也可以显式使用 deferred/result_key 或 detached TaskPlan。`async function` 与 immediate 声明不一致、未归属的 `.then()`、`void promise`、模块级 Promise、普通 node 内监听器或定时器都会在 TypeScript 检查阶段失败；VibeFlow 不靠运行时 thenable 猜测兜底。

### Host 生命周期调用

启用 Host Extension 后，生成模块额外导出 `createWorkflowHost()`：

```ts
const host = createWorkflowHost();
await host.start();
try {
  const result = host.runWorkflow({ name: "VibeFlow" });
  console.log(result);
} finally {
  await host.stop();
}
```

异步 workflow 的 host handle 对应提供 `runWorkflowAsync()`。Host 自动合并扩展提供的 Capability；底层 `runWorkflow()`/`runWorkflowAsync()` 仍可被直接调用并手工注入 fake 或真实 Capability。

扩展工厂收到的 context 至少包含扩展 ID、冻结的 workflow 配置、该 host 的
`AbortSignal` 和对应工作流入口。配置来自 workflow 顶层
`host_extensions[].config`（或 `settings`），不是项目级全局可变状态。

### 原生 Port 与长期 workflow

内核节点 `vibeflow.io` 固定使用 `vibeflow.port`：

```jsonc
{
  "id": "receive",
  "type_used": "vibeflow.io",
  "provides": [{"key": "request", "type": "app.request"}],
  "io": {"operation": "receive", "port": "requests"}
}
```

```jsonc
{
  "id": "send",
  "type_used": "vibeflow.io",
  "requires": [{"type": "app.response", "cardinality": "exactly_one"}],
  "io": {"operation": "send", "port": "responses"}
}
```

`receive` 零输入、一个输出，完成方式固定为 suspend；`send` 一个
`exactly_one` 输入、零输出，完成方式固定为 immediate。需要回执时应定义
项目自己的 suspend Capability operation，不能改变核心 `send` 的语义。

长期程序可以直接使用：

```text
entry_mode: async
→ max_iterations: null 的 loop
→ receive
→ Node/Nodeset
→ send
```

`max_iterations: null` 允许有 stop、组合两个 stop（OR），也允许完全没有
stop 的永久循环。永久循环合法且只产生 warning；VibeFlow 不强制 timeout、
yield、取消路径或退出条件。完整 trace 仍流式交给 `onTrace`，调用内不无限
累积根 trace 数组，已完成 detached task 会从跟踪集合移除。

## 7. 三种构建 profile

| Profile | Target | 主要产物 | 用途 |
| --- | --- | --- | --- |
| `esm-module` | `browser` / `node` | `workflow.js`、`.d.ts`、source map、manifest，可带内部 chunk | 交给 Vite、Webpack、esbuild 或其他应用继续打包 |
| `single-esm` | `browser` / `node` | `index.js`、`.d.ts`、source map、manifest | 本地 workflow、node、`base_lib` 和非 external 依赖合并为一个运行时 JS 文件 |
| `web-app` | 仅 `browser` | `index.html`、`index.js`、`.d.ts`、source map、manifest | 使用用户 HTML 模板和应用入口生成普通网页 |

三种 profile 都不会自动调用 workflow，也不会自动启动 Host Extension。

本节的 `python run.py build` 是生成发行包中的命令前缀。在已安装 VibeFlow
的环境中可替换为 `vibeflow build`；在源码仓库中可使用
`PYTHONPATH=src python -m vibeflow build`，后续参数保持不变。

### `esm-module`

```bash
python run.py build \
  --workspace vibeflow_config.jsonc \
  --config project/configs/greeting.jsonc \
  --target browser \
  --profile esm-module \
  --out-dir dist/module
```

已声明的 external package import 会保留。该 profile 允许 bundler 生成内部 module chunk，因此它保证可导入的 ESM module graph，不保证只有一个运行时 JS 文件。

### `single-esm`

```bash
python run.py build \
  --workspace vibeflow_config.jsonc \
  --config project/configs/greeting.jsonc \
  --target node \
  --profile single-esm \
  --entry-name workflow.js \
  --out-dir dist/node
```

`single-esm` 不允许隐式本地 companion JS chunk。无法内联的本地 worker、动态模块、WASM 或资源会使构建失败。external package 仍由实际宿主解析，所以“单个本地 JS 文件”不等于“没有外部包”。

### `web-app`

HTML 模板必须且只能包含一次：

```html
<!-- VIBEFLOW_APP_ENTRY -->
```

应用入口通过虚拟模块导入 workflow：

```ts
import { runWorkflow } from "@vibeflow/workflow";

document.querySelector("#run")?.addEventListener("click", () => {
  const result = runWorkflow({ name: "VibeFlow" });
  console.log(result);
});
```

构建命令：

```bash
python run.py build \
  --workspace vibeflow_config.jsonc \
  --config project/configs/greeting.jsonc \
  --target browser \
  --profile web-app \
  --html project/web/index.template.html \
  --app-entry project/web/app.ts \
  --out-dir dist/web
```

VibeFlow 会把 marker 替换为加载生成入口的 `<script type="module">`，但不会插入自动启动逻辑。页面 UI、事件监听和调用时机都由应用入口负责。

## 8. CLI 参数

统一命令：

```bash
python run.py build \
  --workspace <vibeflow_config.jsonc> \
  --config <workflow.jsonc> \
  --target browser|node \
  --profile esm-module|single-esm|web-app \
  --out-dir <dist>
```

常用可选参数：

- `--entry-name <name.js>`：固定 JS 入口文件名；
- `--sourcemap none|external|inline`：source map 形式，默认 `external`；
- `--workflow-id <id>`：覆盖生成物中的 workflow ID；
- `--html <template>` 和 `--app-entry <entry.ts>`：`web-app` 必需；
- `--replace`：替换已有且带有效 `vibeflow-build.json` 的构建目录。

默认不会覆盖已存在的输出目录。构建先写入同级临时目录，类型、依赖、bundle 和产物检查全部成功后再原子发布；失败不会破坏旧产物。`--replace` 前会核对 manifest 的完整结构、entry、每个文件的 SHA-256，并拒绝符号链接、被修改的文件、未登记文件或目录。替换已有非空目录时使用 Linux `renameat2(RENAME_EXCHANGE)` 做单次原子交换；平台或文件系统不支持时会保留旧产物并明确失败，不降级成存在短暂空窗的两次 rename。

`vibeflow-build.json` 记录 target、profile、Workflow ABI、`entry_mode`、Host Extension、计划 hash、Node/TypeScript/esbuild 版本、lockfile hash、external package 和所有产物 hash。相同输入、配置和 lockfile 用于确定性构建。

## 9. 工具链要求

项目必须自行安装并锁定：

- Node.js `>=22.12`；
- TypeScript `>=7 <8`；
- esbuild `>=0.28 <0.29`；
- 首版要求 `package-lock.json`。`pnpm-lock.yaml` 和 `yarn.lock` 在加入可靠的已解析版本核验前会明确拒绝，避免“只记录 hash、实际依赖却与锁文件不一致”的伪确定性构建。

例如：

```json
{
  "private": true,
  "type": "module",
  "devDependencies": {
    "typescript": "7.0.2",
    "esbuild": "0.28.1"
  }
}
```

安装依赖是项目维护者的显式步骤，例如在审查 lockfile 后运行 `npm ci`。VibeFlow：

- 不自动执行 `npm install`、`npm ci`、`pnpm install` 或 `yarn install`；
- 不运行第三方 package scripts；
- 只解析项目本地 TypeScript 和 esbuild；
- 使用 TypeScript Compiler API 做严格类型与依赖检查，esbuild 只负责 bundling；
- 把实际版本和 lockfile hash 写入 manifest。

## 10. 当前限制

JS/Web AOT 只接受可静态检查、可移植的流程：

- 不会把 Python node 自动翻译成 JavaScript；
- `python_stub`、delegate-cli、任意 Python 对象和 Python Runtime Plugin 不能进入 JS target；
- workflow 使用的普通 node 和 `base_lib` 必须有唯一的 target-compatible JS/TS 实现；
- node 参数、输入输出和 Capability 边界必须是 JSON 可表达的数据；
- 不支持的动态 import、target API、worker、WASM、资源模式或递归 nodeset 会在构建期失败；
- Web Worker executor 尚未实现；JS TaskPlan 首版使用 event loop；
- VibeFlow 只生成通用 Capability/Host Extension ABI 和核心 Port 契约，不内置任何具体宿主接线。

遇到不支持的功能时，构建应直接失败并指出资源或流程位置，而不是生成只能在运行时才报错的半成品。

## 11. TypeScript 集成沙箱

源码仓库和官方分发包都包含 `examples/typescript_sandbox/`。这个 TypeScript
沙箱不是单节点演示，而是一组经过真实 descriptor、JSONC workflow、
TypeScript Compiler API 和 esbuild 的端到端用例。它用
`node + base_lib` 表达 `(x + a) - b`，并独立覆盖并行 `all` 合流、条件
`any_active` 合流、nodeset、有界/无界 loop、Promise node、Capability，以及
`receive → 数学 node/base_lib → send` 的 Port 链路。

从源码仓库根目录安装项目锁定的工具链和浏览器测试依赖，再运行全部用例：

```bash
npm ci --prefix examples/typescript_sandbox/project
npm ci --prefix tools/mermaid-renderer
PYTHONPATH=src python examples/typescript_sandbox/run_all.py \
  --puppeteer-root tools/mermaid-renderer
```

从分发包根目录运行时，入口会自动从
`kernel/vibeflow-kernel.zip` 导入 VibeFlow，不需要源码树或额外安装 Python
包。分发构建保留 `package.json` 和 lockfile，但不会复制 `node_modules`，
也不会自动执行 npm：

```bash
npm ci --prefix examples/typescript_sandbox/project
python examples/typescript_sandbox/run_all.py --skip-browser
```

如果要运行分发包中的真实浏览器用例，再执行
`npm ci --prefix kernel/tools/mermaid-renderer`，然后去掉 `--skip-browser`。
已有预填充 npm cache 时可以给上述 `npm ci` 增加 `--offline`。如果本机尚未
安装 Puppeteer，可保留 `--skip-browser`，只运行 Node 与构建检查。

完整运行还会验证：

- 模块 import 不自动执行业务；
- 默认入口同步返回，显式异步入口只导出 `runWorkflowAsync`；
- 连续调用、并发调用、trace 和 Capability 状态互相隔离；
- 输入错误、缺失 Capability、预取消和执行中取消使用稳定错误码；
- 节点异常、输出 Schema 失败的错误类型、workflow/node/block 路径与 cause；
- `schedule:false` 与 `transfer:false` 在 portable plan、Python runtime 和
  JS AOT 中保持相同的控制/数据分离语义；
- `required:false` 输入的省略、运行结果和生成 TypeScript 类型一致；
- 多层 nodeset 的限定路径 override、`stop_when`/carry/collect loop，以及
  loop 上限错误、detached 并发隔离、清理、超时和失败后复用；
- `esm-module`、`single-esm`、`web-app` 的文件集合与启动行为；
- 严格 TypeScript 项目可直接消费生成的 `.d.ts`；
- source map、构建清单、锁文件记录、字节确定性和失败发布保护；
- node 跨 node、未声明 `base_lib`、动态 import、未登记本地 helper 及
  browser Node API 会在构建期被拒绝。
- immediate/suspend 与 Promise 源码不一致会在构建期被拒绝。

运行结果写入 `examples/typescript_sandbox/reports/summary.json` 和
`summary.md`；构建目录使用临时目录，不会把测试 bundle 留在源码树中。
