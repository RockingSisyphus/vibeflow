# Python Node 与 BaseLib

Python Node 适合实现一个可独立描述、具有显式输入输出的局部步骤。可复用的纯计算 helper 放入 BaseLib。

## 最小 Node

公共接口来自 `vibeflow.core` 和 `vibeflow.targets.python.project`：

```python
from vibeflow.core import DataProvider, DataRequirement
from vibeflow.targets.python.project import NodeContract, NodeInfo


class NormalizeTextNode:
    NODE_INFO = NodeInfo(
        type_key="example.normalize_text",
        display_name="Normalize text",
        category="text",
        description="Normalizes whitespace in supplied text.",
        version="1.0.0",
        flow_kind="process",
    )
    CONTRACT = NodeContract(
        requires=(
            DataRequirement(
                type="text.raw",
                cardinality="exactly_one",
                display_name="Raw text",
            ),
        ),
        provides=(
            DataProvider(
                key="normalized_text",
                type="text.normalized",
                display_name="Normalized text",
            ),
        ),
        input_semantics={"text.raw": ("Text before whitespace normalization.",)},
        output_semantics={"normalized_text": ("Text with normalized whitespace.",)},
    )

    def run_pure(self, inputs, params):
        value = inputs["text.raw"]["value"]
        return {"normalized_text": " ".join(value.split())}
```

每个端口需要易读名称，`input_semantics` / `output_semantics` 覆盖全部端口。返回 mapping 的 key 必须与 `CONTRACT.provides` 一致。`examples` 可作为源码文档保留，VibeFlow 不自动执行它。

## Registry 与参数

参数 schema/defaults 由 Registry 保存：

```python
from vibeflow.targets.python.project import NodeRegistry


def build_node_registry() -> NodeRegistry:
    registry = NodeRegistry()
    registry.register(
        "example.normalize_text",
        NormalizeTextNode,
        config_schema={
            "collapse_newlines": {"type": "boolean"},
        },
        config_defaults={"collapse_newlines": True},
    )
    return registry
```

调用实例的参数写在 `config` 中；`display_name` 和 `description` 是实例文档，不进入 `params`：

```jsonc
{
  "id": "normalize_title",
  "type_used": "example.normalize_text",
  "display_name": "Normalize title",
  "description": "Normalizes the title before classification.",
  "config": {"collapse_newlines": true}
}
```

## BaseLib

BaseLib 保存可由多个 Node 导入的纯函数：

```python
from vibeflow.targets.python.project import BaseLibInfo

BASE_LIB_INFO = BaseLibInfo(
    module="base_lib.text_tools",
    display_name="Text tools",
    category="text",
    description="Pure text transformation helpers.",
    version="1.0.0",
)

def normalize_whitespace(value: str) -> str:
    return " ".join(value.split())
```

在 `build_base_lib_registry()` 中用 `BaseLibRegistry.register(...)` 登记，再在 workflow 顶层通过 `base_lib.modules[].id` 选择。本流程未选择的 BaseLib 不进入 Node 的允许依赖集合。

验证 Node 和 Registry：

```bash
python run.py validate --config python_project/configs/main.jsonc
python run.py quality --path python_project
```
