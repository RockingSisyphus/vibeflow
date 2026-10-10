# 沙盒登记任务清单（整合后）

本文保留当时的任务数量与顺序；当前入口和登记情况见 [沙盒导航](../../../../sandbox/README.md)。

核对日期：2026-10-09。通过 AST 静态读取当前两个 integration runner 的登记列表，并与本轮完整运行报告逐项核对名称与顺序；本次盘点没有重新执行测试。

计数口径：一次完整 integration runner 最外层报告的一项结果算一个任务。Python 124 项，JavaScript 53 项，合计 **177 项**。数学独立入口已经包含其中，不再另加；一个任务中的配置、循环迭代、源码修改阶段、Node/browser 对照或内嵌 pytest 不展开累计。

这个数字不包括 tests 中独立运行的 pytest，也不等于整个 sandbox 目录的项目数量。JS minimal/run_e2e.py 等独立入口、领域/外部规则/多文件/运行观察项目仍存在，另由专门入口或 pytest 使用；它们没有与上述两个 runner 共用的统一任务计数，不能按目录数直接相加。

## 分类汇总

| 分类 | Python | JavaScript | 合计 |
| --- | ---: | ---: | ---: |
| 数学综合场景 | 4 | 3 | 7 |
| 工作流、执行模型与调度 | 44 | 6 | 50 |
| 资源与架构审查 | 3 | 1 | 4 |
| 源码规则、异常与放行边界 | 67 | 23 | 90 |
| 全局状态、能力与宿主生命周期 | 4 | 3 | 7 |
| 构建、ABI 与交付配置 | 0 | 10 | 10 |
| 浏览器运行 | 0 | 3 | 3 |
| TypeScript 类型 | 0 | 3 | 3 |
| 质量与产物门禁 | 2 | 1 | 3 |
| **总计** | **124** | **53** | **177** |

## 全部任务名称

保持 runner 的原始登记顺序与名称。`invalid:` 是历史分组标签，不代表其中每项都必须报 error：其中有 6 项静态审查的明确放行对照，以及 warning 检查；名称未改以保持报告可追溯。`reject:` 则要求对应非法 JS 项目被拒绝，若成功构建通常反而失败。

六项明确放行对照：ResourceFieldNode、EvalNode、DynamicImportNode、DynamicOutputKeyNode、MissingOutputNode、ExtraOutputNode。这些放行仅针对 Node 静态审查，不表示运行时可以违反输出 Contract。其他案例的具体通过条件以原驱动断言为准。

### Python：124 项

登记入口：[run_all.py](../../../../sandbox/python/integration/run_all.py)。

| 序号 | 分类 | 任务原名 | 备注 |
| ---: | --- | --- | --- |
| 1 | 质量与产物门禁 | `quality:cross_root_workspace` |  |
| 2 | 数学综合场景 | `comprehensive_math` |  |
| 3 | 资源与架构审查 | `review:registered_expanded` |  |
| 4 | 资源与架构审查 | `review:external_nodeset_dedup_visual` |  |
| 5 | 资源与架构审查 | `review:unregistered_fail_closed` |  |
| 6 | 数学综合场景 | `cli_addition` |  |
| 7 | 数学综合场景 | `object_addition` |  |
| 8 | 数学综合场景 | `plugin_addition` |  |
| 9 | 工作流、执行模型与调度 | `execution:python-sync-vs-result-key-thread` |  |
| 10 | 工作流、执行模型与调度 | `execution:python-thread-pool-boundaries` |  |
| 11 | 源码规则、异常与放行边界 | `source-preflight:imported-declarative-contract-helper` |  |
| 12 | 源码规则、异常与放行边界 | `source-preflight:effectful-imported-helper-rejected` |  |
| 13 | 全局状态、能力与宿主生命周期 | `global-state:forbidden-effect-audit` |  |
| 14 | 全局状态、能力与宿主生命周期 | `global-state:protected-async-compile` |  |
| 15 | 全局状态、能力与宿主生命周期 | `global-state:unlocked-overlap` |  |
| 16 | 全局状态、能力与宿主生命周期 | `global-state:failure-releases-lock` |  |
| 17 | 工作流、执行模型与调度 | `valid:free_nodes` |  |
| 18 | 工作流、执行模型与调度 | `valid:io_data_store` |  |
| 19 | 工作流、执行模型与调度 | `valid:comprehensive_flowchart` |  |
| 20 | 工作流、执行模型与调度 | `valid:global_state_execution_lock` |  |
| 21 | 工作流、执行模型与调度 | `valid:ordinary_callback_warning` |  |
| 22 | 工作流、执行模型与调度 | `valid:training_object_flow` |  |
| 23 | 工作流、执行模型与调度 | `valid:training_non_json_metrics` |  |
| 24 | 工作流、执行模型与调度 | `valid:loop_while_nodeset_retry` |  |
| 25 | 工作流、执行模型与调度 | `valid:loop_while_nodeset_retry_compiled` |  |
| 26 | 工作流、执行模型与调度 | `valid:loop_while_inside_nodeset` |  |
| 27 | 工作流、执行模型与调度 | `valid:loop_nested_outer_after_inner_when_accumulate` |  |
| 28 | 工作流、执行模型与调度 | `valid:loop_nested_outer_after_inner_when_accumulate_block` |  |
| 29 | 工作流、执行模型与调度 | `valid:loop_nested_outer_when_inner_after_accumulate` |  |
| 30 | 工作流、执行模型与调度 | `valid:loop_nested_outer_when_inner_after_accumulate_compiled` |  |
| 31 | 工作流、执行模型与调度 | `valid:runtime_boundary_trace` |  |
| 32 | 工作流、执行模型与调度 | `valid:runtime_trace_off` |  |
| 33 | 工作流、执行模型与调度 | `valid:runtime_node_hooks_off` |  |
| 34 | 工作流、执行模型与调度 | `valid:compiled_trace_full` |  |
| 35 | 工作流、执行模型与调度 | `valid:compiled_with_node_hooks` |  |
| 36 | 工作流、执行模型与调度 | `valid:semantic_linear_arithmetic` |  |
| 37 | 工作流、执行模型与调度 | `valid:compiled_semantic_linear_arithmetic` |  |
| 38 | 工作流、执行模型与调度 | `valid:compiled_full_semantic_linear_arithmetic` |  |
| 39 | 工作流、执行模型与调度 | `valid:semantic_decision_branch_left` |  |
| 40 | 工作流、执行模型与调度 | `valid:semantic_decision_branch_right` |  |
| 41 | 工作流、执行模型与调度 | `valid:compiled_semantic_decision_branch_left` |  |
| 42 | 工作流、执行模型与调度 | `valid:compiled_full_semantic_decision_branch_left` |  |
| 43 | 工作流、执行模型与调度 | `valid:compiled_semantic_decision_branch_right` |  |
| 44 | 工作流、执行模型与调度 | `valid:config_resources_nodeset_arithmetic` |  |
| 45 | 工作流、执行模型与调度 | `valid:planned_python_stub_arithmetic` |  |
| 46 | 工作流、执行模型与调度 | `valid:compiled_semantic_nodeset_arithmetic` |  |
| 47 | 工作流、执行模型与调度 | `valid:block_linear_training` |  |
| 48 | 工作流、执行模型与调度 | `valid:compiled_linear_training` |  |
| 49 | 工作流、执行模型与调度 | `valid:compiled_decision_branch_exit` |  |
| 50 | 工作流、执行模型与调度 | `valid:mainline_data_bypass` |  |
| 51 | 工作流、执行模型与调度 | `valid:async_result_key_join` |  |
| 52 | 工作流、执行模型与调度 | `valid:semantic_async_result_key_unconsumed` |  |
| 53 | 工作流、执行模型与调度 | `valid:compiled_fallback_mixed_graph` |  |
| 54 | 工作流、执行模型与调度 | `valid:async_nodeset_result_key_join` |  |
| 55 | 工作流、执行模型与调度 | `valid:async_detached_metrics` |  |
| 56 | 工作流、执行模型与调度 | `valid:mainline_async_nodeset_side_task` |  |
| 57 | 工作流、执行模型与调度 | `valid:safe_or_join_mutually_exclusive_left` |  |
| 58 | 工作流、执行模型与调度 | `valid:safe_or_join_mutually_exclusive_right` |  |
| 59 | 源码规则、异常与放行边界 | `invalid:inspect_node:MissingInfoNode` |  |
| 60 | 源码规则、异常与放行边界 | `invalid:inspect_node:InfoWrongTypeNode` |  |
| 61 | 源码规则、异常与放行边界 | `invalid:inspect_node:EmptyTypeKeyNode` |  |
| 62 | 源码规则、异常与放行边界 | `invalid:inspect_node:MissingContractNode` |  |
| 63 | 源码规则、异常与放行边界 | `invalid:inspect_node:DuplicateKeysNode` |  |
| 64 | 源码规则、异常与放行边界 | `invalid:inspect_node:MissingSemanticsNode` |  |
| 65 | 源码规则、异常与放行边界 | `invalid:inspect_node:MissingRunPureNode` |  |
| 66 | 源码规则、异常与放行边界 | `invalid:inspect_node:ContextRunNode` |  |
| 67 | 源码规则、异常与放行边界 | `invalid:inspect_node:TooManyParamsNode` |  |
| 68 | 源码规则、异常与放行边界 | `invalid:inspect_node:VarArgsNode` |  |
| 69 | 源码规则、异常与放行边界 | `invalid:inspect_node:PublicHelperNode` |  |
| 70 | 源码规则、异常与放行边界 | `invalid:inspect_node:InitWithClientNode` |  |
| 71 | 源码规则、异常与放行边界 | `invalid:inspect_node:ResourceFieldNode` | 静态阶段放行对照 |
| 72 | 源码规则、异常与放行边界 | `invalid:inspect_node:AsyncRunPureNode` |  |
| 73 | 源码规则、异常与放行边界 | `invalid:inspect_node:GeneratorRunPureNode` |  |
| 74 | 源码规则、异常与放行边界 | `invalid:inspect_node:OpenFileNode` |  |
| 75 | 源码规则、异常与放行边界 | `invalid:inspect_node:PathReadTextNode` |  |
| 76 | 源码规则、异常与放行边界 | `invalid:inspect_node:OsGetenvNode` |  |
| 77 | 源码规则、异常与放行边界 | `invalid:inspect_node:SubprocessNode` |  |
| 78 | 源码规则、异常与放行边界 | `invalid:inspect_node:SocketNode` |  |
| 79 | 源码规则、异常与放行边界 | `invalid:inspect_node:RequestsNode` |  |
| 80 | 源码规则、异常与放行边界 | `invalid:inspect_node:SqliteNode` |  |
| 81 | 源码规则、异常与放行边界 | `invalid:inspect_node:EvalNode` | 静态阶段放行对照 |
| 82 | 源码规则、异常与放行边界 | `invalid:inspect_node:DynamicImportNode` | 静态阶段放行对照 |
| 83 | 源码规则、异常与放行边界 | `invalid:inspect_node:NodeImportNode` |  |
| 84 | 源码规则、异常与放行边界 | `invalid:inspect_node:DirectNodeCallNode` |  |
| 85 | 源码规则、异常与放行边界 | `invalid:inspect_node:NodeInternalReadNode` |  |
| 86 | 源码规则、异常与放行边界 | `invalid:inspect_node:DynamicOutputKeyNode` | 静态阶段放行对照 |
| 87 | 源码规则、异常与放行边界 | `invalid:inspect_node:MissingOutputNode` | 静态阶段放行对照 |
| 88 | 源码规则、异常与放行边界 | `invalid:inspect_node:ExtraOutputNode` | 静态阶段放行对照 |
| 89 | 源码规则、异常与放行边界 | `invalid:inspect_node:MutateInputsNode` |  |
| 90 | 源码规则、异常与放行边界 | `invalid:inspect_node:MutateNestedInputNode` |  |
| 91 | 源码规则、异常与放行边界 | `invalid:inspect_node:GlobalStateNode` |  |
| 92 | 源码规则、异常与放行边界 | `invalid:inspect_node:SetAttrNode` |  |
| 93 | 源码规则、异常与放行边界 | `invalid:inspect_node:MonkeyPatchNode` |  |
| 94 | 源码规则、异常与放行边界 | `invalid:inspect_node:LongSourceNode` |  |
| 95 | 源码规则、异常与放行边界 | `invalid:inspect_node:WarnCallChainNode` |  |
| 96 | 源码规则、异常与放行边界 | `invalid:inspect_node:DeepCallChainNode` |  |
| 97 | 源码规则、异常与放行边界 | `invalid:inspect_node:RecursiveNode` |  |
| 98 | 源码规则、异常与放行边界 | `invalid:inspect_node:IndirectRecursiveNode` |  |
| 99 | 源码规则、异常与放行边界 | `invalid:health_node:DeepBaseLibNode` |  |
| 100 | 源码规则、异常与放行边界 | `invalid:base_lib:BASE_LIB.SIDE_EFFECT_CALL` |  |
| 101 | 源码规则、异常与放行边界 | `invalid:base_lib:BASE_LIB.GLOBAL_STATE` |  |
| 102 | 源码规则、异常与放行边界 | `invalid:base_lib:VF_IMPORT_LAYER` |  |
| 103 | 源码规则、异常与放行边界 | `invalid:base_lib:BASE_LIB.BANNED_IMPORT` |  |
| 104 | 源码规则、异常与放行边界 | `invalid:base_lib_chain` |  |
| 105 | 源码规则、异常与放行边界 | `invalid:config:fail_schema_bad_edge.jsonc` |  |
| 106 | 源码规则、异常与放行边界 | `invalid:config:fail_async_result_key_missing.jsonc` |  |
| 107 | 源码规则、异常与放行边界 | `invalid:run:fail_unknown_node.jsonc` |  |
| 108 | 源码规则、异常与放行边界 | `invalid:config:fail_removed_loop_registration.jsonc` |  |
| 109 | 源码规则、异常与放行边界 | `invalid:run:fail_nodeset_key_leak.jsonc` |  |
| 110 | 源码规则、异常与放行边界 | `invalid:run:fail_nodeset_recursion.jsonc` |  |
| 111 | 源码规则、异常与放行边界 | `invalid:config:fail_removed_boundary.jsonc` |  |
| 112 | 源码规则、异常与放行边界 | `invalid:run:fail_decision_cycle_forbidden.jsonc` |  |
| 113 | 源码规则、异常与放行边界 | `invalid:run:fail_planned_architecture_run.jsonc` |  |
| 114 | 源码规则、异常与放行边界 | `invalid:run:fail_planned_transparent_allow_run.jsonc` |  |
| 115 | 源码规则、异常与放行边界 | `invalid:config:fail_plugin_load.jsonc` |  |
| 116 | 源码规则、异常与放行边界 | `invalid:run:fail_rule_missing_record.jsonc` |  |
| 117 | 源码规则、异常与放行边界 | `invalid:run:fail_rule_execution.jsonc` |  |
| 118 | 源码规则、异常与放行边界 | `invalid:config:fail_rule_bad_shape.jsonc` |  |
| 119 | 源码规则、异常与放行边界 | `invalid:runtime_run:fail_loop_max_iterations.jsonc` |  |
| 120 | 源码规则、异常与放行边界 | `invalid:concerns:concern_mainline_unjoined_sync_fanout.jsonc` |  |
| 121 | 源码规则、异常与放行边界 | `invalid:run:fail_mainline_decision_branch_dead_end.jsonc` |  |
| 122 | 源码规则、异常与放行边界 | `invalid:run:fail_safe_or_join_ambiguous_unconditional.jsonc` |  |
| 123 | 源码规则、异常与放行边界 | `invalid:run:fail_safe_or_join_multiple_exactly_one.jsonc` |  |
| 124 | 质量与产物门禁 | `audit:published_diagrams_health_gated` |  |

### JavaScript：53 项

登记入口：[run_all.py](../../../../sandbox/javascript/integration/run_all.py)。

| 序号 | 分类 | 任务原名 | 备注 |
| ---: | --- | --- | --- |
| 1 | 数学综合场景 | `math:plugin-addition` |  |
| 2 | 数学综合场景 | `math:async-addition` |  |
| 3 | 数学综合场景 | `math:comprehensive-plugin-rules` |  |
| 4 | 资源与架构审查 | `review:javascript-expanded-parity` |  |
| 5 | 构建、ABI 与交付配置 | `profile:esm-module` |  |
| 6 | 构建、ABI 与交付配置 | `profile:single-esm` |  |
| 7 | 构建、ABI 与交付配置 | `profile:web-app` |  |
| 8 | 全局状态、能力与宿主生命周期 | `host-extension:lifecycle-and-capability` |  |
| 9 | 工作流、执行模型与调度 | `execution:sync-async-taskplan-metadata` |  |
| 10 | 构建、ABI 与交付配置 | `abi:import-no-side-effect` |  |
| 11 | 构建、ABI 与交付配置 | `abi:input-and-trace-errors` |  |
| 12 | 工作流、执行模型与调度 | `routes:schedule-transfer-split` |  |
| 13 | 工作流、执行模型与调度 | `nodeset:nested-qualified-override` |  |
| 14 | 工作流、执行模型与调度 | `nodeset:nested-deferred-detached` |  |
| 15 | 工作流、执行模型与调度 | `loop:bounded-carry` |  |
| 16 | 工作流、执行模型与调度 | `loop:max-iterations-error` |  |
| 17 | 全局状态、能力与宿主生命周期 | `capability:missing-and-cancel` |  |
| 18 | 全局状态、能力与宿主生命周期 | `async:detached-cleanup-and-timeout` |  |
| 19 | 源码规则、异常与放行边界 | `error:node-cause-and-path` |  |
| 20 | 源码规则、异常与放行边界 | `error:output-schema-and-path` |  |
| 21 | 构建、ABI 与交付配置 | `build:source-map-origins` |  |
| 22 | 构建、ABI 与交付配置 | `build:single-esm-no-chunks` |  |
| 23 | 构建、ABI 与交付配置 | `build:deterministic` |  |
| 24 | 构建、ABI 与交付配置 | `build:atomic-failure-preserves-output` |  |
| 25 | 浏览器运行 | `browser:no-auto-start` |  |
| 26 | 浏览器运行 | `browser:permanent-host-web-app` |  |
| 27 | 浏览器运行 | `browser:permanent-host-esm-module` |  |
| 28 | TypeScript 类型 | `types:strict-consumer` |  |
| 29 | TypeScript 类型 | `types:optional-input-consumer` |  |
| 30 | TypeScript 类型 | `types:capability-consumer` |  |
| 31 | 源码规则、异常与放行边界 | `reject:node_builtin_browser` |  |
| 32 | 源码规则、异常与放行边界 | `reject:direct_node_import` |  |
| 33 | 源码规则、异常与放行边界 | `reject:undeclared_base_lib` |  |
| 34 | 源码规则、异常与放行边界 | `reject:dynamic_import` |  |
| 35 | 源码规则、异常与放行边界 | `reject:runtime_import` |  |
| 36 | 源码规则、异常与放行边界 | `reject:immediate_async` |  |
| 37 | 源码规则、异常与放行边界 | `reject:suspend_sync` |  |
| 38 | 源码规则、异常与放行边界 | `reject:unowned_promise` |  |
| 39 | 源码规则、异常与放行边界 | `reject:suspend_in_sync` |  |
| 40 | 源码规则、异常与放行边界 | `reject:task_in_sync` |  |
| 41 | 源码规则、异常与放行边界 | `reject:barrel_import` |  |
| 42 | 源码规则、异常与放行边界 | `reject:alias_import` |  |
| 43 | 源码规则、异常与放行边界 | `reject:symlink_import` |  |
| 44 | 源码规则、异常与放行边界 | `reject:base_lib_reverse` |  |
| 45 | 源码规则、异常与放行边界 | `reject:undeclared_external` |  |
| 46 | 源码规则、异常与放行边界 | `reject:package_root_escape` |  |
| 47 | 源码规则、异常与放行边界 | `reject:indirect_node_builtin` |  |
| 48 | 源码规则、异常与放行边界 | `reject:module_promise` |  |
| 49 | 源码规则、异常与放行边界 | `reject:discarded_promise` |  |
| 50 | 源码规则、异常与放行边界 | `reject:long_lived_listener` |  |
| 51 | 源码规则、异常与放行边界 | `reject:global_state` |  |
| 52 | 构建、ABI 与交付配置 | `run:dynamic-code` |  |
| 53 | 质量与产物门禁 | `quality:shared-source-rules` |  |
