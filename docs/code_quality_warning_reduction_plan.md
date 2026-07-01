# 代码质量 warning 影响面重审与复杂度降低计划

> 历史说明：本文是早期质量 warning 压降过程记录。文中的 `boundary`、`loop`、`max_executions`、`boundary_trace` 等函数名和概念是历史上下文，不代表当前内核设计。当前实现已移除公开 boundary/loop 注册模型，并通过标准 flowchart 节点、显式 edges、SVG/ASCII/Mermaid 图和 `quality-check --path .` 维护质量基线。

本文档记录对当前 `vibeflow quality-check --self` 剩余 warning 的二次审核结果。此次审核不再只按 warning 数量或函数复杂度排序，而是优先评估“修改这些代码会影响哪些已有行为、公开接口、测试和下游模块”。

初始基线：

```text
CONCERNS
0 errors
28 warnings
longest_dependency_chain=10
```

阶段 0 和阶段 1 完成后的基线：

```text
CONCERNS
0 errors
25 warnings
longest_dependency_chain=10
scope warnings: src=24, tests=0, devtools=0, other=1
```

阶段 2 和阶段 3 完成后的基线：

```text
CONCERNS
0 errors
13 warnings
longest_dependency_chain=10
scope warnings: src=12, tests=0, devtools=0, other=1
```

阶段 4 和阶段 5 完成后的基线：

```text
CONCERNS
0 errors
8 warnings
longest_dependency_chain=10
scope warnings: src=7, tests=0, devtools=0, other=1
```

全部阶段完成后的基线：

```text
PASS
0 errors
0 warnings
longest_dependency_chain=5
scope warnings: src=0, tests=0, devtools=0, other=0
```

结论：当前没有 hard error，也没有 warning。已经完成配置/策略校验、AST 静态扫描、编译器、健康检查主流程、运行入口、运行时调度和注册器重复逻辑的拆分。后续若新增 warning，仍应按影响面递增推进，不能为了消除 warning 直接重构核心入口。

## 影响面总览

### A 类：测试或质量工具自身，生产影响很低

涉及：

- `tests/unit/strict_support.py` 中测试样本源码包含 `open()`。
- `tests/unit/test_strict_runtime.py` 两个插件失败测试 AST 相似。
- `src/vibeflow/devtools/code_quality.py` 中 visitor 方法重复。
- `QUALITY.DEPENDENCY.CHAIN_WARN` 当前最长链从测试模块开始。

影响判断：

- 这些 warning 不代表内核运行路径存在直接设计缺陷。
- 依赖链 warning 的最长链起点是测试 helper 导入 CLI 后串到 policy/purity/node，不应为了这条测试链重构生产模块。
- 可优先处理测试组织和质量工具自身的小重复，但不应以此改变核心架构。

### B 类：配置和策略校验，影响中等但边界清晰

涉及：

- `src/vibeflow/config_schema.py:_validate_boundary`
- `src/vibeflow/config_schema.py:_validate_policy`
- `src/vibeflow/policy.py:_relaxed_rule_ids`
- `src/vibeflow/config_schema.py:_error` 与 `src/vibeflow/policy.py:_policy_schema_finding`

影响判断：

- 这些函数影响 `validate`、`inspect-config`、`run_checked` 的配置拒绝语义。
- 主要风险是 rule_id、failure_layer、object_id、rule_source 或错误顺序变化。
- 适合拆成纯函数和表驱动规则，因为输入输出都是结构化对象，行为较容易用测试锁定。

### C 类：Node/base_lib AST 扫描，影响中高

涉及：

- `src/vibeflow/base_lib.py:visit_Module`
- `src/vibeflow/purity_visitors.py:visit_Call`
- `src/vibeflow/purity_visitors.py:_track_output_dict`
- `src/vibeflow/purity_visitors.py:visit_Module`
- `src/vibeflow/base_lib.py` 与 `src/vibeflow/purity_visitors.py` 的 import visitor 重复
- `src/vibeflow/base_lib.py` 与 `src/vibeflow/purity_metrics.py` 的 BoolOp 统计重复
- `src/vibeflow/purity_validators.py:_validate_examples`

影响判断：

- 这些代码决定 node 和 base_lib 的硬性健康检查，是项目目标的核心。
- 修改不应放宽硬规则，也不应改变 source_location 的行列含义。
- 可以抽取共享 AST 工具，但要避免把 node 规则和 base_lib 规则混成一个大而宽松的“通用规则引擎”。

### D 类：Graph compiler，影响中高

涉及：

- `src/vibeflow/compiler.py:_merge_edges`
- `src/vibeflow/compiler.py:_validate_all_cycles_declared`

影响判断：

- 这些函数影响拓扑编译、循环声明、边执行次数、Mermaid、runtime 调度。
- 风险集中在 loop 边、数据边、显式边合并顺序和 max_executions 继承。
- 可以拆，但拆之前需要补充针对 loop 的黄金行为测试。

### E 类：健康检查、运行入口、运行时调度，影响最高

涉及：

- `src/vibeflow/health.py:validate_graph_health`
- `src/vibeflow/health.py:_append_plugin_findings`
- `src/vibeflow/runner.py:run_checked`
- `src/vibeflow/runtime.py:run`

影响判断：

- `validate_graph_health` 是运行前强制拒绝的核心入口，影响 CLI、runner、插件、base_lib、nodeset、boundary、Mermaid 健康标注和报告结构。
- `_append_plugin_findings` 影响插件 fail-closed 语义，不能为了降低分支把异常吞掉或降级。
- `run_checked` 同时负责配置加载、policy、schema、compile、health、artifact、runtime trace 和拒绝异常，属于对外稳定运行入口。
- `runtime.run` 影响 acyclic 节点、loop、boundary、plugin hook、trace 和 stop_reason。
- 这些代码必须最后拆，且每次只拆一个文件。

### F 类：公开注册器重复，已处理

涉及：

- `src/vibeflow/boundary.py:register/get/decorator`
- `src/vibeflow/registry.py:register/get/decorator`

影响判断：

- 二者重复是真实的，但分别表达 boundary registry 和 node registry 的公开 API。
- 已抽出内部 `RegistryBase`，只复用 `register/get/decorator` 的通用字典注册机制。
- `NodeRegistry` 和 `BoundaryRegistry` 仍分别保留自己的校验入口、异常类型和公开语义，避免把 node 与 boundary 的业务规则耦合在一起。

## 新执行顺序

### 阶段 0：行为锁定与质量报告分层（已完成）

目标：

- 在处理高影响代码前，先锁住当前对外行为。
- 区分 `src`、`tests`、`devtools` 的质量 warning，避免测试链条误导架构重构。

计划：

- 已为 `quality-check` 增加按 scope 汇总的输出能力：`src`、`tests`、`devtools`、`other`。
- 已对 `run_checked` 的关键输出补充行为锁定测试：
  - health report status、rule_id、failure_layer、effective_policy。
  - run refused 时必须写出的 artifact 文件。
  - runtime trace、boundary trace。
  - plugin 抛错和策略放宽未审计时必须 fail-closed。

风险：低。主要增加测试和报告维度，不改变核心行为。

### 阶段 1：低影响清理（已完成）

目标：先清掉不代表生产架构风险的 warning。

计划：

- 已将测试 helper 中的非法 node 从 `open()` 改为仍会被 node 纯度检查禁止、但不会被通用质量工具误判测试文件副作用的 `time.sleep()`。
- 已将两个插件失败测试合并为参数化测试，只保留差异输入。
- 已合并 `devtools/code_quality.py` 中 `visit_FunctionDef` 与 `visit_AsyncFunctionDef` 的重复逻辑。
- 已将质量摘要格式化拆到 `devtools/code_quality_format.py`，避免 `code_quality.py` 新增文件长度 warning。

实际收益：warning 从 28 降到 25，且 `tests`、`devtools` scope warning 均为 0。

风险：低。

### 阶段 2：配置和策略纯函数化（已完成）

目标：降低配置/策略校验复杂度，同时保持错误报告完全稳定。

计划：

- 已把 `config_schema.py:_validate_policy` 拆成：
  - `_validate_node_source_policy`
  - `_validate_int_policy`
  - `_validate_string_list_policy`
  - `_validate_rules_policy`
- 已把 `config_schema.py:_validate_boundary` 拆成：
  - `_validate_boundary_shape`
  - `_validate_boundary_key_prefixes`
- 已把 `policy.py:_relaxed_rule_ids` 拆成：
  - `_relaxed_node_source_rule_ids`
  - `_relaxed_import_rule_ids`
  - `_relaxed_policy_rule_ids`
- 已抽出 `schema_findings.py`，统一 config schema 和 policy schema finding 的公共字段。

必须保持：

- rule_id 不变。
- failure_layer 不变。
- object_id 字段路径不变。
- bool 不得被当作 int。
- policy source 顺序不变。

验证：

```powershell
python -m pytest tests\unit\test_strict_base_config_examples.py tests\unit\test_strict_mermaid_cli.py
python -m pytest tests\unit
```

实际收益：清除了 `config_schema.py:_validate_boundary`、`config_schema.py:_validate_policy`、`policy.py:_relaxed_rule_ids` 相关复杂度 warning，并清理了部分重复 AST 指纹。

风险：中低。

### 阶段 3：Node/base_lib AST 工具拆分（已完成）

目标：降低 AST visitor 复杂度，但保持硬检查不变。

计划：

- 已新增轻量 AST 工具模块 `ast_rules.py`，只放纯函数：
  - import module 收集。
  - module 顶层 statement 分类。
  - name target 提取。
  - BoolOp branch 计数。
- 已将 `purity_visitors.py:visit_Call` 拆成独立检查：
  - banned call。
  - monkey patch。
  - node direct call。
  - input mutation。
  - params_schema 访问。
- 已将 `purity_visitors.py:visit_Module` 拆成 statement 分类函数，visitor 只负责调度。
- 已将 `base_lib.py:visit_Module` 改为复用同一套顶层 statement 分类，但保留 base_lib 自己的 rule_id。
- 已将 `_validate_examples` 拆为 example 准备、运行、契约覆盖、输出校验四个步骤。

必须保持：

- node 与 base_lib 的 rule_id 命名空间分离。
- source_location 的 path、line、column 语义不变。
- policy allowlist 不能放开绝对规则。
- 动态 output key 仍默认非法。

验证：

```powershell
python -m pytest tests\unit\test_strict_node_purity.py tests\unit\test_strict_complexity_nodesets.py
python -m pytest tests\unit
```

实际收益：清除了 base_lib、purity visitor、purity validators 的函数复杂度/嵌套/长度 warning，并清理了部分 AST 规则重复。

风险：中到中高。

### 阶段 4：Graph compiler 拆分（已完成）

目标：把 edge 合并和 cycle 校验拆成更小的纯函数。

计划：

- 已补 loop 编译黄金测试：
  - 显式边和数据边重复时只保留一条 effective edge。
  - loop edge 的 max_executions 继承 max_iterations。
  - loop internal edge 的默认执行次数允许循环内多次执行。
  - undeclared cycle 仍失败。
  - loop 声明 missing edge 仍失败。
- 已拆分 `_merge_edges`：
  - `_loop_edge_names`
  - `_loop_edge_limits`
  - `_loop_internal_limits`
  - `_edge_effective_limit`
  - `_merge_edge_into`
- 已拆分 `_validate_all_cycles_declared`：
  - `_validate_loop_declarations`
  - `_validate_loop_edge_endpoints`
  - `_validate_loop_edge_metadata`
  - `_validate_no_undeclared_cycles`
  - `_validate_loop_edges_exist`

必须保持：

- effective_edges 顺序不变或有测试确认顺序不影响下游。
- GraphCompileError 文案至少保持关键信息不变。
- Mermaid 和 runtime 使用的 compiled payload 不变。

验证：

```powershell
python -m pytest tests\unit\test_strict_core.py tests\unit\test_strict_mermaid_cli.py tests\unit\test_strict_runtime.py
python -m pytest tests\unit
```

实际收益：清除了 `compiler.py:_merge_edges` 和 `compiler.py:_validate_all_cycles_declared` 的复杂度 warning。

风险：中高。

### 阶段 5：健康检查主流程拆分（已完成）

目标：把 `validate_graph_health` 从长编排函数拆成阶段化纯函数和窄副作用函数。

计划：

- 已引入内部 dataclass `_HealthValidationState`，保存 errors、warnings、node_metrics、nodeset_findings、fingerprints、base_lib scan 状态、boundary findings。
- 已拆分阶段：
  - `_compile_error_report`
  - `_validate_graph_nodes`
  - `_validate_graph_node`
  - `_append_base_lib_health`
  - `_append_graph_contract_smells`
  - `_append_nodeset_health`
  - `_append_boundary_health`
  - `_append_graph_plugin_findings`
  - `_build_health_report`
- 已将插件 finding 调度拆到 `health_plugins.py`：
  - `_plugins_for_types`
  - `_call_plugin_hook`
  - `_append_plugin_hook_result`

必须保持：

- `HealthReport.to_dict()` 结构不变。
- finding 顺序尽量不变，至少重要失败不被隐藏。
- 插件异常仍是 `failure_layer="plugin"`，整体 status 仍为 `ERROR`。
- base_lib 间接违规仍能挂到对应 node。

验证：

```powershell
python -m pytest tests\unit\test_strict_node_purity.py tests\unit\test_strict_plugins.py tests\unit\test_strict_base_config_examples.py
python -m pytest tests\unit
```

实际收益：清除了 `health.py:validate_graph_health` 和插件 finding 处理的长度/复杂度 warning，并通过 `health_plugins.py` 避免 `health.py` 超过 500 行。

风险：高。建议单独提交。

### 阶段 6：运行入口和运行时调度拆分（已完成）

目标：降低 `run_checked` 和 `runtime.run` 的编排复杂度，同时保持运行产物与拒绝语义。

计划：

- 已拆分 `runner.py:run_checked`：
  - `_prepare_run_dir`
  - `_load_document_or_refuse`
  - `_load_plugins_or_refuse`
  - `_refuse_on_schema_findings`
  - `_compile_or_refuse`
  - `_validate_run_health`
  - `_write_preflight_artifacts`
  - `_execute_runtime`
  - `_write_refused_artifacts`
- 已拆分 `runtime.py:run`：
  - `_run_preflight_hooks`
  - `_run_acyclic_order`
  - `_run_declared_loops`
  - `_run_single_loop`
  - `_run_loop_iteration`
  - `_finalize_runtime`
  - `_record_runtime_failure`
- 已拆出运行时辅助模块：
  - `runtime_trace.py`：运行 trace 数据结构。
  - `runtime_validation.py`：输入修改、输出 key、JSON snapshot 校验。
  - `runtime_errors.py`：运行时异常类型，避免 runtime 与 validation 形成循环依赖。
- 已拆出 `registry_base.py`，复用注册器机械逻辑但保留具体注册器边界。
- 已将 `health.py`、`runner.py` 和测试辅助文件中的重型模块级依赖改为按需导入，消除最终 dependency chain warning。

必须保持：

- `CheckedRunError` 类型和 message 习惯不变。
- config load、plugin load、schema fail、compile fail、health fail 都必须写出当前约定 artifact。
- runtime trace 和 boundary trace 在失败路径仍必须落盘。
- loop_stop_reasons 的值不变：`until`、`boundary_failed`、`node_failed`、`max_iterations`。

验证：

```powershell
python -m pytest tests\unit\test_strict_runtime.py tests\unit\test_strict_plugins.py tests\unit\test_strict_complexity_nodesets.py
python -m pytest tests\unit
```

实际收益：清除了运行入口、运行时调度、注册器重复和最终依赖链 warning。`quality-check --self` 当前为 `PASS`。

风险：最高。建议最后处理，并拆成 runner 与 runtime 两次独立提交。

## 暂缓项

当前没有剩余 warning。后续如果 warning 来自公开 API 的合理重复或测试样本，应先判断它是否真的代表长期维护风险，再决定是拆代码还是改进质量工具解释。

## 每阶段通用验收

每个阶段完成后必须执行：

```powershell
python -m pytest tests\unit
python -m compileall -q src tests
$env:PYTHONPATH='src'; python -m vibeflow quality-check --self
```

短期目标：

```text
0 errors
15 以下 warnings
```

中期目标：

```text
0 errors
8 以下 warnings
```

当前目标已达到：

```text
0 errors
0 warnings
```

后续仍需谨慎：若新 warning 来自公开 API 的合理重复或测试样本，应优先改进质量工具的分类和解释，而不是为了数字牺牲内核边界清晰度。
