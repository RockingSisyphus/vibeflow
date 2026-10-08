# JavaScript Target 新旧机制残留审计

审计对象：2026-10-07 当前工作树（含未提交改动），基线 `f169429`，迁移提交 `28ebb58`、`3ee7396`。只读源码与历史检查；低成本 Python 探针结果位于 `/tmp/vibeflow-js-migration-probe.json`。没有改业务源码，没有全量测试，没有实际执行用户业务 Node。

## 总体结论

JavaScript 正式 `audit` / `build` 主链已经使用 workflow 选中 SDK 插件的贡献目录、资源声明的 Ruleset 和统一 Rule 引擎。旧 `policy` Plugin 类型及 hooks 已被拒绝，而非继续参与执行。旧 TypeScript 判定算法仍然大量复用，但现在由所选 Rule 调度；这部分是算法实现复用，不能单凭旧文件名称或历史出处判为双规则系统。

仍存在可确认的旧公共入口、重复模型、失去主链调用者的直接判定工具，以及一个正式入口仍能到达的已弃用 Host 启用方式。这些足以造成源码认知与低层 API 行为不一致，但不等于 JavaScript CLI 全面同时执行两套审查理念。

## 现存残留与行为漂移

### JS-1：仍提供完整的旧 AOT WorkflowSpec 模型/解析/校验入口

类别：兼容模型/旧公共入口并存；正式 CLI 不走此入口。

- `targets/javascript/build/builder.py:80-105` 以 `javascript_bindings is not None` 分 canonical 与旧 `normalize_workflow_plan` 分支。旧分支仍单独使用 `implementation_by_type`、旧 `host_extensions` 参数和 import_policy。
- `targets/javascript/frontend/emitter.py:63-79` 同样保留两条输入链：未传 binding 时构造 WorkflowSpec；传 binding 时要求 canonical `WorkflowPlan`，经 `bound_workflow_view`。
- `frontend/model.py:35-42` → `model_types.py:319-322` → `frontend_parser.py:51` → `frontend_validation.py:20` 构成完整旧解析/模型/校验链，不是一个薄的适配函数。
- 旧 parser 仍读旧语义：`frontend_parser.py:405-418` 从 legacy async_mode 推导 schedule；`:448` 从 `flow_kind=terminal` 推导 is_terminal；`:212` 从 flow_kind/global_state 字段识别旧输入形态。探针传只有 flow_kind=terminal、async_mode=result_key 的旧结构，仍成功产生 terminal、deferred 节点。
- 新 canonical 主链在 `tooling/application/javascript/build.py:549-564` 总是将 prepared.plan 和 prepared.javascript_bindings 一起传给 build_aot，因而不会经过旧 parser。公共 `targets/javascript/__init__.py:21-45,90,94` 仍导出 WorkflowSpec/normalize_workflow_plan；大量 test_aot_core / emitter_golden / conformance 测试继续使用旧入口。
- `frontend_validation.py:116-151` 旧模型的 I/O 专门校验与 canonical 编译/绑定约束也并存。因此当前维护者仍要维护两种工作流结构，结构性错误可能在两套位置演进。

历史：这些模型/解析器已存在于 `f169429`；旧 AOT parser 的 I/O 约束最早可追到 `19a26c86`（2026-07-30），目录在 `8926a87`（2026-08-02）移动。不是本次 Rule 重建新增的必要算法。

不应误报：`emission_view.py:383-386` 的 `legacy_emission_payload` 目前只是 `workflow.to_dict()` 的哈希投影，canonical 输入并未因此重新创建 WorkflowSpec。名字含 legacy 不证明在核心链上重新启用了旧 parser。

### JS-2：旧公开 Plugin descriptor parser 与当前统一 decoder 已漂移

类别：旧公共解析器残留；已实证同一合法新声明出现不同结果。

- `frontend/plugin_descriptors.py:105-202` 保留自写 parse_javascript_plugin_descriptor，不委托给 `core.descriptors.decode.decode_resource`。
- 其字段白名单 `:115-133` 不含当前合法 `presentation` 和 `base_libs`；其 implementation 白名单 `:437-440` 不含当前合法 `implementation_files`。
- 统一 decoder `core/descriptors/decode.py:524-571` 支持这些字段；SDK 加载 `targets/javascript/sdk/loading.py:120` 使用统一 decoder。
- 探针：相同 runtime Plugin descriptor 分别包含 base_libs、presentation.shape、implementation_files，统一 decoder 三例均接受，旧公开 parser 三例均报 `VF_AOT_PLUGIN_CONFIG`。
- 旧 parser 目前没有正式 src 调用者，但仍经 `targets/javascript/__init__.py:15,95` 和 `frontend/__init__.py` 公开导出，并被 `test_plugin_foundation.py` 维护。

影响：使用公开 Target parser 的调用者会误以为新版多文件/共享库/展示声明非法；内部 SDK 主链则能使用，出现两种公开行为。仍需维护重复字段白名单和重复实现解析。

历史：基线已包含此 parser；迁移提交只更新了 Rule/Plugin ABI 内容，没有统一解析器。当前 SDK 解码方式在 `3ee7396` 后变成主入口，旧 parser 仍保留。

### JS-3：旧独立 JavaScript quality facts/直接 validator 原样保留，且语义已落后

类别：旧公开审查入口残留；CLI 主链无调用，但可直接调用。

- `quality/models.py`（36 行）与 `quality/validation.py`（201 行）相对 `f169429` 无改动。
- `quality/validation.py:14-22` 不经 Rule 编译或资源 Ruleset，固定运行 `_completion_findings`、`_ownership_findings`、`_import_findings`。
- `quality/__init__.py:3-16` 继续导出该旧 facts 与 validate_javascript_quality / quality_findings_from_toolchain。src 无正式调用者；`tests/core/test_layered_quality.py:120` 直接调用。
- 漂移一：旧 `_illegal_import_message:158-159` 无条件拒绝 Host→任何非 Host source。当前 driver `resources/toolchain_driver.mjs:616-617` 明确允许 Host→声明在 base_libs 中的库。探针旧 validator 对 declared=True BaseLib 报 `QUALITY.JAVASCRIPT.IMPORT.BOUNDARY`。
- 漂移二：旧 `_completion_findings:84-90` 对所有 kind 的 suspend 同步实现报错。当前 Plugin 协议工厂必须同步，completion=suspend 表示其 hooks 可异步；driver `:1051-1052` 明确将 plugin 排除在该 factory 返回 Promise 要求外，`plugin_worker.mjs:217-218` 强制同步工厂。探针旧 validator 对合法类别的同步 suspend Plugin facts 报 `QUALITY.JAVASCRIPT.COMPLETION.SUSPEND_NON_PROMISE`。
- 旧 `_ownership_findings:107-122` 还直接以 kind 判 listener owner 和 dynamic import，既无 Ruleset 选择也无当前实际 TypeScript symbol/source ownership 事实。

影响：保留一套无实际源码提取者的简化 facts/判定 API，并用旧断言维护它。它目前不会悄悄参与正式 audit/build，但会让维护者和低层调用者看到与新系统不同的规则。

### JS-4：nodeset_limits.py 旧直接门禁仅被测试保活

类别：失去生产调用者的旧直接判定工具。

- `build/nodeset_limits.py:13-28` 对默认 depth=4 直接抛 ProjectBuildError；`:31-36` 独立产生 width warnings。
- 文件相对 `f169429` 原样 36 行。src 无 import 或调用；`tests/targets/javascript/test_nodeset_limits.py` 仍直接测它。
- 当前 audit 的 `tooling/application/javascript/audit.py:197` 明确 width_warnings=()；实际 nodeset 判定由 run_javascript_workflow_rules / `vibeflow.graph.nodesets` 或 `vibeflow.workflow` 规则完成，项目数值配置经 Rule defaults 注入（audit.py:190、build.py:240-241）。

影响：旧不可组合直接门禁已经退出主链，文件与测试还在，让删除旧逻辑时不得不先处理与正式入口无关的测试；不能以该 helper 测试通过证明当前正式 Rule 覆盖。

### JS-5：旧 project-level javascript.host_extensions 仍可在正式入口启用 Host

类别：有明确弃用告警的活跃兼容桥；应决定终止时间，不是隐藏旧 policy engine。

- `build/project_paths.py:29-37,53-57` 仍读取项目 javascript.host_extensions。
- `tooling/application/javascript/host_selection.py:8-10` 在 workflow 没有 host_extensions 时，将项目级 legacy_ids 补成 workflow 的 Host 选择。
- build 主链 `tooling/application/javascript/build.py:230` 与 audit 主链 `audit.py:702` 都传入这些 legacy_ids。
- build.py:368-370 记录 uses_legacy_host_extensions，`:451-458` 报 `VF_AOT_HOST_EXTENSION_LEGACY_SELECTION`，明确要求迁到 workflow-level host_extensions。audit 的同一 fallback 没有对应弃用 warning。
- 新 API 的 workflow.host_extensions=[] 会覆盖旧 fallback，不会启用。旧项目仍须通过新版 workflow plugin 贡献目录才能找到 Host，不会重新恢复旧 registry/bundle 发现。

历史：基线 build.py 已含同一 legacy fallback 与 deprecated warning；不是本次迁移必需的新接口。重建设计 `docs/design/rule-system-refactor-plan.md:13` 声明不保留长期兼容桥，故这里至少仍有尚未退休的明确旧接口。

## 较弱的旧分支残留：不要误称主链漏审或新回退

`toolchain_driver.mjs:1844-1913` 的 auditUnclassifiedHiddenWork 仅在 owner.kind=source 时生效（:1846）；当前正式 target_neutral_import_policy (`build/project_resources.py:505-557`) 仅创建 node/base_lib/host_extension/plugin/plugin_declaration owner，传递归属也复制这些 kind。ruleSession import Rule 仍请求 ownership topic（rule_session.py:277-278），driver :2315 仍调用它，但正式生成的任何对象都不能进入该 source 分支。`VF_SOURCE_LISTENER_UNOWNED` / source Promise 判定是已有不可达分支，低层自定义 driver importPolicy 可手工造 source owner，不能称完全死函数。基线的同一 source 分支也正式不可达，见 `docs/design/baseline-rule-inventory-javascript.md` 后半的 source-owner 三例，因此不是重建产生的退化。

同理 `toolchain_driver.mjs:589,598` 中 runtime/registry/capability 的 destination-kind 字面分支没有相应正式 owner 生成器。这是旧泛化白名单分支，不代表当前有旧 Registry/capability 模块加载机制。

## 旧代码仍被当前主链复用，但有明确的新职责

| 当前代码 | 旧职责与当前接入 | 判定 |
|---|---|---|
| resources/toolchain_driver.mjs AST 检查函数 | 基线 auditContracts 无条件调用（基线:2212 起）；当前:2294-2315 按 request.ruleTopics 分 purity/imports/completion/module_state/host_io/ownership 主题 | 活跃算法复用，当前受 Ruleset 选择控制 |
| build/rule_session.py:247-278 | builtin Rule→主题→source driver；副作用主题来自 params.effect_scope，空 Ruleset 没有 source topics | 已迁到新规则调度；没有另一个 flow_kind 副作用授权 |
| build/quality_implementation.py | TS 提取长度/复杂度/调用图，evaluate_registered_facts 调用 Core 纯判定 | 在所选 maintainability / implementation Rule 下执行 |
| build/quality_source.py:101 | source scan 调 Core evaluate_project_quality | 当前 evaluator.py:21-64 本身也编译/执行 Rule 图，非旧引擎旁路 |
| frontend / schema / build_contracts / runtime_helpers | 真实 JSON Schema、TypeScript ABI、产物能力、同步/异步工厂与输出契约 | 原生计划/目标/调用 ABI；设计明确保留，不能因为文件老就移到可选 review Rule |
| plugin_hooks.py | compiler beforeCompile/afterCompile 生命周期及注解 | 原生生命周期明确保留；:164-165 拒绝 findings/relaxations，policy hook没复活 |
| plugin_worker.mjs:214-220 | 只支持 compiler/runtime，拒绝 policy 及 removed hooks | 旧名字仅作为错误提示，已无旧审查实现 |
| frontend/plugin_descriptors.py 其余 resolve/binding 函数 | 当前 Catalog/SDK 贡献 → 原生目标源码绑定 | 正式使用；只应删除/替换旧自写 parser 子链，不能整文件删 |

附带架构边界：builtin_javascript_handlers (`rule_session.py:260-333`) 仍将内置 Rule ID/handler 映射到 Python Target handler，而自定义 JS Rule 使用 worker (`:371-403`)。说明内置 Rule 没有全部改成与自定义相同的 SDK 源码插件；但是普通插件不能重复声明 builtin ID、Rule.handler 与 implementations 互斥、replace_rule 可改为自定义新 ID，这张 handler 表没有证明用户规则实现被静默忽略。属于保留的 backend binding 设计，需要与 core/Python 合并分析。

另一个边界：scan_javascript_quality 未开放 Core evaluator 已支持的 rulesets/rules/catalog/handlers 参数，整个项目 source scan 固定选择内置 project-quality 主题；workflow/Node 主题范围仅为其实现闭包（docs/user/rules-and-nodes.md:104）。数值 CLI thresholds 确实进入 Rule defaults，workflow局部 overrides 也正常参与编译。不能拿 workflow.rulesets=[] 不取消项目级扫描作为旧引擎证据；若要求项目级扫描也可自定义组合，则目前是扩展层未贯通的问题。

## 覆盖边界

已从 Application audit/build/quality CLI 入口追到 SDK contribution加载、Rule execution、TS source driver、compiler/runtime plugin worker、native AOT emitter、运行 helper；对比基线相关文件和实际 Git 变更，全文检索旧 hooks/policy/type-kind/registry/catalog/legacy；检索 src/tests/sandbox 的引用，并做公开 parser 与 validator 六项小探针。

无 src 引用不代表第三方不调用公开 API。报告按“正式链调用 / 公开旧API / 仅测试 / 正式不可达分支”分开，不以死代码判断替代兼容性决策。未进行全量运行，因此不宣称涵盖任意 TypeScript 语法、所有运行期能力或业务正确性。未使用记忆。
