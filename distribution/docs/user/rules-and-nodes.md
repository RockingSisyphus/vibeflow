# Rule、Ruleset 与业务 Node

NodeType 定义外观与局部默认规则；业务 Node 定义契约和实现；workflow 中的调用定义路径、参数和覆盖。Node 的功能来自普通实现、Capability 与显式 Rule 授权，不由形状、颜色或名称赋予。

## 声明业务 Node

Python 在所属 `nodes/` 中导出 `@node` 类，JavaScript/TypeScript 导出 `defineNode` 声明。准备层自动发现这些声明，不另写源码登记表。

```python
# nodes/add.py
from vibeflow.targets.python.sdk import node

@node(
    id="app.add",
    node_type="vibeflow.node",
    rulesets=["vibeflow.process"],
    contract={
        "requires": [{"type": "number", "cardinality": "exactly_one", "display_name": "输入"}],
        "provides": [{"key": "answer", "type": "number", "display_name": "结果"}],
        "input_semantics": {"number": ["待计算数值"]},
        "output_semantics": {"answer": ["输入加一"]},
    },
)
class Add:
    def run_pure(self, inputs, params):
        return {"answer": inputs["number"]["value"] + 1}
```

业务标识使用 `id`；`node_type` 指向已激活的 NodeType。内置 `vibeflow.node` 可用于普通业务声明。自定义外观和默认规则通过 Plugin 贡献的 NodeType 复用，见 [Plugin](plugins-and-integrations.md)。

```jsonc
{"id": "first_add", "definition_id": "app.add", "display_name": "加一",
 "description": "准备下一步的数值", "style": {"shape": "diamond", "fill": "#f2e6c5"}}
```

这是一次调用，同一个 `app.add` 可以有多个调用点。可在调用中配置参数、样式、规则及执行选项。`definition_id` 也可引用所属 root 导入的 NodesetType；Nodeset 调用独立展开，详见 [NodesetType 与 Loop](nodeset-types-and-loops.md)。

## 规则如何选择

局部规则依次取 NodeType 默认、业务 Node 显式列表、调用显式列表。省略表示继承，显式列表替换，`[]` 表示空选择。图级、root 级和项目级规则仍分别执行。

```jsonc
{
  "rulesets": ["vibeflow.workflow"],
  "pipeline": {"nodes": [{
    "id": "first_add", "definition_id": "app.add", "display_name": "加一", "description": "计算数值",
    "rulesets": ["vibeflow.process", {"rule_id": "example.check", "params": {"limit": 8}}]
  }]}
}
```

字符串选择 Ruleset；对象通过 `rule_id` 选择单个 Rule 并提供参数。贡献一个 Rule/Ruleset 不会自动执行它；Ruleset 可通过 `workflow_default` 声明图级默认。显式图级列表替换本图默认。

## Python 进程环境变量

`vibeflow.global_state` Ruleset 使用 `vibeflow.no_side_effects` 的 `effect_scope="global_state"`，允许在运行时通过 `os.environ` / `os.environb` 读取、设置、删除环境键和调用其方法，也允许 `os.getenv` / `os.getenvb`、`os.putenv`、`os.unsetenv`。环境键名不受白名单限制；显式 import policy 和导入时执行检查仍生效。Node、BaseLib 和运行插件使用相同效果检查，流程类别名称本身不授予权限。

Node 可显式选择 `rulesets=["vibeflow.global_state"]`。运行插件可保留 `vibeflow.plugin` 集合，并通过自定义 Ruleset 的 `overrides` 把 `base/effects` 调用的 `effect_scope` 设为 `global_state`，完整写法见下文“Ruleset 与局部覆盖”。这不需要关闭源码检查或修改 imports 调用。

该范围不会自动保存或恢复原值，需在运行生命周期清理中恢复；需要排他访问时显式配置同域 `execution_lock`。它不放开替换 `os.environ` 对象、修改 `sys.path` 等导入状态，也不授予文件、网络、线程或子进程效果。`process`、`io`、`python_io`、`data_store` 默认行为保持不变。

## 四种检查对象

Rule 的 `level` 指定可用信息：

| level | 检查对象与输入 |
|---|---|
| `project` | 项目目录清单、所有 root、workflow 声明和共享资源关系 |
| `root` | 所属 root 的目录/文件清单、workflow、资源和按需准备的源码统计 |
| `graph` | 当前有效图、调用、连接及对应 Target 的图事实 |
| `node` | 当前调用/业务定义、契约及对应 Target 的局部源码事实 |

project/root 的选择与参数分别放在 `project_rules.jsonc`、`root_rules.jsonc`。配置和检查范围见 [项目治理](project-governance.md)。不能在较低等级选择一个较高等级 Rule 来取得额外信息，等级不匹配会报错。

`scope: "call"` / `"source"` 决定结果复用范围，与检查等级不同。需要不同调用配置的 Rule 使用调用范围；源码范围只在来源、参数和输入等身份一致时复用。它不改变 Rule 的可读信息或授予权限。

## 自定义 Rule 与 Record

规则及其实现放在 Plugin 包内，随包统一装载和移除。

```python
# plugins/conventions/plugin.py
from vibeflow.targets.python.sdk import Plugin, rule, ruleset
from vibeflow.core.rules import RuleResult, RuleRecord

@rule(id="example.count", level="project", outputs={"count": "example.count.v1"})
def count(context, inputs, params):
    roots = context.facts["project"]["roots"]
    return RuleResult(records={"count": RuleRecord("example.count.v1", len(roots))})

checks = ruleset(id="example.project", calls=[{"id": "count", "rule_id": "example.count"}])
plugin = Plugin(id="conventions", resources=[count, checks])
```

Ruleset 把 Rule 调用组织为有明确 ID 的检查图。`requires` 关系把提供方的类型化 Record 绑定到消费方输入；`includes` 组合集合；`overrides` 在明确目标上替换参数或实现。消费方不能把缺失、类型不匹配或不可用的 Record 当作有效数据。报告保存计划、调用、执行状态与 Record，业务 workflow 不消费这些审查结果来调度。

Python 返回 `RuleResult` / `RuleRecord`，JS 返回等价 JSON 对象。Rule 运行在对应语言的宿主中；规则语言与业务 Target 可以不同。源码分析仍由各 Target 提供，不通过共享治理层重新解释业务源码。

## Ruleset 与局部覆盖

在 Plugin 包内组合已有集合，并用完整调用路径覆盖参数：

```python
from vibeflow.targets.python.sdk import Plugin, ruleset

workflow_checks = ruleset(
    id="example.workflow", graph_scope="effective_subtree",
    calls=[{"id": "base", "ruleset_id": "vibeflow.workflow"}],
    relations=[{"source": "$self", "target": "base/nodeset_types",
                "kind": "overrides", "params": {"nodeset_max_depth": 9}}],
)
plugin = Plugin(id="conventions", resources=[workflow_checks])
```

在 workflow 或 NodesetType 顶层选择 `"rulesets": ["example.workflow"]`。该集合已包含内置检查，不必再并列选择 `vibeflow.workflow`。覆盖只影响当前集合中的指定路径；其他调用保留自己的默认值。`review-rules` 可核对展开后的路径、有效参数和来源。

## Capability 与效果检查

Node 声明所需 Capability 操作，有效 Rule 策略按完整调用路径授权。同一业务定义的两个调用点不能互借授权。标准 workflow 协同模板显式选择限制和允许规则；`effect_scope` 描述所选源码效果策略，不是通用权限字段。

源码检查按显式选择的 import/static/run 入口执行。它覆盖约定的结构、接口、输入写入及效果模式，不证明任意业务正确性或操作系统安全性。普通算法、局部对象与本机运行环境由作者负责。

旧原生 `io` 配置、类元数据登记、项目 `policy` 合并和 Host Extension 均不属于当前配置。旧源码需按当前 SDK 与治理配置迁移，旧 AOT 重新构建，不保留双轨执行。
