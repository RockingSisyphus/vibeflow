# Python 资源与插件 SDK

用户资源使用 `vibeflow.targets.python.sdk` 定义。Node 的声明与实现可以写在同一个模块，Rule 同样如此；普通导入和装饰器不注册资源。workflow 选择固定 `Plugin` 对象后，其中列出的资源才进入本次 Catalog。

## Node 与固定插件

`plugins/text.py`：

```python
from vibeflow.targets.python.sdk import Plugin, node, data_schema

@node(
    type_key="example.normalize_text",
    display_name="Normalize text",
    description="Normalizes whitespace in supplied text.",
    rulesets=["vibeflow.process"],
    contract={
        "requires": [{"type": "text.raw", "cardinality": "exactly_one", "display_name": "Raw text"}],
        "provides": [{"key": "normalized_text", "type": "text.normalized", "display_name": "Normalized text"}],
        "input_semantics": {"text.raw": ["Text before normalization."]},
        "output_semantics": {"normalized_text": ["Normalized whitespace."]},
    },
)
class NormalizeText:
    def run_pure(self, inputs, params):
        return {"normalized_text": " ".join(inputs["text.raw"]["value"].split())}

normalized = data_schema(type_key="text.normalized", schema={"type": "string"})
plugin = Plugin(id="example.text", resources=[NormalizeText, normalized])
```

workflow 保留 JSONC 和原生连边：

```jsonc
{
  "plugins": [{"source": {"kind": "file", "ref": "plugins/text.py"}}],
  "pipeline": {
    "nodes": [{"id": "normalize", "type_used": "example.normalize_text",
      "display_name": "Normalize", "description": "Normalize the input"}],
    "edges": []
  }
}
```

文件路径相对所属项目 root；可通过 `root` 选择另一个已登记 workspace root。默认导出名为 `plugin`，也支持显式 `export` 和已安装模块的 `source.kind: "module"/"package"`。框架不自动发现或安装插件。

返回对象的 key 与 `provides[].key` 一致；调用点 `params` 使用声明的参数 schema/defaults。`@node` 自动记录实现语言、类与源码位置，不需要类内 `NODE_INFO/CONTRACT` 或项目 registry。

Node 必须明确选择需要的 Ruleset。省略和 `[]` 都表示未选择 Node 审查规则；`flow_kind` 不授予副作用权限。自由 `tags/metadata` 和 `presentation` 由 Node 自己声明，见 [规则与 Node](rules-and-nodes.md)。

## 规则、辅助库及延迟源码

`@rule` 声明普通 `check(context, inputs, params)` 函数；`ruleset` 使用 `RuleCall/RuleRelation` 或同模型的字典组合。把函数及 Ruleset 放入插件的 `resources`。SourceContext 查询、具名 records 和覆盖关系见 [规则接口](rules-and-nodes.md)。

`base_lib`、`data_schema`、`capability` 和 `host_extension` 也产生固定资源定义。原生 Target 能力仍决定哪些资源可以绑定执行；例如 HostExtension 是 JS 宿主协议，Python SDK 可贡献显式 JS 实现声明，不会创造 Python 宿主运行器。

需要独立模块在检查后才导入时，使用相同接口的显式源码引用：

```python
from vibeflow.targets.python.sdk import node, SourceLocator

late_node = node(
    type_key="example.late", contract={}, rulesets=["vibeflow.process"],
    source=SourceLocator(kind="file", ref="nodes/late.py", export="LateNode"),
)
```

插件入口及它直接导入的模块属于受信初始化，会先加载。规则仍可诊断已经发生的顶层行为，但无法提前阻断或撤销；只有明确尚未加载的延迟实现及其闭包保留检查失败后不导入的保证。

```bash
python run.py validate --config python_project/configs/main.jsonc
python run.py quality --path python_project
python run.py review-rules --config python_project/configs/main.jsonc --json
python run.py inspect-resources --config python_project/configs/main.jsonc --json
```

资源查询和规则预览加载固定定义，框架不调用检查函数、业务执行入口或生命周期工厂。
