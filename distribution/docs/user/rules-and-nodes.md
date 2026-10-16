# Rule、Ruleset 与 Node 声明

Rule 用普通代码检查声明、源码或图关系，Ruleset 将规则组合起来。静态声明提供默认，Config 表达当前对象的选择。本文说明如何使用规则，以及如何通过 Plugin 定义和贡献规则；正式诊断进入 validate、quality 和 review。

## 两种默认声明与三种配置选择

静态默认有两种：Node 类型声明中的 `rulesets` 为该类型的调用提供局部默认；Plugin 贡献的 Ruleset 设置 `workflow_default=True`（Python）或 `workflow_default:true`（JS/TS），为 Workflow 提供图级默认。加载 Plugin 后，其声明的 Workflow 默认才会生效；仅把普通 Rule/Ruleset 放进插件不会自动执行。

动态选择有三处：Workflow Config、Nodeset 定义 Config、单次 Node 调用 Config。这些位置都使用 `rulesets` 字段，引用已由内置或所选 Plugin 提供的资源。

## 选择、替代与继承

| 使用位置 | 未填写 `rulesets` | 显式非空列表 | 显式 `[]` |
| --- | --- | --- | --- |
| Workflow | 使用内置及所选 Plugin 的 `workflow_default=True` Ruleset | 替代整个静态默认列表 | 取消根图选择 |
| Nodeset 定义 Config | 继承上级有效图选择 | 接管内部，替代继承列表 | 接管内部，停止继承 |
| Node 调用 Config | 使用类型声明的默认列表 | 仅替代当前调用的类型默认 | 仅取消当前调用的局部规则 |

类型声明未选择规则时，其默认列表为空。Config 缺省与显式空列表必须保留区别，不能用 `null` 表示选择。Node 的 `rulesets` 是调用声明字段，不属于业务 `params`。例如类型默认检查十个 `t`，某调用选择十个 `d`，该调用只执行 `d`，其他同类型调用仍执行 `t`。

所有位置中的字符串明确引用 Ruleset；直接 Rule 使用 `{"rule_id":"example.check","params":{"limit":3}}`。有依赖的 Rule 必须放进 Ruleset，用 `requires/bindings` 声明，不根据列表顺序传递 Records。

```jsonc
{
  "rulesets": ["example.graph"],
  "pipeline": {"nodes": [
    {"id":"normal","type_used":"example.transform"},
    {"id":"special","type_used":"example.transform","rulesets":["example.local"]},
    {"id":"unchecked","type_used":"example.transform","rulesets":[]}
  ]}
}
```

`example.graph` 对这三个调用所在的图施加约束；`special` 同时受自身 `example.local` 的局部检查。Node 空列表不会取消图级约束。子 Nodeset 选择 C 后，上级 B 仍检查它作为父图调用对象的外部连接和契约，内部图由 C 接管，内部 Node 自身规则继续生效。明确填写与父层相同的列表也形成新边界。

显式列表不会自动追加 `vibeflow.workflow` 或其他默认。若需要自定义图规则和内置 Workflow 检查共同生效，应同时列出它们；局部 A 与图级 B 的共同生效则无需合并两份列表。

## 资料与负责范围

Node 类型和调用选择的 Rule 只取得自己的声明、当前调用、当前及继承实现、实际引用的 helper。同文件其他 Node 的源码不会随当前实现一起提供；不能读取完整图、其他调用或全量资源。`scope="source"` 还会移除当前调用及参数，依赖调用参数的规则应使用 `scope="call"`。Rule 与 Plugin 是受信扩展代码。

Workflow/Nodeset Rule 可以读取当前命令取得的完整背景图、相关声明和源码闭包。`facts.graph` 是当前负责的图，子 Nodeset 仅保留外部契约；`facts.global_graph` 是完整背景。`facts.graphs` 明确列出本任务负责的各图及调用路径；默认检查遍历它，不递归背景中的所有定义。未关联的项目文件不会被扫描。

Ruleset 的 `graph_scope` 默认为 `current_graph`，每张图各检查一次；子 Nodeset 在父图中作为调用节点，内部由子任务检查。`effective_subtree` 在有效范围入口执行一次，负责各张继承图，遇到显式子选择停止。重复调用按完整路径分别规划；循环体按静态结构检查，不按迭代重复执行。

```python
from vibeflow.targets.python.sdk import ruleset

workflow_rules = ruleset(id="example.graph", workflow_default=True,
    graph_scope="effective_subtree", calls=[{"id": "check", "rule_id": "example.graph_check"}])
```

`workflow_default` 只贡献静态默认，显式 Workflow 选择会完整替代它。同一个 Ruleset 及其嵌套依赖必须使用同一图范围；嵌套 Ruleset 未填写范围时继承外层，显式混用两种范围会报错。Node 不能选择整体范围 Ruleset。`source/call` 与图范围是不同概念。

整体 Ruleset 可以先分析各图，再让多个检查 Rule 通过 Records 和明确依赖共享结果。内置 `vibeflow.workflow` 使用整体范围，负责综合 Workflow 审查。

同一规则出现在不同调用、阶段或负责范围时，可以执行多次。需要核对当前配置时，用 `review-rules` 预览选择、来源与依赖，再用 `validate` 或 `quality` 查看实际诊断。空选择不跳过真正的语法、实现绑定和原生编译错误。

## 通过 Plugin 提供 Workflow 默认规则

以下 Python 插件检查每张负责图的直接调用数量。它不递归遍历背景图，因此子 Nodeset 内部由该子图自己的有效规则检查。

```python
from vibeflow.targets.python.sdk import Plugin, rule, ruleset

@rule(id="example.graph_limit",
      params_schema={"limit": {"type": "integer", "minimum": 1}},
      params_defaults={"limit": 10})
def check_graph(context, inputs, params):
    findings = []
    for item in context.require("graphs"):
        count = len(item["graph"].nodes)
        if count > params["limit"]:
            findings.append({
                "rule_id": "EXAMPLE.GRAPH.TOO_WIDE", "severity": "warning",
                "object_type": "workflow", "object_id": item["owner"],
                "message": "当前图的直接调用数量超过限制。",
                "details": {"count": count, "call_paths": [list(item["call_path"])]},
            })
    return {"findings": findings}

graph_rules = ruleset(
    id="example.graph", workflow_default=True, graph_scope="current_graph",
    calls=[{"id": "check", "rule_id": "example.graph_limit"}],
    entrypoints={"static": ["check"]},
)
plugin = Plugin(id="example.rules", resources=[check_graph, graph_rules])
```

JS/TS 使用相同声明字段，检查函数读取 `context.facts.graphs`：

```ts
import {definePlugin, defineRule, defineRuleset} from "@vibeflow/plugin";

export const graphLimit = defineRule({
  id: "example.graph_limit",
  params_schema: {limit: {type: "integer", minimum: 1}},
  params_defaults: {limit: 10},
  check(context, inputs, params) {
    const findings = [];
    for (const item of context.facts.graphs) {
      const count = item.graph.nodes.length;
      if (count > params.limit) findings.push({
        code: "EXAMPLE.GRAPH.TOO_WIDE", severity: "warning",
        subject_id: item.owner, message: "当前图的直接调用数量超过限制。",
        details: {count, call_paths: [item.call_path]},
      });
    }
    return {findings};
  },
});
export const graphRules = defineRuleset({
  id: "example.graph", workflow_default: true, graph_scope: "current_graph",
  calls: [{id: "check", rule_id: "example.graph_limit"}],
  entrypoints: {static: ["check"]},
});
export const plugin = definePlugin({id: "example.rules", resources: [graphLimit, graphRules]});
```

保存为 `plugins/rules.py` 或 `plugins/rules.ts`，在顶层 Workflow 的 `plugins` 中选择导出。下面是配置片段；JS/TS 将文件扩展名改为 `.ts`：

```jsonc
{
  "plugins": [{"source": {"kind": "file", "ref": "plugins/rules.py", "export": "plugin"}}]
  // 不填写 rulesets：example.graph 和内置 Workflow 默认共同生效。
}
```

要动态指定图规则，填写 `"rulesets": ["example.graph"]`；这样只保留该选择。要同时保留内置综合检查，填写 `["vibeflow.workflow", "example.graph"]`。Node 局部规则按自己的列表独立生效。

## Nodeset 接管的配置位置

Nodeset 的图规则写在导入的定义文件顶层，与 `pipeline` 并列，而非写在父图调用它的 Node 上。例如下面是 Nodeset 定义片段：

```jsonc
{
  "type_key": "example.block",
  "display_name": "Block", "description": "自定义内部约束",
  "requires": [], "provides": [],
  "rulesets": ["example.graph"],
  "pipeline": {"nodes": [], "edges": []}
}
```

删除 `rulesets` 字段则继承父图；改成 `[]` 则停止继承。所需 Plugin 仍由顶层 Workflow 选择。实际使用时在 `pipeline` 中填写内部节点和连接。

## 完整 Node 声明

在所属语言的插件中声明资源，并由 workflow 显式选择。例如 Python 的模型功能块：

```python
from vibeflow.targets.python.sdk import Plugin, node, ruleset, RuleCall

model_rules = ruleset(
    id="ml.model_block", calls=[RuleCall(id="base", ruleset_id="vibeflow.process")],
    entrypoints={"import": ["base"], "static": ["base"], "run": ["base"]},
)

@node(
    type_key="ml.model_block", display_name="模型功能块", description="一个明确的模型功能",
    flow_kind="process", tags=["model_block"], rulesets=["ml.model_block"],
    presentation={"fill": "#dbeafe", "shape": "rect", "icon": "M"},
    contract={},
)
class ModelBlock:
    def run_pure(self, inputs, params):
        return {}

plugin = Plugin(id="ml", resources=[ModelBlock, model_rules])
```

SDK 将声明与实现一起提供给 Plugin。workflow 使用 `plugins: [{"source": {"kind": "file", "ref": "plugins/model.py"}}]` 后才能通过 `type_used` 引用这些资源。

SDK 声明统一保存 Node 的契约、参数、实现、Ruleset 与展示。Node 类型声明中的列表提供调用默认；调用 Config 的缺省、非空替代与 `[]` 取消遵守上述表格。示例中的 `ml.model_block` 复用 `vibeflow.process`，包含无副作用等默认检查；领域插件可以继续加入模型归属规则。`flow_kind` 表达执行身份，tags/metadata 提供领域规则使用的业务资料。

颜色和形状按原生默认、Node 默认、状态、调用点 style 的顺序解析。Architecture 分别保存有效展示、逐字段来源、真实 flow_kind、external、planned 和规则标记。Node、BaseLib、Plugin 与 Host 的支撑文件和展示字段见[多文件资源](multifile-resources.md)。

## 一条规则

```python
from vibeflow.targets.python.sdk import rule
from vibeflow.core import Finding
from vibeflow.core.rules import RuleRecord, RuleResult

@rule(
    id="example.limit", description="检查当前范围内的领域约束",
    params_schema={"limit": {"type": "integer", "minimum": 1}},
    params_defaults={"limit": 3}, outputs={"count": "example.count.v1"},
)
def check(context, inputs, params):
    count = len(context.require("source_context").helpers(context.subject["type_key"]))
    findings = ()
    if count > params["limit"]:
        findings = (Finding(
            code="EXAMPLE.COUNT.EXCEEDED", severity="error",
            subject_type="node", subject_id=context.subject["type_key"],
            message="当前 Node 的 helper 数量超过限制。", details={"count": count},
        ),)
    return RuleResult(records={"count": RuleRecord("example.count.v1", count)}, findings=findings)
```

把 `check` 放入固定插件的 `resources`。JS/TS 使用相同的具名 records：

```ts
import {defineRule} from "@vibeflow/plugin";
export const count = defineRule({
  id: "example.count", outputs: {count: "example.count.v1"},
  check(context, inputs, params) {
    return {records: {count: {type_id: "example.count.v1", value: 1}}, findings: []};
  },
});
```

JavaScript/TypeScript 使用相同的 `check(context, inputs, params)` 顺序，允许 Promise，返回值遵守严格 JSON 契约。records 可以包含对象、数组、字符串、有限数值、布尔和 null；Map、Date、undefined 及循环对象会产生结果错误。完整类型见发行包的 `kernel/javascript/rule_abi.d.ts`，Rule ABI 为 `vibeflow.rule.v2`。

正式诊断的 `definition_id` 是稳定规则资源 ID，`code` 是诊断码；一个规则可以产生多种诊断码。`rule_id` 是通用 Finding 中诊断码的别名。

Rule 的 `scope` 默认为 `call`，每个调用分别检查；`source` 用于源码检查，只有局部源码、实现、声明、有效 Rule 参数和输入一致时才在本次检查中复用。

`state` 的 completed/failed/unavailable 表示资料是否完成，findings 表示审查意见。completed 且符合输出契约的 records 可供依赖消费，包括有效空列表及伴随 error finding 的 records；解析失败或缺失所需输出时，依赖消费者停止执行。

## Ruleset 与局部覆盖

```python
from vibeflow.targets.python.sdk import ruleset, RuleCall, RuleRelation

console_process = ruleset(
    id="example.console_process",
    calls=[RuleCall(id="base", ruleset_id="vibeflow.process")],
    relations=[RuleRelation(source="$self", target="base/effects", kind="overrides",
                            params={"effect_scope": "terminal"})],
    entrypoints={"static": ["base"], "run": ["base"], "import": ["base"]},
)
```

JS `defineRuleset` 使用同样的 `calls/relations/entrypoints` 字段；也可以像前面的示例一样用字典填写这些字段。

保持 Node 的 flow_kind 为 process，只把声明的 Ruleset 改成这个组合，就能允许其运行方法访问终端 print。顶层导入约束是另一个调用 `base/imports`，要允许模块初始化行为也需明确覆盖它；运行授权不会自动放开模块初始化。

局部调用 ID 标识一次使用，定义 ID 标识可复用资源。关系 `A → B`：includes 表示 A 包含 B，requires 表示 A 读取 B 的具名输出而 B 先执行，overrides 表示 A 在当前组合覆盖 B 参数或实现。requires 的 bindings 是 `{消费者输入名: 提供者输出名}`，实现替换用 replace_rule 指向替代规则且保持目标接口。

覆盖作用于局部调用实例，明确的覆盖链决定优先级。同值和不同字段可合并；同字段不同值且没有明确覆盖链时报冲突。includes/requires/overrides 分别检查循环，混合图可以保留各关系允许的结构。

Workflow 默认包含 `vibeflow.workflow`；Nodeset 缺省继承上级有效选择，显式配置建立接管边界。空选择取消该范围的图级审查；实际解析、符号绑定与执行计划仍由 Target 和原生编译器完成。

源码主题也使用同一组合机制：`vibeflow.quality.files`、`vibeflow.quality.dependencies` 和 `vibeflow.quality.structure` 分别检查文件、依赖与结构。它们接收普通 Rule 参数，例如 `max_file_lines`、`max_function_branches` 和 `max_dependency_chain`；调用参数与局部 overrides 可以覆盖默认值。Node 或 workflow 选择这些主题时，只分析该命令已取得的源码及实现闭包，不扩大到整个项目。

正式报告的 `rule_executions` 保存实际计划和结果，`record_availability` 区分资料可用、不可用及未选择；未检查的依赖或结构结果为 `null`。failed/unavailable 表示检查未完成，会使正式检查失败。

## 效果与导入参数

效果权限来自实际选中 Rule 的有效参数，与 Node、BaseLib、Plugin 或 Host 的身份独立。共享源码仍按各资源自己的参数分别检查。

同一插件声明文件可以贡献独立的 Node、Host 或生命周期资源。效果检查从当前资源的真实实现与可达 helper 出发，不把它的参数应用到闭包内未被其使用的其他资源。Node 调用的库 helper 仍受 Node 自身的效果选择约束。compiler Plugin 若实际写文件，应显式选择 python_io；编译身份不授予额外权限。Rule/compiler 专用依赖留在检查编译环境，运行产物按真实引用打包。

| effect_scope | 允许的效果 |
| --- | --- |
| none | 不授予效果权限 |
| terminal | 终端输入输出，例如 print/console；不允许 fetch 或文件 I/O |
| python_io | 各 Target 对应的一般 I/O；显式导入禁止继续生效 |
| global_state | 共享或模块状态；不允许修改 builtin、原型及宿主关键状态 |
| trusted | 不增加权限 |

默认效果规则不禁止 Date、performance 或 Math 的时间与随机数操作，也不证明算法确定性。各 Target 的有限外部操作检查仍按实际所选政策执行，两个语言分析器的覆盖不保证完全相同。

effects 与 imports Rule 的 `policy.imports` 支持 `allowed_roots`、`banned_roots`、`allowed_modules`、`banned_modules` 四个字符串数组。显式模块禁止优先，其次检查模块允许，再处理根政策；根允许是同根禁止的例外。允许只影响导入政策，不解除效果检查或未声明资源依赖。JS 支持 scoped npm 包、子路径，以及 fs/node:fs 等价形式。

Python effects 的默认根禁止数组为空，并保留 urllib.parse/vibeflow 模块允许；imports-only 的四数组默认都为空，仍检查导入期执行和真实 ownership。importlib 不因模块名被默认禁止；项目可在所选规则的政策中明确禁止它。显式空数组不会回退旧禁止表。参数只能包含实际 handler 消费的内容，未知或不相关字段明确失败；对象参数的显式覆盖整体替换原对象，有效参数与来源在正式记录中可查。

global/nonlocal 声明和 Node 调用内部的局部闭包不等同于共享状态修改。规则检查可明确识别的模块全局赋值、删除、共享对象变异及外部操作；复杂归属未知时不据此证明行为或产生硬错误。有限输入写入规则独立检查直接输入写入与简单直线别名，不对无赋值值的类型注解报告写入，也不追踪跨函数污染。

## 入口、范围与源码归属

import 检查在后续实现绑定前执行，static 用于正式静态检查，run 执行运行入口选择的规则。新领域 Ruleset 未填写 run/import 时，这两个入口为空；未填写 static 时执行其静态组合。插件固定定义及直接导入先初始化，延迟源码可保留检查后绑定的顺序，详见[加载与检查](plugins-and-integrations.md#加载与检查)。

Workflow 及实际调用的 Nodeset/Loop 也执行所选 import 入口。此时可读取图、声明和当前源码资料；依赖绑定或编译结果的检查放入后续入口。import 返回错误、failed 或 unavailable 时停止后续绑定或构建。已经加载但未调用的 Nodeset 检查声明和真实可得资料，上下文标记为 `nodeset_definition`，调用路径为空。

公开资料边界由选择位置决定，见上面的“资料与负责范围”。Python 提供 SourceContext 的符号、导入、helper 引用和归属；JS 提供只读文本、符号、导入与 AST 查询。源码在本次检查内复用，引用与所有权分别记录，共享文件按各所属资源的规则分别检查。

规则通过 `context.subject` 取得当前对象声明，通过 `context.scope` 了解实际范围。Node 检查中，Python 的 `context.subject["descriptor"]` 是只读 NodeDescriptor，JS 是同模型的 JSON 对象；库、插件与 Host 检查提供各自的声明。调用级规则读取当前调用，源码级规则不取得调用列表或当前调用参数。

Python 的公开分析对象是 `context.require("source_context")`，类型从 `vibeflow.targets.python.quality` 导入。常用查询如下：

| 接口 | 返回资料 |
|---|---|
| `nodes` / `calls` | Node 局部视图中仅有自己的声明与实现，calls 为空；当前调用另由 facts.call 提供 |
| `files` / `file(path)` | 源码文本、root、解析错误和独立 AST 副本 |
| `symbols` / `symbol(path, name)` | 类、方法、函数和模块变量；起止行号和 AST 副本 |
| `imports` | 源路径、specifier、解析后的 module/目标路径、symbol/alias 和行列；范围外或无法解析的目标路径为空 |
| `references` | 可见范围内已解析的符号调用、引用关系及位置 |
| `owners(symbol_id)` | 实现归属或 helper 引用关系，Node 局部视图只记录当前实现的归属 |
| `import_closure(path)` | 公开局部视图中的实际引用闭包，范围外资料不可查询 |
| `metrics(type_key)` | 与默认健康规则共享的只读实现、helper 和依赖链指标 |
| `helpers(type_key)` | 当前 Node 实现可达的已解析辅助符号 |

JS 的 `context.facts.source_files` 给出当前实现路径，`context.sources` 提供 `text(path)`、`ast(path)`、`symbols(path)`、`imports(path)`、`reachable(path)`、`ownership(path)` 和 `nodes(path, kind)`。类型及返回结构见 Rule ABI 声明；AST 节点是 TypeScript 分析服务提供的只读局部视图；未知路径报 `RULE.SOURCE.UNAVAILABLE`。两种 Target 的语言专属查询不同，规则入口、声明、参数、具名 records 和诊断协议一致。

JavaScript 的 `facts.graph` 是只读 JSON 声明快照。`graph.nodesets` 按 `type_key` 保存当前图调用的 Nodeset 外部边界；整体任务通过 `facts.graphs` 访问负责的子图，通过 `facts.global_graph` 查背景。import 阶段不提供 `compiled`，static 阶段仅在真实原生编译后提供它。

领域插件用明确约定识别模型定义和功能块，例如参数化 tags 及 `model_forward` / `modelForward` 符号。选中的领域规则检查当前命令取得的对象和源码闭包；检查范围见[命令与产物](commands-and-results.md#检查范围)。

```bash
python run.py review-rules --config python_project/configs/main.jsonc --node process --json
python run.py review-rules --config python_project/configs/main.jsonc --output rules.svg
```

review-rules 加载选中插件的受信固定定义，再展开有效计划；框架不调用 Rule、Node 或生命周期工厂。

## 插件贡献与规则语言

插件导出固定资源列表：Python `Plugin(id="example.package", resources=[MyNode, check, my_rules])`；JS/TS `definePlugin({id: "example.package", resources: [myNode, check, myRules]})`。跨模块定义可以普通导入，再将资源加入所选插件。插件配置提供参数及上下文，资源、契约和规则图保持固定。

SDK 记录 Rule 的执行语言和源码入口。一个执行族最多一个实现，JS/TS 属于同一族；JS Rule 在 Node worker 中检查，业务的 Node.js/Browser 平台作为 `context.target` 资料供规则使用。BaseLib、Plugin 和 HostExtension 同样选择自己的 rulesets；插件声明源码使用独立的 declaration_rulesets。

公开版本为 Plugin ABI v3、Rule ABI v2 和 Workflow ABI v7。升级旧项目的写法对应见[声明迁移](rule-system-migration.md)。
