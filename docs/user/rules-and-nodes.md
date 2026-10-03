# Rule、Ruleset 与 Node 声明

规则是普通代码，规则组合是可检查的声明。Node 选择一套 Ruleset，核心展开组合、解析覆盖、执行依赖，正式诊断进入 validate、quality 和 review。

## 完整 Node 声明

在所属语言的插件中声明资源，并由 workflow 显式选择。例如 Python 的模型功能块：

```python
from vibeflow.targets.python.sdk import Plugin, node

@node(
    type_key="ml.model_block", display_name="模型功能块", description="一个明确的模型功能",
    flow_kind="process", tags=["model_block"], rulesets=["ml.model_block"],
    presentation={"fill": "#dbeafe", "shape": "rect", "icon": "M"},
    contract={},
)
class ModelBlock:
    def run_pure(self, inputs, params):
        return {}

# model_rules 是同插件或显式选中的另一插件贡献的 Ruleset。
plugin = Plugin(id="ml", resources=[ModelBlock, model_rules])
```

SDK 自动保存 Descriptor、实现和源码位置，普通导入不修改 Catalog。workflow 使用 `plugins: [{"source": {"kind": "file", "ref": "plugins/model.py"}}]` 后才能通过 `type_used` 引用这些资源。

NodeDescriptor 是唯一权威声明，保存契约、参数、实现、Ruleset 与展示。省略 `rulesets` 或指定 `[]` 都表示未选择 Node 审查规则。默认 Process 项目明确选中 `vibeflow.process`，其中包含无副作用规则；核心不按 flow_kind 隐式补回它。tags/metadata 是供领域规则解释的自由资料，不提供分类继承或权限。

颜色和形状按原生默认、Node 默认、状态、调用点 style 的顺序解析。Architecture 保存有效值及每个字段来源。自定义形状不会移除真实 flow_kind、external、planned 和规则标记。

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

JavaScript/TypeScript 使用相同的 `check(context, inputs, params)` 顺序，允许 Promise，返回严格 JSON；Map、Date、undefined、非有限数值和循环对象被拒绝，不会悄悄转换；类型契约见发行内核 `targets/javascript/resources/rule_abi.d.ts`。Rule ABI 是 `vibeflow.rule.v1`。正式诊断的 `definition_id` 是稳定规则资源 ID，`code` 是诊断码；一个规则可以产生多种诊断码。`rule_id` 仍是通用 Finding 中诊断码的别名。

Rule 的 `scope` 默认为 `call`，每个调用分别检查；`source` 用于源码检查，只有源码身份、声明、有效配置和输入一致时才在本次检查中复用。

`state` 的 completed/failed/unavailable 与 findings 分开。有错误意见的规则仍可能提供可用事实；有效空列表也能作为依赖资料。依赖不能把“没有诊断”当成资料成功。解析失败或缺失输出不会伪造完成。

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

覆盖不修改共享定义，不靠文件加载顺序决定结果。同值和不同字段可合并；同字段不同值且没有明确覆盖链时报冲突。includes/requires/overrides 分别检查循环，混合图不必整体无环。

workflow 和 Nodeset 文件顶层也可选择 `rulesets`，默认 `vibeflow.workflow`。这里的空选择取消审查意见，仍须具备实际解析、符号绑定和执行计划，不能创造不存在的 Target 能力。

源码主题也使用同一组合机制：`vibeflow.quality.files`、`vibeflow.quality.dependencies` 和 `vibeflow.quality.structure` 分别检查文件、依赖与结构。它们接收普通 Rule 参数，例如 `max_file_lines`、`max_function_branches` 和 `max_dependency_chain`；调用参数与局部 overrides 可以覆盖默认值。Node 或 workflow 选择这些主题时，只分析该命令已取得的源码及实现闭包，不扩大到整个项目。

供 Target 或工具复用的 `evaluate_project_quality(facts, rulesets=..., rules=..., ruleset_catalog=..., handlers=...)` 接收真实 `ProjectQualityFacts`，支持直接规则或自定义组合。省略选择使用内置组合，空选择只保留事实。报告的 `rule_executions` 记录实际计划和结果，`record_availability` 区分可用、不可用及未选择；未检查的依赖或结构结果为 `null`。规则返回 failed/unavailable 会使正式检查失败，即使没有返回错误意见。

## 入口、范围与源码归属

插件固定定义先加载。import 在后续实现绑定前执行，对于尚未加载的独立延迟实现可以阻止导入；不能撤销插件受信入口及直接导入模块已经发生的初始化。static 用于正式静态检查；run 保留运行入口所选规则。新领域 Ruleset 未填写 run/import 时，这两个入口为空；未填写 static 时执行其静态组合。选择 Ruleset 不创建生命周期实例；选中插件可以同时贡献资源和 compiler/runtime 工厂，工厂仍在各自原生阶段调用。

Workflow 及实际调用的 Nodeset/Loop 也执行所选 import 入口。此时提供已读取的图、声明和当前源码资料，尚未完成的绑定或编译结果不提供；需要这些结果的检查应放入后续入口。import 返回错误、failed 或 unavailable 时停止后续绑定或构建；报告区分已加载、未加载和未知源码状态。已经加载但未调用的 Nodeset 仍检查声明和真实可得资料，上下文标记为 `nodeset_definition`，不提供虚构的调用路径。

上下文覆盖当前命令实际范围中的声明、调用、实现与相关辅助源码。Python 提供 SourceContext 的符号、导入、helper 引用和归属；JS 提供只读文本、符号、导入与 AST 查询。源码只在本次检查内复用。引用 helper 不等于归属，共享 helper 不继承调用者中最宽权限。

规则通过 `context.subject` 取得当前声明，通过 `context.scope` 了解实际范围。Python 的 `context.subject["descriptor"]` 是只读 NodeDescriptor，JS 是同模型的 JSON 对象。调用级规则可以读取实际调用；源码级规则取得全部调用关联，不提供当前调用身份，避免共享源码结果依赖恰巧先检查的调用。

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

模型定义和一个功能块如何识别，由领域规则的明确约定决定；核心不自动理解任意模型代码。未调用、未选择或不在当前命令范围中的领域代码不承诺覆盖。Python/JS 规则都是受信扩展代码，只读上下文不是操作系统沙箱。

```bash
python run.py review-rules --config python_project/configs/main.jsonc --node process --json
python run.py review-rules --config python_project/configs/main.jsonc --output rules.svg
```

review-rules 加载选中插件的受信固定定义，再展开有效计划；框架不调用 Rule、Node 或生命周期工厂。

## 插件包与迁移

插件导出固定资源列表：Python `Plugin(id="example.package", resources=[MyNode, check, my_rules])`；JS/TS `definePlugin({id: "example.package", resources: [myNode, check, myRules]})`。跨模块定义可以普通导入，只有列入选中插件的资源才注册。配置只影响参数及上下文，不能生成不同契约或规则组合。

| 旧接入 | 代码插件接入 |
|---|---|
| JSONC Node/Rule 文件、descriptors 目录和 bundle | SDK 声明与实现，固定插件 resources |
| registry.py 与项目级注册 | workflow.plugins 显式 source |
| 类内 NODE_INFO/CONTRACT | @node 声明，类保留 run_pure |
| flow_kind 或 external 隐式放行 | 显式 Ruleset 与副作用参数 |
| policy validate hooks | @rule/defineRule 与 Ruleset |
| 生命周期 module/class 选择 | Plugin/definePlugin 的 compiler/runtime 工厂 |
| 调用点逐个配置颜色 | Node presentation 默认，调用 style 覆盖 |

Plugin ABI 为 v3，Rule ABI v1 和 Workflow ABI v4 不变。旧登记入口明确报告迁移错误，不继续扫描或加载。

领域示例展示插件包同时贡献完整 Node 和规则的用法：模型功能块乘以 `2`，数据变换节点加 `1`，整个工作流计算 `3 × 2 + 1 = 7`。Node 自己声明展示和规则选择，领域规则通过参数化 tags 识别归属，并以 `model_forward` / `modelForward` 作为明确代码约定；诊断包含错误定义的位置和行号，原生连边负责实际数据传递。

Rule 实现使用独立的 `RuleImplementationDescriptor(language, source)`，没有业务平台 targets。一个执行族最多一个实现，JS/TS 属于同一族。JS Rule 在 Node worker 中运行，业务的 Node.js/Browser 平台作为 `context.target` 资料提供。BaseLib、Plugin 和 HostExtension 也直接选择 rulesets；生命周期绑定和健康审查分别消费真实的协议事实和规则结果。
