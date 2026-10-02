# 业务节点分类与领域源码检查实施方案

本文面向 VibeFlow 内核维护者，说明如何让插件声明业务节点分类、检查实际实现及其辅助代码，并为正式架构图提供统一默认样式。首个应用是浅蓝色的模型功能块 Node；接口同时适用于数据变换、损失、资源管理等业务分类。

状态为待实现方案，依据 2026 年 10 月 2 日的当前源码整理。本文中的新增类型、字段和接口是拟议契约，尚不是可直接调用的公共 API。

## 已确定的实施范围

本期实现分类声明、公开源码检查上下文、领域源码 hook、正式诊断接入和共享样式解析。包内 Node 批量注册作为后续增强纳入设计。原生 Node、Nodeset、Loop、Config、契约、连边和执行机制继续承担组合与运行职责。

根据本次需求取舍，不实现项目级领域规则启用与孤立源码专项覆盖：不增加 `quality.plugins`、项目级规则开关、登记插件自动启用或新的全项目领域扫描，也不重新划分命令范围。领域规则沿用 workflow 现有 `plugins` 选择；`quality` 通过已有 workflow 检查汇总取得这些规则的结果。

这一取舍意味着：本期能检查已启用插件的 workflow 实现及相关辅助代码，但不承诺发现其他文件中的全部未注册、未使用模型定义。一般项目源码扫描继续执行原有通用规则。插件未启用、workflow 未被本次命令检查或源码不在关联范围时，均不能把通用检查通过解释为领域规则通过。

模型定义必须归属模型功能块 Node；如何识别模型定义、允许怎样拆分实现，以及如何判断一个明确功能块，由领域插件决定。内核提供归属事实和诊断通路，不内置模型框架知识或预设模型拓扑。

## 当前逻辑与拟议修改

| 位置 | 当前逻辑及目的 | 修改后的逻辑及目的 |
|---|---|---|
| Node 类型信息 | `category/tags` 保存业务分类；`flow_kind` 保存原生语义 | 保留这些字段，增加可引用的分类声明，集中保存默认外观和说明 |
| 源码分析 | 各原生检查取得类、文本、指标、导入或 descriptor 实现事实 | 复用已有分析，向领域插件提供公开的节点、符号、辅助代码和归属上下文 |
| Python policy hook | `validate_node` 检查当前节点，`validate_graph` 等检查结构 | 增加可选源码 hook，一次检查当前 workflow 的关联实现集合 |
| 正式检查入口 | Python workflow 诊断可进入 health；JS 插件 hook 主要进入构建流程 | 源码规则进入各 Target 的正式检查链路，保留完整领域诊断 |
| 架构展示 | 按系统状态选择默认颜色，允许调用点自定义 `style` | 增加分类默认样式，两套 presenter 消费同一份解析事实 |
| 包内 Node 接入 | 项目逐个登记包导出的 Node 类型和注册参数 | 增加显式批量登记便利接口，仍合并到原生 Registry/Catalog |

现有 schema 扩展 hook 不能直接替代此次改动。Python 的 `extend_node_metadata_schema`、`extend_contract_schema` 和 `extend_purity_rules` 当前只调用方法并检查返回 Mapping 的形状，并未将返回值应用为新的 schema 或规则。新增能力应有明确执行语义，不扩大这些含糊接口的用途。

相关实现入口为 [NodeInfo](../../src/vibeflow/targets/python/project/node.py)、[NodeDescriptor](../../src/vibeflow/core/descriptors/models.py)、[Python workflow 检查](../../src/vibeflow/targets/python/quality/workflow/validation.py)、[Python 源码扫描](../../src/vibeflow/tooling/application/python/project/quality_scan.py) 和 [JavaScript 插件 hook](../../src/vibeflow/targets/javascript/build/plugin_hooks.py)。

## 业务分类声明

增加语言无关的 `NodeCategoryDescriptor`，通过现有资源目录的扩展保存和查询。分类 ID 使用领域命名空间，例如 `ml.model_block`。建议字段如下。

| 字段 | 含义 |
|---|---|
| `id` | 分类稳定 ID，对应 Node 类型的 `category` |
| `display_name` | 面向读者的业务名称 |
| `description` | 分类含义和使用说明 |
| `default_style` | 可选 `fill/stroke/text` 默认值 |
| `icon` | 可选普通文本或稳定图标 ID |
| `metadata` | 可选可移植 JSON 元数据 |

拟议声明示例：

```json
{
  "id": "ml.model_block",
  "display_name": "模型功能块",
  "description": "表达一个明确的模型功能",
  "default_style": {
    "fill": "#dbeafe",
    "stroke": "#1d4ed8",
    "text": "#172554"
  },
  "metadata": {}
}
```

NodeInfo 和 NodeDescriptor 继续使用原有 `category`，`tags` 供辅助检索和规则匹配。默认颜色由主分类提供，不根据多个 tags 的加载顺序竞争。旧分类没有附加声明时继续使用原有默认样式，不强制旧项目补登记。

分类声明是注册阶段的纯数据资源。项目通过现有显式 Registry/descriptor 接入路径引入插件包提供的声明；资源可用不等于检查 hook 已启用。分类与 Node 的引用关系在形成有效展示事实时解析，不由 runtime hook 临时改写。

分类属于 Node 类型，Config 调用点继续只描述本次用途并覆盖允许的展示属性，不恢复调用点 `category`。分类、图标和额外元数据均不改变契约、effect scope、权限或执行语义，也不新增 `flow_kind`。

## 公开源码检查上下文

增加公开的 `SourceCheckContext`，供领域规则读取当前检查对象的相关实现。它不开放可修改图、调度器或全局 Registry。Tooling 负责范围及文件读取，语言 Target 负责解析和实现定位，插件负责业务判断，Core 承载语言无关的数据及 Finding。

| 内容 | 最小信息与用途 |
|---|---|
| 检查对象 | workflow ID、project Target、当前 root、实际覆盖的文件和实现 |
| Node 类型 | type key、category、tags、descriptor 及实际实现标识 |
| 调用位置 | 当前图中使用该类型的调用 ID 和限定路径 |
| 实现定位 | 语言、文件、qualname/export、符号起止行及类型归属 |
| 源码集合 | 关联文件文本、来源和读取或解析结果 |
| 引用关系 | 可解析的导入、符号引用及 Node 使用 helper 的关系 |
| 归属事实 | 登记实现、明确声明归属、共享引用或无明确归属，并保留依据 |

注册位置与实现位置分别保存。`NodeRegistry.registration_info()` 描述在哪登记，不能代替实现源码位置。Python 可复用真实类的 module/qualname 和源码定位；JS/TS 可复用 descriptor、文件和 export 定位。

实现身份按 Node 类型、实际来源和 qualname/export 建立。调用实例单独关联；同一类型出现多次时，源码检查去重，诊断可关联到多个调用位置。同一文件中的不同符号分别保存归属，不因为文件里存在一个模型 Node 就把整份文件判为允许模型定义。

收集当前 workflow 的实现时，递归进入实际调用的 Nodeset 和 Loop body。这里只补齐当前对象内部的实现覆盖，不追加未使用 Nodeset、其他 workflow 或全项目孤立文件。Python 现有部分节点 hook 仅遍历顶层图，新源码 hook 的上下文必须覆盖这些内部调用。

helper 引用与源码归属分别记录。模型 Node 导入共享 helper 仅说明依赖，不自动使其中任意模型定义合法。插件可要求专属实现声明、限制共享模型定义或允许特定拆分方式；无法解析的关系保留为未知并由插件给出有依据的诊断，不猜测唯一 owner。

源码文本、位置、实现身份和归属是首期公共契约。可复用的 AST、符号查询和导入分析作为 Target 分析访问接口提供；不把 Python AST 或 JS/TS Program 放进 Core，也不开放能污染其他规则的共享可变 AST。解析结果只在本次命令内按实际需要复用，不增加持久分析状态或检查资格。

稳定入口通过各 Target 的公共聚合 API 导出。插件不需要导入 `_source_info`、私有 visitor 或 Tooling loader。后续语言通过实现相同基础事实和自己的分析访问接口接入；已有 Python 领域规则不会因此自动获得其他语言的识别能力。

## 领域 hook 与正式诊断

沿用 policy 插件类型，增加可选源码检查 hook，不新增第四类 Plugin。拟议 Python 接口为：

```python
def check_sources(self, context: SourceCheckContext) -> Sequence[Finding]:
    ...
```

Python 入口将返回的公共 Finding 适配到既有 HealthFinding；已有返回 HealthFinding 的 hook 继续保持行为。JS 使用等价 `checkSources` 与可移植上下文数据。没有新 hook 的旧插件直接跳过，不额外执行其 runtime hook。

源码 hook 必须只读并可重复执行。现有 review 的 preflight 与正式验证可能分别触发检查，本方案不承诺每条 CLI 命令只调用一次；去重针对同一检查上下文的实现与诊断，不通过新增持久状态跳过后续检查。

每次正式 workflow 检查的顺序为：解析现有插件选择及类型事实，收集当前对象的关联实现，执行原生检查，执行已选择的领域源码 hook，汇总诊断。基础解析失败而无法形成上下文时报告真实失败；可取得的有效事实继续按现有检查方式处理。原生契约、连边、执行和纯度规则仍由原入口承担，领域插件不重复实现它们，也不能移除 Core 不可降级错误。

源码上下文和新 hook 由本方案列出的检查入口显式组织。Python run 也复用当前 workflow health 验证函数，因此不能在该函数中无条件启动新源码 hook，导致 run 自动增加领域源码预检。validate、review 及 quality 的对应检查调用可以复用同一领域检查组件；run 保持已有行为，不新增公开开关或运行准入条件。

启用和命令调度沿用现状：

| 入口 | 新 hook 如何进入 | 保留的边界 |
|---|---|---|
| Python validate | 由检查编排提供上下文，调用已选择 policy 插件的共享源码检查组件 | 只检查当前对象的关联实现，不因 run 复用 health 而自动检查 |
| Python review | 消费同一份 workflow 检查结果 | 验证失败仍按原逻辑停止正式发布 |
| Python quality | 已有逐 workflow validate 自然包含新 hook，最终状态照常汇总 | 一般源码扫描器不直接执行领域插件；单文件或子目录模式不保证发现 workflow |
| JS validate 和 review | 在共享 audit 检查阶段接入已选择源码 hook | 不为了检查选择 browser/node 运行语义 |
| JS quality | 通过已有 workflow audit 接入，保留既有原生资源审计 | 不把全量原生审计文件直接当成领域上下文 |
| JS build | 复用相关检查组件及诊断适配，不重复执行同一源码 hook | compiler/runtime hook 保持各自阶段 |

JavaScript 的新增检查宿主需要明确区分源码分析阶段与 browser/node 执行阶段。源码上下文表达项目语言及分析事实；已存在的工厂上下文和运行 hook 保持兼容。新增源码检查接口按现有 ABI 策略声明分析阶段，不能假定 node 目标或借检查开放宿主操作，也不将 Node 运行结果用作源码检查输入。

诊断复用现有 Finding 字段：规则 ID、严重度、对象、`source_location`、原因、修复建议和 root/source 信息。插件来源由宿主记录，领域规则 ID 使用自身命名空间，不增加独立报告、历史通过凭据或预检文件。示例结果为：

```text
ML.MODEL_DEFINITION_LOCATION
project/nodes/ordinary.py:42
模型定义 Encoder 不归属模型功能块 Node。
```

领域违规、插件执行异常和非法返回值分别处理。领域错误进入正式 error 集合；插件异常及返回形状错误使用既有插件错误语义。JS 不再在错误转换过程中丢失原始规则 ID、文件或行号；汇总与异常承载完整 diagnostics，再由现有命令决定退出状态。

源码 Finding 与图节点的关联需要显式投影：通过实现身份找到当前图中的调用 ID 和限定路径，保留原始文件诊断，并提供调用定位信息。仅有文件行号不会自动触发现有 Mermaid 节点高亮。可用诊断视图消费该投影；正式 review 仍遵守检查失败不发布图的现有语义，不新增错误时也必须发布 SVG 的流程。

相关事实见 [Python 插件结果适配](../../src/vibeflow/targets/python/quality/workflow/plugins.py)、[Finding](../../src/vibeflow/core/findings.py)、[Python quality 汇总](../../src/vibeflow/tooling/application/python/cli/quality.py)、[JS audit](../../src/vibeflow/tooling/application/javascript/audit.py)、[JS 插件 ABI](../../src/vibeflow/targets/javascript/resources/plugin_abi.d.ts) 和 [JS 注册实现定位](../../src/vibeflow/targets/javascript/build/quality_implementation.py)。

## 分类默认样式与正式架构图

在共享 Tooling 展示层增加一个分类样式解析入口，输入分类声明、现有系统状态和调用点 style，输出统一展示事实。Python 与 JavaScript presenter 消费同一结果，不分别实现一套分类优先级。

正常实现的业务节点使用分类默认样式；planned、错误、警告等状态以及原生边界标记沿用已有语义。显式调用点 style 保留现有覆盖行为，包括现有已承诺的状态色覆盖，不在此次改动中反转优先级。没有分类默认值的字段使用原有默认值。

模型功能块使用前述 `#dbeafe` 浅蓝。当前系统保留了 `#e0f2fe`、`#eff6ff` 等颜色，分类声明采用符合现有样式契约的配色，不借此取消系统色约束。图标首先支持文字或稳定 ID 的呈现，不提供任意 CSS、SVG 或 renderer 回调。

分类声明及已解析的展示事实进入 Architecture 的确定性数据，Mermaid 和 SVG 从这些事实生成。分类样式变更能够反映到重生成的正式架构文档；插件不直接改 SVG。分类只影响附加展示，Node 的原生形状、Nodeset 容器和执行结构继续表达既有语义。

实现入口为 [共享样式模块](../../src/vibeflow/tooling/presentation/style.py)、[Core 样式词汇](../../src/vibeflow/core/style.py)、[Python Mermaid](../../src/vibeflow/tooling/application/python/presentation/mermaid/__init__.py) 和 [JS review 展示](../../src/vibeflow/tooling/application/javascript/review.py)。

## 插件包批量提供 Node

后续增加显式的资源批量引入接口。包可以导出分类声明、Node 类型、配置 schema/defaults 和检查插件登记信息；项目在原有 Registry/descriptor 装配阶段引入这些资源，图解析及绑定随后消费它们。

批量引入复用现有 Registry/Catalog 的类型检查、ID 冲突和来源记录，不另造包管理器或全局服务容器。包导出 Node 不等于该 Node 已被某个 workflow 调用，导出 policy 插件也不等于其 hook 已启用。Python 与 JS/TS 的实现绑定仍分别留在各自 Target。

该增强不依赖 runtime 插件临时注册 Node，也不要求 workflow 先运行才能得到类型目录。第一阶段仍可使用现有显式登记方式完成核心需求。

## 预计修改位置

| 层及文件 | 拟议修改 |
|---|---|
| `core/descriptors` 及公共导出 | 分类纯数据模型与目录扩展，保留 NodeDescriptor 分类来源 |
| `targets/python/project` | 分类声明适配、公开实现绑定信息，后续增加批量登记便利接口 |
| `targets/python/quality` | 公开基础源码上下文与分析访问接口，复用已有源码事实，增加 policy 源码 hook 适配 |
| `tooling/application/python/project` 及检查编排 | 组织当前 workflow 的递归实现和 helper 事实，保持现有工作区依赖上下文，按检查入口调度新 hook |
| `targets/javascript` | 提供可移植源码上下文、分析阶段插件调用和完整诊断承载 |
| `tooling/application/javascript/audit.py` 及 build 编排 | 接入共享领域检查，保持各阶段职责并避免重复 hook |
| `tooling/presentation` 及两个 Target presenter | 共享分类样式解析、源码诊断调用定位、Architecture 展示事实 |
| 文档与现有 sandbox | 完成公共接口说明，增加模型与另一个业务分类的使用示例 |

`quality_scan.py` 的一般源码扫描逻辑、项目 `quality` 字段启用结构、原生调度器和工作流组合机制不因本方案而增加新行为。具体新增文件应跟随上述现有分层，不建立平行检查系统。

## 实施顺序

1. 增加分类数据及显式登记路径，接入共享样式解析和 Architecture，先验证两个 Target 的默认色与覆盖兼容。
2. 整理已有源码事实，公开上下文和实现身份，覆盖当前 workflow 的 Nodeset/Loop 内部实现，明确 helper 归属与引用差别。
3. 增加 Python policy 源码 hook，复用正式 Finding 和已有 validate/review/quality 汇总，由检查入口调度，避免 run 自动增加源码预检。
4. 增加 JS/TS 分析阶段源码 hook，接通 audit 与 build 的共享检查和诊断适配，保留 Target 中立的审核行为。
5. 增加最小领域插件示例及验收案例，用模型与数据变换两个分类验证接口通用性。
6. 增加包内 Node 批量登记便利接口，再按实际插件需求扩展 AST 查询、图标及其他语言分析接口。

前四步形成必需能力，第五步验证通用性，第六步交付接入便利与可选增强。每步使用对应的普通测试和真实 sandbox 验证，按仓库要求完成最终检查，不追加项目运行资格、历史报告或全项目预检。

## 验收标准

| 场景 | 预期结果 |
|---|---|
| 合规模型 Node 中定义模型 | 已启用模型插件时通过领域规则；默认浅蓝色 |
| 当前 workflow 的普通 Node 或关联 helper 中定义模型 | 插件按自身规则报告实际文件、行号和原因 |
| 同一文件中模型 Node 与普通 Node 并存 | 按符号归属检查，不整文件放行 |
| Node 专属实现、共享 helper 或未知引用 | 上下文分别呈现事实，插件不因导入自动放行模型定义 |
| Nodeset 或 Loop 内部使用模型 Node | 新源码 hook 不漏检内部实现 |
| 同一实现被多次调用 | 同一上下文内源码诊断去重，调用定位包含相关实例 |
| 模型节点处于串行、分支或其他合法原生组合 | 原生组合仍可用，不强制模型 Nodeset 或固定拓扑 |
| 模型插件与数据变换插件同时使用 | 共用分类、上下文和 Finding 接口，不添加领域专用内核分支 |
| 未启用领域插件或不存在对应 hook | 不执行该领域检查，旧插件保持既有行为 |
| 孤立或未使用的模型文件 | 不要求本期领域规则发现，不新增项目级启用入口 |
| quality 检查发现的 workflow | 领域结果自然进入原有 workflow 报告及最终状态 |
| quality 仅检查单文件或不发现 workflow 的子目录 | 保留现有行为，不宣称领域规则已执行 |
| JS 原生审计包含额外注册源码 | 领域上下文不因此自动扩展到整个项目 |
| 领域错误、插件异常及非法结果 | 类型区分清楚，正式输出保留规则、来源、文件和位置 |
| 正式 review 检查失败 | 诊断进入正式结果，发布行为保持现状 |
| run 复用原有 workflow health 验证 | 保持既有检查，不自动执行新源码 hook 或读取领域检查历史结果 |
| 正常节点、planned 状态及调用点样式覆盖 | 两个 Target 的默认值与覆盖语义一致 |
| 分类声明或默认样式变化 | Architecture 与正式图可从真实事实确定性重生成 |
| 未使用新声明的旧项目 | 不要求补分类登记，原有展示与检查行为保持兼容 |

验证源码规则使用能够体现领域意图的正反例，不以规则自身实现的复刻测试替代验收。图形能力需要检查实际 Mermaid/SVG 输出，正式结果需要检查 CLI 文本和 JSON。结构及领域检查通过不代替模型计算或其他业务结果的真实运行验收。

## 维护约束

每类事实保留一个来源：业务身份来自类型 category，实现来自 Registry/descriptor 绑定，检查范围来自当前对象，诊断使用 Finding，默认外观使用共享分类样式解析。公共行为在 Python 与 JS/TS 的正式入口、文档和适用测试中同步维护。

本方案不改变现有 [系统架构](system-architecture.md)、[执行模型](execution-model.md) 和 [检查阻断边界](../maintainers/quality-boundaries.md)。实现后把已完成的公共接口写入使用者手册；本文仍作为方案记录，不将未实现接口装配为发行包的使用规范。
