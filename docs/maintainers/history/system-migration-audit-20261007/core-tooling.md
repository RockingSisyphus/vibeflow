# Core / Tooling 新旧体系迁移审计

审计对象：2026-10-07 当前工作树（包括未提交改动），旧基线 `f169429` 已由父代理展开到 `/tmp/vibeflow-migration-baseline-f169429`。只读源码 / Git 对比和几个内存探针；无源码修改，无全量测试。探针原始结果：`/tmp/vibeflow-core-tooling-probes.json`。

## 结论

Core / Tooling 已切断项目级旧资源发现 / 注册主入口，正式工作流通过选中 SDK 插件取得资源；旧硬编码检查的多数“判定算法”留在原文件内，由新 Rule 消费。不能把保留原算法等同仍有两个独立约束系统。

仍存在以下清理遗漏 / 分层不整齐 / 可组合粒度限制，具体证据如下。最明显的是旧公开 `evaluate_*` 接口被改为固定 Rule 小图后再调用原算法、默认 workflow 单个 Rule 内继续手工聚合、旧静态诊断目录、迁移时重复 Catalog 类和废弃 Policy 插件形参。

## A. 迁移残留或限制

### A1. 旧 maintainability API → 固定 Rule 小图 → 原算法的永久桥

- 旧版 `core/quality/implementation.py` 直接由 `evaluate_node_implementation`、`evaluate_base_lib_implementation`、`evaluate_base_lib_dependency_chain` 根据 `ImplementationMetrics` / `ImplementationLimits` 判定。
- 重建 `788a1ab` 将旧判定改名为 `_node_implementation_facts`、`_base_lib_implementation_facts`、`_base_lib_dependency_facts`；保留原公开名，改成新 Rule 包装。这些 `_facts` 实际产生带严重程度的诊断，并不是仅提取资料。
- 当前 `core/quality/implementation.py:176-189` 调用 `core/rules/builtin/implementation.py:46-61`，每次现建只有一个调用的 Ruleset、加载固定的 builtin descriptor / handlers，后者 `:19-31` 再回导旧私有判定算法。形成 quality → builtin Rule → quality 双向依赖。
- 当前正式 Python default maintainability 在 `targets/python/quality/rules/maintainability.py:25-42` 一次检查多次走上述桥。JS 在 `targets/javascript/build/quality_implementation.py:173-197` 同样调用旧公开 API。
- 这些内层 Rule 小图使用自身 `implementation_resources()` 和 `implementation_handlers()`，不取用户本次 Catalog；其执行结果被外层 handler转换后返回，内层计划也不进入外层 `rule_executions`。在用户的规则图中，无法单独对这批内层步骤局部覆盖，只能换外层 maintainability 或直接选择 public implementation topic。
- **额外实际问题，但范围应准确**：公开的 Core `implementation_handlers()` 都不读取 `params`，descriptor 却声明 `policy` 参数（`builtin/implementation.py:34-38`）；只读内存探针把 `policy.node_source.max_lines` 从 1 改成 1000，plan 确有两种参数，但实际均按 context 中 `limits.max_source_lines=5` 对10行源码报错。
- **不可夸大**：正式 Python `source_implementation_handlers` (`maintainability.py:57-79`) 和 JS `rule_session.py:279-327` 先读取有效 Rule 参数构建 limits / policy_data，所以未证明正常 CLI 局部参数覆盖失效。问题是公开 Core handler 契约不齐，以及桥造成固定内层组合和重复适配。

### A2. 默认 workflow 仍是一个大 Rule 内手工组织检查

- `core/rules/builtin/effects.py:35-36` 的 `vibeflow.workflow` Ruleset 只有 `workflow → vibeflow.workflow` 一个调用。
- 当前 Core `builtin/workflow.py:76-85` 内部直接调用 `_flow/_join/_nodesets/_duplicates/_planned`。
- Python `targets/python/quality/rules/workflow.py:20-43` 从 topic handler map 直接调用 flow / join / duplicates / nodesets / planned，并在同一函数继续调用旧 `validate_node_config_health`、`validate_nodesets`、`registry_namespace_findings`；`:48` 调用旧 `append_mainline_health`。这些原检查函数成为此 Rule 的内部实现，而不是规则图节点。
- JS `targets/javascript/build/rule_session.py:332` 默认 workflow handler 直接使用 Core `workflow_rule_checks`。
- 可观察范围：`review-rules` 展开的默认图仅有一个 workflow 调用。已注册 `vibeflow.graph.flow` 等 topic 并非该图的子调用，针对 topic 的图级 replacement / params 不自动穿透默认 workflow；需替换整个 workflow，或自行显式选择 / 组合 topic。Python 专属若干检查尚无独立 descriptor。
- 探针证明：向执行器提供自定义 `vibeflow.graph.flow` handler，默认 workflow 图执行时调用次数0；单独选择该 topic 的图执行时调用次数1。
- **分类**：架构分层与可组合粒度限制，不是规则选择完全失效。首版计划允许按完整主题组织一条 Rule 输出多个诊断，不能声称它已违反承诺。用户如果期望“全部系统组件都按同一可组合机制维护”，这块确实还不是那种状态。

### A3. 旧静态 RULE_CATALOG 原样存在并进入每份 Python health report

- `core/quality/workflow_rules/rule_catalog.py` 与 `f169429` 逐字节相同，Git 最后修改早于 Rule 重建（`e25dd05` / `8926a87`）。
- `targets/python/quality/workflow/report.py:23,50` 无条件塞入其18个固定诊断码，包含 GRAPH / NODE.EFFECT / NODESET 等旧分类；从不根据有效 Rule plan 或自定义插件贡献增减。
- 实际探针：`GraphConfig(nodes=(),rulesets=())` 得到 PASS，`workflow_rulesets=[]`、`rule_executions=[]`，但 `info.rule_catalog` 仍含这18项。
- `core/quality/__init__.py` 和 `workflow_rules/__init__.py` 仍导出旧目录符号，测试也固定断言一些目录键。
- **分类**：旧报告/metadata概念残留。它是“诊断码目录”，不是新可执行 `RuleCatalog`，不负责执行或覆盖；不能作为双引擎证据。命名和固定内容容易让使用者误读当前有效规则，也要求额外维护目录。

### A4. 迁移期间新增的重复 / 无内部调用模块

- `core/descriptors/rule_catalogs.py:7-14` 定义 RuleCatalog / RulesetCatalog；正式 `core/descriptors/catalogs.py:180-195` 又有同名类，且 `core/descriptors/__init__.py:37` 导出后者。全 src / tests / tools 未见前者的导入。前者由 `788a1ab` 引入后未再修改，属于迁移清理遗漏，非0.14文件残留。
- `core/descriptors/rule_models.py:3-6` 只是从真正的 `core.rules.models` 与 descriptor models 重导出，src / tests / tools未见模块导入。由 `788a1ab` 引入、`1b0aa73` 修改。不是独立模型系统，但无用途的重导出层增加入口混乱。只能判仓内无调用；外部消费者未知。
- `core/quality/evaluator.py:8-9,17-18` 仍导入旧顶层判定函数 dependency_findings / duplicate_function_findings / analyze_root_structure / analyze_directory_structure，该模块不再使用它们（新 builtin/project_quality 直接导入消费）。属于低风险残余 import。
- 不把 `tooling/project/schema_resources.py` 列为无用途：`tests/fixtures/support/strict_support.py:50` 用它，`tools/verify_project.py:436` 显式检查打包七种 schema。

### A5. Policy 插件移除后旧形参和说明仍保留

- `tooling/application/python/project/effective_policy.py:3-4` 仍说 Python plugin extensions 应用在 shared policy 后，但 `28ebb58` 已删除 `_apply_policy_plugins` 和调用。
- `resolve_effective_policy(...plugin_registry=...)` (`:30`) 形参仍在，函数完全不使用它；其 import `PluginRegistry` 仅维持旧形参类型。
- `tooling/application/python/project/policy.py:26` 的 `resolve_workspace_effective_policy(...plugin_registry=...)` 同样不使用，`28ebb58` 删除了 apply_policy_plugins。
- **分类**：废弃接口 / 说明残留，不是旧 Policy hook 仍运行。调用者继续传参会被静默忽略，容易造成迁移认知错误。

### A6. 独立项目源码扫描工具保留8条不存在的旧目录豁免值

- `tooling/application/python/project/quality_scan.py:47-58` 的 SIDE_EFFECT_BOUNDARY_PATHS 来自重建前，含旧扁平 `src/vibeflow/base_lib.py`、cli.py、config_loader.py、devtools/code_quality.py、tooling/project/quality_scan.py、mermaid_render.py、purity_source.py、runner.py。
- 探针逐个检查，当前8个全部不存在。
- 当前 `scan_code_quality(check_side_effects=True)` (`:86-89`) 仍按这些路径判断源码副作用检查豁免。
- **分类**：更早目录迁移遗留值，属于仓库 / 源码扫描维护债；不是当前工作流 Rule 选择未迁移。它说明旧名字未清理，但不会重新启用旧 Node 资源注册。

## B. 历史文件保留，但当前作用合理，不应直接删

1. **内建规则自动贡献**：`core/descriptors/contributions.py:133-139` 手动造 `vibeflow.core` ContributionBuilder，不是用户SDK Plugin；`descriptor_loader.py:90` 自动加入。和用户插件加载路径不同，但合并后共用 Catalog / Rule graph。当前设计文档 `system-architecture.md:48` 明确允许“内置资源与选中贡献合并”。事实应说“builtin尚未全部改为SDK插件”，不能说偷偷保留旧运行系统。
2. **正式旧资源主入口已拒绝**：`workspace_loader.py:238-242` 拒绝 project.registry/descriptors/base_lib/plugins；`descriptor_loader.py:94-102` 拒绝 ID-only / 旧插件字段。新插件由 source 加载固定资源，没有递归发现旧 descriptor 目录。
3. **源语言事实提取及纯算法可复用**：旧 Core `dependencies.py`、`duplicates.py`、`structure.py`、`structure_distance.py` 和 `workflow_rules/flow_data.py`、helpers.py、join_exclusivity.py 当前成为 new Rule 内部实现。旧硬编码顶层 evaluate_project_quality 的直接全量判定流程已被替换为标准 compile_ruleset / execute_rule_plan (`evaluator.py:21-64`)；rule参数覆盖、自定义handler、facts-only选择有效。
4. **decode/rule_decode保留是传输协议**：JSON descriptor 解码现在服务SDK贡献/JS worker序列化，不能据文件曾解析JSON manifest就认为旧JSONC发现主入口仍存在。`decode_resource` 没有I/O或发现目录能力。
5. **PluginSelection / plugin_review保留服务内部生命周期**：SDK插件贡献 compiler/runtime descriptor 后形成 `catalogs.lifecycle_selections`，JS audit `application/javascript/audit.py:631-633` 先替换config.plugins为这个内部分组才交给旧selection metadata适配。因此接受 string ID 的内部函数不证明外部workflow仍能ID-only选旧注册插件。
6. **quality --path / --project全目录扫描是另一授权范围**：Python quality_scan.py:94 / JS build/quality_source.py:101 默认调用 project quality Ruleset；它们都用同一Rule执行器。此命令不取workflow领域选择，是项目源码健康命令的既有范围，不应据此说有旧独立引擎。
7. **原生解析/编译/协议绑定及状态展示**：config schema、Node实例真正绑定、循环/调度等仍由Target/Core实现。这些必须存在，不能全部移成可绕过规则。

## C. 历史保留量

`core/quality` 旧基线21个Python文件当前均仍在：12个逐字节相同，9个变化。`tooling/project` 仍对应旧基线21个同路径Python文件：14个相同，7个变化（旧 descriptor_* 结构已另外迁移/删除）。数量只能说明保留源码量，不能说明21个旧模块都需删除；上面逐项区分了原生服务、通用算法、桥/元信息和真正重复文件。

Core quality逐字节相同的12文件：__init__.py、dependencies.py、duplicates.py、structure.py、structure_distance.py、workflow.py、workflow_rules/__init__.py、flow_data.py、helpers.py、join_exclusivity.py、rule_catalog.py、schema_findings.py。

Tooling project逐字节相同的14文件：__init__.py、architecture_types.py、config_loader.py、diagnostic_sink.py、document_kinds.py、graph_config.py、paths.py、plugin_review.py、project_architecture.py、quality_policy.py、resource_helpers.py、schema_common.py、schema_resources.py、workflow_discovery.py。

## D. 探针及边界

- 直接运行当前 `PYTHONPATH=src` 的纯内存 Rule 图和空工作流；没有取旧wheel，无网络，无训练。
- 没有证实外部用户依赖重复模块，删除前需再看公开API承诺与发行文档。
- 本报告不替代父代理对 Python Node/Registry / JS driver资源系统的审计；默认源检查中的旧AST visitor调用由它们负责。
- node.schema.json 当前 examples只列inputs/params且additionalProperties=false（:126-144），但新版声明/JS规则支持outputs，已反馈父代理做 schema实际反例验证；本报告不重复计数。
