# 0.15 Rule 与 Node 声明迁移

0.15.0 使用代码插件声明资源。升级时将旧登记转换为所属语言的 SDK 声明和 workflow 插件选择。公开契约为 Rule ABI v1、Plugin ABI v3、Workflow ABI v4；原生数据路由、Nodeset、Loop 和业务执行协议保持原有语义。

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

省略 `rulesets` 与显式 `[]` 都表示未选择 Node 审查。需要默认 Process 约束时明确填写 `vibeflow.process`。改变 `flow_kind` 不再获得副作用权限。领域规则通过参数约定 tags，例如 `model_tag=model_block`；核心不判断任意模型代码的功能块，也不规定模型拓扑。

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

源码解析、符号、导入关系和指标由 Target 提供；同次检查共享资料，公开上下文只读。Python 使用解析后的相对导入及允许的辅助目录，JS 包括 literal dynamic import 和 require。公开 Node/BaseLib/dependency_chain leaf 与默认 maintainability 使用相同指标资料。

Node 导入 Rule 检查自身的实际导入闭包。helper 的引用关系与实现归属分别记录，共享文件按各资源所选规则分别检查。已加载未调用的 Nodeset 使用声明及真实可得资料，调用路径为空。planned helper 的初始化由所选 planned Rule 检查。

BaseLib、Plugin、HostExtension 通过 `rulesets` 选择审查，插件包声明使用 `declaration_rulesets`。报告按实际选择记录约束与来源。插件入口先初始化，独立延迟实现按所选导入规则检查后绑定；时序见[加载与检查](plugins-and-integrations.md#加载与检查)。compiler/runtime 生命周期保留原生协议。

`review-rules` 展示当前作用域内的有效规则、参数来源和资源选择，加载受信插件固定定义，框架不调用 Rule、Node 或生命周期工厂。Python 预览可使用 Target 的解析闭包定位已引用库。

## 默认检查行为

默认规则检查 Decision 路由输出、契约重叠、examples 形状、公开 callable、decorator 和模块结构。声明模型接受 `examples.outputs`；Python 默认接口 Rule 禁止该字段，JS 默认 Rule 接受合法输出示例。Python 默认导入 Rule 拒绝模块级 `try/match`，需要放宽时替换该 Rule。

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
