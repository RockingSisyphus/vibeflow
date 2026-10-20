# 0.16 统一资源与旧 API 退役

自 0.15.0 起，VibeFlow 使用代码插件声明资源。升级时将旧登记转换为所属语言的 SDK 声明和 workflow 插件选择。当前公开契约为 Rule ABI v2、Plugin ABI v3、Workflow ABI v9；原生数据路由、Nodeset、Loop 和业务执行协议保持原有语义。

0.16 完成内部迁移，直接移除旧公开 API。默认资源由自动接入的内置插件贡献，无需在 Config 中声明；内置和外部插件共用贡献校验、来源、冲突处理和实现绑定。资源进入 Catalog 不表示选中了它的规则，显式空 Ruleset 仍只提供资料。

## 删除的接口及替代入口

| 旧接口或输入 | 当前入口 |
| --- | --- |
| NodeInfo、NodeContract、类内 NODE_INFO/CONTRACT | Python `@node` 或完整 NodeDescriptor/NodeContractDescriptor |
| Context、RegistryBase、旧 runtime.config facade、boundary_registry 参数 | 原生 runtime 返回值与 Core 的显式 scope/config 契约；副作用由所选 Rule 与原生 I/O/生命周期承担 |
| BaseLibInfo、BaseLibRegistry、自动 scan/analyze、Registry → Catalog adapter | SDK `base_lib` 声明及 `inspect-resources`、所选 Ruleset |
| PluginInfo、metadata normalizer、module/class 插件选择 | SDK `Plugin` 的 compiler/runtime 工厂与显式 source 选择 |
| workflow base_lib.paths、module/name 注册与 policy.base_lib allowlist | 资源 ID 选择及 Descriptor 中的 base_libs/dependencies/implementation_files |
| JS WorkflowSpec、独立 workflow/parser/validator 与 Plugin parser | WorkflowPlan + 必填 JavascriptBindingPlan；SDK 与统一 decoder |
| 项目级 JavaScript Host 选择 | workflow.host_extensions；项目字段存在即报迁移错误，包括空列表，预览与验证共用该契约 |
| Python pipeline.inputs 缺省或 null 的 required | 每项明确声明 required 为 true 或 false；Core 构造使用 `PipelineInputSpec(key, type, required=True)`，其他位置参数含义保持不变 |
| Target `analyze_python_source` / `analyze_python_source_tree` 的 `check_side_effects` 参数 | Target 只返回源码事实；使用 Application `scan_code_quality(check_side_effects=True)` 或 CLI 的 `--check-side-effects` 执行所选效果 Rule |
| Target `scan_javascript_quality` 默认检查入口 | Target 提取源码事实；Application `vibeflow.tooling.application.javascript.quality_scan.scan_javascript_quality` 复用所选 Catalog 执行项目规则 |

使用正式 CLI 和发行入口时，内置资源自动提供，外部资源通过 Workflow 选择的 Plugin 提供。调用规则是否生效取决于实际的默认或配置选择。

库放在 `boundary`、`nodes`、`runtime` 或其他目录不会改变身份。身份来自声明、具名导出、支撑文件和真实导入位置；未声明的跨资源依赖仍会失败。纯 Node 调用有副作用的库 helper，仍受 Node 自身选中的效果规则约束，即使库的 `rulesets=[]`。

未被资源声明归属的普通代码也不会因目录名成为 Node、BaseLib 或 Plugin；与库入口同目录不构成库归属。普通代码继续参与已选项目规则的数量、复杂度和依赖距离等通用检查。

## Node 自己声明规则和展示

删除 `node_category` 文件、`descriptors.node_categories`、bundle 的 `categories` 引用和 Node 的 `category` 字段。把原分类的默认规则、颜色和形状展开到每个完整 Node。config 继续通过 `type_used` 引用它。

```python
from vibeflow.targets.python.sdk import Plugin, node, ruleset, RuleCall

model_rules = ruleset(
    id="domain.model_block", calls=[RuleCall(id="base", ruleset_id="vibeflow.process")],
    entrypoints={"import": ["base"], "static": ["base"], "run": ["base"]},
)

@node(type_key="model.affine", contract={}, flow_kind="process", tags=["model_block"],
      rulesets=["domain.model_block"], presentation={"fill": "#cceeff", "shape": "hex"})
class Affine:
    def run_pure(self, inputs, params):
        return {}

plugin = Plugin(id="model", resources=[Affine, model_rules])
```

`model_rules` 同样由 SDK 声明并列入插件。workflow 的 `plugins` 使用显式文件/模块 source；项目 `descriptors/registry`、JSONC bundle 和 ID-only 插件选择不再加载。

Node **类型声明**省略 `rulesets` 或填写 `[]`，都表示该类型没有局部默认规则。Node **调用 Config** 省略该字段则使用类型默认；调用显式 `[]` 才取消当前调用的局部选择。需要默认 Process 约束时明确填写 `vibeflow.process`。改变 `flow_kind` 不再获得副作用权限。领域规则通过参数约定 tags，例如 `model_tag=model_block`；核心不判断任意模型代码的功能块，也不规定模型拓扑。

默认展示按原生默认、Node 默认、状态展示、调用点覆盖依次应用。保留系统状态色，Node 默认展示不能占用它们。图中执行身份和诊断标记独立保留。浅蓝模型示例使用 `#cceeff`。

## Rule 声明执行语言和入口

Rule 的实现改用独立的 `RuleImplementationDescriptor(language, source)`。移除实现中的 `targets`、`completion`。这些字段仍属于 Node、Plugin 等原生业务实现的契约。

```ts
import {defineRule} from "@vibeflow/plugin";
export const definitionRule = defineRule({
  id: "domain.model_definition", scope: "source",
  params_schema: {model_tag: {type: "string"}}, params_defaults: {model_tag: "model_block"},
  check(context, inputs, params) { return {records: {}, findings: []}; },
});
```

JS 和 TS 属于同一个执行族，不能分别登记一个 node 实现和一个 browser 实现。使用一个 `check(context, inputs, params)`，按业务平台资料自行处理，或组合不同 Rule。JS Rule 在实际 Node worker 环境加载。

`RuleResult.state` 必须为 `completed/failed/unavailable`；finding severity 必须为 `error/warning/info`。有效 error finding 不取消有效 records；损坏的结果使 provider 失败，其 consumer 不执行。JS records 必须为真实 JSON 数据，Map、Date、undefined、非有限数和循环对象会报错。生命周期中合法的 void 返回不受这项 Rule 数据契约影响。

替换实现保持局部调用身份和输入输出接口，默认参数来自替代 Rule。显式参数和覆盖关系随后生效，报告保留每个有效值的来源。加载顺序不决定覆盖优先级。

## 源码资料与范围

源码解析、符号、导入关系和指标由 Target 提供；同次检查共享资料，公开上下文只读。Python 使用真实导入闭包与显式源码归属，JS 包括 literal dynamic import 和 require。公开 Node/BaseLib/dependency_chain topic 与默认 maintainability 使用相同指标资料。

Node 导入 Rule 检查自身的实际导入闭包。helper 的引用关系与实现归属分别记录，共享文件按各资源所选规则分别检查。已加载未调用的 Nodeset 使用声明及真实可得资料，调用路径为空。planned helper 的初始化由所选 planned Rule 检查。

BaseLib、Plugin、HostExtension 通过 `rulesets` 选择审查，插件包声明使用 `declaration_rulesets`。报告按实际选择记录约束与来源。插件入口先初始化，独立延迟实现按所选导入规则检查后绑定；时序见[加载与检查](plugins-and-integrations.md#加载与检查)。compiler/runtime 生命周期保留原生协议。

`review-rules` 展示当前作用域内的有效规则、参数来源和资源选择，加载受信插件固定定义，框架不调用 Rule、Node 或生命周期工厂。Python 预览可使用 Target 的解析闭包定位已引用库。

## 默认检查行为

综合 Workflow 使用整体范围检查，依赖及实际调用都出现在执行记录中。可独立选择的 topic Rule 使用显式 Ruleset 组合；覆盖有效 `policy` 参数会影响相应判定。

`vibeflow.no_side_effects` 在两个 Target 都消费有效 `effect_scope`、`policy` 参数。Python 的 Node、BaseLib、Plugin 和普通源码共用效果遍历；可解析 helper 按真实函数体判断，纯函数改名为 write/read/close 不改变结果。资源仍独立选择规则，BaseLib 保留自身顶层结构与显式支撑文件检查，不继承调用者权限。

普通项目源码的效果审查默认使用 `none`；`terminal` 仅允许终端效果，`python_io` 允许相应一般 I/O，`global_state` 允许共享或模块状态但不允许修改 builtin、原型及宿主关键状态。`trusted` 不提供额外豁免。scope 不解除显式导入禁止、资源依赖或硬性效果限制。参数细则见[效果与导入参数](rules-and-nodes.md#效果与导入参数)。

迁移旧 policy 时，区分导入禁止与效果分类：Python effects 默认 banned_roots 为空，不再默认禁止 importlib；imports-only 默认四个政策数组为空。旧模板中用于表示一般 I/O 分类的 banned_roots 不应继续作为显式禁令，项目确需禁止的模块则继续明确列出。显式空数组会生效，不回退旧禁用表；effects/imports 不接受指标政策，指标规则也不再记录未消费的导入参数。

所有活动 workflow、Nodeset body、Loop body 和 SDK 输入都必须明确填写布尔 required；必需输入写 true，可缺省输入写 false。运行时先拒绝未声明键再检查必填键，空 inputs 只接受 `{}`。值为 null 仍算键存在，不能用它恢复旧的整组免检行为。低层 portable supplied 输入不得改变原声明的 key、type、required 或顺序。

接口规则检查实际入口 ABI、公开 callable 与声明形状；正常嵌套生成器 helper 不改变 run_pure 的接口，真正含 yield 的入口仍被拒绝。输入类型名与输出键可以重叠，Decision 端口无需固定命名，Python/JS 均接受合法 `examples.outputs`。真实路由及运行输出协议继续由声明、编译和 Runtime 检查，不静态证明返回值构造。Python 默认导入 Rule 保留有限 decorator 和模块结构政策，包括模块级 `try/match`；需要放宽时替换该 Rule。

规则审查源码与架构健康度。项目的类型检查和业务测试负责业务类型及结果；JS AOT 使用原有 TypeScript 转译流程。解析、实现绑定、原生 ABI 与执行结果按各阶段事实报告。

## 代码插件的一次迁移

1. 把 Node/Rule 声明移入 `@node/@rule` 或 `defineNode/defineRule`，与实现放在一起；删除实现类中的重复元数据。Ruleset 用语言对象保持原图关系。
2. 使用固定 `Plugin/definePlugin` 导出，列出全部需要贡献的资源；删除声明工厂与全局注册。
3. 在每个顶层 workflow 的 `plugins` 写入显式 source；Nodeset 导入不隐式开启插件。
4. 把旧生命周期接入改为同插件的 compiler/runtime 工厂；插件参数只读且不同 workflow 隔离。
5. 移除项目 descriptors、bundle、registry 配置。Python 和 JS SDK 随内核发行；TypeScript paths 指向 SDK 类型声明。
6. 使用 `implementation_files` 显式登记 Node、BaseLib、Plugin 与 Host 的支撑文件；Host 和生命周期 Plugin 通过 `base_libs` 引用独立库。
7. 为插件声明填写 `declaration_rulesets`，为生命周期填写 `rulesets`，按各资源需要选择检查。默认可维护性规则逐文件使用 500 行上限。
8. 使用 `inspect-resources --config` 和 `review-rules --config` 核对资源、双方冲突来源、有效参数与原始实现位置，再运行正式检查和业务测试。

旧资源接入会报告明确的迁移诊断。升级后的多文件登记、样式字段和正式图内容见[多文件资源](multifile-resources.md)。

## 统一选择与 Rule ABI v2 迁移

升级后，配置中的字段缺省、显式列表与显式空列表具有不同含义。外部插件应作以下调整：

1. Node 类型声明的 rulesets 作为默认；需要替代的调用在 Config 中填写列表，需要取消时写 `[]`。序列化时保留字段缺省，不能把缺省转成空列表。
2. 希望静态全局生效的 Ruleset 声明 `workflow_default=True` / `workflow_default:true`，通过既有 Plugin 贡献。根动态列表替代全部默认。Nodeset 明确列表接管内部，即使列表等于父层，也建立新范围。
3. Node Rule 迁为只读取自己的符号、继承实现和实际 helper。文件整体、跨资源或多 Node 检查移到 Workflow/Nodeset。共享源文件不会让一个 Node Rule 看到其他实现。领域示例把模型文件整体归属放在 `example.model_layout` 图规则中，局部模型定义检查保留在 Node Ruleset。
4. 需要整体检查时在外层 Ruleset 声明 `graph_scope="effective_subtree"`；嵌套组合不填写范围即可继承。完整计划不能混合 current_graph 与 effective_subtree。使用 facts.graphs 遍历负责图，用 global_graph 查询背景，遵守 boundaries；删除 handler 内的隐式递归。
5. source Rule 不再收到其他调用或当前调用参数。依赖参数的规则使用 call 范围；共享分析通过同一计划的 Records 与 requires/bindings 实现。
6. JavaScript 插件按 `vibeflow.rule.v2` 的公开类型更新。sources 对未知路径报 RULE.SOURCE.UNAVAILABLE；不再使用文件系统回退。Plugin ABI v3 与 Workflow ABI v9 保持各自原生协议。
7. 规则字符串只引用 Ruleset。直接 Rule 改写为 `{rule_id, params}` 对象；参数不作为 Node 业务 params 传入。核对具体调用的有效选择、负责范围与执行记录，不只看 Node 类型摘要。

`review-rules` 可在不执行检查时预览来源、替代、范围和依赖。实际验收仍需 validate、quality、首次加载与运行。迁移不会让空选择绕过真实解析、绑定和编译错误。

普通节点的并发分发、显式汇合、取消与实际收尾合同见[普通图并发](graph-concurrency.md)。
