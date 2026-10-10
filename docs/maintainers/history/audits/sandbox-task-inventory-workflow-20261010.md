# 沙盒登记任务清单（嵌套与循环数学整合后）

本文保留当时的任务数量与顺序；当前入口和登记情况见 [沙盒导航](../../../../sandbox/README.md)。

核对日期：2026-10-10。此前 167 项保留为历史快照，本轮移除 19 项并加入两 Target 的 workflow_math。通过完整报告核对任务名与顺序；逐项替代与验收见 [整合归档](workflow-math-20261010.md)。

计数口径：两个 integration runner 的最外层报告任务；Python **102**，JavaScript **48**，合计 **150**。内部观察、pytest 和其他独立沙盒不另外累计。

| 分类 | Python | JavaScript | 合计 |
| --- | ---: | ---: | ---: |
| 数学综合场景 | 6 | 4 | 10 |
| 工作流、执行模型与调度 | 20 | 0 | 20 |
| 资源与架构审查 | 3 | 1 | 4 |
| 源码规则、异常与放行边界 | 67 | 23 | 90 |
| 全局状态、能力与宿主生命周期 | 4 | 3 | 7 |
| 构建、ABI 与交付配置 | 0 | 10 | 10 |
| 浏览器运行 | 0 | 3 | 3 |
| TypeScript 类型 | 0 | 3 | 3 |
| 质量与产物门禁 | 2 | 1 | 3 |
| **总计** | **102** | **48** | **150** |

`invalid:` 包含历史放行/warning 对照，名称不等于应当报 error；详细通过判定以驱动为准。

## python：102 项

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
| 10 | 数学综合场景 | `workflow_math` |
| 11 | 工作流、执行模型与调度 | `execution:python-sync-vs-result-key-thread` |
| 12 | 工作流、执行模型与调度 | `execution:python-thread-pool-boundaries` |
| 13 | 源码规则、异常与放行边界 | `source-preflight:imported-declarative-contract-helper` |
| 14 | 源码规则、异常与放行边界 | `source-preflight:effectful-imported-helper-rejected` |
| 15 | 全局状态、能力与宿主生命周期 | `global-state:forbidden-effect-audit` |
| 16 | 全局状态、能力与宿主生命周期 | `global-state:protected-async-compile` |
| 17 | 全局状态、能力与宿主生命周期 | `global-state:unlocked-overlap` |
| 18 | 全局状态、能力与宿主生命周期 | `global-state:failure-releases-lock` |
| 19 | 工作流、执行模型与调度 | `valid:free_nodes` |
| 20 | 工作流、执行模型与调度 | `valid:io_data_store` |
| 21 | 工作流、执行模型与调度 | `valid:comprehensive_flowchart` |
| 22 | 工作流、执行模型与调度 | `valid:global_state_execution_lock` |
| 23 | 工作流、执行模型与调度 | `valid:ordinary_callback_warning` |
| 24 | 工作流、执行模型与调度 | `valid:training_object_flow` |
| 25 | 工作流、执行模型与调度 | `valid:training_non_json_metrics` |
| 26 | 工作流、执行模型与调度 | `valid:config_resources_nodeset_arithmetic` |
| 27 | 工作流、执行模型与调度 | `valid:planned_python_stub_arithmetic` |
| 28 | 工作流、执行模型与调度 | `valid:block_linear_training` |
| 29 | 工作流、执行模型与调度 | `valid:compiled_linear_training` |
| 30 | 工作流、执行模型与调度 | `valid:compiled_decision_branch_exit` |
| 31 | 工作流、执行模型与调度 | `valid:async_result_key_join` |
| 32 | 工作流、执行模型与调度 | `valid:semantic_async_result_key_unconsumed` |
| 33 | 工作流、执行模型与调度 | `valid:compiled_fallback_mixed_graph` |
| 34 | 工作流、执行模型与调度 | `valid:async_nodeset_result_key_join` |
| 35 | 工作流、执行模型与调度 | `valid:async_detached_metrics` |
| 36 | 工作流、执行模型与调度 | `valid:mainline_async_nodeset_side_task` |
| 37 | 源码规则、异常与放行边界 | `invalid:inspect_node:MissingInfoNode` |
| 38 | 源码规则、异常与放行边界 | `invalid:inspect_node:InfoWrongTypeNode` |
| 39 | 源码规则、异常与放行边界 | `invalid:inspect_node:EmptyTypeKeyNode` |
| 40 | 源码规则、异常与放行边界 | `invalid:inspect_node:MissingContractNode` |
| 41 | 源码规则、异常与放行边界 | `invalid:inspect_node:DuplicateKeysNode` |
| 42 | 源码规则、异常与放行边界 | `invalid:inspect_node:MissingSemanticsNode` |
| 43 | 源码规则、异常与放行边界 | `invalid:inspect_node:MissingRunPureNode` |
| 44 | 源码规则、异常与放行边界 | `invalid:inspect_node:ContextRunNode` |
| 45 | 源码规则、异常与放行边界 | `invalid:inspect_node:TooManyParamsNode` |
| 46 | 源码规则、异常与放行边界 | `invalid:inspect_node:VarArgsNode` |
| 47 | 源码规则、异常与放行边界 | `invalid:inspect_node:PublicHelperNode` |
| 48 | 源码规则、异常与放行边界 | `invalid:inspect_node:InitWithClientNode` |
| 49 | 源码规则、异常与放行边界 | `invalid:inspect_node:ResourceFieldNode` |
| 50 | 源码规则、异常与放行边界 | `invalid:inspect_node:AsyncRunPureNode` |
| 51 | 源码规则、异常与放行边界 | `invalid:inspect_node:GeneratorRunPureNode` |
| 52 | 源码规则、异常与放行边界 | `invalid:inspect_node:OpenFileNode` |
| 53 | 源码规则、异常与放行边界 | `invalid:inspect_node:PathReadTextNode` |
| 54 | 源码规则、异常与放行边界 | `invalid:inspect_node:OsGetenvNode` |
| 55 | 源码规则、异常与放行边界 | `invalid:inspect_node:SubprocessNode` |
| 56 | 源码规则、异常与放行边界 | `invalid:inspect_node:SocketNode` |
| 57 | 源码规则、异常与放行边界 | `invalid:inspect_node:RequestsNode` |
| 58 | 源码规则、异常与放行边界 | `invalid:inspect_node:SqliteNode` |
| 59 | 源码规则、异常与放行边界 | `invalid:inspect_node:EvalNode` |
| 60 | 源码规则、异常与放行边界 | `invalid:inspect_node:DynamicImportNode` |
| 61 | 源码规则、异常与放行边界 | `invalid:inspect_node:NodeImportNode` |
| 62 | 源码规则、异常与放行边界 | `invalid:inspect_node:DirectNodeCallNode` |
| 63 | 源码规则、异常与放行边界 | `invalid:inspect_node:NodeInternalReadNode` |
| 64 | 源码规则、异常与放行边界 | `invalid:inspect_node:DynamicOutputKeyNode` |
| 65 | 源码规则、异常与放行边界 | `invalid:inspect_node:MissingOutputNode` |
| 66 | 源码规则、异常与放行边界 | `invalid:inspect_node:ExtraOutputNode` |
| 67 | 源码规则、异常与放行边界 | `invalid:inspect_node:MutateInputsNode` |
| 68 | 源码规则、异常与放行边界 | `invalid:inspect_node:MutateNestedInputNode` |
| 69 | 源码规则、异常与放行边界 | `invalid:inspect_node:GlobalStateNode` |
| 70 | 源码规则、异常与放行边界 | `invalid:inspect_node:SetAttrNode` |
| 71 | 源码规则、异常与放行边界 | `invalid:inspect_node:MonkeyPatchNode` |
| 72 | 源码规则、异常与放行边界 | `invalid:inspect_node:LongSourceNode` |
| 73 | 源码规则、异常与放行边界 | `invalid:inspect_node:WarnCallChainNode` |
| 74 | 源码规则、异常与放行边界 | `invalid:inspect_node:DeepCallChainNode` |
| 75 | 源码规则、异常与放行边界 | `invalid:inspect_node:RecursiveNode` |
| 76 | 源码规则、异常与放行边界 | `invalid:inspect_node:IndirectRecursiveNode` |
| 77 | 源码规则、异常与放行边界 | `invalid:health_node:DeepBaseLibNode` |
| 78 | 源码规则、异常与放行边界 | `invalid:base_lib:BASE_LIB.SIDE_EFFECT_CALL` |
| 79 | 源码规则、异常与放行边界 | `invalid:base_lib:BASE_LIB.GLOBAL_STATE` |
| 80 | 源码规则、异常与放行边界 | `invalid:base_lib:VF_IMPORT_LAYER` |
| 81 | 源码规则、异常与放行边界 | `invalid:base_lib:BASE_LIB.BANNED_IMPORT` |
| 82 | 源码规则、异常与放行边界 | `invalid:base_lib_chain` |
| 83 | 源码规则、异常与放行边界 | `invalid:config:fail_schema_bad_edge.jsonc` |
| 84 | 源码规则、异常与放行边界 | `invalid:config:fail_async_result_key_missing.jsonc` |
| 85 | 源码规则、异常与放行边界 | `invalid:run:fail_unknown_node.jsonc` |
| 86 | 源码规则、异常与放行边界 | `invalid:config:fail_removed_loop_registration.jsonc` |
| 87 | 源码规则、异常与放行边界 | `invalid:run:fail_nodeset_key_leak.jsonc` |
| 88 | 源码规则、异常与放行边界 | `invalid:run:fail_nodeset_recursion.jsonc` |
| 89 | 源码规则、异常与放行边界 | `invalid:config:fail_removed_boundary.jsonc` |
| 90 | 源码规则、异常与放行边界 | `invalid:run:fail_decision_cycle_forbidden.jsonc` |
| 91 | 源码规则、异常与放行边界 | `invalid:run:fail_planned_architecture_run.jsonc` |
| 92 | 源码规则、异常与放行边界 | `invalid:run:fail_planned_transparent_allow_run.jsonc` |
| 93 | 源码规则、异常与放行边界 | `invalid:config:fail_plugin_load.jsonc` |
| 94 | 源码规则、异常与放行边界 | `invalid:run:fail_rule_missing_record.jsonc` |
| 95 | 源码规则、异常与放行边界 | `invalid:run:fail_rule_execution.jsonc` |
| 96 | 源码规则、异常与放行边界 | `invalid:config:fail_rule_bad_shape.jsonc` |
| 97 | 源码规则、异常与放行边界 | `invalid:runtime_run:fail_loop_max_iterations.jsonc` |
| 98 | 源码规则、异常与放行边界 | `invalid:concerns:concern_mainline_unjoined_sync_fanout.jsonc` |
| 99 | 源码规则、异常与放行边界 | `invalid:run:fail_mainline_decision_branch_dead_end.jsonc` |
| 100 | 源码规则、异常与放行边界 | `invalid:run:fail_safe_or_join_ambiguous_unconditional.jsonc` |
| 101 | 源码规则、异常与放行边界 | `invalid:run:fail_safe_or_join_multiple_exactly_one.jsonc` |
| 102 | 质量与产物门禁 | `audit:published_diagrams_health_gated` |

## javascript：48 项

| 序号 | 分类 | 任务原名 |
| ---: | --- | --- |
| 1 | 数学综合场景 | `math:workflow-nesting-and-trace` |
| 2 | 数学综合场景 | `math:plugin-addition` |
| 3 | 数学综合场景 | `math:async-addition` |
| 4 | 数学综合场景 | `math:comprehensive-plugin-rules` |
| 5 | 资源与架构审查 | `review:javascript-expanded-parity` |
| 6 | 构建、ABI 与交付配置 | `profile:esm-module` |
| 7 | 构建、ABI 与交付配置 | `profile:single-esm` |
| 8 | 构建、ABI 与交付配置 | `profile:web-app` |
| 9 | 全局状态、能力与宿主生命周期 | `host-extension:lifecycle-and-capability` |
| 10 | 构建、ABI 与交付配置 | `abi:import-no-side-effect` |
| 11 | 构建、ABI 与交付配置 | `abi:input-and-trace-errors` |
| 12 | 全局状态、能力与宿主生命周期 | `capability:missing-and-cancel` |
| 13 | 全局状态、能力与宿主生命周期 | `async:detached-cleanup-and-timeout` |
| 14 | 源码规则、异常与放行边界 | `error:node-cause-and-path` |
| 15 | 源码规则、异常与放行边界 | `error:output-schema-and-path` |
| 16 | 构建、ABI 与交付配置 | `build:source-map-origins` |
| 17 | 构建、ABI 与交付配置 | `build:single-esm-no-chunks` |
| 18 | 构建、ABI 与交付配置 | `build:deterministic` |
| 19 | 构建、ABI 与交付配置 | `build:atomic-failure-preserves-output` |
| 20 | 浏览器运行 | `browser:no-auto-start` |
| 21 | 浏览器运行 | `browser:permanent-host-web-app` |
| 22 | 浏览器运行 | `browser:permanent-host-esm-module` |
| 23 | TypeScript 类型 | `types:strict-consumer` |
| 24 | TypeScript 类型 | `types:optional-input-consumer` |
| 25 | TypeScript 类型 | `types:capability-consumer` |
| 26 | 源码规则、异常与放行边界 | `reject:node_builtin_browser` |
| 27 | 源码规则、异常与放行边界 | `reject:direct_node_import` |
| 28 | 源码规则、异常与放行边界 | `reject:undeclared_base_lib` |
| 29 | 源码规则、异常与放行边界 | `reject:dynamic_import` |
| 30 | 源码规则、异常与放行边界 | `reject:runtime_import` |
| 31 | 源码规则、异常与放行边界 | `reject:immediate_async` |
| 32 | 源码规则、异常与放行边界 | `reject:suspend_sync` |
| 33 | 源码规则、异常与放行边界 | `reject:unowned_promise` |
| 34 | 源码规则、异常与放行边界 | `reject:suspend_in_sync` |
| 35 | 源码规则、异常与放行边界 | `reject:task_in_sync` |
| 36 | 源码规则、异常与放行边界 | `reject:barrel_import` |
| 37 | 源码规则、异常与放行边界 | `reject:alias_import` |
| 38 | 源码规则、异常与放行边界 | `reject:symlink_import` |
| 39 | 源码规则、异常与放行边界 | `reject:base_lib_reverse` |
| 40 | 源码规则、异常与放行边界 | `reject:undeclared_external` |
| 41 | 源码规则、异常与放行边界 | `reject:package_root_escape` |
| 42 | 源码规则、异常与放行边界 | `reject:indirect_node_builtin` |
| 43 | 源码规则、异常与放行边界 | `reject:module_promise` |
| 44 | 源码规则、异常与放行边界 | `reject:discarded_promise` |
| 45 | 源码规则、异常与放行边界 | `reject:long_lived_listener` |
| 46 | 源码规则、异常与放行边界 | `reject:global_state` |
| 47 | 构建、ABI 与交付配置 | `run:dynamic-code` |
| 48 | 质量与产物门禁 | `quality:shared-source-rules` |
