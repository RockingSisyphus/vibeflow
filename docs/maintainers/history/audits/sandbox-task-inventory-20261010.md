# 沙盒登记任务清单（分段数学整合后）

本文保留当时的任务数量与顺序；当前入口和登记情况见 [沙盒导航](../../../../sandbox/README.md)。

核对日期：2026-10-10。在 10 月 9 日清单基础上逐项移除 11 个 Python 任务、加入 piecewise_math；Python 名称与顺序逐项核对本轮 114/114 通过的完整报告，JS 登记本轮没有修改、没有重跑。旧清单保留历史快照。完整批次结果及逐项对应见 [整合归档](piecewise-math-20261010.md)。

计数口径：两个 integration runner 的最外层报告任务；Python **114**，JavaScript **53**，合计 **167**。内部观察、pytest 和其他独立沙盒不另外累计。

| 分类 | Python | JavaScript | 合计 |
| --- | ---: | ---: | ---: |
| 数学综合场景 | 5 | 3 | 8 |
| 工作流、执行模型与调度 | 33 | 6 | 39 |
| 资源与架构审查 | 3 | 1 | 4 |
| 源码规则、异常与放行边界 | 67 | 23 | 90 |
| 全局状态、能力与宿主生命周期 | 4 | 3 | 7 |
| 构建、ABI 与交付配置 | 0 | 10 | 10 |
| 浏览器运行 | 0 | 3 | 3 |
| TypeScript 类型 | 0 | 3 | 3 |
| 质量与产物门禁 | 2 | 1 | 3 |
| **总计** | **114** | **53** | **167** |

`invalid:` 包含历史放行/warning 对照，名称不等于应当报 error；详细通过判定以原驱动为准。

## python：114 项

| 序号 | 分类 | 任务原名 |
| ---: | --- | --- |
| 1 | 质量与产物门禁 | `quality:cross_root_workspace` |
| 2 | 数学综合场景 | `comprehensive_math` |
| 3 | 资源与架构审查 | `review:registered_expanded` |
| 4 | 资源与架构审查 | `review:external_nodeset_dedup_visual` |
| 5 | 资源与架构审查 | `review:unregistered_fail_closed` |
| 6 | 数学综合场景 | `cli_addition` |
| 7 | 数学综合场景 | `object_addition` |
| 8 | 数学综合场景 | `plugin_addition` |
| 9 | 数学综合场景 | `piecewise_math` |
| 10 | 工作流、执行模型与调度 | `execution:python-sync-vs-result-key-thread` |
| 11 | 工作流、执行模型与调度 | `execution:python-thread-pool-boundaries` |
| 12 | 源码规则、异常与放行边界 | `source-preflight:imported-declarative-contract-helper` |
| 13 | 源码规则、异常与放行边界 | `source-preflight:effectful-imported-helper-rejected` |
| 14 | 全局状态、能力与宿主生命周期 | `global-state:forbidden-effect-audit` |
| 15 | 全局状态、能力与宿主生命周期 | `global-state:protected-async-compile` |
| 16 | 全局状态、能力与宿主生命周期 | `global-state:unlocked-overlap` |
| 17 | 全局状态、能力与宿主生命周期 | `global-state:failure-releases-lock` |
| 18 | 工作流、执行模型与调度 | `valid:free_nodes` |
| 19 | 工作流、执行模型与调度 | `valid:io_data_store` |
| 20 | 工作流、执行模型与调度 | `valid:comprehensive_flowchart` |
| 21 | 工作流、执行模型与调度 | `valid:global_state_execution_lock` |
| 22 | 工作流、执行模型与调度 | `valid:ordinary_callback_warning` |
| 23 | 工作流、执行模型与调度 | `valid:training_object_flow` |
| 24 | 工作流、执行模型与调度 | `valid:training_non_json_metrics` |
| 25 | 工作流、执行模型与调度 | `valid:loop_while_nodeset_retry` |
| 26 | 工作流、执行模型与调度 | `valid:loop_while_nodeset_retry_compiled` |
| 27 | 工作流、执行模型与调度 | `valid:loop_while_inside_nodeset` |
| 28 | 工作流、执行模型与调度 | `valid:loop_nested_outer_after_inner_when_accumulate` |
| 29 | 工作流、执行模型与调度 | `valid:loop_nested_outer_after_inner_when_accumulate_block` |
| 30 | 工作流、执行模型与调度 | `valid:loop_nested_outer_when_inner_after_accumulate` |
| 31 | 工作流、执行模型与调度 | `valid:loop_nested_outer_when_inner_after_accumulate_compiled` |
| 32 | 工作流、执行模型与调度 | `valid:runtime_boundary_trace` |
| 33 | 工作流、执行模型与调度 | `valid:runtime_trace_off` |
| 34 | 工作流、执行模型与调度 | `valid:runtime_node_hooks_off` |
| 35 | 工作流、执行模型与调度 | `valid:compiled_trace_full` |
| 36 | 工作流、执行模型与调度 | `valid:compiled_with_node_hooks` |
| 37 | 工作流、执行模型与调度 | `valid:config_resources_nodeset_arithmetic` |
| 38 | 工作流、执行模型与调度 | `valid:planned_python_stub_arithmetic` |
| 39 | 工作流、执行模型与调度 | `valid:compiled_semantic_nodeset_arithmetic` |
| 40 | 工作流、执行模型与调度 | `valid:block_linear_training` |
| 41 | 工作流、执行模型与调度 | `valid:compiled_linear_training` |
| 42 | 工作流、执行模型与调度 | `valid:compiled_decision_branch_exit` |
| 43 | 工作流、执行模型与调度 | `valid:async_result_key_join` |
| 44 | 工作流、执行模型与调度 | `valid:semantic_async_result_key_unconsumed` |
| 45 | 工作流、执行模型与调度 | `valid:compiled_fallback_mixed_graph` |
| 46 | 工作流、执行模型与调度 | `valid:async_nodeset_result_key_join` |
| 47 | 工作流、执行模型与调度 | `valid:async_detached_metrics` |
| 48 | 工作流、执行模型与调度 | `valid:mainline_async_nodeset_side_task` |
| 49 | 源码规则、异常与放行边界 | `invalid:inspect_node:MissingInfoNode` |
| 50 | 源码规则、异常与放行边界 | `invalid:inspect_node:InfoWrongTypeNode` |
| 51 | 源码规则、异常与放行边界 | `invalid:inspect_node:EmptyTypeKeyNode` |
| 52 | 源码规则、异常与放行边界 | `invalid:inspect_node:MissingContractNode` |
| 53 | 源码规则、异常与放行边界 | `invalid:inspect_node:DuplicateKeysNode` |
| 54 | 源码规则、异常与放行边界 | `invalid:inspect_node:MissingSemanticsNode` |
| 55 | 源码规则、异常与放行边界 | `invalid:inspect_node:MissingRunPureNode` |
| 56 | 源码规则、异常与放行边界 | `invalid:inspect_node:ContextRunNode` |
| 57 | 源码规则、异常与放行边界 | `invalid:inspect_node:TooManyParamsNode` |
| 58 | 源码规则、异常与放行边界 | `invalid:inspect_node:VarArgsNode` |
| 59 | 源码规则、异常与放行边界 | `invalid:inspect_node:PublicHelperNode` |
| 60 | 源码规则、异常与放行边界 | `invalid:inspect_node:InitWithClientNode` |
| 61 | 源码规则、异常与放行边界 | `invalid:inspect_node:ResourceFieldNode` |
| 62 | 源码规则、异常与放行边界 | `invalid:inspect_node:AsyncRunPureNode` |
| 63 | 源码规则、异常与放行边界 | `invalid:inspect_node:GeneratorRunPureNode` |
| 64 | 源码规则、异常与放行边界 | `invalid:inspect_node:OpenFileNode` |
| 65 | 源码规则、异常与放行边界 | `invalid:inspect_node:PathReadTextNode` |
| 66 | 源码规则、异常与放行边界 | `invalid:inspect_node:OsGetenvNode` |
| 67 | 源码规则、异常与放行边界 | `invalid:inspect_node:SubprocessNode` |
| 68 | 源码规则、异常与放行边界 | `invalid:inspect_node:SocketNode` |
| 69 | 源码规则、异常与放行边界 | `invalid:inspect_node:RequestsNode` |
| 70 | 源码规则、异常与放行边界 | `invalid:inspect_node:SqliteNode` |
| 71 | 源码规则、异常与放行边界 | `invalid:inspect_node:EvalNode` |
| 72 | 源码规则、异常与放行边界 | `invalid:inspect_node:DynamicImportNode` |
| 73 | 源码规则、异常与放行边界 | `invalid:inspect_node:NodeImportNode` |
| 74 | 源码规则、异常与放行边界 | `invalid:inspect_node:DirectNodeCallNode` |
| 75 | 源码规则、异常与放行边界 | `invalid:inspect_node:NodeInternalReadNode` |
| 76 | 源码规则、异常与放行边界 | `invalid:inspect_node:DynamicOutputKeyNode` |
| 77 | 源码规则、异常与放行边界 | `invalid:inspect_node:MissingOutputNode` |
| 78 | 源码规则、异常与放行边界 | `invalid:inspect_node:ExtraOutputNode` |
| 79 | 源码规则、异常与放行边界 | `invalid:inspect_node:MutateInputsNode` |
| 80 | 源码规则、异常与放行边界 | `invalid:inspect_node:MutateNestedInputNode` |
| 81 | 源码规则、异常与放行边界 | `invalid:inspect_node:GlobalStateNode` |
| 82 | 源码规则、异常与放行边界 | `invalid:inspect_node:SetAttrNode` |
| 83 | 源码规则、异常与放行边界 | `invalid:inspect_node:MonkeyPatchNode` |
| 84 | 源码规则、异常与放行边界 | `invalid:inspect_node:LongSourceNode` |
| 85 | 源码规则、异常与放行边界 | `invalid:inspect_node:WarnCallChainNode` |
| 86 | 源码规则、异常与放行边界 | `invalid:inspect_node:DeepCallChainNode` |
| 87 | 源码规则、异常与放行边界 | `invalid:inspect_node:RecursiveNode` |
| 88 | 源码规则、异常与放行边界 | `invalid:inspect_node:IndirectRecursiveNode` |
| 89 | 源码规则、异常与放行边界 | `invalid:health_node:DeepBaseLibNode` |
| 90 | 源码规则、异常与放行边界 | `invalid:base_lib:BASE_LIB.SIDE_EFFECT_CALL` |
| 91 | 源码规则、异常与放行边界 | `invalid:base_lib:BASE_LIB.GLOBAL_STATE` |
| 92 | 源码规则、异常与放行边界 | `invalid:base_lib:VF_IMPORT_LAYER` |
| 93 | 源码规则、异常与放行边界 | `invalid:base_lib:BASE_LIB.BANNED_IMPORT` |
| 94 | 源码规则、异常与放行边界 | `invalid:base_lib_chain` |
| 95 | 源码规则、异常与放行边界 | `invalid:config:fail_schema_bad_edge.jsonc` |
| 96 | 源码规则、异常与放行边界 | `invalid:config:fail_async_result_key_missing.jsonc` |
| 97 | 源码规则、异常与放行边界 | `invalid:run:fail_unknown_node.jsonc` |
| 98 | 源码规则、异常与放行边界 | `invalid:config:fail_removed_loop_registration.jsonc` |
| 99 | 源码规则、异常与放行边界 | `invalid:run:fail_nodeset_key_leak.jsonc` |
| 100 | 源码规则、异常与放行边界 | `invalid:run:fail_nodeset_recursion.jsonc` |
| 101 | 源码规则、异常与放行边界 | `invalid:config:fail_removed_boundary.jsonc` |
| 102 | 源码规则、异常与放行边界 | `invalid:run:fail_decision_cycle_forbidden.jsonc` |
| 103 | 源码规则、异常与放行边界 | `invalid:run:fail_planned_architecture_run.jsonc` |
| 104 | 源码规则、异常与放行边界 | `invalid:run:fail_planned_transparent_allow_run.jsonc` |
| 105 | 源码规则、异常与放行边界 | `invalid:config:fail_plugin_load.jsonc` |
| 106 | 源码规则、异常与放行边界 | `invalid:run:fail_rule_missing_record.jsonc` |
| 107 | 源码规则、异常与放行边界 | `invalid:run:fail_rule_execution.jsonc` |
| 108 | 源码规则、异常与放行边界 | `invalid:config:fail_rule_bad_shape.jsonc` |
| 109 | 源码规则、异常与放行边界 | `invalid:runtime_run:fail_loop_max_iterations.jsonc` |
| 110 | 源码规则、异常与放行边界 | `invalid:concerns:concern_mainline_unjoined_sync_fanout.jsonc` |
| 111 | 源码规则、异常与放行边界 | `invalid:run:fail_mainline_decision_branch_dead_end.jsonc` |
| 112 | 源码规则、异常与放行边界 | `invalid:run:fail_safe_or_join_ambiguous_unconditional.jsonc` |
| 113 | 源码规则、异常与放行边界 | `invalid:run:fail_safe_or_join_multiple_exactly_one.jsonc` |
| 114 | 质量与产物门禁 | `audit:published_diagrams_health_gated` |

## javascript：53 项

| 序号 | 分类 | 任务原名 |
| ---: | --- | --- |
| 1 | 数学综合场景 | `math:plugin-addition` |
| 2 | 数学综合场景 | `math:async-addition` |
| 3 | 数学综合场景 | `math:comprehensive-plugin-rules` |
| 4 | 资源与架构审查 | `review:javascript-expanded-parity` |
| 5 | 构建、ABI 与交付配置 | `profile:esm-module` |
| 6 | 构建、ABI 与交付配置 | `profile:single-esm` |
| 7 | 构建、ABI 与交付配置 | `profile:web-app` |
| 8 | 全局状态、能力与宿主生命周期 | `host-extension:lifecycle-and-capability` |
| 9 | 工作流、执行模型与调度 | `execution:sync-async-taskplan-metadata` |
| 10 | 构建、ABI 与交付配置 | `abi:import-no-side-effect` |
| 11 | 构建、ABI 与交付配置 | `abi:input-and-trace-errors` |
| 12 | 工作流、执行模型与调度 | `routes:schedule-transfer-split` |
| 13 | 工作流、执行模型与调度 | `nodeset:nested-qualified-override` |
| 14 | 工作流、执行模型与调度 | `nodeset:nested-deferred-detached` |
| 15 | 工作流、执行模型与调度 | `loop:bounded-carry` |
| 16 | 工作流、执行模型与调度 | `loop:max-iterations-error` |
| 17 | 全局状态、能力与宿主生命周期 | `capability:missing-and-cancel` |
| 18 | 全局状态、能力与宿主生命周期 | `async:detached-cleanup-and-timeout` |
| 19 | 源码规则、异常与放行边界 | `error:node-cause-and-path` |
| 20 | 源码规则、异常与放行边界 | `error:output-schema-and-path` |
| 21 | 构建、ABI 与交付配置 | `build:source-map-origins` |
| 22 | 构建、ABI 与交付配置 | `build:single-esm-no-chunks` |
| 23 | 构建、ABI 与交付配置 | `build:deterministic` |
| 24 | 构建、ABI 与交付配置 | `build:atomic-failure-preserves-output` |
| 25 | 浏览器运行 | `browser:no-auto-start` |
| 26 | 浏览器运行 | `browser:permanent-host-web-app` |
| 27 | 浏览器运行 | `browser:permanent-host-esm-module` |
| 28 | TypeScript 类型 | `types:strict-consumer` |
| 29 | TypeScript 类型 | `types:optional-input-consumer` |
| 30 | TypeScript 类型 | `types:capability-consumer` |
| 31 | 源码规则、异常与放行边界 | `reject:node_builtin_browser` |
| 32 | 源码规则、异常与放行边界 | `reject:direct_node_import` |
| 33 | 源码规则、异常与放行边界 | `reject:undeclared_base_lib` |
| 34 | 源码规则、异常与放行边界 | `reject:dynamic_import` |
| 35 | 源码规则、异常与放行边界 | `reject:runtime_import` |
| 36 | 源码规则、异常与放行边界 | `reject:immediate_async` |
| 37 | 源码规则、异常与放行边界 | `reject:suspend_sync` |
| 38 | 源码规则、异常与放行边界 | `reject:unowned_promise` |
| 39 | 源码规则、异常与放行边界 | `reject:suspend_in_sync` |
| 40 | 源码规则、异常与放行边界 | `reject:task_in_sync` |
| 41 | 源码规则、异常与放行边界 | `reject:barrel_import` |
| 42 | 源码规则、异常与放行边界 | `reject:alias_import` |
| 43 | 源码规则、异常与放行边界 | `reject:symlink_import` |
| 44 | 源码规则、异常与放行边界 | `reject:base_lib_reverse` |
| 45 | 源码规则、异常与放行边界 | `reject:undeclared_external` |
| 46 | 源码规则、异常与放行边界 | `reject:package_root_escape` |
| 47 | 源码规则、异常与放行边界 | `reject:indirect_node_builtin` |
| 48 | 源码规则、异常与放行边界 | `reject:module_promise` |
| 49 | 源码规则、异常与放行边界 | `reject:discarded_promise` |
| 50 | 源码规则、异常与放行边界 | `reject:long_lived_listener` |
| 51 | 源码规则、异常与放行边界 | `reject:global_state` |
| 52 | 构建、ABI 与交付配置 | `run:dynamic-code` |
| 53 | 质量与产物门禁 | `quality:shared-source-rules` |
