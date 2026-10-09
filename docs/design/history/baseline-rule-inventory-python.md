# Python 基线审查规则与真实入口案例清单

比较基线为 `f169429`，当前生产版本为 `15adf51`。本轮只增加沙箱案例和证据，不修生产代码。这里的“保留”指相同约定下仍获得原有检查结果；存在同名诊断码、同名私有函数或单元测试通过，均不单独证明正式入口已经接上。

沙箱入口为 `tests/fixtures/rule_parity/python/cases.py` 的 `run_cases(work_root, variant, toolchain_root=None)`。父进程为两版分别选择 `PYTHONPATH=<kernel>/src`，每条案例再启动独立进程。加载案例模块时不导入 VibeFlow。旧 `NODE_INFO/CONTRACT` 只在 `variant=baseline` 生成的夹具中使用，当前版只生成声明资源及纯实现类。

## 入口与边界

| 入口 | 基线实际调用链 | 当前实际调用链 | 本沙箱证据 |
| --- | --- | --- | --- |
| `python -m vibeflow inspect-node` | Tooling `cli/node.py:93` 静态预检后加载实现；`:155` 调 `validate_node_class(scan_module=True)`、`scan_base_lib`、依赖链汇总 | Tooling `cli/node.py:10` 装配声明、读取源码，`:25-26` 分别执行 `import/static` 所选规则，不加载业务类 | 基线 229 条、当前 235 条 Node/契约/纯度/导入观察，含 6 条单列的旧 CLI 异常运输 |
| 公开 `validate_node_class` | 实际加载安全源码后调原公开 validator，取得真实 `PurityViolation` | 当前权威移至声明；对应案例经真实 `inspect-node` 装配拒绝 | 6 条非法 contract 形状：原 CLI 在报告序列化时异常，不能说它已正常运输 validator 的诊断 |
| 公开 `validate_graph_health` | `quality/workflow/validation.py` 编译事实，收集 Node 参数和源码，调用类审查 | 同名入口收集 `SourceContext`、执行 Node 和 Workflow 所选 Ruleset | 两条真实 start→demo→end 参数图及 4 条完整第二 Node 注册的耦合/普通 helper 图 |
| 公开 `scan_base_lib` | `project/base_lib.py:181` 读取允许目录，AST 扫描、数值限制与依赖闭包 | Tooling 读取同范围，Target `quality/base_lib.py` 经所选 BaseLib Rule 判断 | 35 条独立 BaseLib 正反例 |
| 公开 `analyze_python_source` | `quality/source.py` 将实际 Python 语法变成 `FileQuality/FunctionQuality/ImportSite` | 同名入口继续抽取；可选副作用判断通过内置 Rule 执行 | 9 条 Target 源码抽取案例 |
| 正式 `quality-check --path <单个 Python 文件> --json` | Tooling `project/quality_scan.py` 读指定文件→Target 抽取→Core 通用质量规则 | 同一边界→Core 所选项目质量 Ruleset，记录真实规则执行 | 4 条 CLI：syntax、effects、params、duplicates |
| 正式 `run --workspace` | 原 registry import tree preflight 在业务模块执行前拒绝 | 当前真实资源/Rule 装配后执行唯一 Node 的 import-only Ruleset，再延迟绑定实现 | 2 条 try/match 命中分支写 marker 的有限案例；static/run为空、start/end显式无规则，避免其他审查掩盖 |

上述源码案例没有扩张到孤立源码、未调用 Node 或项目全部领域源码。一般项目质量扫描的既有范围与 Node/Workflow 领域规则的实际调用闭包是不同入口。这里验证的是静态审查结果和导入阻断；没有把 `inspect-node` 或 quality 的成功解释成业务运算成功。业务运行、Rule 图、资源注册与架构图的其他沙箱由总清单另行列出。

## 默认选择、参数及严重度

基线 `targets/python/quality/source_analysis/__init__.py:46-105` 无条件执行契约/interface；其余判断受 `effective_effect_scope(info)` 影响，`external` 的 trusted 分支会提早返回。默认 Process 的 scope 为 none。当前选择由声明/category 的 Ruleset 决定，不从 `flow_kind` 或 `external` 偷偷授权。

当前 `core/rules/builtin/effects.py:24-36` 声明如下：

| Ruleset | static/run | import | scope 参数 |
| --- | --- | --- | --- |
| `vibeflow.process` | no_side_effects、node_interface、maintainability | import_side_effects | none |
| `vibeflow.io` | 同上 | 同上 | terminal |
| `vibeflow.python_io/document/data_store` | 同上 | 同上 | python_io |
| `vibeflow.global_state` | 同上 | 同上 | global_state |
| `vibeflow.base_lib` | no_side_effects、maintainability | import_side_effects | none |
| `vibeflow.workflow` | workflow | 默认空 | 图检查默认深度 4、宽度警告 10 |

Python handler 注册位置为 `targets/python/quality/rules/__init__.py:10-20`，合并 Core implementation/project-quality/workflow handler 与 Python AST handler。Core 继续只判断通用事实；Python 负责语言语法、导入及源码归属。

Node 数值默认由 `core/quality/policy_data.py:9-23` 提供：源码 500 行/60000 字节，警告 450 行/54000 字节；函数/分支/嵌套/参数/契约宽度的硬上限默认 `None`，需要配置才触发；内部链警告/上限 4/4；BaseLib 链警告/上限 4/6。直接创建 `PurityPolicy()` 的警告阈值与正式 CLI 经 EffectivePolicy 装配的阈值不完全相同，案例明确选择入口，不把两者混为同一默认。

当前 `quality/rules/helpers.py:20-44` 将同一公开嵌套 `policy.node_source/complexity/imports/base_lib/maintainability` 参数映射到 Target Policy；显式 RuleCall/override 优先。项目质量 Rules 的数值默认经 `quality/rule_adapter.py:43-47` 注入 Core RuleDescriptor。Node 源码指标和一般文件指标口径不同：前者针对实现类；后者针对文件以及函数。

## 活跃判定库存

下表按实际判定主题列出基线活跃路径，不以诊断字符串数量推算规则数量。“案例”是此次可复用观察的 ID 后缀；所有 ID 均以 `python.` 开头。新增具体分支以 `variant.` 开头。文末逐项列出上一轮源码追踪项的关闭证据及仍然不同的事实/运输边界；不声称任意 AST 排列均已覆盖。

### Node 声明、契约及 interface

基线路径为 `quality/source_analysis/validators.py:23-143` 与 `helpers.py:14-48`，由 `validate_node_class` 的 `_append_contract_violations` 实际调用。

| 判定 | 基线诊断/严重度 | 当前归属及证据 |
| --- | --- | --- |
| NodeInfo 存在，type/display/category/description/version 非空，flow_kind 合法，external 布尔，类型匹配 | `NODE.CONTRACT.MISSING_NODE_INFO`、`NODE.METADATA.NODE_INFO_*`、`NODE.FLOW_KIND.*`、`NODE.EXTERNAL.INVALID`、`NODE.METADATA.TYPE_MISMATCH`，error | `variant.metadata.*` 逐字段空值/非字符串、flow invalid、external non-bool、type mismatch 和 normal。旧 class 属性权威由 4 条 `authority.*` 证明授权移除；当前真实声明 category 空值另有接受差异，不能用授权迁移掩盖 |
| NodeContract 存在；requires/provides 列表及条目类型、非空字段、cardinality、重复 type/key | `NODE.CONTRACT.MISSING_CONTRACT/CONTRACT_REQUIREMENT_LIST/CONTRACT_REQUIREMENT_SHAPE/CONTRACT_DUPLICATE_REQUIREMENT_TYPE/CONTRACT_PROVIDER_LIST/CONTRACT_PROVIDER_SHAPE/CONTRACT_DUPLICATE_KEY`，error | `variant.contract.requires_scalar/requires_item/provides_scalar/provides_item/duplicate_requirements/requirement_*/provider_*/requirement_valid`；旧 typed contract 判定与当前 canonical 声明拒绝分别实测。非法列表的旧 CLI 异常运输另列，不伪造诊断 |
| requires type 与 provides key 不重叠 | `NODE.CONTRACT.CONTRACT_OVERLAP`，error | `contract.overlap`：基线拒绝，当前接受，已证实回退 |
| 输入/输出 semantics 为映射，覆盖实际键，无多余键，每值为非空字符串元组 | `NODE.CONTRACT.CONTRACT_SEMANTICS/CONTRACT_SEMANTICS_MISSING/CONTRACT_SEMANTICS_EXTRA`，error | `variant.semantics.scalar/value_scalar/value_blank/value_number/input_value_blank/input_value_number/normal` 及原 missing/extra。形状和空字符串拒绝保留；输入/输出数字值当前被字符串化接受，两条原期待仍拒绝 |
| Decision 应提供 route/decision/branch/selected/done/should_retry 一类键 | `NODE.DECISION.MISSING_ROUTE_OUTPUT`，error | `contract.decision_missing_route/decision_route`：反例当前漏检，正常对照通过。前次原生 GraphCompiler 实测也接受反例，不能说迁到了原生编译 |
| examples 元组，元素为映射，inputs/params 均为映射 | `NODE.MAINTAINABILITY.EXAMPLE_SHAPE`，warning | `contract.example_missing_params/example_missing_inputs/example_bad_params` 三条当前漏警告；当前 handler 没接旧判断 |
| examples.outputs 已删除 | `NODE.PURITY.EXAMPLE_OUTPUTS_REMOVED`，error | `contract.example_outputs_removed` 两版都拒绝，当前 canonical parser/load-error 运输 |
| run_pure 存在、同步、恰好 self/inputs/params；无 varargs/kwargs/keyword-only | `NODE.CONTRACT.MISSING_RUN_PURE/RUN_PURE_SIGNATURE/ASYNC_RUN_PURE`，error | 原 interface 案例加 `variant.signature.varargs/kwargs/keyword_only/wrong_order/extra_default/posonly/defaults/normal`；普通 AST 方法的全部所列签名分支实测保留 |
| __init__ 无配置参数；不自定义 run(context)；不暴露额外公开 callable | `NODE.CONTRACT.INIT_SIGNATURE/CONTEXT_RUN_FORBIDDEN/PUBLIC_CALLABLE`，error | `variant.signature.init_default_self/init_keyword_only/init_varargs/init_kwargs/init_normal` 加原 context-run/public-helper 对照。`variant.signature.public_lambda/public_value` 区分 callable 与普通数据：lambda 当前漏检，不能仅凭 def 检测通过说整个 callable 分支保留 |

### Node 可维护性与数值

基线 `validators.py:147-204` 调 Core `quality/implementation.py` 的通用数值算法，AST 指标及链来自 Target `metrics.py`。当前入口是 `quality/rules/maintainability.py:11-78`，仍调用 Core 数值规则。

| 判定 | 原诊断/条件 | 真实案例与状态 |
| --- | --- | --- |
| 源码行/UTF-8 字节超过上限，达到 warning 阈值 | `NODE.PURITY.SOURCE_TOO_LARGE/SOURCE_BYTES_TOO_LARGE/SOURCE_NEAR_LIMIT/SOURCE_BYTES_NEAR_LIMIT` | 原 source 三条加 `variant.numeric.byte_warning_220/100`，真实 UTF-8 bytes 高/低警告阈值对照均保留 |
| 函数、分支、最大嵌套、配置参数、契约键个数超过显式上限 | `NODE.MAINTAINABILITY.COMPLEXITY_MAX_FUNCTIONS/MAX_BRANCHES/MAX_NESTING_DEPTH/MAX_PARAMS/MAX_CONTRACT_KEYS` | 原 functions/allowed、branches、nesting、configured_params_2/4 加 `variant.numeric.contract_key_limit_2/3`；显式 key 上限拒绝/放行均保留 |
| 内部 helper 递归或链过长 | `NODE.MAINTAINABILITY.RECURSIVE_CALL_CHAIN/CALL_CHAIN_TOO_DEEP`，warning/error 由阈值决定 | `metrics.recursive_helper/call_chain_warning/call_chain_error` 保留 |
| 临时键、不规范拼写、契约超过 10 键 | `NODE.MAINTAINABILITY.TEMPORARY_KEY/CONFUSING_KEY_NAME/WIDE_CONTRACT`，warning | 原 temporary/confusing 加 `variant.numeric.contract_width_10/11`；10 不警告、11 警告的真实边界保留 |
| Node→BaseLib 模块链过长/递归事实 | `NODE.MAINTAINABILITY.DEPENDENCY_CHAIN_TOO_DEEP`，warning/error | absolute chain 2/4 保留；relative chain 2/4 当前长度均停在 2，基线为 3/5，已证实回退 |
| Reachable BaseLib 源码数值限制 | `BASE_LIB.SOURCE.MAX_LINES/MAX_BYTES`、`BASE_LIB.COMPLEXITY.MAX_FUNCTIONS/MAX_BRANCHES/MAX_NESTING_DEPTH` | `library.reachable_functions_base_lib` 保留；同一允许配置改为 support 目录，基线仍报函数超限，当前漏检 |

Node 依赖链回退不是 Core 阈值函数失效：`maintainability.py:47` 只选 module 名包含字面 `base_lib` 的文件，`:52-56` 从 `import_modules` 字面结果建边，没有消费 SourceContext 已解析的相对导入关系。自定义支持目录链长度旧版也为 0，`library.chain_custom_path_2/4` 特别记为 `baseline_limitation`；这不能冒充本次新增回退。自定义目录的函数复杂度则旧版确实检查，本次是不同的已证实回退。

### 无副作用、输入所有权、输出与 Node 耦合

基线 `quality/source_analysis/visitors.py` 的 NodePurityVisitor 与 ModulePurityVisitor 由正式类审查调用，依赖 `effects.py` 的导入/调用分类、别名跟踪与 `input_tracking.py`。当前 `quality/rules/effects.py:11-94` 调同类语言分析算法，但授权来自真实 Rule 输出，源码范围来自 SourceContext。

| 活跃主题 | 原诊断/证据 |
| --- | --- |
| 禁止有副作用模块/调用，sys.argv、terminal streams、SystemExit、动态模块命名空间 | 原 imports/purity 案例加 `variant.effect.argv_module_alias/argv_from_alias/stdout_alias/stderr_module_alias/stdin_read/exit_alias/exit_builtin/exit_quit/ffi_root_alias/callback_hook/path_alias`。terminal 输出/exit、显式 argv 输入与 argparse 显式参数为正常邻居；两版结论保留 |
| 动态执行 eval/exec/compile/__import__ 等、动态 namespace lookup、boundary 层导入 | `variant.effect.eval_builtin_alias/eval_assignment_alias/dynamic_import_alias/globals_lookup/locals_lookup/vars_sensitive/dunder_sensitive/boundary_import`。真正 namespace 反例使用非字面 key；固定字面 math 键与普通 dict 是合法对照。依赖实际 alias/module 事实，未把所有 banned token 当作已实测 |
| monkey patch、持有 context/client/session/browser 等资源字段 | `NODE.PURITY.MONKEY_PATCH/RESOURCE_FIELD`；`purity.setattr/resource_field` 实测保留 |
| global/nonlocal、外部导入模块属性写入、模块可变状态 | `NODE.PURITY.GLOBAL_STATE/MODULE_GLOBAL_STATE`；`purity.ambient_module_mutation` 和 `imports.mutable_module` 实测拒绝；当前后者经 import Rule 报 `NODE.IMPORT.SIDE_EFFECT` |
| 原始 inputs、别名、从 inputs 取得的容器，通过 assign/delete/修改方法/传给 helper 被修改 | 原 purity/helpers 加 38 条 `variant.ownership.*`；10 个 mutator 各有输入/局部容器对照，嵌套/属性/注解/get/链别名及 helper 位置/关键字/传递参数实际覆盖。`+= [1]`、分支重绑定两版均漏，明确记原局限；私有 class helper 参数传播当前新增 |
| run_pure 内 while、yield/yield-from | `NODE.PURITY.INTERNAL_LOOP/GENERATOR_RUN_PURE`；原 while/yield 加 `variant.syntax.yield_from/for_allowed/comprehension_allowed`，拒绝生成器同时保留正常 for/comprehension |
| return 字面 dict 的动态键、额外键、缺声明键 | `NODE.PURITY.DYNAMIC_OUTPUT_KEY/UNDECLARED_OUTPUT/MISSING_OUTPUT`；对应 3 条 `purity.*_output` 实测保留 |
| 从运行时 inputs 取 callable 执行 | `NODE.EFFECT.RUNTIME_DISPATCH.UNDECLARED`，warning；`purity.runtime_dispatch` 实测保留。不能把未知 callable 当作已证实无副作用 |
| 引用其他 Node 模块、直接调用、读取其内部、未经允许或禁止的 BaseLib | 原 4 条 coupling 加 `variant.library.node_method_undeclared/banned/allowed`，方法内允许/禁止配置保留；完全相同导入放模块顶层的 `node_module_undeclared/banned/allowed` 两版都未应用 Node allow/banned 判定，明确记原局限 |

基线有一个诊断映射细节：`types.py:_default_rule_id` 先处理所有 `node_*`，因此真实 `node_import/node_direct_call/node_internal_read` 会先进入 `NODE.METADATA.*` 分支。其后写着的 `NODE.COUPLING.*` 分支不能单凭字符串认定为正式发出的码。新的 4 条耦合案例通过公开图审查和完整第二 Node 注册执行：第二模块故意叫 `implementations.other`，不使用含 Node 的目录名触发启发式；基线注册真实导入模块的类，以提供准确 `__module__`，当前提供真实 NodeDescriptor。普通 helper 的合法对照仍同时注册第二 Node。私有字段读取旧版接受、当前拒绝属于 new_feature，未伪装为旧版已经具有的全面私有成员审查。当前声明识别不应恢复 class 属性启发式。

同文件 helper 保留；跨文件 helper 的源码归属/输入参数传播是本次新能力：`helpers.cross_file_input_mutation` 基线接受，当前明确拒绝，分类 `new_feature`。共享 helper 与传递导入不是“全文件被某 Node 合法拥有”的证明，领域定义位置仍由插件自行判定。

### 导入前审查

基线 Tooling `cli/node.py:93` 调 `source_analysis/preflight.py`，沿本地导入闭包在实现加载前做检查；类元信息/安全声明构造有专门 AST 识别。`validate_node_class(scan_module=True)` 又执行模块纯度检查。当前 `quality/rules/import_side_effects.py:8-101` 用 SourceContext 扫描导入时真正执行的表达式/语句：module/class 调用、函数 default、decorator、class bases/keywords、metaclass、`__init_subclass__`、await/context manager/iteration/control flow、可变模块状态。

`imports.top_level_call/function_default_call/class_decorator` 现在生成真正会写 marker 的实现，各版均在执行 marker 前拒绝，`actual.metrics.marker == ''` 已验。旧正式 CLI 把 preflight 失败运输为 `NODE.INSPECT.LOAD_ERROR`，消息包含真实来源及 legacy reason；当前为带位置的 `NODE.IMPORT.SIDE_EFFECT`。`imports.mutable_module` 旧码为 `NODE.PURITY.MODULE_GLOBAL_STATE`。期待显式按 variant 区分运输码，没有把这个变化记成漏检。

`import_variants.py` 另有 26 条具体表达式/语句：default literal 与 keyword/nested default call；builtin/local base 与 base call、`__init_subclass__`、metaclass；staticmethod/classmethod/qualified staticmethod/property；顶层 with/for/while/if/try/match/raise；TYPE_CHECKING、immutable tuple、annotated mutable 与 annotation call；正式 runtime try/match marker 两条。marker 反例均观测真实未执行。当前误拒原本安全的 qualified staticmethod/property，漏掉空 try/match 的原语法拒绝；保留原期待形成红例。TYPE_CHECKING 在旧 preflight 被认可，但后续模块 visitor 仍拒绝，作为原误判单列。

函数 annotation 的实际调用同时受旧 preflight 和当前 static effect Rule 约束；annotation_call 两版都拒绝且 marker 为空，当前真实码是 `NODE.EFFECT.CALL_FORBIDDEN`。这证明默认完整 Node 检查链保留能力，不能改称当前 import visitor 单独已检查 annotation。空 try/match 反例也证明当前接受的是这两种语法形式，未据此推断 try 内任意 IO 都逃过默认 static Rule。

`variant.import.try_marker/match_marker` 则通过正式 CLI run 尝试真实实现装配：baseline 由原 registry preflight 拒绝，真实码 `WORKSPACE.REGISTRY.IMPORT`，原因精确指出 node.py 内 `open.write`；当前由 `NODE.IMPORT.SIDE_EFFECT` 拒绝。当前 demo 只选 import 入口，static/run 均为空，start/end 的 rulesets 也显式为空，不靠相邻 Node 或 static effect 检查补偿；两个命中分支各会真正写文件，四次观察 marker 都为空。这证明本次 try/match 的真实 open/write 副作用仍在绑定前阻断，空控制结构的语法差异不能称为这两条实际副作用安全泄漏。

当前 Node/Workflow/实际 Nodeset/Loop 的所选 import 入口共用正式装配点；默认 Workflow import 为空。上述 291 条主要验证 Node 和一般源码入口，Workflow import 生命周期及重复调用范围的真实测试位于既有 `tests/targets/python/test_workflow_import_rules.py` 等文件，不能用本清单的源码案例数代替这些生命周期验收。

### 独立 BaseLib

基线 `project/base_lib.py:49-103,241-417,462-550` 实际扫描以下主题；当前 AST 判定在 `quality/rules/base_lib_effects.py`，数值判定经 maintainability/Core。

| 活跃主题 | 诊断 | 此次案例 |
| --- | --- | --- |
| Python 语法 | `BASE_LIB.SYNTAX` | `library.scan_syntax` |
| mutable module/global/nonlocal | `BASE_LIB.GLOBAL_STATE` | mutable_global/global_statement |
| module 顶层控制/执行语句 | `BASE_LIB.TOP_LEVEL_SIDE_EFFECT` | 原 top_level_control 加 `variant.library.top_with/top_for/top_while/top_try/top_expression/immutable_tuple` |
| 侧效调用、argv、namespace、exit | `BASE_LIB.SIDE_EFFECT_CALL` | 原 side_effect/dynamic_namespace 加 `variant.library.namespace_locals/namespace_sensitive/namespace_module/ordinary_lookup/exit_raise/exit_sys_alias/argv_alias/ordinary_raise`；argv from-import 的真实运输为 `BASE_LIB.BANNED_IMPORT` |
| Node/plugin/boundary/runtime 等项目执行层导入 | `BASE_LIB.FORBIDDEN_PROJECT_IMPORT` | project_import |
| 一般禁用模块与显式 banned_base_lib_modules | `BASE_LIB.BANNED_IMPORT/BANNED_MODULE` | 原 banned_import 加 `variant.library.explicit_banned_module/math_allowed`，显式 math 禁用与允许邻居 |
| 源码行/字节、函数/分支/嵌套上限 | `BASE_LIB.SOURCE.*`、`BASE_LIB.COMPLEXITY.*` | 原 lines/functions 加 `variant.library.bytes_100/10/branches_1/2/nesting_1/2`，真实读取 AST 和 UTF-8 源码后拒绝/放行，不用手造 Core 指标 |
| 依赖闭包出现违规库 | `BASE_LIB.DEPENDENCY_CLOSURE_VIOLATION`、Node 间接包装 `NODE.BASE_LIB.INDIRECT_VIOLATION` | `variant.library.dependency_closure/dependency_closure_valid` 用真实相对导入及违规/纯 helper 对照；不要求所有旧包装逐字相同，只保留直接错误与来源 |

### 一般源码的 Target→Core 事实链

基线 `quality/source.py:93-182,191-375,378-435` 实际抽取：UTF-8 字节、行数、函数/类/公开 API 数、分支/嵌套、import sites（实际源码行列与相对模块解析）、函数区间、必需参数（排除默认与方法 self）、规范化 AST 指纹。语法异常 `QUALITY.SYNTAX.PYTHON` 有真实文件/行列。`check_side_effects=True` 才产生 `QUALITY.SIDE_EFFECT.IMPORT/CALL` warning；默认关闭。

当前 `quality/source.py:51-123` 保留这些抽取及可选开关，已有 AST 可复用不再解析。`source_specs.py` 的 13 条案例将这些能力连接到公开 Target API，并选 4 条通过正式 CLI→Tooling scanner→Target→Core；不是用手造 Core FileQuality 代替 Target 抽取。

项目文件/函数阈值、依赖距离/目录结构/链、重复逻辑属于 Core 通用判断，仍以 Target 事实为输入。`QUALITY.DUPLICATE.AST_FINGERPRINT` 至少两段 3 行函数才触发；位置信息在 function_details 中，未伪造不存在的单一 source_location。syntax 案例当前可能附加 unavailable/input 诊断，这属于真实未完成事实运输，不将它们当作空图/空依赖正常完成。

## 不应算作丢失的授权变化与基线局限

| 分类 | 场景 | 可复用案例 |
| --- | --- | --- |
| approved_change | 实现类不再承载 NODE_INFO/CONTRACT，资源声明仍完整 | authority.class_metadata_removed |
| approved_change | `rulesets=[]` 明确未约束，不隐式恢复 Process no-effects | selection.empty，当前 metrics.effect_scope=unconstrained |
| approved_change | 同 flow_kind=process 显式选 terminal Rule 可允许 print | selection.process_terminal，当前 scope=terminal |
| approved_change | external 元信息不再隐式 trusted | selection.external_no_grant，当前明确 process Rule 拒绝 |
| baseline_limitation | 非 base_lib 命名的允许 support 模块链没有旧 Node dependency 长度 | library.chain_custom_path_2/4，两版实际 0 |
| baseline_limitation | 输入容器 augmented assignment、分支后别名覆盖没有完整 ownership 传播 | variant.ownership.augmented_alias/conditional_alias，两版接受；其中 augmented assignment 真正使用 `+= [1]` |
| baseline_limitation | module 顶层 BaseLib 导入没有应用 Node 的声明允许/禁止判断 | variant.library.node_module_undeclared/node_module_banned；相同 method 导入明确拒绝 |
| baseline_limitation | TYPE_CHECKING 已被 preflight 识别，但随后 module visitor 仍拒绝 | variant.import.type_checking；基线 MODULE_SIDE_EFFECT，当前安全静态声明被接受 |
| baseline_limitation | 非法 requires/provides/semantics 经旧 CLI 序列化时未正常返回诊断 JSON | variant.contract.*.cli_transport、variant.semantics.*.cli_transport，6 条；公共 validator 的 6 条独立观察仍有正式规则诊断 |
| new_feature | 跨文件 helper 输入修改沿真实符号归属审查 | helpers.cross_file_input_mutation |
| new_feature | 用 canonical 注册事实识别第二 Node 的任意私有成员读取；旧版只保护其 NODE_INFO/CONTRACT | coupling.private_registered_node |
| new_feature | 私有 class helper 的位置参数/关键字参数输入 ownership 传播 | variant.ownership.class_helper_position/class_helper_keyword |

FFI allowlist 没有解除 NoEffect：`imports.ffi_policy_allow` 两版实际均报 `NODE.EFFECT.IMPORT_FORBIDDEN`，属于 preserved，不能因 policy 中 allowed_roots 出现 ctypes 就推断旧版合法。

## 只有残留代码，不能当作活跃能力的分支

基线 `source_analysis/helpers.py` 的 `_validate_key_tuple` 被 validators import，但 `_validate_contract` 已直接审查 DataRequirement/DataProvider；没有该 helper 的正式调用。`_validate_schema_mapping` 同样没有活跃契约调用，旧 schema/snapshot 诊断字符串不证明 f169429 正式 Node 契约仍做那套输出 schema 检查。

基线 `quality/rules.py:side_effect_findings` 与 `quality/imports.py:_collect_import_sites` 保留了另一套辅助实现，实际一般源码入口调用的是 `quality/source.py` 本地 `_side_effect_findings/_collect_import_sites`。库存以 source.py 实际链为准。旧 NodeInfo/Contract 检查在当前移到 canonical 声明权威；删除旧属性审查本身不属于退步，但 Decision/overlap/example 判断没有在新权威路径重接是已实测的独立问题。

## 上一轮源码追踪项的逐项关闭

这里的“关闭”是提供该具体判定的实测案例，或明确证明其不是正式入口的活跃判定；它不等于把原局限改成完备，也不等于把旧 class 元信息重新设为当前权威。以下 ID 均省略共同前缀 `python.`。

| 原追踪项 | 关闭证据与边界 |
| --- | --- |
| Node 元信息各必填字段坏形状及类型 | `variant.metadata.{type_key,display_name,category,description,version}_empty` 与各自 `_non_string`；flow_kind non_string 的真实旧码为 FLOW_KIND.MISSING；normal、flow_invalid、external_non_bool、type_mismatch 对照。空 category 当前被设计成可选字段，属于待核定的声明契约差异，未标为安全问题 |
| NodeInfo/NodeContract 缺失或错误对象 | 原 `authority.class_metadata_removed` 加 `variant.authority.invalid_info/missing_contract/invalid_contract`。当前完整资源声明仍为唯一权威；旧 class 属性无效或被忽略属于已授权迁移，不要求它们继续有效 |
| requires/provides 列表和条目坏形状 | `variant.contract.requires_scalar/requires_item/provides_scalar/provides_item` 的基线 public validator 与当前 CLI 声明拒绝；另 4 条 `.cli_transport` 如实保留旧 CLI 异常。旧算法假定 DataRequirement/DataProvider 内部字段为 typed facts，不能把任意非法 Python 对象的 `.strip()` 异常冒充规则诊断 |
| 重复 requirement、requirement/provider 字段和 cardinality | `variant.contract.duplicate_requirements/requirement_type/requirement_cardinality/requirement_display_name/provider_key/provider_type/provider_display_name/requirement_valid`，原 duplicate_provider 保留。均有完整正常 contract 邻居 |
| semantics 映射/值、输入与输出 | `variant.semantics.scalar/value_scalar/value_blank/value_number/input_value_blank/input_value_number/normal` 加原 missing/extra。scalar/value_scalar 的旧 CLI 序列化异常另 2 条单列。两条数字值的当前漏拒绝保留为红例 |
| run_pure 参数数量、次序、种类和 defaults | `variant.signature.varargs/kwargs/keyword_only/wrong_order/extra_default/posonly/defaults/normal` 加原 missing/async；普通 Python def 签名的明确各分支已观察。`signature_unavailable` 是旧 inspect 对不可取得签名对象的事实错误运输，普通合法 AST def 无法触发，未伪造手动抛错案例证明能力 |
| __init__、公开 callable 与公开数据 | `variant.signature.init_default_self/init_keyword_only/init_varargs/init_kwargs/init_normal/public_lambda/public_value` 加原 context-run/public method/private helper。lambda 的新漏检单列，不由普通 def 正例代替 |
| 源码 byte warning、固定 contract width、可配置 key 数 | `variant.numeric.byte_warning_220/100/contract_width_10/11/contract_key_limit_2/3`，全部通过正式 CLI，不仅调用 Core 阈值函数 |
| import/call alias、argv、streams、SystemExit | `variant.effect.argv_module_alias/argv_from_alias/stdout_alias/stderr_module_alias/stdin_read/exit_alias/exit_builtin/exit_quit/eval_builtin_alias/eval_assignment_alias/dynamic_import_alias/ffi_root_alias/path_alias/callback_hook`，另 argv_declared_input/stdout_terminal/exit_terminal/ordinary_exception/math_alias/argparse_True 等邻居 |
| 动态 namespace 与 boundary 导入 | `variant.effect.globals_lookup/locals_lookup/vars_sensitive/dunder_sensitive/boundary_import`，非字面 key 是实际禁止分支；`vars_module/dunder_dict/ordinary_dict_lookup` 为固定安全读取邻居，不能把这些合法静态查找校准成假负例 |
| 输入 mutator 方法的不同拼写 | append、clear、extend、insert、pop、popitem、remove、setdefault、sort、update 各有 `variant.ownership.<method>_input/<method>_local`，20 条真实 source 对照 |
| 嵌套/别名/属性/annotated/方法/helper 参数所有权 | `variant.ownership.nested_set/nested_delete/nested_attribute/annotated_alias/get_alias/alias_chain/helper_position/helper_keyword/helper_chain/helper_local/class_helper_position/class_helper_keyword`；rebound_local/copy_list/copy_dict/ordinary_read 为邻居；augmented_alias/conditional_alias 是实测原局限 |
| yield-from 与合法 for/comprehension | `variant.syntax.yield_from/for_allowed/comprehension_allowed`，并保留原 while/yield 案例 |
| Node→BaseLib undeclared/banned、module/method 差别 | `variant.library.node_{module,method}_{undeclared,banned,allowed}` 6 条；两版 method 拒绝保留，module 两项漏查明确记原局限 |
| 独立 BaseLib 顶层执行、namespace、exit | `variant.library.top_with/top_for/top_while/top_try/top_expression/immutable_tuple/namespace_locals/namespace_sensitive/namespace_module/ordinary_lookup/exit_raise/exit_sys_alias/argv_alias/ordinary_raise`；真实 AST scanner，不 import 库执行 |
| 独立 BaseLib banned 配置及闭包 | `variant.library.explicit_banned_module/math_allowed/dependency_closure/dependency_closure_valid`。闭包用实际 relative import 和违规 print helper；直接诊断、依赖间接诊断均保留 |
| 独立 BaseLib bytes/branches/nesting | `variant.library.bytes_100/10/branches_1/2/nesting_1/2`，拒绝/放行边界与已有 lines/functions 案例一起覆盖数值主题 |
| Node 导入 default/decorator/bases/metaclass | `variant.import.default_literal/keyword_default_call/nested_default_call/base_call/init_subclass/metaclass/explicit_type_metaclass/object_base/local_base/decorator_{static,class,qualified_static,property}`。安全 base 与 default/decorator 有正常邻居；qualified decorator/property 新误拒单列 |
| Node 导入 with/iteration/control flow/mutable/annotation | `variant.import.with/for/while/if/try/match/raise/type_checking/immutable_tuple/annotated_mutable/annotation_call` 加正式 run 的 `try_marker/match_marker`。所有 marker 期待为空；try/match 空结构是当前漏掉语法拒绝，实际 open/write 在唯一 import-only 规则下仍被提前阻断；annotation 默认链由 static Rule 拒绝，不伪称 import visitor 单独具备 |
| schema/snapshot/key-tuple 辅助 validator 及重复 source helper 实现 | 上一节已按实际引用证明 `_validate_schema_mapping/_validate_key_tuple` 不在原契约调用链、一般源码使用 source.py 本地实现；属于非活跃残留，不为它们生成手调私有函数的假 parity 证明 |

库扫描允许目录、未调用规则、自定义资源选择等语义仍由原公开入口确定。这次关闭的是上述已盘点具体分支，不扩展成项目全源码领域扫描，也没有增加原生执行门禁。

## 此轮观察结果与复验

共 291 条，每个 variant ID 一致；原 101 条和新 188 条已分别在两个内核实际观察，新条受影响的 117 条再次隔离复验；最后 2 条正式 run marker 与原 24 条 import 对照又在两个内核观察，并将 start/end 控制为显式无规则后复验。基线观察均满足校准后的原有事实期待；当前共 16 条不满足原接受/拒绝/警告或指标期待，含原 8 条和新 8 条。统一 runner 的新鲜全组结果以总报告为准。

原 8 条没有删除或改成当前行为：

| ID | 基线实际 | 当前实际 |
| --- | --- | --- |
| python.contract.decision_missing_route | FAIL，MISSING_ROUTE_OUTPUT error | PASS |
| python.contract.overlap | FAIL，CONTRACT_OVERLAP error | PASS |
| python.contract.example_missing_params | CONCERNS，EXAMPLE_SHAPE warning | PASS |
| python.contract.example_missing_inputs | CONCERNS，EXAMPLE_SHAPE warning | PASS |
| python.contract.example_bad_params | CONCERNS，EXAMPLE_SHAPE warning | PASS |
| python.library.chain_relative_2 | 长度 3 | 长度 2 |
| python.library.chain_relative_4 | 长度 5，DEPENDENCY_CHAIN_TOO_DEEP error | 长度 2，PASS |
| python.library.reachable_functions_support | FAIL，BASE_LIB.COMPLEXITY.MAX_FUNCTIONS error | PASS |

这 8 条是 5 类问题的多种真实输入；保留原期待，没有把当前缺检查改为 expected accept。正常对照包括 Decision route、普通完整契约、绝对导入链、base_lib 目录函数上限及参数上限放宽。源码抽取/正式 quality 的原 13 条两版均符合期待。

新增 8 条差异分属不同性质，不能合称副作用安全问题：

| ID | 基线实际 | 当前实际 | 判断性质与位置 |
| --- | --- | --- | --- |
| python.variant.metadata.category_empty | NODE.METADATA.NODE_INFO_CATEGORY error，exit 1 | PASS，exit 0 | 声明契约差异待核定：`descriptor_parser.py:123` category 为 optional；不能与“实现类旧 metadata 被忽略”混为一谈 |
| python.variant.semantics.value_number | NODE.CONTRACT.CONTRACT_SEMANTICS error | PASS | 真实输出 semantics `[1]` 被 `core/descriptors/models.py:23-27,37-45,90-107` 字符串化，不是 class 权威迁移 |
| python.variant.semantics.input_value_number | NODE.CONTRACT.CONTRACT_SEMANTICS error | PASS | 同一行为发生于真实 required input 的 semantics `[1]`；空字符串和合法字符串邻居均已测 |
| python.variant.signature.public_lambda | NODE.CONTRACT.PUBLIC_CALLABLE error | PASS | `node_interface.py:15,27-30` 只收集 FunctionDef/AsyncFunctionDef，没有覆盖赋值形式 callable；普通公开数据邻居两版允许 |
| python.variant.import.decorator_qualified_static | PASS，exit 0 | NODE.IMPORT.SIDE_EFFECT error，exit 1 | `import_side_effects.py:30-33` 只认可静态 Name；旧 `preflight.py:120-128` 明确允许 builtins.staticmethod |
| python.variant.import.decorator_property | PASS，exit 0 | NODE.IMPORT.SIDE_EFFECT error，exit 1 | 同一 decorator 判断遗漏 property；property 只是 getter 声明，在本案例不会导入执行 getter |
| python.variant.import.try | NODE.PURITY.MODULE_SIDE_EFFECT error，exit 1 | PASS，exit 0 | import visitor 没有 Try 拒绝分支；空 try 不伪装成产生 IO，原语法约定的拒绝能力真实不同 |
| python.variant.import.match | NODE.PURITY.MODULE_SIDE_EFFECT error，exit 1 | PASS，exit 0 | import visitor 没有 Match 拒绝分支；同样为模块控制结构约定差异 |

267 条分类为 preserved（包含上述期待仍失败的案例），7 条为 approved_change，13 条为 baseline_limitation，4 条为 new_feature。分类描述的是场景归属，不是测试通过标签。新增 190 条为 174 preserved、3 approved_change、11 baseline_limitation、2 new_feature。

6 条旧非法 contract CLI 异常运输使用明确 `expected.status=ERROR`、`metrics.transport=uncaught_exception`、非零 exit_code 和 `message_contains=contract_payload`。当前对应实际 `health.status` 也为 ERROR，但带正式 `NODE.INSPECT.LOAD_ERROR` Finding；current variant 显式替换运输与期待，没有伪写 FAIL，也没有将这类已知旧 CLI 失败混成基础设施异常。对应 6 条公开 validator 观察另有旧正式诊断，两条证据分别说明“判断存在”与“CLI 运输不完整”。

父 runner 应调用稳定 API，而不是依赖开发者机器的 `/tmp` 日志或归档路径。每条 observation 保留实际 command、project、entrypoint、JSON payload、codes/severities、位置、指标、marker 与 exit_code；matcher 对 codes 默认作包含判断，可以增加 located_codes/metrics/forbidden_codes。导入 marker 的空值是正式期待，CLI syntax 的退出码 1 与 effects warning 的退出码 0 同样写入指标。

所有 `cli.inspect-node/cli.quality-check/cli.run` 案例在应用 variant 期待后，默认增加退出码 0（应接受）或 1（应拒绝）期待，显式值优先。公开 Python API 以子进程打印正式报告，报告 FAIL 时该观察进程仍可正常 exit 0，不给它附加 CLI 退出码假定。

此次 291 条没有承诺所有规则的任意 AST 变体、插件运行、两个 Target 的注册异常和架构图均完备。源码追踪项已在 closure 表逐项给出具体案例或事实/非活跃边界；Core 通用图/数值全集与 JS 的案例应与本清单并列汇总。测试/库存阶段结束后，是否调整声明契约或修复其他已确认差异由后续任务裁决。
