# Python 资源与插件 SDK

使用 `vibeflow.targets.python.sdk` 把 Node、Rule 的声明与实现放在一起，再用固定 `Plugin` 列出贡献资源。workflow 显式选择该插件后，其资源进入本次检查和运行范围。

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

raw = data_schema(type_key="text.raw", schema={"type": "string"})
normalized = data_schema(type_key="text.normalized", schema={"type": "string"})
plugin = Plugin(id="example.text", resources=[NormalizeText, raw, normalized],
                declaration_rulesets=["vibeflow.plugin_declaration"])
```

workflow 保留 JSONC 和原生连边，下面是插件选择与 Node 调用片段：

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

插件 source 的文件路径相对所属项目 root；可通过 `root` 选择另一个已登记 workspace root。默认导出名为 `plugin`，也支持显式 `export` 和已安装模块的 `source.kind: "module"/"package"`。

返回对象的 key 与 `provides[].key` 一致；调用点 `params` 使用声明的参数 schema/defaults。`@node` 保存契约、规则选择、默认展示以及实现类的源码位置。

默认值支持 JSON 数组、对象及其嵌套组合。SDK 保存只读声明；`run_pure` 每次调用收到原生 `list/dict` 参数副本。默认值和调用点覆盖分别复制，修改本次参数不会影响保存的默认值、调用者的容器或后续运行。

Node 通过 `rulesets` 选择审查约束。省略和 `[]` 都表示未选择 Node 审查规则；`flow_kind` 表达执行身份。自由 `tags/metadata` 和 `presentation` 由 Node 自己声明，见 [规则与 Node](rules-and-nodes.md)。

## 规则与其他资源

`@rule` 声明普通 `check(context, inputs, params)` 函数；`ruleset` 使用 `RuleCall/RuleRelation` 或同模型的字典组合。把函数及 Ruleset 放入插件的 `resources`。SourceContext 查询、具名 records 和覆盖关系见 [规则接口](rules-and-nodes.md)。

`base_lib`、`data_schema`、`capability` 和 `host_extension` 也产生固定资源定义。HostExtension 的运行协议由 JS/TS Target 提供；Python SDK 可贡献显式 JS 实现声明。

## 多文件实现与辅助库

在 `@node`、`@base_lib` 或生命周期声明中，用 `implementation_files=["support.py"]` 列出支撑文件。路径相对声明模块；同一资源的传递依赖也逐一登记。独立共享库使用 `@base_lib` 声明，由 Node 或生命周期的 `base_libs` 引用。库依赖其他库时使用 `dependencies`。

各资源选择自己的 Ruleset 与 `presentation`。例如，Node 选 `vibeflow.process`，库选 `vibeflow.base_lib`，生命周期选 `vibeflow.plugin`，插件声明选 `declaration_rulesets=["vibeflow.plugin_declaration"]`。默认可维护性规则按每个文件检查 500 行上限。完整登记和样式覆盖见[多文件资源](multifile-resources.md)。

## 延迟源码与加载时机

需要独立模块在检查后才导入时，使用相同接口的显式源码引用：

```python
from vibeflow.targets.python.sdk import node, SourceLocator

late_node = node(
    type_key="example.late", contract={}, rulesets=["vibeflow.process"],
    source=SourceLocator(kind="file", ref="nodes/late.py", export="LateNode"),
)
```

插件入口先加载固定定义，其直接导入按 Python 的模块机制初始化。显式延迟实现接受所选 import 规则后再绑定；检查失败时，尚未加载的实现及闭包保持未加载。完整流程见[插件加载与检查](plugins-and-integrations.md#加载与检查)。

```bash
python run.py validate --config python_project/configs/main.jsonc
python run.py quality --path python_project
python run.py review-rules --config python_project/configs/main.jsonc --json
python run.py inspect-resources --config python_project/configs/main.jsonc --json
```

资源查询和规则预览加载固定定义，框架不调用检查函数、业务执行入口或生命周期工厂。
