# Core 基线规则盘点与对照沙箱

基线是 `f169429`，重构实现是 `15adf51`。本清单按真实调用位置区分原生事实失败、审查判定和仅用于说明的诊断目录。沙箱入口为 `sandbox/rule_parity/core/cases.py::run_cases`；根 runner 为 `sandbox/rule_parity/run_all.py`，通过两个独立 Python 进程分别加载 baseline/current 的 `src`。

本轮只增加案例与证据，没有修复生产实现。`classification=preserved` 表示验收要求应保留，不能解释为当前已经通过；实际结果必须看 observation。确认的批准变化标记为 `approved_change`，新入口标记为 `new_feature`。

## 入口与责任边界

| 类别 | f169429 实际入口 | 当前实际入口 | 是否可由审查选择关闭 |
| --- | --- | --- | --- |
| 原生图编译 | `core.compiler.compile_core` / `GraphCompiler.compile` | 同一入口；契约解析、Target 能力、role、async、执行锁和普通图环校验主体保留 | 否；`rulesets=[]` 不取消真实语法、契约事实或编译要求 |
| Workflow 健康 | Target 调用 `append_flowchart_health`、`append_data_contract_warnings`、`append_join_policy_health`、`nodeset_quality_findings`、`duplicate_logic_findings`、`planned_health_events` | 当前函数仍公开，但经统一 Rule 引擎；默认 `vibeflow.workflow` handler 调用原算法，各主题也公开为 `vibeflow.graph.*` | 是；必须选择 Rule，不能关闭后由旧旁路再拒绝 |
| Node/BaseLib 数值度量 | `evaluate_node_implementation`、`evaluate_base_lib_implementation`、`evaluate_base_lib_dependency_chain` | 公共兼容入口通过 `vibeflow.implementation.*`；Target 的选中 `vibeflow.maintainability` 提供实际 metrics/limits/chain | 是；只在所选审查读取了这些事实时判定 |
| 项目源码质量 | `evaluate_project_quality(ProjectQualityFacts, QualityPolicy)` 顺序运行全部共通算法 | 同 API，省略选集则运行 `vibeflow.quality.project`；files/dependencies/structure/duplicates 通过 Rule 调度，typed records 汇聚 | 显式空选集只保留事实；默认集合保持四主题 |
| 有限 portable block 编译 | `block_compiler.compile_graph_plan` / `compile_workflow` | 同一有限展开要求；实际递归引用不能编译成有限 block | 否；这不是深度审美阈值或审查插件权限 |

当前资源/阶段：

| 默认资源 | import | static | run |
| --- | --- | --- | --- |
| `vibeflow.workflow` | 空 | workflow | workflow |
| `vibeflow.quality.project` | 空 | dependencies、duplicates、files、structure | 空 |
| `vibeflow.process` 等 Node 集合 | import_side_effects | no_side_effects、node_interface、maintainability | 同 static |
| `vibeflow.base_lib` | import_side_effects | no_side_effects、maintainability | 同 static |

`GraphConfig.rulesets` 默认 `("vibeflow.workflow",)`；Root 与 Nodeset 的显式 `[]` 是有意不选择审查。Ruleset 未声明阶段时，只在 `static` 默认选中所有本地 calls，import/run 不会自动继承 static。项目源码 evaluator 默认 `entrypoint="static"`。Python checked-run 显式选 run；JS build/audit 显式选 static，生成产物的 `runWorkflow` 不注入 Rule worker。源码与 Workflow import 入口必须在真实 binding/build 的后续阶段之前完成。

定位：`core/flow.py:251`、`core/config/graph.py:64,124,344`、`core/rules/builtin/effects.py:27-36`、`core/rules/builtin/project_quality.py:160-173`、`core/rules/graph.py:98-101`、`core/quality/evaluator.py:21-64`。

## 项目源码：活跃判定

以下算法在 baseline 为实际 evaluator 调用，在 current 为实际 builtin handler 调用。`core/quality/dependencies.py`、`duplicates.py`、`structure.py`、`root_structure.py`、`structure_distance.py` 的算法没有因本次重构替换。

| 主题 | 活跃诊断（省略共同前缀） | 默认/边界 | 对照案例 ID 前缀 |
| --- | --- | --- | --- |
| 文件，`QUALITY.FILE.*` | `WARN_LINES`、`MAX_LINES`、`MAX_BYTES`、`TOO_MANY_FUNCTIONS`、`TOO_MANY_CLASSES`、`TOO_WIDE_PUBLIC_API`、`TOO_MANY_BRANCHES` | 行数 450–500 warning，>500 error；bytes >60000 error；functions >40/classes >20/public API >30/branches >150 warning | `core.project.file.*` |
| 函数，`QUALITY.FUNCTION.*` | `MAX_LINES`、`TOO_MANY_BRANCHES`、`TOO_DEEP_NESTING`、`TOO_MANY_PARAMS` | lines >80、branches >12、nesting >4、params >6 均 warning；位置取实际 FunctionQuality.line_start | `core.project.function.*` |
| 依赖，`QUALITY.DEPENDENCY.*` | `CHAIN_WARN`、`CHAIN_TOO_DEEP`、`CYCLE`、`BIDIRECTIONAL` | 长度 >=6 warning，>10 error；环/双向依赖 error；导入位置来自 ImportSite | `core.project.dependencies.*` |
| 重复函数 | `QUALITY.DUPLICATE.AST_FINGERPRINT` | 长度 >=3 的函数按 Target 提供的 AST fingerprint 聚组，重复 warning | `core.project.duplicate_function.*` |
| 目录，`QUALITY.STRUCTURE.*` | `DIRECTORY_FANIN`、`DIRECTORY_FANOUT` | >25 warning | `core.project.directory.*` |
| 前缀/边界，`QUALITY.STRUCTURE.*` | `PREFIX_CLUSTER_SHOULD_BE_PACKAGE`、`INTERNAL_MODULE_IMPORTED_EXTERNALLY`、`PUBLIC_ENTRY_BYPASSED` | 同前缀 >12 warning；外部直引 internal warning；public candidate 存在时，internal 直引 >3 warning | `core.project.prefix_cluster.*`、`public_entry_bypass.*` |
| 目录距离，`QUALITY.STRUCTURE.*` | `DISTANT_INTERNAL_IMPORT`、`CLUSTER_SCATTERED_DEPENDENCY` | 距离 >3 的 internal 导入 warning；远距离依赖目录 >6 warning；保留 Target conventions 的免检 stem | `core.project.internal_distance.*`、`scattered_dependencies.*` |
| Root 规模，`QUALITY.STRUCTURE.*` | `ROOT_TOO_MANY_CODE_FILES`、`ROOT_TOO_MANY_CODE_DIRS` | 需启用 QualityStructureLimits；默认 files >=96 warning/>120 error，dirs >=18/>24 | `core.project.structure.root_*` |
| 目录规模，`QUALITY.STRUCTURE.*` | `DIRECTORY_TOO_MANY_CODE_FILES`、`DIRECTORY_TOO_DEEP`、`DIRECTORY_TOO_MANY_CHILD_CODE_DIRS` | 默认 files >=12/>16，depth >=3/>4，child dirs >=6/>8；warning 包含最大值，error 严格超过最大值 | `core.project.structure.directory_*`、`child_dirs.*` |
| Root 层文件 | `QUALITY.STRUCTURE.ROOT_LEVEL_CODE_FILE` | 默认非允许名单文件 >=1 warning/>2 error；`__init__.py`、`registry.py` 默认允许 | `core.project.structure.root_level.*` |
| 角色导入，`QUALITY.STRUCTURE.*` | `BASE_LIB_UPWARD_IMPORT`、`NODE_UNDECLARED_PROJECT_IMPORT`、`PLUGIN_NODE_IMPORT` | 启用结构/角色约束时 error；合法 Node→BaseLib 正向对照；支持显式角色和路径推断 | `core.project.roles.*` |

项目质量表中的数值均可通过 QualityPolicy 的对应字段配置。重构后这些数值装配为 Rule 的 `params_defaults`，call params/图中 overrides 更优先；handler 不从第二个 policy fact 偷读阈值。Root 结构并非无条件开启：`structure_limits=None` 或 `enabled=False` 时不判断该组规则，这在 baseline/current 一致。第一组结构规模案例使用显式较小阈值和 quiet 其它阈值，追加变体也逐项使用真实默认阈值，覆盖 normal/warn/max/error 四个边界；输入是公开 FileQuality 事实，不声称创建或扫描了对应规模的目录。

baseline 定位：`quality/evaluator.py:21-92,95-183`、`quality/dependencies.py:11-119`、`quality/duplicates.py:6-42`、`quality/structure.py:174-331`、`quality/structure_distance.py:26-54`、`quality/root_structure.py:17-39,77-234`。current 入口：`rules/builtin/project_quality.py:25-43,88-151`。现有验收依据：`tests/core/test_quality_shared_rules.py` 的文件/函数阈值案例与 `tests/core/test_layered_quality.py` 的共通结构事实案例。

## Node/BaseLib 度量：活跃判定

| 主题 | 实际诊断 | 默认/边界 | 对照案例 |
| --- | --- | --- | --- |
| Node 大小 | `NODE.PURITY.SOURCE_NEAR_LIMIT`、`SOURCE_TOO_LARGE`、`SOURCE_BYTES_NEAR_LIMIT`、`SOURCE_BYTES_TOO_LARGE` | lines >=450 warning、>500 error；bytes >=54000 warning、>60000 error | `core.implementation.node.*` |
| Node 复杂度 | `NODE.MAINTAINABILITY.COMPLEXITY_MAX_FUNCTIONS/MAX_BRANCHES/MAX_NESTING_DEPTH/MAX_PARAMS/MAX_CONTRACT_KEYS` | 各默认 None，不预设限制；显式限值时 actual >limit error | `core.implementation.optional.*` |
| Node helper | `NODE.MAINTAINABILITY.CALL_CHAIN_TOO_DEEP`、`RECURSIVE_CALL_CHAIN` | length=4 warning、>4 error；self/mutual recursion error | `core.implementation.chain.*`、`recursion.*` |
| BaseLib 大小 | `BASE_LIB.SOURCE.MAX_LINES/MAX_BYTES` | >500 lines、>60000 bytes error；等于最大值合法 | `core.implementation.library.source_*` |
| BaseLib 复杂度 | `BASE_LIB.COMPLEXITY.MAX_FUNCTIONS/MAX_BRANCHES/MAX_NESTING_DEPTH` | 默认 None；显式限值后 >limit error | `core.implementation.library.max_*` |
| BaseLib 依赖链 | `NODE.MAINTAINABILITY.DEPENDENCY_CHAIN_TOO_DEEP` | length=4 合法、5–6 warning、>6 error；保留具体最长路径/递归链证据 | `core.implementation.dependency_chain.*` |

baseline 的 `quality/implementation.py:93-168` 判断主体在 current 保留，旧公开函数现在于 `:171-184` 调用 Rule 兼容层。新 handler 位于 `rules/builtin/implementation.py:17-54`。这些案例直接输入公开 ImplementationMetrics/CallChain，不声称验证 Python AST 或 TypeScript parser 的提取正确性；Target 沙箱负责那一层。

## Workflow 与 Nodeset：活跃判定

| 主题 | 活跃诊断 | 入口/默认与证据 | 沙箱 |
| --- | --- | --- | --- |
| 流程健康 | `GRAPH.FLOW.MISSING_START/MISSING_END/UNREACHABLE_FROM_START/CANNOT_REACH_END/ORPHAN_NODE` | `append_flowchart_health`；terminal/IO start/end、实际schedule边；算法没有固定业务拓扑 | `core.workflow.normal/missing_boundaries/orphan` |
| Decision | `GRAPH.DECISION.BRANCH_CANNOT_REACH_END` | 选中Workflow审查，判断分支实际可达终点；缺 when 是原生编译错误，见下表 | `core.workflow.decision.dead_end` |
| 重复边 | `GRAPH.EDGE.DUPLICATE/CONFLICTING_DUPLICATE` | 同 endpoint 多次声明 warning，编译仍合并边；条件不同和role矛盾是不同问题 | `core.workflow.duplicate_edge.*` |
| join | `GRAPH.JOIN.AMBIGUOUS_UNCONDITIONAL/ALL_DEPENDS_ON_TRANSFER_ONLY/ALL_BRANCHES_MUTUALLY_EXCLUSIVE/REDUNDANT_ALL` | safe_any 混合来源；all 必须有真实并行schedule前驱，不能等互斥Decision替代支；单前驱all warning | `core.workflow.join.*` |
| 数据交付 | `GRAPH.DATA.MISSING_DIRECT_PROVIDER/TYPE_CARDINALITY_AMBIGUOUS/UNCONSUMED_PROVIDER/RUNTIME_REQUIREMENT_UNREACHABLE/NO_PAYLOAD_BYPASS` | 分清schedule与transfer边及requires.type/provides.type；error/warning原逻辑保留 | `core.workflow.data.*` |
| 逻辑重复 | `GRAPH.SMELL.DUPLICATE_LOGIC` | 相同run fingerprint warning；纯wrapper、带原因的合法similar_to抑制 | `core.workflow.duplicate_logic.*` |
| Nodeset | `NODESET.SMELL.TOO_WIDE/RECURSION/NESTING.DEPTH_EXCEEDED` | width >10 warning；直接或Loop body递归 error；声明嵌套深度 >4 error，含未调用/planned定义；显式深度可配置 | `core.workflow.nodeset.*` |
| Planned | `GRAPH.PLANNED.NODE/NODESET/PARENT_HAS_PLANNED_CHILD` | planned声明 warning；已实现父定义含blocking child error，transparent child warning；stub实际源码检查仍属Python Target | `core.workflow.planned.*` |

baseline 定位：`quality/workflow_rules/flow.py:24-68,117-189,212-355`、`flow_data.py:14-46,49-168,229-309`、`join_exclusivity.py:9-61`、`duplicates.py:8-52`、`planned.py:30-63`、`quality/nodesets.py:15-66`。current：相同算法改私有名保存，`rules/builtin/workflow.py:15-85` 和 Target handler 负责正式选择。

基线实际细节：`optional_one` 没有 direct provider 时，旧 `append_data_contract_warnings` 也会产生 `GRAPH.DATA.MISSING_DIRECT_PROVIDER` error；只有 `exactly_one` 额外触发 `RUNTIME_REQUIREMENT_UNREACHABLE`。沙箱保留这一行为作为基线证据，不根据名字推测原语义应该允许。规则可配置能力并不等于原生契约获得了任意修改权限。

## 原生事实、图编译及执行约束

以下仍直接由真实解析/编译入口运行；记录异常不需要假 Rule implementation。

| 失败/事实 | 原生诊断/异常 | 真实位置（baseline/current基本同主体） | 沙箱 |
| --- | --- | --- | --- |
| 严格Node类型未知或Node/Nodeset同名 | `NODE.TYPE.UNKNOWN/CONFLICT` | `compiler.py:397-428`；Target 提供 ImplementationFacts | `core.native.strict_unknown/type_conflict` |
| 输出 key重复、输出与Root输入key冲突 | `GRAPH.COMPILE` + 具体原因 | `compiler.py:431-446` | `core.native.duplicate_provider/input_provider_conflict` |
| schedule/transfer普通图环 | `GRAPH.CYCLE.FORBIDDEN/GRAPH.DATA.CYCLE.FORBIDDEN` | `compiler.py:717-758`；迭代应使用原生Loop | `core.native.cycle.*` |
| 重复边role矛盾、边无role | `GRAPH.EDGE.ROLE_CONFLICT/NO_ROLE` | `compiler.py:468-525` | `core.native.conflicting_edge_roles/no_edge_role` |
| Decision无when | `GRAPH.DECISION.MISSING_EDGE_CONDITION` | `compiler.py:761-769` | `core.native.decision_missing_when` |
| Async result契约/路由不成立 | `GRAPH.ASYNC.RESULT_KEY_CONTRACT/RESULT_UNJOINABLE` | `compiler.py:321-351,528-558` | `core.native.async_result_*` |
| Target缺global_state/执行锁支持 | `TARGET.FEATURE.UNSUPPORTED` | `compiler.py:354-394` | `core.native.feature.*` |
| 受保护域detached/result不能静态join | `GRAPH.EXECUTION_LOCK.DETACHED_FORBIDDEN/RESULT_UNJOINABLE` | `compiler.py:561-649` | `core.native.lock.detached/result_unjoined` |
| 不同nested key锁冲突 | `GRAPH.EXECUTION_LOCK.NESTED_KEY_CONFLICT` | `compiler.py:979-1050`；同key合法 | `core.native.lock.conflicting_nested_keys/same_key` |
| 全局状态缺有效锁 | `GRAPH.EXECUTION_LOCK.GLOBAL_STATE_UNCOORDINATED` advisory | `compiler.py:852-878`；真实编译仍成功 | `core.native.global_uncoordinated` |
| mainline歧义/死分支/无激活bypass | `GRAPH.MAINLINE.UNDECLARED_SYNC_FANOUT/AMBIGUOUS_SIDE_BRANCH/DECISION_BRANCH_DEAD_END/DATA_BYPASS_WITHOUT_MAINLINE_TRIGGER` advisory | `mainline.py:170-277`；Core产出事实，正式是否进报告要审计Target消费入口 | `core.native.mainline.*` |
| 无节点、重复id、无效endpoint、错误契约authority、max_steps/join/lock/旧boundary/旧loops | `GraphConfigError` + 具体field/message；并非全部有独立code | `config/graph.py:67-214,385-424` | `core.native.config.*`，同时检查message |
| Loop body/iterations/stop/carry/collect无效 | `GraphConfigError` + 具体field/message | `config/loop.py:16-118`、`config/graph.py:559-568`；默认max_iterations=1000，None明确无上限，仍支持原生stop/carry/collect | `core.native.loop.*`，含bounded/unbounded正向对照 |
| 真正有限block不可能表示递归 | `PortablePlanError` + recursive nodeset reference | `block_compiler/compiler.py:272-274`，开启真实nested编译 | `core.native.portable_recursion` |

Core编译本身不判断“任意模型是一个功能块”；业务分类和领域源码判断来自插件。真实 finite-block recursion拒绝与可配置深度阈值分离：提高/关闭审查深度，不使实际递归图能编译成无限展开的有限产物。

## 仅目录、残留名称与批准变化

`quality/workflow_rules/rule_catalog.py::RULE_CATALOG` 是诊断说明表，**不是 Rule 调度表**。其中的 `NODE.EFFECT.CALL_FORBIDDEN/IMPORT_FORBIDDEN/RUNTIME_DISPATCH.UNDECLARED` 和 `GRAPH.SMELL.CONFUSING_NODE_NAME/MISSING_NODE_DESCRIPTION/MISSING_NODE_DISPLAY_NAME` 不在 Core 目录表中实际执行；必须检查 Target 中对应 handler/validator 的活跃调用，不能以码仍存在认定检查已迁移。源码 syntax facts 同样由 Target 产生，Core 不自行解析Python/TypeScript；所选规则需要但不能取得真实事实时，应报告未完成，不能制造空事实冒充成功。旧 `nodeset_depth_error_report` 或 `check_nodeset_depth` helper仍存在，也不能说明命令还独立调用它们。

批准变化有明确语义，不能把非批准遗漏改写成变化：

- `effect_scope` 不再由 flow_kind 自动派生；没有规则输出时为 `unconstrained`，planned真实权限未知时为 `unavailable`。仍保留原生flow身份。`core.native.effect_fallback` 用variant专属预期验证。
- 原诊断事后 downgrades/exemptions 被图中的Rule选择/替换/参数覆盖替代；不得由后加载规则抹去另一条finding。数值默认仍保留并注入Rule参数。
- Root/Nodeset/Node显式空选集关闭其对应审查；后续真实解析、binding、执行要求继续生效。分类不存在或default_rulesets为空时，不能从flow身份悄悄补权限或审查。
- 新Rule阶段/typed records是新增可组合入口。缺handler/缺fact/未完成provider必须unavailable/failed，不能制造空record冒充成功。`core.quality.rule_report` 会正式拒绝未完成状态。

## 当前观察与覆盖边界

`core.workflow.unconstrained_child_identity` 是正式Target编排反例，输入是完整可编译的 receive→Nodeset→send 图。baseline默认审查该合法图；current子Nodeset明确 `rulesets=[]` 后仍应保持原生声明身份。当前 `targets/python/quality/rules/workflow.py:18` 先删掉其声明，`:34-35` 再检查残缺图，实际产生 `RULE.EXECUTION` / `vibeflow.workflow` / unknown child查询失败。案例要求成功，未使用xfail或降低断言；生产修复留给后续授权阶段。

这些共通案例验证 portable事实算法和真实编译，不代替Target扫描、真实插件worker、CLI默认范围及业务执行。它们能揭示Core判定变化，也必须结合Python/JavaScript对照套件判断“默认正式命令是否仍调用该判定”。当前位置记录不伪造：Core source-quality诊断保留FileQuality/ImportSite中的真实位置；纯图错误没有源码位置时明确为空。native parser只有共同异常类别的分支，另外验证message_contains，防止无关早期错误造成假通过。

建议复验命令：`PYTHONDONTWRITEBYTECODE=1 python sandbox/rule_parity/run_all.py --target core --baseline f169429 --report /tmp/vibeflow-core-parity.json`。根runner报告与child日志是本轮实际通过/失败依据，不引用旧全量门禁来证明检查覆盖完整。

首轮统一 runner 实际结果（生产树 `15adf51`）：baseline 185 个观察，current 195 个观察；195 个合并案例中 194 符合，唯一 regression 是 `core.workflow.unconstrained_child_identity`。报告位于 `/tmp/vibeflow-core-parity-final.json`，夹具与进程日志保留在 `/tmp/vibeflow-core-parity-final/`；runner 退出 1 是如实检测到该回退，不是把失败改成预期失败。十个 current-only 选集案例按 `new_feature` 单独列出。

## 正式 Target 消费链补验

`sandbox/rule_parity/core/formal_cases.py` 追加 13 个两版公开 Python Target `validate_graph_health` 对照；与直接评估 Core facts 的案例分开。八个 Nodeset 图案例只有原生 IO 和已加载 Nodeset 声明，receive 有一个实际输出，send 有一个 exactly_one 输入，连边和 Nodeset 调用契约明确一致。元信息反例使用公开 GraphConfig 模型构造缺 display_name/description 的调用，验证 validator 的诊断，不宣称该反例能通过 JSON 配置元信息 schema。五个 Root 源码案例分别验证真实 class AST 重复逻辑、不同逻辑、合法 similar_to、global_state 无锁 advisory、有锁正常；baseline 从真实模块绑定类，current 从真实源码快照和规范声明取得同类事实。

正式报告消费结果：

| 主题 | baseline 默认入口 | current 默认入口 | 两版实际观察 |
| --- | --- | --- | --- |
| 已调用子图 mainline/flow/元信息 | `workflow/validation.py:93-97` 递归定义；`flow_data.py:57-100`、`mainline.py:26-34` | `workflow/rule_phase.py:22-37,64-73` 实际调用；`rules/workflow.py:46-58` 当前子图 | 告警和错误保留，正常对照均通过 |
| 已加载、未调用且仍选默认 Rule 的子图 | 同上，递归全部已加载声明 | actual invocation walker 未调度该声明的 handler | **范围遗漏**：metadata 两条 warning、mainline fanout warning、orphan/cannot-reach-end errors 与 unconsumed warning 消失；mainline 子图报告也消失 |
| Root 重复逻辑 | `validation.py:174-184,406-416` 实测指标与 fingerprints 进入共通算法 | `rule_phase.py:95-98` 取得维护性 Rule 的真实 metrics，`rules/workflow.py:22-23` 消费 | `GRAPH.SMELL.DUPLICATE_LOGIC` 保留；不同逻辑和合法 similar_to 均无误报 |
| Root 全局状态协调 advisory | `validation.py:97,439-455` 消费 compilation.findings | `rules/workflow.py:60-64` 将真实 compilation.findings 纳入所选 workflow Rule | 无锁 warning 保留，有锁正常 |

已加载的 Nodeset 声明属于原命令的结构检查范围；它与范围外的孤立源码不同。未调用声明保留默认规则，却被 actual-calls-only 调度忽略，未按批准变化解释，也未 xfail。显式 `rulesets=[]` 关闭对应审查仍是批准变化；`core.workflow.unconstrained_child_identity` 单独要求关闭审查不破坏原生声明身份。

追加后的统一 runner 真实结果：baseline 198 个观察、current 208 个观察，204 matched、4 regression、无 baseline fixture failure。新增三项未调用声明消费遗漏，加上原 child[] 身份误拒。报告 `/tmp/vibeflow-core-parity-formal-final.json`，源码夹具与进程日志 `/tmp/vibeflow-core-parity-formal-final/`，退出 1；生产代码未修改。这些结果不扩大为 JavaScript 或所有 CLI 的完整证明，Target 对照套件独立提供各自正式入口证据。

## 剩余有限分支的逐项对照

追加案例位于 `core/variants.py` 与 `core/formal_variants.py`，共用 `support.py` 只整理实际返回的 findings/records/编译结果。主 `cases.py` 保持 488 行。以下将上一轮剩余项对应到实际案例；同一活跃分支已经有对照时引用原案例，不为数量再造一个同义图。ID 中的 `*` 表示文件中的有限参数枚举，不表示穷举任意图或阈值。

| 原清单分支 | 实际案例 ID | 验证边界与结果依据 |
| --- | --- | --- |
| 结构默认、关闭、自定义阈值 | `core.variant.structure.default.{root_files,root_dirs,directory_files,directory_depth,child_dirs,root_level}.{below,warn,max,above}`；`core.variant.structure.closed.{none,disabled}`；原 `core.project.structure.*` | 六组默认阈值逐项四边界；None/disabled 不判定；原小阈值四边界保留 |
| 文件/函数自定义上限 | `core.variant.project.custom.{file,function}.{2,3}`；原 `core.project.file.configured`、`core.project.file.*`、`core.project.function.*` | 自定义值等于上限正常、超过上限精确诊断；原行数覆盖及默认各边界保留 |
| Node helper/BaseLib 自定义与关闭警告 | `core.variant.implementation.warning_disabled.*`、`custom_chain.{2,3,4}`、`custom_dependency.{2,3,4}`；原 `core.implementation.optional.*`、`library.*` | Nullable source warning 关闭；helper 的 >=warn 与依赖的 >warn 分开验证；默认未设复杂度限制与显式上限保留 |
| 角色路径推断、显式覆盖与合法依赖 | `core.variant.roles.{inferred_node,inferred_task_node,inferred_custom_nodes,inference_off,module_base,path_base,explicit_override,prefix_exact}`；原 `core.project.roles.*` | `nodes`/`task_nodes`/`*_nodes` 的路径推断、关闭推断、module/path BaseLib、显式角色优先、路径前缀精确匹配 |
| 免检 stem 与 public entry 前提 | `core.variant.distance.stem.{runner,custom_runner,entry}`、`core.variant.structure.ignored_stem.*`、`core.variant.structure.public_entry.*` | stem 精确匹配；ignored stem 影响 internal 判定；public API/export 要求启闭控制 public-entry-bypassed |
| 依赖多路径、外部、重复导入、自环 | `core.variant.dependencies.{diamond,self_cycle,duplicate_import,external_missing,self_cycle_direct}`；原 `core.project.dependencies.{cycle,bidirectional,chain.*}` | 对照真实最长路径/诊断；default evaluator 的自导入过滤是基线限制，见下节 |
| helper 多路径与未知符号 | `core.variant.call_graph.{diamond,unknown_target,unknown_entry}`；原 `core.implementation.recursion.{self,mutual}` | 真实 public CallChain 的路径长度；外部符号不作为本地 helper，未知入口返回长度 0 |
| 重复函数阈值与 fingerprint 边界 | `core.variant.duplicate.{empty_fingerprint,different_fingerprint}`；原 `core.project.duplicate_function.*` | 正常不同 fingerprint、长度阈值与空 fingerprint 的实际基线限制 |
| async/result/执行锁 | `core.variant.native.result_consumer.{False,True}`、`result_without_outgoing`、`detached_unlocked`；原 `core.native.async_result_*`、`lock.*` | 实际 compile_core；无条件 result 消费者合法，条件消费者不能保证静态 join；无锁 detached 正常 |
| Nodeset/Loop 继承锁与 planned 排除 | `core.variant.native.nested_lock.{nodeset,loop}.{same_key,different_key,detached,planned_detached}` | 同 key 合法、不同 key 冲突、detached 锁域拒绝；planned detached 不进入实际执行节点集合 |
| Decision/join 互斥操作与支配路径 | `core.variant.workflow.exclusive.{eq_neq,neq_eq,neq_neq,same_eq,different_keys}`、`exclusive.dominators.*`；原 `core.workflow.join.exclusive_all` | 相同键 ==/!= 互斥、!=/!= 与不同键不保证互斥；间接分支的 dominator 与额外非支配入口 |
| schedule/transfer 与数据 cardinality | `core.variant.workflow.cardinality.{exactly_one,optional_one,all}`、`cardinality.conditional.*`、`cardinality.mixed_role_cycle.{exactly_one,all}`；原 `core.workflow.join.transfer_only`、`data.unreachable.*` | unconditional 两来源的 error、普通 conditional/混合 role 回路的 warning、Decision 互斥来源正常；all 能汇集多个来源；混合回路案例保留真实两组编译边 |
| 数据 bypass 与导出 | `core.variant.workflow.bypass.actual_payload`、`exported_provider.*`；原 `core.workflow.data.bypass_empty` | 有实际同 type payload 的 bypass 正向对照；空 payload 明确拒绝；Root 输出抑制未消费 warning |
| Nodeset 默认/配置深度、宽度、递归 | 原 `core.workflow.nodeset.{depth.*,configured_depth,unused_depth,width.*,recursion.*}`；`core.variant.planned.unused_mutual_recursion.{nodeset,loop}` | 已调用/未调用/planned 深度链；直接、Loop body、两定义互递归的实际声明算法；有限展开另见 `core.native.portable_recursion` |
| planned 父子三种行为与引用 | `core.variant.planned.parent.{blocking,transparent,python_stub}`、`reference_flags.{blocking,transparent,python_stub}.{False,True}`；原 `core.workflow.planned.*` | 父定义 severity 与真实 stub-check event；声明 warning 不等于实际引用 flag；blocking/transparent/stub 的 active flags 分开验证 |
| 正式重复 Nodeset 调用与 Loop body | `core.variant.formal.{repeat,loop}.default.{False,True}`、`repeat.run_default` | 实际公开 Target validator，合法 IO 契约；正常和 body fanout warning；run 指审查阶段，不声称执行业务实现 |
| 正式默认与显式 [] | `core.variant.formal.{repeat,loop}.{explicit_empty,child_empty_identity}`；原 `core.workflow.unconstrained_child_identity` | Root/body 都 [] 正常关闭审查；仅子 [] 不应删除原生身份；重复 Nodeset 误拒仍为红例，Loop 对照正常 |
| 正式 import/static/run 的真实资料 | `core.variant.formal.phases.capture.{import,static,run}` | Current-only 真实 Rule callable；Root 与两次 body 调用各自执行。import 没有 compiled；static/run 的前置 import 与后续实际 compiled 事实分别记录 |
| 正式已加载但未调用声明 | 原 `core.formal.nodeset.{flow,mainline,metadata}.{unused,used}` | 保留原三项 scope 遗漏红例与已调用正常控制；没有将遗漏当作批准的 actual-calls-only 变化 |
| 正式 mainline/advisory/duplicate 消费 | 原 `core.formal.root.*` 与上述 mainline 变体 | 真实 class AST 重复/不同/similar_to、global-state 有锁/无锁；直接 Core facts 通过不能代替正式 Target 消费 |

## 基线限制与覆盖边界

这些说明区分真实 baseline 的能力限制与重构回退，不能把限制反过来当成“正常实现必然正确”：

- `core.variant.dependencies.self_cycle`：基线 `quality/evaluator.py:261-267` 构建项目依赖图时滤掉 `target == file.module`，default evaluator 不报告该自环；位置收集同样在 `:279` 过滤。直接 `dependency_findings` 能识别显式自环，由 `core.variant.dependencies.self_cycle_direct` 单列。两版均保留，不误记为当前遗漏。
- `core.variant.duplicate.empty_fingerprint`：基线 `quality/duplicates.py:7-13` 只用函数长度过滤，不排除空 fingerprint，所以两个长度够的空 fingerprint 会产生 duplicate warning。它是对传入事实的真实限制，不表示实际语言 parser 一定产生空值。
- `core.variant.native.result_without_outgoing`：基线 `compiler.py:538-541` 在没有有效 outgoing 边时跳过普通 result route 判定；无锁时原生编译可以通过。锁域无静态消费者仍拒绝，正常 result 消费者另有对照。不能从这项编译接受推断整个工作流健康或业务执行正确。
- `flow_data.py:263-264,361-370` 的 cyclic-alternatives 降级分支不能泛称为不可达：两种边角色各自无环，合并后仍可能成环。`core.variant.workflow.cardinality.mixed_role_cycle.exactly_one` 使用 `a→consumer`（schedule+transfer）、`consumer→b`（仅 schedule）、`b→consumer`（仅 transfer），a/b 提供同一 type，两版真实编译成功并产生 `TYPE_CARDINALITY_AMBIGUOUS` warning；对应 `.all` 正常。案例记录两组真实编译边，不需要伪造 compiled。原 `core.native.cycle.{schedule,transfer}` 仅证明单角色的普通环会被拒绝。
- `PlannedImplementationCheck` 只表示 Core 要求 Target 检查 stub，不能证明 Python stub 实现已经检查。Core 已记录准确 event，Python suite 独立覆盖实际源码、绑定和 stub 行为；Loop 声明解析和 TaskPlan 语言规则同样不由 Core fact probe 代替。

本轮没有把 schema 或元信息偏好泛称为不可覆盖。原生事实失败的边界是该解析/绑定/编译操作不能产生真实结果；审查插件可以选择、替换判定或参数，但缺少结果时不能制造成功编译事实。每条观察保留其具体调用入口，结合 Target/Tooling 对照判断该命令当时是否真正需要这一步。

最终 Core 独立 runner 结果：**baseline 311 个观察、current 324 个观察；319 matched、5 regression、baseline fixture failure 0**。新增 116 个 current 案例中 113 个有 baseline 对照，3 个真实 phase Rule 入口按 new_feature 单列。报告 `/tmp/vibeflow-core-parity-variants-complete.json`；两版源码夹具与进程日志 `/tmp/vibeflow-core-parity-variants-complete/`。退出 1 准确保留原四项红例，追加一项 `core.variant.formal.repeat.child_empty_identity` 是同一 child[] 身份误拒在重复调用上的证据。`core.variant.formal.loop.child_empty_identity` 通过，不能把该回退扩大为所有 Loop。

本轮可执行 Core 沙箱文件已冻结，生产树仍为 `15adf51`，没有修复或放宽任何生产判定。这里的零 baseline fixture failure 表示本清单的有限案例在原实现中达到事先校准的预期，不表示所有可能的图、代码、语言与命令均被穷举。
