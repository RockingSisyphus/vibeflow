# Rule、Ruleset 与 Node 声明

规则是普通代码，规则组合是可检查的声明。Node 选择一套 Ruleset，核心展开组合、解析覆盖、执行依赖，正式诊断进入 validate、quality 和 review。

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

SDK 自动保存 Descriptor、实现和源码位置，普通导入不修改 Catalog。workflow 使用 `plugins: [{"source": {"kind": "file", "ref": "plugins/model.py"}}]` 后才能通过 `type_used` 引用这些资源。

SDK 声明统一保存 Node 的契约、参数、实现、Ruleset 与展示。省略 `rulesets` 或指定 `[]` 都表示未选择 Node 审查规则。示例中的 `ml.model_block` 复用 `vibeflow.process`，包含无副作用等默认检查；领域插件可以继续加入模型归属规则。`flow_kind` 表达执行身份，tags/metadata 提供领域规则使用的业务资料。

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
    count = len(context.require("source_context").nodes)
    findings = ()
    if count > params["limit"]:
        findings = (Finding(
            code="EXAMPLE.COUNT.EXCEEDED", severity="error",
            subject_type="node", subject_id=context.subject["type_key"],
            message="当前检查范围内的功能块数量超过限制。", details={"count": count},
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

JavaScript/TypeScript 使用相同的 `check(context, inputs, params)` 顺序，允许 Promise，返回值遵守严格 JSON 契约。records 可以包含对象、数组、字符串、有限数值、布尔和 null；Map、Date、undefined 及循环对象会产生结果错误。完整类型见发行包的 `kernel/javascript/rule_abi.d.ts`，Rule ABI 为 `vibeflow.rule.v1`。

正式诊断的 `definition_id` 是稳定规则资源 ID，`code` 是诊断码；一个规则可以产生多种诊断码。`rule_id` 是通用 Finding 中诊断码的别名。

Rule 的 `scope` 默认为 `call`，每个调用分别检查；`source` 用于源码检查，只有源码身份、声明、有效配置和输入一致时才在本次检查中复用。

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

JS `defineRuleset` 使用同样的 `calls/relations/entrypoints` 字段；字典形式和 Python `RuleCall/RuleRelation` 使用同一 Core 图模型，不另建组合语言。

保持 Node 的 flow_kind 为 process，只把声明的 Ruleset 改成这个组合，就能允许其运行方法访问终端 print。顶层导入约束是另一个调用 `base/imports`，要允许模块初始化行为也需明确覆盖它；运行授权不会自动放开模块初始化。

局部调用 ID 标识一次使用，定义 ID 标识可复用资源。关系 `A → B`：includes 表示 A 包含 B，requires 表示 A 读取 B 的具名输出而 B 先执行，overrides 表示 A 在当前组合覆盖 B 参数或实现。requires 的 bindings 是 `{消费者输入名: 提供者输出名}`，实现替换用 replace_rule 指向替代规则且保持目标接口。

覆盖作用于局部调用实例，明确的覆盖链决定优先级。同值和不同字段可合并；同字段不同值且没有明确覆盖链时报冲突。includes/requires/overrides 分别检查循环，混合图可以保留各关系允许的结构。

workflow 和 Nodeset 文件顶层也可选择 `rulesets`，默认 `vibeflow.workflow`。空选择取消相应审查；实际解析、符号绑定与执行计划仍由 Target 和原生编译器完成。

源码主题也使用同一组合机制：`vibeflow.quality.files`、`vibeflow.quality.dependencies` 和 `vibeflow.quality.structure` 分别检查文件、依赖与结构。它们接收普通 Rule 参数，例如 `max_file_lines`、`max_function_branches` 和 `max_dependency_chain`；调用参数与局部 overrides 可以覆盖默认值。Node 或 workflow 选择这些主题时，只分析该命令已取得的源码及实现闭包，不扩大到整个项目。

正式报告的 `rule_executions` 保存实际计划和结果，`record_availability` 区分资料可用、不可用及未选择；未检查的依赖或结构结果为 `null`。failed/unavailable 表示检查未完成，会使正式检查失败。

## 入口、范围与源码归属

import 检查在后续实现绑定前执行，static 用于正式静态检查，run 执行运行入口选择的规则。新领域 Ruleset 未填写 run/import 时，这两个入口为空；未填写 static 时执行其静态组合。插件固定定义及直接导入先初始化，延迟源码可保留检查后绑定的顺序，详见[加载与检查](plugins-and-integrations.md#加载与检查)。

Workflow 及实际调用的 Nodeset/Loop 也执行所选 import 入口。此时可读取图、声明和当前源码资料；依赖绑定或编译结果的检查放入后续入口。import 返回错误、failed 或 unavailable 时停止后续绑定或构建。已经加载但未调用的 Nodeset 检查声明和真实可得资料，上下文标记为 `nodeset_definition`，调用路径为空。

上下文覆盖当前命令实际范围中的声明、调用、实现与相关辅助源码。Python 提供 SourceContext 的符号、导入、helper 引用和归属；JS 提供只读文本、符号、导入与 AST 查询。源码在本次检查内复用，引用与所有权分别记录，共享文件按各所属资源的规则分别检查。

规则通过 `context.subject` 取得当前对象声明，通过 `context.scope` 了解实际范围。Node 检查中，Python 的 `context.subject["descriptor"]` 是只读 NodeDescriptor，JS 是同模型的 JSON 对象；库、插件与 Host 检查提供各自的声明。调用级规则读取实际调用，源码级规则取得全部调用关联。

Python 的公开分析对象是 `context.require("source_context")`，类型从 `vibeflow.targets.python.quality` 导入。常用查询如下：

| 接口 | 返回资料 |
|---|---|
| `nodes` / `calls` | 范围内声明、实现路径和符号；实际调用路径与参数 |
| `files` / `file(path)` | 源码文本、root、解析错误和独立 AST 副本 |
| `symbols` / `symbol(path, name)` | 类、方法、函数和模块变量；起止行号和 AST 副本 |
| `imports` | 源路径、specifier、解析后的 module/目标路径、symbol/alias 和行列；范围外或无法解析的目标路径为空 |
| `references` | 已解析的符号调用和全局引用关系及位置 |
| `owners(symbol_id)` | 实现归属或 helper 引用关系，可以有多个调用者 |
| `import_closure(path)` | 当前文件实际导入闭包和包初始化模块 |
| `metrics(type_key)` | 与默认健康规则共享的只读实现、helper 和依赖链指标 |
| `helpers(type_key)` | 当前 Node 实现可达的已解析辅助符号 |

JS 的 `context.facts.source_files` 给出当前实现路径，`context.sources` 提供 `text(path)`、`ast(path)`、`symbols(path)`、`imports(path)`、`reachable(path)`、`ownership(path)` 和 `nodes(path, kind)`。类型及返回结构见 Rule ABI 声明；AST 节点是 TypeScript 分析服务提供的只读视图。Python 的符号 AST 也是独立副本，不把内部分析缓存交给插件修改。两种 Target 的语言专属查询不同，规则入口、声明、参数、具名 records 和诊断协议一致。

JavaScript 的 `facts.graph` 是只读 JSON 声明快照。`graph.nodesets` 按 `type_key` 保存有限的 Nodeset 声明；每个 `nodeset.graph.nodeset_refs` 列出子图引用的注册表 ID，可以在当前 `facts.graph.nodesets` 查找。引用避免共享注册表形成循环 JSON。import 阶段不提供 `compiled`，static 阶段仅在真实原生编译后提供它。

领域插件用明确约定识别模型定义和功能块，例如参数化 tags 及 `model_forward` / `modelForward` 符号。选中的领域规则检查当前命令取得的对象和源码闭包；检查范围见[命令与产物](commands-and-results.md#检查范围)。

```bash
python run.py review-rules --config python_project/configs/main.jsonc --node process --json
python run.py review-rules --config python_project/configs/main.jsonc --output rules.svg
```

review-rules 加载选中插件的受信固定定义，再展开有效计划；框架不调用 Rule、Node 或生命周期工厂。

## 插件贡献与规则语言

插件导出固定资源列表：Python `Plugin(id="example.package", resources=[MyNode, check, my_rules])`；JS/TS `definePlugin({id: "example.package", resources: [myNode, check, myRules]})`。跨模块定义可以普通导入，再将资源加入所选插件。插件配置提供参数及上下文，资源、契约和规则图保持固定。

SDK 记录 Rule 的执行语言和源码入口。一个执行族最多一个实现，JS/TS 属于同一族；JS Rule 在 Node worker 中检查，业务的 Node.js/Browser 平台作为 `context.target` 资料供规则使用。BaseLib、Plugin 和 HostExtension 同样选择自己的 rulesets；插件声明源码使用独立的 declaration_rulesets。

公开版本为 Plugin ABI v3、Rule ABI v1 和 Workflow ABI v4。升级旧项目的写法对应见[声明迁移](rule-system-migration.md)。
