# Rule、Node 与组件系统迁移残留审计

审计日期：2026-10-07。审计对象是当前工作区，包含未提交修改；Git HEAD 为 `9c443f3`。旧基线为 `f169429`，并检查了实际 `archive/vibeflow-distribution-0.14.2.zip`；新版发行对照为 `archive/vibeflow-distribution-0.15.2.zip`。

本轮只增加审计说明、源文件清单、复现程序和观察结果，没有修改产品代码或删除文件。没有运行全量回归，不将局部探针通过解释为系统整体验收。

记录状态：本轮全部发现统一收录在本文的 **R01–R19** 中，包括已确认的问题、旧公开接口与兼容残余、无仓内用途的文件和函数、测试迁移负担，以及需要保留的设计边界和排除项。各项附有位置、调用关系或复现依据；分层报告和 JSON 文件作为证据附件。当前尚未整改，后续可按编号逐项跟踪。

本文保留2026-10-07修复前的现场。修复后的逐项状态及新增剩余问题见[2026-10-08独立复核](system-migration-recheck-20261008.md)，不要将下文历史观察当作修复后的现状。

## 结论

存在用户担心的部分情况，且有正式 CLI 的行为证据。但它的形态是：**主入口已迁移，内部仍有旧角色假设；外围保留旧公开接口、第二种模型和废弃实现；某些新 Rule 是旧综合检查的包装。** 未发现两个完整的旧、新项目注册与审查系统同时作为正式主入口运行。

最优先的问题不是文件名旧，而是同一个组件已经按新 SDK 声明了身份和依赖，旧代码仍按目录名或另一份元数据判定它。Python 的两个正式对照证明了这一点：已声明的纯库或支撑文件，只改变目录名称，就从 PASS 变为 FAIL。

另有明确的公共接口漂移：旧 Python BaseLib 适配器丢失规则选择；旧 JavaScript Plugin parser 拒绝合法新字段；旧 JavaScript 独立 validator 与新协议冲突；发布的 Node Schema 仍保留旧 examples 限制。这些路径有些已退出 CLI，但仍公开或随发布包交付。

默认规则的粗粒度组合、内置 handler 表、原生执行协议和通用算法复用需分开看。当前设计明确保留原生执行机制，并允许一条主题 Rule 输出多个诊断；不能据此声称所有旧文件都该删除。

## 审计范围与依据

- 源代码完整物理清单共 **348 个文件**：329 个 Python 文件、9 个 MJS 文件、3 个 TypeScript 声明文件、7 个 JSON Schema。Python 模块静态图有328个名字，因为 `quality/rules.py` 与 `quality/rules/__init__.py` 占用同一模块名。
- 从两种语言的正式命令入口追到 SDK、插件贡献、Catalog、实现绑定、源码归属、Rule 执行、编译、生命周期、运行和展示；检索旧 hooks、发现/注册、身份权限、兼容分支和模块/函数引用。
- 旧0.14.2发行内核的266个源文件与 `f169429` 源码逐文件完全一致；0.15.2发行内核的348个源文件与当前 `src/vibeflow` 逐文件完全一致。因此以下残留并非只存在于未发布的开发目录。
- 旧文件中127个原样保留、130个改变、9个删除；当前另有91个新文件。这些是历史保留量，**不是缺陷数量或可删文件数量**。
- 运行了正式 Python CLI 的14个目录/导入位置/支撑文件对照，以及公开解析器、Rule handler、适配器与报告的小探针。Schema 检查比较声明实际序列化结果与 Schema 字段约束，没有安装或运行第三方 JSON Schema validator。
- 另核对清理工具列出的更早旧目录（如旧 `src/vibeflow/purity/plugins/runtime/descriptors`）：当前全部不存在，没有发现这些旧路径以源码或空目录形式残留。[目录清单](../evidence/index.md#artifact-0c922bff7a81d989)为空；现存问题集中在保留/迁移后的模块内部。
- 静态无引用不能证明任意第三方不调用公开 API；动态导入、lazy exports、handler 表与 AST visitor 的自动分派已专门核对。报告将公开兼容层与真正无仓内用途的私有代码分开。

证据目录：[system-migration-audit-20261007](../evidence/index.md)。完整层级审计：[Python](system-migration-audit-20261007/python.md)、[JavaScript](system-migration-audit-20261007/javascript.md)、[Core / Tooling](system-migration-audit-20261007/core-tooling.md)。[逐文件清单](../evidence/index.md#artifact-568f56bb6747cf33)保留新旧状态及静态导入边；它不是自动删除清单。

[可重复执行的CLI探针](../evidence/index.md#artifact-76b8244a46588057)已实际运行，14项观察与本文对照一致；[完整观察摘要](../evidence/index.md#artifact-67fd4da1d0924f47)保存在仓库。它创建新的 `/tmp` 项目、使用当前正式CLI，不修改源项目，不使用测试转换桥。复现中的项目不声明Architecture文档要求，以直接观察目标源码规则；所有对照使用相同的项目配置。

## 重建前后实际机制

### 重建前：多种登记方式与内置检查编排

Python 项目由 registry 登记类、库和插件。Node 的 `NODE_INFO`、`CONTRACT` 等类元数据参与声明，检查器先从实现类取得这些信息；`flow_kind` 派生 effect scope，trusted 等身份还会改变检查行为。源码 purity、BaseLib 扫描、workflow health 与 policy hooks 在各自的编排中运行。

JavaScript 已有 JSONC descriptor / Catalog 与 AOT，不是所有组件都写死在框架内。但检查主题主要由 Target 固定编排，插件 policy hooks 与源码检查相互适配；低层还支持单独的 `WorkflowSpec` 模型。

因此旧版也可以自定义 Node 和插件。此次重建的核心变化是声明权威、规则选择与资源贡献方式的统一，而不是第一次允许用户写自己的类。

### 重建后：选中插件贡献声明，由 Ruleset 决定审查

```text
workflow.plugins 显式 source
  → Target 加载固定 SDK Plugin
  → PluginContributions + 内置贡献
  → 本次 Catalog / 唯一 Descriptor / 真实实现身份
  → 对象的 import / static / run Ruleset
  → 统一 Rule 图、参数、资料、诊断
  → 原生编译、绑定、执行与展示
```

已完成的关键切换有直接源码证据：

- `tooling/project/workspace_loader.py:238–242` 拒绝旧项目 `registry/descriptors/base_lib/plugins` 登记字段。
- `tooling/project/descriptor_loader.py:88–102` 从内置贡献与显式选中的 SDK source 组装资源，并拒绝 ID-only 的外部旧插件选择。
- `targets/python/project/registry.py:54–63` 要求 `NodeDescriptor`，不再靠旧类元数据登记。
- Python 和 JS 的源码/工作流检查由 Rule/Ruleset 调度；没有发现 `flow_kind` 或 external 自动豁免所选效果规则的旧权限机制继续运行。
- policy 插件检查 hooks 已删除/拒绝；compiler/runtime 生命周期继续保留。
- JSON 解码器仍用于 SDK/worker 数据运输，保留它不等于仍有 JSONC 目录发现入口。

## 一、已确认有行为冲突或公开契约漂移

### R01：Node 新依赖声明与旧模块名称/allowlist 判断并存

路径：`validate_graph_health → execute_python_node_rules → no_side_effects → NodePurityVisitor._check_import`。

当前位置：`targets/python/quality/source_analysis/visitors.py:373–386`、`quality/rules/source_ownership.py:9–50`、`quality/rules/effects.py:160–176`。

新归属判断按 Descriptor、`base_libs` 和真实导入位置判断；旧 visitor 仍把模块名中的 `boundary`、`nodes`、`base_lib` 当成组件角色，并要求 `base_lib.*` 同时满足旧 `allowed_base_lib_modules`。正确声明的库导出已能豁免部分 nodes 误判，但没有统一替代其余名称判断。

正式 CLI 对照基于 `sandbox/python/multifile_resources`：同一纯函数库、同一 `demo.math` 资源、同一 Node 的 `base_libs=["demo.math"]`，导入位于 `run_pure` 内，只移动库所在目录：

| 库目录 | validate结果 | 目标诊断 |
| --- | --- | --- |
| `ordinary` | PASS | 无 |
| `base_lib` | FAIL | `NODE.BASE_LIB.BASE_LIB_UNDECLARED` |
| `boundary` | FAIL | `NODE.PURITY.BOUNDARY_IMPORT` |
| `nodes` | PASS | 无 |
| `runtime` | PASS | 无 |

把相同导入移动到 Node 模块顶层，五种目录全部 PASS。新 handler 的顶层导入路径主要检查 known Node modules，方法内又进入旧名称判断，造成位置差异。

旧基线 `visitors.py:437–442` 已有 base_lib 名称/allowlist 分支。旧 policy 装配仍从 workflow 的 `base_lib.modules` 生成 allowlist（`application/python/project/resources.py:103–122`、`workspace_service.py:373–404`），而非直接把 Node 的资源依赖作为唯一判断依据。补一份旧式配置能掩盖问题，但不能解释为系统已统一。

证据：[正式 CLI 结果](../evidence/index.md#artifact-4f0fe6058608009e)、[声明归属与效果 handler 对照](../evidence/index.md#artifact-f2bbad4430b556d3)。这是当前主链内真实的两种判断依据冲突。

### R02：已登记 BaseLib 支撑文件仍被旧禁用目录词拒绝

当前位置：`targets/python/quality/rules/base_lib_effects.py:209–219`。

`_BaseLibAstScanner` 只要在导入模块分段中看到 `boundary/boundaries/nodes/plugin/plugins/runtime` 就报错，不看那个文件实际属于哪个已声明资源。

正式对照中，纯加法函数已经登记为同一 BaseLib 的 `implementation_files`，声明和代码一致，只改变支撑文件所在子目录：

| 支撑目录 | validate结果 | 诊断 |
| --- | --- | --- |
| `parts` | PASS | 无 |
| `runtime` | FAIL | `BASE_LIB.FORBIDDEN_PROJECT_IMPORT` |
| `nodes` | FAIL | 上述诊断及 `NODE.METADATA.NODE_IMPORT` |
| `plugins` | FAIL | `BASE_LIB.FORBIDDEN_PROJECT_IMPORT` |

这些目录中的文件并不是 Runtime/Node/Plugin 资源。当前 source ownership 对明确同库支撑关系判定合法，旧 scanner 仍按词汇拒绝。其历史源头是旧 `project/base_lib.py:44–46,376–386`。

证据：[正式 CLI 结果](../evidence/index.md#artifact-155592d478dec103)、[同库归属 handler 对照](../evidence/index.md#artifact-2546a825ee47b57a)。

### R03：Node 内还有按 `base_lib` 模块名触发的额外库扫描

当前位置：`targets/python/quality/rules/effects.py:135–147`。

新效果 Rule 仍把模块名包含 `base_lib` 的 helpers 单独送入 `_BaseLibAstScanner`，整模块再扫描并可报 `NODE.BASE_LIB.INDIRECT_VIOLATION`。正常已声明库另由 `project/resource_rules.py:94–158` 按实际 BaseLibDescriptor 和所选 Ruleset 审查。

因此“是否额外按库扫描”仍部分由名字决定，和按真实资源声明的到达库审查并存。Node 的有效效果约束需要检查真实 helper，这一职责可以保留；应替换的是名字识别和整模块特殊路径。这里确认了双路径结构，没有声称所有项目都会重复报错。

`project/source_closure.py:97,133,259–260` 还保留按路径填 `PythonSourceFact.is_base_lib` 的旧标记；未找到当前读取者，属于伴随的闲置资料字段。

### R04：旧 Python BaseLib 适配器公开保留，转换会丢失新规则

当前位置：`targets/python/project/descriptors.py:67–102,123–151`，公开导出在 `project/__init__.py:50–59`。

`base_lib_descriptor_from_registry` / `adapt_base_lib_registry` 仍把旧 native Registry 模型转换、合并为 Catalog，复制元数据和实现却漏掉 `rulesets`。

探针：native resource 的 `rulesets=("custom.review",)`，转换后 descriptor 为 `rulesets=()`。这是规则选择被静默剥离的实际接口缺陷。正常 workflow SDK 装配不调用这条适配器；目前由测试和公开 API 保留，不能夸大为所有 CLI 都丢规则。

证据：[Python API 探针](../evidence/index.md#artifact-5aa53a1b0dc9d8fb)。

### R05：旧 JavaScript Plugin parser 与新统一 decoder 漂移

当前位置：`targets/javascript/frontend/plugin_descriptors.py:105–202,437–440`。

公开 `parse_javascript_plugin_descriptor` 自写字段白名单，漏掉新版合法的 `base_libs`、`presentation`、implementation 的 `implementation_files`。SDK 正式加载使用 `core.descriptors.decode.decode_resource`，接受这些字段。

三项公开接口对照中，新 decoder 全部接受，旧 parser 全部报 `VF_AOT_PLUGIN_CONFIG`。该 parser 仍从 Target/frontend 聚合 API 导出，测试直接维护，主 CLI 已不使用它。

因此该文件不能整删：同文件内的 Catalog → 原生 lifecycle binding 函数仍由新链使用。应单独退役或统一旧解析子链。

证据：[JS API 探针](../evidence/index.md#artifact-2bef26d44865275b)。

### R06：旧 JS 独立 quality validator 公开保留，规则已落后

当前位置：`targets/javascript/quality/models.py`、`quality/validation.py:14–22,84–90,158–159`，两个文件相对旧基线原样保留。

它固定运行 completion/ownership/import 判定，不接收资源 Ruleset。正式 CLI 不调用，但 `quality/__init__.py` 仍公开导出，`tests/core/test_layered_quality.py` 直接测试。

已实证两种漂移：

- Host 导入已声明 BaseLib：旧 validator 无条件拒绝；当前 driver `toolchain_driver.mjs:616–617` 接受声明在 `base_libs` 的库。
- Plugin 声明 suspend、工厂同步返回：旧 validator 报 SUSPEND_NON_PROMISE；新协议要求工厂同步，允许 hooks 异步，当前 driver/worker 明确区分两者。

这是第二套旧判定 API 继续对外存在，不是旧引擎偷偷进入每次 build。

### R07：发布的 Node Schema 仍保留旧 examples 限制

当前位置：`tooling/project/schema/node.schema.json:124–136`。

`examples` 只允许 inputs/params，`additionalProperties=false`；新版 Descriptor 可以序列化 `outputs`，JS 默认接口 Rule 也接受合法输出示例。用户迁移文档明确区分“声明接受”与“Python 默认接口 Rule 禁止”。

观察中实际 NodeDescriptor 接受、输出含 outputs；打包 Schema 却明确禁止这个键。这里只核对了真实声明和 Schema 数据约束，未运行第三方 Schema validator。Schema 随0.15.2分发，验证工具也检查其存在，不能当作未发布的历史文件。

证据：[Schema 对照](../evidence/index.md#artifact-bd5802666b2d10a7)。

### R08：Core 公开 implementation Rule handler 不兑现自己的参数

当前位置：`core/rules/builtin/implementation.py:19–38`。

descriptor 声明 `policy` 参数，Core handler 实际只读取 context 的 `limits`。探针对10行源码将 `policy.node_source.max_lines` 从1改为1000，plan记录两种参数，结果均按 context limit=5 报错。

正式 Python 与 JS handler 会先把有效参数转换成 limits/policy_data，故没有证明它们的 CLI 参数覆盖失效。漂移发生在仍公开保留的 Core 内置 Rule 接口，反映内层包装未完全统一。

证据：[Core 探针](../evidence/index.md#artifact-bba7e10051dff9f1)。

## 二、旧接口、包装和第二种模型仍然存在

### R09：旧检查 API → 固定 Rule 小图 → 旧判定算法的桥仍在主链

当前位置：`core/quality/implementation.py:176–189`、`core/rules/builtin/implementation.py:19–61`。

原公开 evaluate_* API 改成创建固定内置小 Rule 图；handler 又回导同文件的 `_node_implementation_facts/_base_lib_implementation_facts/_base_lib_dependency_facts`。这些 `_facts` 其实已产生诊断，不只是提取事实。形成 `quality → builtin Rule → quality` 双向依赖。

正式 Python maintainability 和 JS implementation 判定仍走这个桥。内层资源是固定 builtin 集合，不来自用户本次 Catalog，执行不作为独立步骤显示在外层 `rule_executions`。它不否定外层 Rule 可替换，但增加适配层、隐含组合和删除旧模块的耦合。

类似的 `evaluate_workflow_topic` 为旧 graph 检查 API 创建小图，再回到私有纯判定函数。算法保留合理；同一模块同时承担旧公共入口和新规则内部实现，边界仍可收敛。

### R10：默认 workflow 与 Python effects 仍使用综合检查包装

默认 `vibeflow.workflow` Ruleset 只含一个 workflow调用（`builtin/effects.py:35–36`）；Core `builtin/workflow.py:76–85`、Python `quality/rules/workflow.py:20–48` 在 handler 内手工组织 flow/join/duplicates/nodesets/planned，以及 Python 专属旧 helper。

因此注册的 topic Rules 不都是默认图子调用。探针替换 graph.flow 的 handler，执行默认 workflow 时调用次数0，显式选择 topic 时次数1。要单独放宽它，需要自己组图或替换完整 workflow，而非覆盖默认图里不存在的子调用。

Python `no_side_effects` 也继续使用旧 NodePurityVisitor，混入返回契约、内部 while、yield、类资源字段等约束（`visitors.py:224–246,309–355`）。这是主题耦合，而不是未选规则仍执行。空 Node rulesets 没有触发这些检查。

**性质：可组合粒度和维护结构限制。** 首版计划明确允许按完整主题组织一条 Rule 产生多个诊断。不能把粗粒度直接当成违反原设计的 bug；但它尚未达到“所有内部检查都作为可独立组合的插件规则维护”的状态。

### R11：内置规则仍使用特殊贡献与 Target handler 表

`builtin_contributions()` 经 Core 的 ContributionBuilder 自动加入 Catalog；Python/JS 内置 handler 由框架映射绑定，自定义语言 Rule 则加载用户实现/worker。它们最终使用同一规则图，但并非全部通过和用户相同的 SDK 源码插件实现。

当前设计明确允许“内置资源与选中贡献合并”，内置 ID 冲突也会报告；用 replacement 指向新的自定义 Rule 仍可工作。没有证据证明这些表静默吞掉合法的自定义实现。

**性质：有意保留的 backend/内置实现边界。** 如果未来目标是框架只提供系统、默认组件也全部外置为普通插件，这里仍有工作；本轮不把该目标静默替用户加入重建验收。

### R12：完整旧 JS AOT 工作流模型仍与 canonical 模型并存

当前位置：`build/builder.py:80–105`、`frontend/emitter.py:63–79`、`frontend/model.py`、`model_types.py`、`frontend_parser.py`、`frontend_validation.py`。

不传 `javascript_bindings` 的低层 build/emitter 仍支持旧 WorkflowSpec；传 bindings 才走 canonical WorkflowPlan。旧 parser 仍接受 async_mode 推导 schedule、flow_kind 推导 terminal 等旧结构。

正式 Application build 始终传新 bindings，不走旧 parser；但公开 Target API 和大量 AOT/emitter/conformance 测试仍走旧链。这不是薄重导出，而是第二套模型、解析与校验逻辑，需同时维护。它主要早于此次 Rule 重建，继续保留不代表重建新增回退。

`legacy_emission_payload` 当前只是已有 emission view 的序列化投影，不能仅因名字而视为重新解析旧 WorkflowSpec。

### R13：旧 BaseLib 自动扫描、模型与 metadata API 仍公开

Python `project/base_lib.py:49–101,182–239` 的 analyze/scan API 仍按 `base_lib` 目录或旧允许路径自动发现文件，并固定选择内置 `vibeflow.base_lib`；不能接收本次插件 Catalog 和各资源 Ruleset。正式 SDK 到达库审查已改用声明/source context，这条旧分析路径仍公开并由多组旧测试维护。

`NodeInfo/NodeContract` 与新 Descriptor 共存；新一些检查参数仍标注旧类型，测试还先造旧类型再转成新声明。`normalize_plugin_info/normalize_base_lib_info` 仍读 PLUGIN_INFO / BASE_LIB_INFO 形状，已无正常调用点但继续导出。

旧 `Context` 只由公开 API 和旧测试使用，运行期采用其他上下文；`RegistryBase` 仍公开，NodeRegistry 已不继承。它们不是当前声明权威，却扩大了维护面。

### R14：新版贡献仍要转换为旧 native resource/config 模型

`application/python/project/contributions.py:14–49` 将新 Catalog 的 BaseLib/Plugin 再转成 BaseLibRegistry / PluginResourceRegistry / ConfigResources；生命周期再进入现有 PluginRegistry executor。

语言绑定与 lifecycle 复用合理，但旧 config 选择、policy allowlist、resource metadata 等仍沿这层流动。这使 `project/resources.py`、Tooling resource适配器不能直接整删。R01 的问题正是旧策略语义继续由该层承载，而不是仅仅类名里还有 Registry。

### R15：已弃用 project-level Host 选择仍能进入正式 JS build/audit

`application/javascript/host_selection.py:8–10` 在 workflow 没有 `host_extensions` 时补入项目 `javascript.host_extensions`。build 与 audit 都传 legacy_ids；build发弃用提示，audit没有对应提示。

显式 workflow `host_extensions=[]` 会覆盖旧 fallback，Host 仍须来自新版插件 Catalog；这里没有恢复旧 registry/bundle。它是尚未退休的正式兼容桥，早于此次重建。

### R16：旧规则目录、形参、说明与路径值残留

- Python health报告 `quality/workflow/report.py:50` 始终塞入重建前的18项 `info.rule_catalog`。空 Ruleset、无 execution 的 PASS 工作流仍显示这18项。它是诊断码目录，不是本次有效可执行 RuleCatalog，名字容易误导且内容要另行维护。
- 两个 policy resolver 继续接受但不使用 `plugin_registry`；`project/effective_policy.py` 说明仍声称应用 plugin policy extensions，而相关 hooks 已删除。
- `application/python/project/quality_scan.py:47–58` 保留8条当前全不存在的旧扁平目录副作用豁免路径；它们早于此次重建，属于源码扫描的历史值残留。
- 现行 finding 中还频繁使用 `move_to_boundary` 和旧 Context/boundary 词汇。新系统仍有 I/O/Host/lifecycle 等边界概念，因此不能仅凭“boundary”一词判错；若说明指向已移除的 boundary插件/旧资源字段，则需更新成实际新声明路线。

## 三、可以明确定位的闲置文件、函数与测试负担

### R17：整文件与重复入口清单

| 文件 | 现状 | 归类 |
| --- | --- | --- |
| `targets/python/quality/rules.py` | 被同名新包遮蔽；正常导入走包，直载还因已删常量报 ImportError | 确认的影子旧文件 |
| `targets/python/quality/imports.py` | 无当前仓内调用，另有 source/evaluator 活跃实现 | 确认的闲置重复文件 |
| `core/descriptors/rule_catalogs.py` | 重复定义 RuleCatalog/RulesetCatalog；正式 catalogs.py有另一份，前者无仓内调用 | 重建中产生的清理遗漏 |
| `core/descriptors/rule_models.py` | 闲置重导出，正式模型在core.rules.models | 非第二套模型，但多余入口 |
| `targets/javascript/build/nodeset_limits.py` | 旧默认depth直接门禁已退出src调用，旧测试仍测 | 测试保活旧helper |
| `targets/python/quality/workflow/base_lib.py` | 正式主链不用旧报告/依赖转换，仍lazy导出 | 公开旧helper |
| `targets/python/quality/base_lib.py` | 转发旧BaseLib扫描API，无正式内部调用 | 兼容文件 |
| `targets/python/project/descriptors.py` | 旧adapter公开/测试保留，R04存在真实丢字段 | 不能整体称死文件 |
| `targets/python/project/context.py` | 非当前运行上下文，旧公开API/测试保留 | 旧模型 |
| `targets/python/project/registry_base.py` | 当前NodeRegistry不继承，无内部使用，仍公开 | 旧容器API |
| `targets/python/runtime/config.py` | 重导出Core scope并翻译异常；仅兼容测试调用 | 兼容适配 |
| `tooling/application/python/cli/reports.py` | 给 canonical reports 的sys.modules别名，无正式内部调用 | 更早兼容facade |

上述公开层不能仅靠仓内无调用就认定第三方完全不用。真正已破损/被遮蔽的 rules.py 和未使用重复实现，可先作为清理候选；其余需按支持的公开入口做一次明确收口。

### R18：活跃文件内部的旧死函数与闲置字段

下列私有函数已对当前 src/tests/sandbox/tools/distribution 查找调用和符号引用；公开-only 与更早债务另注明。不要据此整删仍有活跃实现的模块。

| 模块 | 函数/字段 | 说明 |
| --- | --- | --- |
| Python `source_analysis/helpers.py` | `_validate_key_tuple`(14)、`_validate_semantics`(23)、`_validate_schema_mapping`(37)、`_is_inputs_subscript`(82)、`_dedupe_violations`(183) | 前两者只被旧validators导入，没有调用 |
| Python `source_analysis/validators.py` | `_validate_source_size`(23)、`_validate_complexity_metrics`(31)、`_validate_call_chain_metrics`(35)、`_core_metrics`(42)、`_numeric_violations`(60)、`_validate_contract_examples_shape`(133) | 两个内部函数仅服务死入口；architecture_smells仍活跃 |
| Python `source_analysis/source.py` | `_parse_source`(25) | 旧编排移除后未清理；同文件inspect helper仍使用 |
| Python `runtime/engine.py` | `_execute_graph_block`(359)、`_assert_block_eligible`(400) | 当前graph_block callable调度不用；重建前就已闲置 |
| Python `application/project/resources.py` | `implemented_base_lib_modules`(42) | 无当前读取，旧policy辅助属性 |
| Python `application/cli/config.py` | `_configured_nodeset_depth`(69)及未用 `validate_nodeset_depth` import | depth判断已转到Ruleset |
| Python `presentation/mermaid/__init__.py` | `_render_custom_node_style`(470) | 当前共享presentation解析已替代调用 |
| JS `application/review.py` | `_custom_node_style`(595) | 同上 |
| JS `application/audit.py` | `_cloud_path`(496) | 无调用，旧图形helper |
| JS `application/cli.py` | `_validate_review_documents`(1117) | 自称旧programmatic compatibility但无仓内调用 |
| Core `workflow_rules/duplicates.py` | `_duplicate_fingerprints`(74) | 活跃逻辑使用_fingerprint_groups，旧生成器无调用 |
| Tooling `schema_common.py` | `_string_items`(120) | 无调用，更早残余 |
| Python `source_closure.py` / SourceFact | `is_base_lib`及按目录赋值 | 当前未读取，旧角色标签 |
| Python `project/resources.py` | `normalize_plugin_info`(272)、`normalize_base_lib_info`(298) | 公开-only旧metadata normalizer，无正常调用；其字段解析helpers随之保留 |
| Python `project/base_lib.py` | `node_base_lib_imports`(208)、`summarize_base_lib_dependency_chain`(129) | 公开-only；base_lib_imports_from_source还服务前者 |

另有 graph/Nodeset/planned 的旧公开工具仍由tests或导出维持：`workflow/planned.append_planned_findings`、`workflow/nodesets.validate_nodeset_depth/nodeset_depth_error_report`、Core/Python flow适配链。新主链通过所选Rule中的topic/helper执行；这些旧工具不是第二个正式主入口。完整调用情况见各层报告。

JS source-driver 的 `owner.kind="source"` 分支、runtime/registry/capability destination-kind 分支在正常新装配中没有对应资料生产者；基线也不可达。低层手工driver输入可造这些kind，所以它们属于正式不可达的泛化旧分支，而非证明所有函数绝对死掉。

### R19：回归资产仍以旧形状构造，转换层长期保留

`tests/fixtures/resource_migration/` 有446个文件：314个JSONC、58个Python、73个TS、1份README。`tests/fixtures/support/code_plugins.py` 继续解析旧descriptor/bundle/registry形状并生成SDK插件，39个测试/沙箱文件引用这个转换层，部分在测试文件末尾包装正式 loader 的局部名字。

它们只在临时回归夹具中转换，产品代码不导入这层；旧历史冻结数据不应当作运行系统残余删除。保留历史行为对照有价值。

维护负担来自两部分：测试读起来仍像旧接入、需要额外转换语义；旧独立API测试又会保活已退出正式链的实现。需要区分“冻结旧输入作证据”和“继续维护旧产品API”。不能用转换后的测试全绿证明旧实现文件均已删除，也不能把446份归档全当死产品源码。

## 不应误判为迁移失败的保留内容

1. 原生 Node/Nodeset/Loop、执行计划、契约绑定、语言调用ABI、真实同步/异步返回和运行状态仍是系统职责；设计明确保留。
2. `flow_kind` 用于终端调度、全局状态锁等执行身份合理；问题是自动授予审查权限，而这条旧机制已退出。
3. AST、复杂度、依赖图、图路由算法可留在旧文件；如果判断由有效Ruleset选择且事实来源统一，就是合理复用。
4. JSON decoder/schema等服务新版声明运输与公开结构；应修正漂移，不能因曾支持manifest就全删。
5. 内置默认贡献与用户贡献合并是当前明确设计；“有内置规则”不等于仍有内置强制检查旁路。
6. 项目source quality与workflow领域检查范围不同。当前project evaluator本身也走Rule引擎；workflow.rulesets=[]不取消整目录scan，不能作为两套引擎证据。向project扫描贯通自定义Catalog/Rulesets属于额外扩展目标，原需求没有承诺。
7. 独立仓库 `quality/` 维持标准库、与被检查内核隔离是刻意边界，不应要求它变成依赖内核的业务插件系统。
8. 历史发布包、冻结对照与审计报告是参考资产；本轮没有发现产品通过它们恢复旧发现/注册系统。

## 建议的收敛顺序

第一批处理R01–R08的真实结果/接口漂移：组件角色与依赖只消费同一份Descriptor/source ownership；统一公開解析与参数接口；同步声明Schema。用本文正式合法/非法对照验收，不能靠改目录名、补旧allowlist或提高阈值掩盖。

第二批明确保留哪些公开低层API，再收口旧WorkflowSpec/registry adapter/自动scan/quality validator。薄适配只能翻译到唯一实现，不能继续独立维护字段白名单或判定表。直接无用途、破损、重复的私有代码可以先移除对应残余测试/import。

第三批拆掉quality↔builtin循环桥、重复表示和报告静态目录。默认主题是否细拆、内置组件是否全部外置成SDK插件属于用户可观察的能力取舍，需要单独明确目标；本轮没有替用户做决定或改动机制。

**本次给出的是完整范围审查中的残留清单与行为证据，不是已经修复或已通过系统验收的结论。** 导出API的第三方使用情况、所有语言语法组合和业务运行正确性不由本轮静态审计证明。
