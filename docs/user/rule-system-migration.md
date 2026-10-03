# 0.15 Rule 与 Node 声明迁移

本次声明格式一次迁移，不提供新旧并行加载。版本为 0.15.0，Rule ABI v1、Plugin ABI v2、Workflow ABI v4 保持不变。原生数据路由、Nodeset、Loop 和业务执行协议继续使用原有机制。

## Node 自己声明规则和展示

删除 `node_category` 文件、`descriptors.node_categories`、bundle 的 `categories` 引用和 Node 的 `category` 字段。把原分类的默认规则、颜色和形状展开到每个完整 Node。config 继续通过 `type_used` 引用它。

```jsonc
{
  "kind": "node",
  "type_key": "model.affine",
  "display_name": "Affine",
  "description": "一个仿射计算功能块",
  "version": "1.0",
  "flow_kind": "process",
  "tags": ["model_block"],
  "contract": {},
  "rulesets": ["domain.model_block"],
  "presentation": {"fill": "#cceeff", "shape": "hex"},
  "implementations": [{
    "language": "python",
    "targets": ["python"],
    "source": {"kind": "file", "ref": "nodes/affine.py", "export": "Affine"}
  }]
}
```

省略 `rulesets` 与显式 `[]` 都表示未选择 Node 审查。需要默认 Process 约束时明确填写 `vibeflow.process`。改变 `flow_kind` 不再获得副作用权限。领域规则通过参数约定 tags，例如 `model_tag=model_block`；核心不判断任意模型代码的功能块，也不规定模型拓扑。

默认展示按原生默认、Node 默认、状态展示、调用点覆盖依次应用。保留系统状态色，Node 默认展示不能占用它们。图中执行身份和诊断标记独立保留。浅蓝模型示例使用 `#cceeff`。

## Rule 声明执行语言和入口

Rule 的实现改用独立的 `RuleImplementationDescriptor(language, source)`。移除实现中的 `targets`、`completion`。这些字段仍属于 Node、Plugin 等原生业务实现的契约。

```jsonc
{
  "kind": "rule",
  "id": "domain.model_definition",
  "scope": "source",
  "params_schema": {"model_tag": {"type": "string"}},
  "params_defaults": {"model_tag": "model_block"},
  "implementations": [{
    "language": "typescript",
    "source": {"kind": "file", "ref": "rules/model_definition.ts", "export": "check"}
  }]
}
```

JS 和 TS 属于同一个执行族，不能分别登记一个 node 实现和一个 browser 实现。使用一个 `check(context, inputs, params)`，按业务平台资料自行处理，或组合不同 Rule。JS Rule 在实际 Node worker 环境加载。

`RuleResult.state` 必须为 `completed/failed/unavailable`；finding severity 必须为 `error/warning/info`。有效 error finding 不取消有效 records；损坏的结果使 provider 失败，其 consumer 不执行。JS records 必须为真实 JSON 数据，Map、Date、undefined、非有限数和循环对象会报错。生命周期中合法的 void 返回不受这项 Rule 数据契约影响。

替换实现保持局部调用身份和输入输出接口，默认参数来自替代 Rule。显式参数和覆盖关系随后生效，报告保留每个有效值的来源。加载顺序不决定覆盖优先级。

## 源码资料与范围

源码解析、符号、导入关系和指标由 Target 提供；同次检查共享资料，公开上下文只读。Python 使用解析后的相对导入及允许的辅助目录，JS 包括 literal dynamic import 和 require。公开 Node/BaseLib/dependency_chain leaf 与默认 maintainability 使用相同指标资料。

Node 导入 Rule 只检查自己的实际导入闭包。helper 的引用关系与实现归属分别记录，共享 helper 不继承最宽权限。已加载未调用的 Nodeset 可以检查声明及真实编译资料；上下文不包含虚构调用。planned helper 的初始化检查由所选 planned Rule 执行。

BaseLib、Plugin、HostExtension 都直接选择 `rulesets`。Python 注册与报告保留此选择；已引用库和已选插件进入同一引擎，插件导入入口在原生绑定前执行。独立 JS 插件同样显式选择规则，compiler/runtime 生命周期继续使用原生协议。报告不再把这类资源固定标成 `trusted`。

`review-rules` 展示当前作用域内的有效规则、参数来源和资源选择，不执行 Rule 或业务代码。Python 预览可使用 Target 的解析闭包定位已引用库。

## 默认规则的恢复与边界

默认规则恢复 Decision 路由输出、契约重叠、examples 形状 warning、公开 callable、内置 decorator 识别和模块结构限制。中立声明允许 `examples.outputs`；Python 默认接口 Rule 保留原禁止行为，JS 默认 Rule 接受合法输出示例。Python 模块级 `try/match` 默认拒绝，需要放宽时替换导入 Rule。

规则只审查代码和架构健康度。普通业务类型错误不会新增为 VibeFlow 的通用健康规则；JS 原生 Target 的现有 TypeScript 转译也不因此变成完整类型检查。解析、实现绑定、原生 ABI 和执行失败仍按实际事实报告。
