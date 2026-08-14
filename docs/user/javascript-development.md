# JavaScript/TypeScript Node 与 AOT

JavaScript Target 使用静态 descriptor 记录资源信息，并把 workflow 构建为普通 ESM。生成物不读取原始 Config，也不依赖 Python Runtime。

## Node descriptor

```jsonc
{
  "kind": "node",
  "type_key": "example.normalize_text",
  "display_name": "Normalize text",
  "category": "text",
  "description": "Normalizes whitespace in supplied text.",
  "version": "1.0.0",
  "flow_kind": "process",
  "contract": {
    "requires": [
      {"type": "text.raw", "cardinality": "exactly_one", "display_name": "Raw text"}
    ],
    "provides": [
      {"key": "normalized_text", "type": "text.normalized", "display_name": "Normalized text"}
    ],
    "params_schema": {},
    "params_defaults": {},
    "input_semantics": {"text.raw": ["Text before normalization."]},
    "output_semantics": {"normalized_text": ["Text with normalized whitespace."]}
  },
  "implementations": [
    {
      "language": "typescript",
      "targets": ["browser", "node"],
      "source": {"kind": "file", "ref": "nodes/normalize_text.ts", "export": "run"}
    }
  ],
  "base_libs": [],
  "capabilities": []
}
```

Node descriptor 的端口和语义必须完整。`params_schema` / `params_defaults` 描述调用实例 `config`；输出结构不在 Node 上覆盖，provider 的 `type` 对应独立 Data Schema。

## 实现 ABI

```ts
export function run(
  inputs: Readonly<Record<string, unknown>>,
  params: Readonly<Record<string, unknown>>,
  context: Readonly<Record<string, unknown>>,
) {
  const raw = inputs["text.raw"] as { value: string };
  return { normalized_text: raw.value.trim().replace(/\s+/g, " ") };
}
```

实现返回普通对象，key 与 `provides[].key` 一致。`completion: "immediate"` 使用同步返回；`completion: "suspend"` 返回 Promise，并要求 `pipeline.entry_mode: "async"`。Promise 必须返回给当前调用或交给显式 TaskPlan。

## Data Schema

```jsonc
{
  "kind": "data_schema",
  "type_key": "text.normalized",
  "representation": "json",
  "schema": {"type": "string"}
}
```

公共输入、Node 输出、Capability 边界和公共输出使用 `type_key` 查找 Data Schema。缺失所需 Schema 时 AOT 构建失败。

项目 root 在 `vibeflow_project.jsonc` 中登记 descriptor 目录和工具链根：

```jsonc
{
  "project_target": "javascript",
  "descriptors": {
    "nodes": ["manifests/nodes"],
    "data_schemas": ["manifests/data"]
  },
  "javascript": {"package_root": ".", "external_packages": []}
}
```

## 构建和调用

```bash
npm ci --prefix javascript_project
python run.py validate --config javascript_project/configs/main.jsonc
python run.py build --config javascript_project/configs/main.jsonc --target node --profile esm-module --out-dir javascript_project/build/node
```

同步 workflow 导出 `runWorkflow(inputs, options)`，异步 workflow 导出 `runWorkflowAsync(inputs, options)`：

```js
import { runWorkflow } from "./build/node/workflow.js";
const result = runWorkflow({ request: { message: "hello" } });
```

Browser/Node 平台由本次 `build --target` 选择，不写进 workflow Config。项目自己的 `tsc`、ESLint 和业务测试继续由项目显式运行。
