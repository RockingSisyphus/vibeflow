# 适配修复：案例、接口与验收对应

这份表供维护者定位回归和核对修复范围。案例定义位于 [adaptation_regressions](../../../sandbox/adaptation_regressions/README.md)，稳定 ID 由 [cases.json](../../../sandbox/adaptation_regressions/cases.json) 管理。runner 将缺失、额外、重复 ID 和观察异常记为错误；不匹配会使运行失败。

当前稳定清单为 **207 个案例**：`core_sdk` 57 项、`python_runtime` 30 项、`javascript` 95 项、`structure` 25 项。它包含第一轮 178 项，以及后续补充的 20 项 JS 源码归属对照和 9 项 JS 字面路径对照。当前清单的完整运行结果与全量测试、浏览器、wheel、分发验收由上级 [修复记录](../adaptation-repair-20261005.md) 汇总。

第一次修复后的专项观察为 **178 项匹配、0 个观察错误**，对应当时的源码快照。机器证据见 [after-summary.json](after-summary.json)、[after.json.gz](after.json.gz) 和 [first-fixed-source.json](first-fixed-source.json)。该历史报告的实际分组为 Core/SDK 57、Python 30、JS 66、源码结构 25。

原 178 项的冻结基线来源见 [baseline-source.json](baseline-source.json)。基线与第一次修复后的源码使用相同夹具、相同正确期待，修复前完整对照由 `before-summary.json` 和 `before.json.gz` 保存。`matched=false` 表示实际结果与正确期待不同，观察程序本身失败另计入 `errors`。

后续 29 项的修复前观察使用 `/tmp/vf-adaptation-first-fixed-20261005/src`，即第一次修复后的冻结源码（first-fixed），不是原始基线。20 项归属对照的修复前结果为 14 项匹配、6 项不匹配；9 项路径对照为 0 项匹配。对应现场报告为 [JS 归属补充观察](js-scope-before.json.gz) 和 [JS 路径补充观察](js-path-before.json.gz)。这些差异用于定位第一次修复仍遗漏的行为，不并入原始基线 178 项的差异数量。

## 主题与修复接口

下表的数量按案例主题计数；完整 ID 列表在文末。接口是修复的落点，并不是新公开 ABI。

| 主题 | 案例数 | 修复接口 | 关键验收 |
| --- | ---: | --- | --- |
| A01：声明与绑定身份一致 | 47 | Python [normalize_contributions](../../../src/vibeflow/targets/python/sdk/identity.py)；JS [normalizeDirect](../../../src/vibeflow/targets/javascript/resources/sdk.mjs)；Target 绑定消费规范化后的同一来源 | Python Node／Rule 和 JS Node／Rule／BaseLib：自动、同源元数据、真实别名与延迟来源合法；指向其他实际实现的直接绑定报 `RESOURCE.IMPLEMENTATION.CONFLICT`；checked run 不执行被拒绝的业务 marker；JS 的字面 `%`、`#`、空格路径在自动、同源显式定位、导出别名中均正确识别 |
| A02：Python compiler 单次阶段 | 4 | [PythonCheckSession](../../../src/vibeflow/targets/python/project/check_session.py) 保存阶段产物；[GraphCompiler._refresh_rule_facts](../../../src/vibeflow/targets/python/project/compiler.py)；[PreparedWorkspaceGraph](../../../src/vibeflow/tooling/application/python/project/prepared_graph.py)；[PipelineRuntime](../../../src/vibeflow/targets/python/runtime/engine.py) 消费最终结果 | `created → before → after → dispose → Node Rule → workflow Rule` 各一次；`after` 的合法 `providers` 修改保留；真实运行再产生一次业务事件，数值为 7；before／after 错误仍保留 `GRAPH.COMPILE` 根因并 dispose |
| A03：JS 原生图有限运输 | 7 | [graph_wire](../../../src/vibeflow/targets/javascript/build/graph_wire.py)，compiler 和 Rule 运输共用 | serial／Nodeset／nested／shared／Loop：定义保存一次、子图用引用；factory／before／after／dispose 各一次，manifest 保留两阶段 annotation，真实数值为 6；void 合法，图修改返回值仍拒绝 |
| A04：源码查询与活动范围分开 | 6 | [analyze_node_source_context / publish_python_source_context](../../../src/vibeflow/tooling/application/python/project/declarations.py)；compiler 的 runtime-dispatch 查询只消费返回值 | 补充查询及事实编译不改变 snapshot、session.sources、load states；未调用 B 不导入、不运行；实际 A 绑定后状态为 loaded；所选 import Rule 拒绝时 A 的导入／业务 marker 都不存在 |
| A05：真实源码归属替代目录权限 | 58 | [resource_structure_scopes](../../../src/vibeflow/tooling/project/source_roles.py)、[python_import_scopes](../../../src/vibeflow/targets/python/project/structure_sources.py)、[resource_import_violations](../../../src/vibeflow/core/quality/resource_imports.py) 和双 Target 所有权资料 | Python 25、JS 33：入口／支撑／独立库／声明／生命周期分别判断；登记文件合法，未登记或越权依赖拒绝；共享文件按符号分开，跨 root 来源完整，多 workflow 不合并权限；补充模块初始化、擦除类型、副作用导入、真实调用的方法与构造函数；负例检查目标码、严重度、对象和源码位置 |
| A06：inspect-config 单次准备 | 4 | [inspect_config_payload / _inspect_workspace_graph](../../../src/vibeflow/tooling/application/python/cli/config.py)；workspace inspect 消费同一 prepared.health／graph／compiled | project 和 workspace 各一组合法／非法：environment、prepare、health 各 1；8 个真实调用的 call Rule 执行 8 次；每份实际 Python 源码解析 1 次；有效连边不变；非法库的目标为 `BASE_LIB.SIDE_EFFECT_CALL`，`lib0.py:4:5` |
| A07：inspect-node 使用 workflow 政策 | 16 | [inspect_node_payload](../../../src/vibeflow/tooling/application/python/cli/node.py) 使用实际 config 的 [resolve_effective_policy](../../../src/vibeflow/tooling/application/python/project/effective_policy.py) | 同一入口 validate／inspect-node 成对覆盖：默认 → 同 workflow 目录发现 → 显式 policy → inline；Ruleset 调用参数再覆盖默认参数。28 行／10 行上限得到 `NODE.PURITY.SOURCE_TOO_LARGE`，`leaf.py:1:1`；邻居坏 Node 不扩大所选范围 |
| A08：Record 共享快照与内部摘要 | 31 | [RuleRecord._record_snapshot](../../../src/vibeflow/core/rules/models.py) 使用 memo；[record_inputs_fingerprint / value_fingerprint](../../../src/vibeflow/core/rules/fingerprint.py)；执行和 Python 诊断消费同一内部摘要 | 12 层 tuple／mapping 输入、Record 和 Context 均为 12 个不同对象；混合结构 4 个对象，保持只读及输入隔离；循环拒绝；内容、类型、端口、配置、来源、阶段和调用边界均参与复用判断；正式 provider 2 次、可复用 consumer 1 次，8 层共享输出保留 8 个对象 |
| A09：JS 清理完成后报告错误 | 4 | [JavascriptPluginSession](../../../src/vibeflow/targets/javascript/build/plugin_session.py)、[finish_cleanup](../../../src/vibeflow/targets/javascript/build/cleanup.py)、定义 owner 释放 | normal／dispose／主错误加 dispose／多个插件：所有观测到的本实例 worker 都退出，stdio 与临时资源释放；主 hook 错误保留为正式根因，secondary dispose 写入结构化 details |
| A10：Host 依赖先固定再审查 | 16 | [active_host_ids](../../../src/vibeflow/targets/javascript/build/host_selection.py) 和 [共享 Host 选择](../../../src/vibeflow/tooling/application/javascript/host_selection.py)，审查／预览／绑定／打包消费同一闭包 | 子 Host 支撑文件 500 行合法、501 行由 validate 和 build 拒绝；两个 300 行文件分别合法；`[]` 和未选资源保留现有语义；planned／unknown／cycle 保留原生诊断；shared dependency 只创建、启动、停止一次；真实结果为 6 |
| S01：固定贡献一次收集 | 6 | [Plugin._fixed_contributions](../../../src/vibeflow/targets/python/sdk/plugin.py)、JS [PluginDefinition](../../../src/vibeflow/targets/javascript/sdk/loading.py)、Core [PluginContributions._with_config](../../../src/vibeflow/core/descriptors/contributions.py) | Ruleset 内部 `to_dict()` 投影 0 次、最终 contribution_facts 边界 1 次；资源及 Descriptor 共享，Catalog 和 config 隔离；模式依次为 1／2／1；公开入口仍拒绝 raw entry、错误 Descriptor、错误 origin 和重复 ID，冲突保留双方来源 |
| S02：JS 同次分析会话 | 2 | 私有 [check_scope / DriverScope](../../../src/vibeflow/targets/javascript/build/driver_session.py)、[_check_session](../../../src/vibeflow/targets/javascript/build/rule_session.py)、[AnalysisSession](../../../src/vibeflow/targets/javascript/resources/analysis_program.mjs) | validate 与 quality 各 1 个 Rule session、1 个 analysis driver；相同 Program identity、函数指标 identity 和调用图 identity 的重复构造均为 0。不同检查对象仍分别执行规则判断 |
| S03：移除 raw lifecycle 预审旁路 | 6 | [JavascriptPluginSession](../../../src/vibeflow/targets/javascript/build/plugin_session.py) 负责生命周期；所选资源规则统一由 [Rule session](../../../src/vibeflow/targets/javascript/build/rule_session.py) 执行 | accepted validate／build 的所选 Rule 各 1 次；仅 build 创建 1 次 factory。rejected 两入口 Rule 1 次、factory 0 次；review-rules／inspect-resources 均 Rule 0 次、factory 0 次 |

低层无所属 project 的 `inspect-config` 也收口为一次读取、一次 parse 和一次原生编译；对应 [test_inspect_config_preparation.py](../../../tests/tooling/test_inspect_config_preparation.py) 验证 planned 警告、原生 cycle 和 JSON 错误保留。这三项单测不计入 207 个沙箱 ID。

A07 的政策组合对照属于 project 模式。workspace 模式继续使用自己的政策装配和 inline policy 限制；这轮没有通过 inspect 放宽该限制。规则调用的显式参数仍由 Ruleset 图解析，不能把文件层政策当成另一套权限授权。

JS A05 补充对照由 [js_structure_scope.py](../../../sandbox/adaptation_regressions/js_structure_scope.py) 提供。每种形式都有登记／未登记成对案例，均通过显式 workflow 的正式 `quality-check` 检查：

| 形式 | 登记支撑文件 | 未登记支撑文件 | 保留的归属边界 |
| --- | --- | --- | --- |
| 模块顶层 `void value`、常量初始化 | 合法 | 拒绝 | 模块实际初始化引用计入所选资源的实现范围 |
| 直接类型注解、经类型别名使用 | 合法 | 拒绝 | type-only 擦除不取消源码审核归属 |
| 纯副作用导入 | 合法 | 拒绝 | 未使用具名符号的导入仍是实际源码依赖 |
| 同文件两资源的独立符号 | 合法 | 只拒绝未登记 helper 的 `demo.model` | `audit.right` 不继承另一个符号的导入限制 |
| 对象方法调用、构造函数调用 | 合法 | 拒绝 | 已实际调用的 helper 体纳入初始化引用分析 |
| 未调用的对象方法、未调用的构造函数 | 合法 | 合法 | 不把仅定义的函数体伪造为已发生的初始化引用 |

拒绝对照要求 `QUALITY.STRUCTURE.NODE_UNDECLARED_PROJECT_IMPORT`，并保留 `demo.model` 所属资源和真实导入第 2 行。各 Node 显式选择 `rulesets: []`，该组测试针对项目结构检查，不借其他源码规则错误遮挡目标。

## 计数读法与性能边界

Python 的 `parsing_counts` 观测实际 `ast.parse` 入口及项目源码文件名。A06 的 `call_checks=8` 是公开 call-scoped Rule 的 marker 数量，不是 Node 执行次数。检查与展示不执行业务 Node；A02 的 checked-run 单独验证真实执行。

S02 从 Target 资源副本中的实际 `ts.createProgram` 或 native `api.updateSnapshot` 入口计数，并从 `qualityFunctions`、`qualityCallGraph` 入口记录指标 identity。第一次专项观察使用 native 后端：

| 正式命令 | Rule session | Driver 进程 | Program 构造／不同 identity | 重复 Program | 函数指标／重复 | 调用图／重复 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| validate | 1 | 1 | 8／8 | 0 | 9／0 | 10／0 |
| quality-check | 1 | 1 | 6／6 | 0 | 9／0 | 11／0 |

Program identity 包含文件集合、源码快照、编译选项、包位置和后端信息。不同 identity 可以各自构造一个 Program。这些数字证明相同身份的 Target 构造和指标入口被复用，**没有测量 TypeScript 后端内部 parser 调用次数**，也不表示所有文件只解析一次。Program 数量不是新的公开接口或跨机器性能阈值。

A08 按不同对象身份计数；共享 DAG 与等值树的内容摘要可以相同。native typed records 保留实际类型，并按现有边界不复用 source consumer。正式共享 Record 的 cache／diagnostic `to_dict()` 投影均为 0；最终 JSON 报告仍作普通 JSON 投影，当前两个正式对照各观测到 final 投影 2 次。JSON 不表达共享引用，输出尺寸仍取决于展开后的数据，内部修复不等于端到端输出零成本。

S01 的 0／1 只针对夹具 Ruleset 的 `to_dict()` 调用，不表示所有字段验证函数只执行一次。公开声明入口仍完整校验；复用发生在已经固定的资源定义与本次独立配置之间。

时间对照由 [timings.py](../../../sandbox/adaptation_regressions/timings.py) 保存，每组用新进程、单 worker，默认三次重复并报告中位数。时间用于分析收益，专项 gate 依靠稳定计数和语义结果；本表不将尚未完成的时间对照写成性能结论。

## 夹具与期待修正记录

各组对照使用同一夹具和正确期待，案例 ID 保留；原 178 项使用原始冻结基线，补充 29 项使用 first-fixed。下列修改纠正入口、观察方式或无关的原生结构错误；没有把已证实缺陷改成通过期待。

| 夹具／观察 | 修正原因及保留的判断 |
| --- | --- |
| A01 显式来源 | JS 早期调查的 `plugin.ts` 不指向真实 `src/plugin.ts`；改用真实绝对路径，避免定位失败遮挡身份冲突。同源和 alias 仍必须合法，另一文件／符号仍必须报冲突 |
| A01 字面路径补充 | 使用真实目录 `literal%23#space name`，分别检查 Node、Rule、BaseLib 的自动定位、同源显式定位和同文件导出别名。路径按文件系统字面值处理，不能把 `#` 或 `%23` 解释成 URL fragment 或解码后的另一文件；该组修复前观察来自 first-fixed |
| A01 实际运行 | marker 只清理本夹具自己的记录；business.log 从本次 run_dir 读取，避免历史运行输出污染。仍断言被拒绝实现没有实际执行 |
| A02 数值执行 | Process 单独存在不是可运行的原生入口；增加真实 Start／End 和串行连边，再断言数值 7 及 after 产物，冻结基线也使用这份结构 |
| A05 同文件两 Node | 两个 Node 原先提供同一 `result` 会先命中原生重复 producer；使用 `result`／`result2` 保留两符号共享导入的目标判断 |
| A06 合法状态 | 复用的真实性能夹具具有既有 duplicate-logic 警告，因此期待为 CONCERNS，错误列表仍为空；低层 planned 对照明确保留两个 `GRAPH.PLANNED.NODE` 警告 |
| A08 Record-only workflow | 业务 Node 没有数值输出契约；删除无关 workflow 输出要求，使正式 provider／consumer 规则本身成为目标。循环、合法 error finding 保留 records、调用关联仍分别断言 |
| A08 投影观测 | Python 3.13 的 comprehension 可以内联，计数识别对应 frame，避免漏记 cache／diagnostic `record.to_dict()`；对象数量按 distinct identity 计算 |
| JS shared Nodeset | 父级两个同名输出造成原生重复 producer；共享子定义的两次调用使用空输出，由末尾普通 Node 输出数值。仍验证有限定义表、两阶段 annotation 和实际结果 6 |
| JS review-rules | 成功结果是规则图而没有 status；检查退出码、图内容及未调用 Rule／factory，不虚构 PASS 字段 |
| JS 目标诊断 | Node→Node 使用实际 `VF_IMPORT_NODE_TO_NODE`；Host planned dependency、unknown、cycle 使用各自原生诊断，不以通用错误替代 |
| JS planned-only Host | 不产生可执行 Host 时，产物提供 runWorkflow；观测程序不要求不存在的 createWorkflowHost，仍检查数值和零 Host 工厂事件 |
| JS quality 范围 | 显式传入真实 workflow config，使 SDK 资源实际装配；否则测到的是没有选中插件的另一个范围 |
| JS cleanup owner | 正式子进程会在退出时释放定义 owner。内存观察持有 Session 引用时显式执行同一 owner release，再读取存活进程和句柄；finally 只清理本探针创建的 PID |
| JS 未选插件 | 旧测试 helper 自动把 Host 写进已启用资源，实际已经选中。改为独立未选 SDK 插件及 throw marker；仍保留项目源码指标包含该文件、资源审核不加载该插件的原要求 |
| S02 测量副本 | Target instrumentation 放在工作流源码范围外，避免把计数程序当用户源码审查；观测仍来自真实 Program／指标构造入口，不用请求数代替 |

## 稳定案例 ID

以下列表对应当前 `cases.json`，便于从压缩机器报告中检索，不能以删去 ID 处理不匹配。

### A01（47 项）

```text
A01.node.auto_actual
A01.node.auto_actual.checked_run
A01.node.delayed
A01.node.delayed.checked_run
A01.node.metadata_preserved
A01.node.module_alias
A01.node.other_file
A01.node.other_file.checked_run
A01.node.relative_alias
A01.node.same_file_other_symbol
A01.node.same_source_metadata
A01.node.same_source_metadata.checked_run
A01.node.symbol_alias
A01.rule.auto
A01.rule.builtin_alias
A01.rule.delayed
A01.rule.handler_with_direct
A01.rule.handler_with_source
A01.rule.other_file
A01.rule.same_source
js.A01.base_lib.alias
js.A01.base_lib.auto
js.A01.base_lib.delayed
js.A01.base_lib.other_file
js.A01.base_lib.other_symbol
js.A01.base_lib.path_alias
js.A01.base_lib.path_auto
js.A01.base_lib.path_same_source
js.A01.base_lib.same_source
js.A01.node.alias
js.A01.node.auto
js.A01.node.delayed
js.A01.node.other_file
js.A01.node.other_symbol
js.A01.node.path_alias
js.A01.node.path_auto
js.A01.node.path_same_source
js.A01.node.same_source
js.A01.rule.alias
js.A01.rule.auto
js.A01.rule.delayed
js.A01.rule.other_file
js.A01.rule.other_symbol
js.A01.rule.path_alias
js.A01.rule.path_auto
js.A01.rule.path_same_source
js.A01.rule.same_source
```

### A02（4 项）

```text
A02.python.compiler.after-failure
A02.python.compiler.before-failure
A02.python.compiler.checked-run
A02.python.compiler.success
```

### A03（7 项）

```text
js.A03.compiler.loop
js.A03.compiler.mutation
js.A03.compiler.nested
js.A03.compiler.nodeset
js.A03.compiler.serial
js.A03.compiler.shared
js.A03.compiler.void
```

### A04（6 项）

```text
A04.python.scope.control-run
A04.python.scope.pure-query
A04.python.scope.unused-refused-run
A04.python.scope.unused-refused-validate
A04.python.scope.unused-run
A04.python.scope.unused-validate
```

### A05（58 项）

```text
A05.python.cross-root-allowed.quality-check
A05.python.cross-root-allowed.validate
A05.python.cross-root-denied.quality-check
A05.python.cross-root-denied.validate
A05.python.declaration-contribution.quality-check
A05.python.declaration-contribution.validate
A05.python.library-support.quality-check
A05.python.library-support.validate
A05.python.library-unregistered.quality-check
A05.python.library-unregistered.validate
A05.python.lifecycle-contribution-denied.quality-check
A05.python.lifecycle-library-allowed.quality-check
A05.python.node-support-conventional.quality-check
A05.python.node-support-conventional.validate
A05.python.node-support.quality-check
A05.python.node-support.validate
A05.python.node-unregistered.quality-check
A05.python.node-unregistered.validate
A05.python.shared-denied.quality-check
A05.python.shared-denied.validate
A05.python.shared-symbol-isolated.quality-check
A05.python.shared-symbol-isolated.validate
A05.python.workflow-isolation-allowed.validate
A05.python.workflow-isolation-denied.validate
A05.python.workflow-isolation-mixed.quality-check
js.A05.scope.alias_type.registered
js.A05.scope.alias_type.unregistered
js.A05.scope.constructor_called.registered
js.A05.scope.constructor_called.unregistered
js.A05.scope.constructor_unused.registered
js.A05.scope.constructor_unused.unregistered
js.A05.scope.direct_type.registered
js.A05.scope.direct_type.unregistered
js.A05.scope.method_called.registered
js.A05.scope.method_called.unregistered
js.A05.scope.method_unused.registered
js.A05.scope.method_unused.unregistered
js.A05.scope.side_effect.registered
js.A05.scope.side_effect.unregistered
js.A05.scope.symbol_isolation.registered
js.A05.scope.symbol_isolation.unregistered
js.A05.scope.top_const.registered
js.A05.scope.top_const.unregistered
js.A05.scope.top_void.registered
js.A05.scope.top_void.unregistered
js.A05.structure.base_support.registered
js.A05.structure.base_support.unregistered
js.A05.structure.base_upward
js.A05.structure.declaration.registered
js.A05.structure.declaration_lifecycle_use
js.A05.structure.foreign_node
js.A05.structure.host_support.registered
js.A05.structure.host_support.unregistered
js.A05.structure.node_support.registered
js.A05.structure.node_support.unregistered
js.A05.structure.plugin_support.registered
js.A05.structure.plugin_support.unregistered
js.A05.structure.type_support.registered
```

### A06（4 项）

```text
A06.python.inspect-config.project-invalid
A06.python.inspect-config.project-valid
A06.python.inspect-config.workspace-invalid
A06.python.inspect-config.workspace-valid
```

### A07（16 项）

```text
A07.python.policy.discovered-denied.inspect-node
A07.python.policy.discovered-denied.validate
A07.python.policy.explicit-wins.inspect-node
A07.python.policy.explicit-wins.validate
A07.python.policy.inline-allowed.inspect-node
A07.python.policy.inline-allowed.validate
A07.python.policy.inline-denied.inspect-node
A07.python.policy.inline-denied.validate
A07.python.policy.inline-wins.inspect-node
A07.python.policy.inline-wins.validate
A07.python.policy.nested-discovery.inspect-node
A07.python.policy.nested-discovery.validate
A07.python.policy.rule-params-win.inspect-node
A07.python.policy.rule-params-win.validate
A07.python.policy.unrelated-node.inspect-node
A07.python.policy.unrelated-node.validate
```

### A08（31 项）

```text
A08.cache.different_leaf
A08.cache.equal_tree
A08.cache.integer_boolean
A08.cache.integer_float
A08.cache.mapping_order
A08.cache.native_types
A08.cache.native_vs_json
A08.cache.same_dag
A08.cache.set_vs_sequence
A08.cache.signed_zero
A08.cache_identity.call_scope
A08.cache_identity.no_source_identity
A08.cache_identity.params
A08.cache_identity.phase
A08.cache_identity.port
A08.cache_identity.rule_id
A08.cache_identity.source
A08.cache_identity.target
A08.cache_identity.type_id
A08.formal.cycle
A08.formal.provider_error
A08.formal.shared
A08.snapshot.cycle_dataclass
A08.snapshot.cycle_list
A08.snapshot.cycle_mapping
A08.snapshot.cycle_tuple_list
A08.snapshot.json_boundary
A08.snapshot.mapping
A08.snapshot.mixed
A08.snapshot.native
A08.snapshot.tuple
```

### A09（4 项）

```text
js.A09.cleanup.dispose
js.A09.cleanup.multiple
js.A09.cleanup.normal
js.A09.cleanup.root_and_dispose
```

### A10（16 项）

```text
js.A10.health.child500.build
js.A10.health.child500.validate
js.A10.health.child501.build
js.A10.health.child501.validate
js.A10.health.explicit501.build
js.A10.health.two300.build
js.A10.health.unconstrained501.build
js.A10.health.unselected501.validate
js.A10.preview.dependency_rules
js.A10.state.cycle
js.A10.state.disabled_dependency
js.A10.state.disabled_planned_dependency
js.A10.state.planned_dependency
js.A10.state.planned_only
js.A10.state.shared_dependency
js.A10.state.unknown_dependency
```

### S01（6 项）

```text
S01.fixed_contribution
S01.public_validation.duplicate
S01.public_validation.raw_entry
S01.public_validation.wrong_descriptor
S01.public_validation.wrong_origin
S01.workflow_isolation
```

### S02（2 项）

```text
js.S02.analysis.one_check_session
js.S02.analysis.quality_check_session
```

### S03（6 项）

```text
js.S03.formal.accepted.build
js.S03.formal.accepted.validate
js.S03.formal.preview.inspect-resources
js.S03.formal.preview.review-rules
js.S03.formal.rejected.build
js.S03.formal.rejected.validate
```
