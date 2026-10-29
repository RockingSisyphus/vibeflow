# Rule、Ruleset 与业务 Node

NodeType 提供默认局部规则，业务 Node 与调用点可以分别选择适合自身的规则。Rule 定义检查逻辑，Ruleset 将检查组织成可复用的规则图。

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

字符串选择 Ruleset；对象通过 `rule_id` 选择单个 Rule 并提供参数。Plugin 贡献使规则可供选择，Ruleset 的 `workflow_default` 可加入图级默认。

Workflow 顶层 `rulesets` 省略时使用内置及所选 Plugin 的图级默认，显式列表替换默认，`[]` 取消本图选择。要同时使用内置与自定义图规则，可写 `["vibeflow.workflow", "example.graph"]`。NodesetType 在定义文件顶层选择内部图规则：省略时继承上级，显式列表接管内部选择，`[]` 停止继承；上级仍检查该调用的外部连接。

## 效果范围

| Ruleset | 默认效果范围 |
| --- | --- |
| `vibeflow.process` | 纯处理 |
| `vibeflow.io` | 终端输入输出 |
| `vibeflow.document` / `vibeflow.data_store` | 文件、网络、数据库等 Python I/O |
| `vibeflow.global_state` | 有限效果检查识别的共享／模块状态操作 |

有效规则记录中的 `effect_scope` 表达所选源码效果政策。`flow_kind` 描述执行身份，`external` 标记外部边界；Capability 操作由其声明及有效授权 Rule 控制。

## Python 进程环境变量

`vibeflow.global_state` Ruleset 使用 `vibeflow.no_side_effects` 的 `effect_scope="global_state"`，允许在运行时通过 `os.environ` / `os.environb` 读取、设置、删除环境键和调用其方法，也允许 `os.getenv` / `os.getenvb`、`os.putenv`、`os.unsetenv`。环境键名不受白名单限制；显式 import policy 和导入时执行检查仍生效。Node、BaseLib 和运行插件使用相同效果检查，流程类别名称本身不授予权限。

Node 可显式选择 `rulesets=["vibeflow.global_state"]`。运行插件可保留 `vibeflow.plugin` 集合，并通过自定义 Ruleset 的 `overrides` 把 `base/effects` 调用的 `effect_scope` 设为 `global_state`，覆盖调用路径的写法见 [Ruleset 与局部覆盖](#ruleset-与局部覆盖)。

原值由运行生命周期保存和恢复；排他访问通过同域 `execution_lock` 协调。替换 `os.environ` 对象、修改 `sys.path`、文件、网络、线程及子进程操作继续按各自效果政策检查。

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

Python 返回 `RuleResult` / `RuleRecord`，JS 返回等价 JSON 对象。Rule 运行在对应语言宿主中，规则语言可以与业务 Target 不同；源码事实由各 Target 提供。

`RuleResult.state` 为 `completed`、`failed` 或 `unavailable`，finding 的 `severity` 为 `error`、`warning` 或 `info`。有效 error finding 保留有效 records；损坏的结果使依赖它的 consumer 停止执行。JS records 使用普通 JSON：Map、Date、undefined、非有限数和循环对象需先转换。Python/JS 的公共规则上下文只读，同次检查复用 Target 源码事实。显式源码声明使用 `RuleImplementationDescriptor` 的 `language` 与 `source`。

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

## 相关文档

- [Python 开发](python-development.md)、[JavaScript 开发](javascript-development.md)：业务 Node 和 SDK 实现。
- [项目治理](project-governance.md)：project/root 的规则配置。
- [Workflow 协同](workflow-coordination.md#capability-与显式规则)：Capability 操作授权。
- [产品检查边界](product-check-boundaries.md)：源码检查的实际覆盖。
