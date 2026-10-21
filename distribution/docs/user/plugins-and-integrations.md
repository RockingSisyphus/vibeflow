# Plugin 与宿主 API

Plugin 是一个原子资源包，贡献 NodeType、Rule、Ruleset、DataSchema、私有 BaseLib、Capability 及可选 compiler/runtime 扩展。业务 Node 在所属 `nodes/` 中独立声明，不放入 Plugin 的 `resources`。

目录和可见性、四级规则配置及迁移要求见 [项目治理与资源分层](project-governance.md)。规则参数、契约与调用配置见 [Rule、Ruleset 与 Node](rules-and-nodes.md)。

## 声明与选择

```python
# plugins/layout/plugin.py
from vibeflow.targets.python.sdk import Plugin, node_type

process = node_type(
    id="layout.process",
    display_name="Process",
    rulesets=["vibeflow.process"],
    presentation={"shape": "hex", "fill": "#f2e6c5", "stroke": "#191919"},
)
plugin = Plugin(id="layout", resources=[process])
```

```python
# nodes/calculate.py
from vibeflow.targets.python.sdk import node

@node(id="app.calculate", node_type="layout.process", contract={})
class Calculate:
    def run_pure(self, inputs, params):
        return {}
```

```jsonc
{
  "plugins": [{"source": {"kind": "file", "ref": "plugins/layout/plugin.py"}}],
  "pipeline": {
    "nodes": [{"id": "calculate", "definition_id": "app.calculate",
      "display_name": "Calculate", "description": "执行计算"}]
  }
}
```

JavaScript/TypeScript 使用相同的分层：包内通过 `defineNodeType`、`defineRule` 等固定声明贡献资源；`nodes/` 通过 `defineNode({id, node_type, contract, run, ...})` 声明业务实现。用 `scope: "project"` 选择项目共享 Plugin，默认只在当前 root 的 `plugins/` 内定位文件。

Plugin 的文件入口及贡献代码必须在同一包内。包内相对导入可组织多个文件；外部标准库、第三方依赖与公开 SDK 正常使用。业务 Node 不能通过引入 Plugin 的实现代码取得其类型或权限，按类型 ID 引用即可。

`id` 可选，用来核对导出的 Plugin 身份。`enabled: false` 跳过该选择；`status: "planned"` 保存尚未实现的规划，不加载占位源码。`config` 与 Plugin 的 defaults/schema 合并后交给该次操作的只读上下文，不决定固定资源列表。

Plugin 的安装只使规则可被选择。Ruleset 的 `workflow_default` 可加入图级默认；Plugin 自身 `rulesets` 检查生命周期实现，`declaration_rulesets` 检查包声明，不能把它们当成所有 Node 的局部规则。项目/root 治理中加载的包不自动加入 workflow。

## 原生加载与生命周期

准备层加载受信 SDK 声明，校验所有权、可见性、配置和冲突，再执行所选检查和实现绑定。声明加载可能执行其模块初始化；检查不是沙箱，也不能撤销已经发生的初始化。延迟实现通过显式 source 定位，所选 import 检查失败后不进入业务绑定。

`inspect-resources` 与 `review-rules` 读取声明和选择，不调用业务 `run_pure/run`、检查函数或生命周期工厂。

Plugin 可提供 compiler/runtime 工厂，每个适用操作创建独立实例，并在结束或失败时释放。它们用于编译、观察等框架扩展。Python 工厂接收只读上下文，包括 `context["config"]`；JS 工厂使用 `context.config`。不要在模块初始化时创建运行实例。

```python
# 仍位于 Plugin 包内
class Audit:
    def before_run(self, payload):
        pass
    def dispose(self):
        pass

def create_runtime(context):
    return Audit()

# plugin = Plugin(id="audit", resources=[...], runtime=create_runtime, ...)
```

嵌套 JSON 配置可用公开的 `freeze_json` / `thaw_json` 转换。它们复制容器，保留值与结构；修改导出副本不会修改原配置。

## 宿主集成

宿主提供普通 Capability API，Node 显式声明所用操作，并由 Rule 授权。比如浏览器应用构造一个尚未监听消息的 API，将其注入运行；图中的“建立监听”节点调用 open，接收节点等待消息，关闭节点调用 close。宿主提供取消后的必要资源释放，图中仍可审查正常路径的关键生命周期。

Host Extension 已删除，不再提供自动宿主工厂、隐藏监听或自动托管 workflow 生命周期。浏览器、桌面程序和后台服务保留自己的生命周期；跨程序拉起和收发使用 [workflow 协同](workflow-coordination.md)。

Capability 声明和有效 Rule 策略共同限定上下文提供的操作；它们不是操作系统权限隔离。节点的名字、形状、颜色和 `flow_kind` 不赋予功能。

## 审查资源

默认审查生成结构化快照，通过 HTML 查看流程和资源。Plugin 视图按包显示一张卡片；BaseLib 视图仅显示独立库及其依赖。包内事实仍保存在快照详情中，但不会展开成一堆内部实现节点。需要 SVG 对照时使用 `review --with-svg` 或显式 `--output FILE.svg`。
