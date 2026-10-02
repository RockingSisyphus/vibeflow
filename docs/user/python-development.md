# Python Node 与 BaseLib

Node 使用独立声明描述身份、契约、规则与实现。实现类只负责执行，不再定义 NODE_INFO/CONTRACT，也不再通过 registry.py 发现 Node。

## 声明一个 Node

项目配置指定目录：

```jsonc
{"project_target": "python", "descriptors": {"nodes": ["manifests/nodes"]}}
```

`manifests/nodes/normalize.jsonc`：

```jsonc
{
  "kind": "node", "type_key": "example.normalize_text",
  "display_name": "Normalize text", "category": "text",
  "description": "Normalizes whitespace in supplied text.", "version": "1.0.0",
  "flow_kind": "process", "rulesets": ["vibeflow.process"],
  "contract": {
    "requires": [{"type": "text.raw", "cardinality": "exactly_one", "display_name": "Raw text"}],
    "provides": [{"key": "normalized_text", "type": "text.normalized", "display_name": "Normalized text"}],
    "input_semantics": {"text.raw": ["Text before normalization."]},
    "output_semantics": {"normalized_text": ["Normalized whitespace."]},
    "params_schema": {"collapse_newlines": {"type": "boolean"}},
    "params_defaults": {"collapse_newlines": true}
  },
  "implementations": [{"language": "python", "targets": ["python"],
    "source": {"kind": "file", "ref": "nodes/normalize.py", "export": "NormalizeTextNode"}}]
}
```

`nodes/normalize.py`：

```python
class NormalizeTextNode:
    def run_pure(self, inputs, params):
        value = inputs["text.raw"]["value"]
        return {"normalized_text": " ".join(value.split())}
```

返回 mapping 的 key 与声明 provides 一致。参数 schema/defaults 属于声明，调用实例的 `config` 覆盖参数；display_name/description 是实例说明。声明和 import 规则先读取，实际实现延迟绑定。

程序化使用也只登记明确的声明：`registry.register(descriptor, ImplementationClass)`，或提供 loader 延迟绑定。Registry 不读取实现类元数据。

## 业务分类与规则

`category/tags` 表达业务身份，`flow_kind` 表达原生执行身份。Node 的约束来自所选 Ruleset；分类默认颜色、形状、图标和规则选择见 [Rule、Ruleset 与业务分类](rules-and-categories.md)。模型功能块不需要固定连接方式，可以使用原生串行、分支、Nodeset 和 Loop。

## BaseLib

BaseLib 保存可复用的 helper。现有 BaseLib 资源登记与 workflow 选择保留；源码约束由相应内置 Rule 执行。Node 导入 helper 仅产生引用关系，不自动赋予其中定义领域对象的归属。

```bash
python run.py validate --config python_project/configs/main.jsonc
python run.py quality --path python_project
python run.py review-rules --config python_project/configs/main.jsonc --json
```
