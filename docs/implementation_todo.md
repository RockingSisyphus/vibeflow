# topology-kernel 待实现清单

本清单对比当前实现状态、目标愿景和严格设计文档整理而成。排序按整体实现难度从低到高排列；同一阶段内，靠前项目通常是后续项目的前置依赖。

完成本清单后，内核应达到目标：业务项目只编写小型纯函数 node、受控 `base_lib`、可选插件、nodeset JSONC 和最终 pipeline JSONC；运行入口自动强制健康检查，失败拒绝运行，并给出可定位、可审计、可维护的报告。

## 难度 1：稳定现有原型接口

- [x] 统一公开 API 命名和文档术语：`node`、`nodeset`、`pipeline`、`boundary`、`base_lib`、`policy`、`plugin`。
- [x] 将当前 `HealthReport` / `HealthFinding` 扩展为稳定数据结构。
- [x] 为健康报告增加固定状态枚举：`PASS`、`CONCERNS`、`FAIL`、`ERROR`、`SKIPPED`。
- [x] 为每条 finding 增加 `rule_id`、`severity`、`object_type`、`object_id`、`source_location`、`rule_source`、`failure_layer`、`message`、`suggested_fix_type`。
- [x] 为健康报告增加 JSON 序列化输出，并确保字段顺序稳定。
- [x] 为现有纯函数、编译、环路、nodeset、Mermaid 测试适配新的健康报告结构。
- [x] 为现有 CLI 增加 `--json` 输出健康报告。
- [x] 增加 `inspect-node` CLI，输出 node 元数据、契约、源码规模和纯函数检查结果。
- [x] 增加 `inspect-config` CLI，输出配置解析结果、有效边、nodeset 和 loop 摘要。
- [x] 明确 `validate` 的退出码：通过为 `0`，`CONCERNS` 可配置，`FAIL` / `ERROR` 必须非零。

## 难度 2：配置和策略基础

- [x] 实现 `.json` / `.jsonc` 配置加载入口。
- [x] JSONC 注释必须只作为说明，剥离后不得进入运行时语义。
- [x] JSONC 解析错误应尽量保留原始文件行列信息。
- [x] 定义最小 `kernel_policy.jsonc` / `governance.jsonc` 结构。
- [x] 实现内核默认 policy。
- [x] 实现项目 policy 加载与合并。
- [x] 健康报告输出 `effective_policy`。
- [x] policy 支持 node 源码最大行数、最大字节数、复杂度阈值。
- [x] policy 支持允许/禁止导入模块。
- [x] policy 支持允许的 `base_lib` 路径和模块范围。
- [x] policy 支持可降级规则、降级作用域和降级原因。
- [x] policy 支持显式豁免项、豁免作用域和过期条件。
- [x] 健康报告必须显示规则来源：内核默认策略、项目策略或插件策略。
- [x] 增加配置结构模式检查，覆盖 `pipeline.nodes`、`pipeline.edges`、`pipeline.loops`、`nodesets`、`boundary`、`policy`。
- [x] 区分配置 schema 错误和拓扑语义错误。

## 难度 3：Node 契约和纯函数硬检查

- [x] 完整检查 `NodeInfo` 必填字段：`type_key`、`display_name`、`category`、`description`、`version`、`purity`。
- [x] 完整检查 `NodeContract` 必填字段：`requires`、`provides`、`input_semantics`、`output_semantics`、`params_schema`、`output_schema`。
- [x] 检查 node 只能暴露 `run_pure(inputs, params) -> outputs`。
- [x] 检查 node 不允许普通 `run(context, ...)`。
- [x] 检查 node 不允许接收或持有 `Context`、boundary、数据库连接、浏览器对象、会话对象。
- [x] 扩展 AST 禁止调用列表：文件、网络、数据库、浏览器、外部进程、环境变量、动态执行。
- [x] 扩展 AST 禁止语法：模块级可变全局状态、`global` / `nonlocal` 写入、猴子补丁、动态导入、`eval` / `exec`。
- [x] 实现 node 间导入扫描。
- [x] 实现 node 间直接调用扫描。
- [x] 实现 node 读取其他 node 内部常量或类的扫描。
- [x] 实现导入白名单和黑名单。
- [x] 检查 node 返回值只能包含 `provides` 声明的 key。
- [x] 检查 node 必须返回所有声明输出。
- [x] 检查 node 输入没有被原地修改。
- [x] 检查 node 输出可 JSON 快照，或被 `output_schema` 显式允许。
- [x] 增加参数结构模式校验。
- [x] 增加输出结构模式校验。
- [x] 增加 node 源码行数和字节数的 policy 化检查。
- [x] 对接近阈值的 node 输出 warning。

## 难度 4：复杂度、职责边界和长期维护风险检查

- [x] 统计每个 node 的函数数量。
- [x] 统计每个 node 的分支复杂度。
- [x] 统计每个 node 的最大嵌套深度。
- [x] 统计每个 node 的参数规模。
- [x] 统计每个 node 的 `requires` / `provides` key 数量。
- [x] 健康报告展示每个 node 的行数、字节数、复杂度和契约规模。
- [x] 检查 node 名称、类型、描述、语义和契约 key 是否明显不一致。
- [x] 检查未消费输出。
- [x] 检查临时 key、命名混乱、过宽 nodeset 等架构气味。
- [x] 检查重复逻辑的基础信号，例如相似函数名、相似 AST 片段、重复 key 转换逻辑。
- [x] 检查每个 node 是否提供最小测试或示例输入输出。
- [x] 区分“缺测试”“测试存在但未覆盖契约”“测试失败”。
- [x] 为超限或职责过宽 node 输出修复类型：`split_node`、`fix_contract`、`fix_nodeset`、`fix_base_lib`。

## 难度 5：`base_lib` 防逃逸

- [x] 定义 `base_lib` 发现规则和受控目录结构。
- [x] 扫描 `base_lib` 文件规模。
- [x] 扫描 `base_lib` 复杂度和嵌套深度。
- [x] 扫描 `base_lib` 导入白名单。
- [x] 扫描 `base_lib` 依赖闭包。
- [x] 禁止 `base_lib` 导入 node、boundary、runtime 或项目副作用层。
- [x] 禁止 `base_lib` 读写文件、网络、数据库、浏览器、环境变量或外部进程。
- [x] 禁止 `base_lib` 持有可变全局状态。
- [x] 检查 node 对 `base_lib` 的使用是否在 policy 声明范围内。
- [x] 健康报告区分 node 自身违规、node 通过 `base_lib` 间接违规、`base_lib` 自身违规。
- [x] 防止把巨型 node 的复杂度迁移到 `base_lib` 后逃过检查。

## 难度 6：Nodeset 完整治理

- [x] 完整检查 nodeset 元数据：`name`、`version`、`display_name`、`category`、`description`、`purity`。
- [x] 完整检查 nodeset 契约：`requires`、`provides`、`exports`。
- [x] 检查 nodeset 递归引用。
- [x] 检查 nodeset 间接递归引用。
- [x] 实现 nodeset 内部 key 作用域隔离。
- [x] 检查 nodeset 内部中间 key 不泄漏。
- [x] 检查 nodeset 只能导出 `exports` 声明的 key。
- [x] 检查外部 pipeline 只能看到 nodeset 的 `requires` / `provides`。
- [x] 健康报告支持折叠和展开 nodeset findings。
- [x] nodeset 作为 node 使用时，编译器必须统一处理契约和数据边。
- [x] nodeset 过宽或内部节点过多时输出架构气味 warning。

## 难度 7：拓扑编译和环路执行

- [x] 完整区分 explicit edges、data edges、effective edges。
- [x] 编译时检查所有 node 类型可解析。
- [x] 编译时检查缺失 provider。
- [x] 编译时检查重复 provider。
- [x] 编译时检查未声明环路。
- [x] 编译时检查 loop 声明覆盖所有环路边。
- [x] 编译时检查 loop 必须有 `max_iterations`。
- [x] 编译时检查 loop `until` key 可解析。
- [x] 每条边支持 `max_executions`。
- [x] 循环边继承或覆盖 loop 执行上限。
- [x] 运行时记录每条边实际执行次数。
- [x] 运行时记录每个 loop 实际迭代次数。
- [x] 实现比当前 `loop.nodes` 顺序重复更完整的调度策略。
- [x] 避免有界环路中的 node 通过常驻进程或内部循环绕过运行时调度。
- [x] 健康报告和 trace 中显示 loop 停止原因：达到上限、满足 `until`、node 失败、boundary 失败。

## 难度 8：全局边界和副作用隔离

- [x] 定义 `GlobalBoundary` 接口。
- [x] 实现 `before_run`、`after_run`、`before_iteration`、`after_iteration` 生命周期。
- [x] 保证 boundary 不进入 node registry。
- [x] 保证 node 不能导入或持有 boundary。
- [x] 配置中显式声明 boundary 类型和配置。
- [x] 检查 boundary 类型可解析。
- [x] 检查 boundary 配置结构模式。
- [x] node 只能通过结构化请求、效果或发件箱数据表达副作用意图。
- [x] boundary 将外部结果转换为下一轮输入 key。
- [x] 标记所有依赖 boundary 的 key。
- [x] boundary 产生的文件、缓存、下载物、数据库或外部进程产物必须进入 `run_dir` 或配置声明的受控路径。
- [x] 记录 `boundary_trace.jsonl`。
- [x] boundary 失败必须进入健康报告或 runtime trace，并阻断不安全继续执行。

## 难度 9：运行产物、追踪和可复现性

- [x] 为每次正式运行生成 `run_id`。
- [x] 为每次正式运行创建 `run_dir`。
- [x] 写出 `input_summary.json`。
- [x] 写出 `effective_policy.json`。
- [x] 写出 `compiled_graph.json`。
- [x] 写出 `health_report.json`。
- [x] 写出 `graph.mmd`。
- [x] 写出 `runtime_trace.jsonl`。
- [x] 写出 `boundary_trace.jsonl`。
- [x] trace 记录 node 执行顺序。
- [x] trace 记录 nodeset 进入和退出。
- [x] trace 记录输入摘要和输出摘要。
- [x] trace 记录耗时和失败原因。
- [x] trace 默认不保存敏感原文，只保存摘要。
- [x] `run` 入口必须先执行完整健康检查。
- [x] 健康检查 `FAIL` 或 `ERROR` 时拒绝运行。
- [x] 禁止普通运行入口跳过硬性健康检查。

## 难度 10：插件系统

- [x] 定义插件注册表。
- [x] 定义插件加载机制。
- [x] 定义插件优先级。
- [x] 定义插件作用域。
- [x] 定义插件冲突策略。
- [x] 实现 `PolicyPlugin`。
- [x] `PolicyPlugin` 支持扩展元数据结构模式。
- [x] `PolicyPlugin` 支持扩展契约结构模式。
- [x] `PolicyPlugin` 支持扩展纯函数规则。
- [x] `PolicyPlugin` 支持扩展文件大小和复杂度规则。
- [x] `PolicyPlugin` 支持追加 node / nodeset / boundary 检查。
- [x] 治理类插件必须 fail-closed。
- [x] 插件加载失败必须产生 `ERROR`。
- [x] 插件执行异常必须产生 `ERROR`。
- [x] 插件放宽规则必须声明规则编号、作用域、理由和来源。
- [x] 插件不能放宽内核绝对规则，除非默认 policy 明确标记该规则可降级。
- [x] 实现 `CompilerPlugin` 扩展点。
- [x] 实现 `RuntimePlugin` 扩展点。
- [x] 实现 `BoundaryPlugin` 扩展点。
- [x] 健康报告显示插件参与后的最终有效策略。

## 难度 11：Mermaid 和架构可视化

- [x] Mermaid 导出支持折叠 nodeset。
- [x] Mermaid 导出支持展开 nodeset。
- [x] Mermaid 导出显示契约 key。
- [x] Mermaid 导出显示语义。
- [x] Mermaid 导出显示 loop 名称和最大执行次数。
- [x] Mermaid 导出显示边级 `max_executions`。
- [x] Mermaid 导出显示策略检查结果。
- [x] Mermaid 导出显示全局 boundary。
- [x] Mermaid 导出显示 boundary 输入输出 key。
- [x] Mermaid 导出与 `compiled_graph.json` 保持一致。
- [x] Mermaid 导出支持从健康报告标记错误节点或警告节点。

## 难度 12：完整 CLI 和发布形态

- [x] `topology-kernel validate --config ...`
- [x] `topology-kernel validate --config ... --json`
- [x] `topology-kernel inspect-node --type ...`
- [x] `topology-kernel inspect-config --config ...`
- [x] `topology-kernel export-mermaid --config ... --output ...`
- [x] `topology-kernel export-mermaid --config ... --expand-nodesets`
- [x] `topology-kernel run --config ...`
- [x] `run` 自动执行强制健康检查。
- [x] `run` 写出完整运行产物。
- [x] CLI 错误信息包含文件、行列和规则编号。
- [x] 包结构调整到目标形态：`core/`、`plugins/`、`devtools/`、`resources/schema/`。
- [x] 公共 API 只暴露稳定对象。
- [x] 为 JSONC、policy、health report、node、nodeset、boundary 提供 schema 或等价结构定义。

## 难度 13：目标完整性验证

- [x] 增加覆盖所有绝对规则的单元测试。
- [x] 增加 JSONC 行列错误定位测试。
- [x] 增加 policy 合并和降级测试。
- [x] 增加插件 fail-closed 测试。
- [x] 增加 node 间导入/调用禁止测试。
- [x] 增加 `base_lib` 防逃逸测试。
- [x] 增加 nodeset 递归和 key 泄漏测试。
- [x] 增加显式有界环路执行计数测试。
- [x] 增加 boundary 隔离测试。
- [x] 增加运行产物完整性测试。
- [x] 增加 Mermaid 展开/折叠一致性测试。
- [x] 增加一个最小示例项目，证明只通过 node、base_lib、plugins、nodesets、configs 即可运行。
- [x] 增加一个失败示例集，覆盖巨型 node、隐藏副作用、动态导入、node 互调、未声明环路、非法 boundary、`base_lib` 逃逸等典型违规。

## 难度 14：Node 调用链和依赖链深度检查

本阶段把“隐藏在单个 node 内部的过深调用链 / 依赖链”纳入 node 健康检查。目标是防止 LLM 把复杂度从一个巨型函数转移到一串互相调用的私有函数或过深的 helper 依赖中，从而绕过行数、分支数和嵌套深度检查。

默认阈值建议：

- 链长 `<= 3`：正常。
- 链长 `== 4`：输出 warning，提示 node 已接近职责边界。
- 链长 `> 4`：判定为不健康，输出 error，建议拆分 node、抽取受控 `base_lib` 或提升为 nodeset。

这里的链长以 `run_pure` 作为入口计算，`run_pure -> helper_a -> helper_b -> helper_c` 计为 4。普通 node 最多允许三层 helper 深度；超过该深度通常说明 node 已经不再原子化。

- [x] 为 node AST 构建内部函数调用图。
- [x] 从 `run_pure` 开始计算最长内部调用链长度。
- [x] 检测递归调用和间接递归调用。
- [x] 检测 `run_pure` 到私有 helper 的调用链是否达到 warning 阈值 4。
- [x] 检测 `run_pure` 到私有 helper 的调用链是否超过 hard fail 阈值 4。
- [x] 健康报告展示每个 node 的最长调用链长度和对应路径。
- [x] 超过阈值时输出 `NODE.MAINTAINABILITY.CALL_CHAIN_TOO_DEEP`。
- [x] 递归调用输出 `NODE.MAINTAINABILITY.RECURSIVE_CALL_CHAIN`。
- [x] `suggested_fix_type` 对过深调用链使用 `split_node` 或 `fix_base_lib`。
- [x] 扫描 node 依赖的允许模块，建立 node 到 `base_lib` 的依赖链摘要。
- [x] 对 node 依赖链长度设置默认阈值：超过 4 输出 warning，超过 6 输出 error。
- [x] 对过深依赖链输出 `NODE.MAINTAINABILITY.DEPENDENCY_CHAIN_TOO_DEEP`。
- [x] 增加合法短调用链测试。
- [x] 增加调用链长度为 4 的 warning 测试。
- [x] 增加调用链长度超过 4 的 error 测试。
- [x] 增加直接递归和间接递归测试。
- [x] 增加过深 `base_lib` 依赖链测试。
- [x] `inspect-node` 输出调用链和依赖链摘要。

## 完成判定

当以上 checkbox 全部完成后，内核应满足以下最终判定：

- [x] 普通 node 无法直接产生副作用。
- [x] 普通 node 无法直接调用或导入其他 node。
- [x] `base_lib` 无法成为隐藏副作用或巨型逻辑的逃逸口。
- [x] 所有拓扑关系只能由 JSONC 配置显式组织。
- [x] 所有环路必须显式声明且有执行上限。
- [x] nodeset 可以承载复杂功能，但不会泄漏内部 key 或递归引用。
- [x] 运行入口无法绕过强制健康检查。
- [x] 健康检查失败会拒绝运行。
- [x] 健康报告能定位失败对象、规则来源、失败层级和建议修复类型。
- [x] Mermaid、编译图、健康报告和运行 trace 能共同解释程序结构。
- [x] 插件可以扩展或收紧治理，但不能隐式绕过绝对规则。
- [x] 每次运行都有可审计、可复现的运行产物。

## 后续扩展：通用代码质量检查工具

在核心内核目标完成后，基于本项目已经实现的自动代码检查能力，开发一个不要求目标项目使用 `topology-kernel` 的通用代码质量检查小工具。

该工具的目标不是替代内核本身，而是把内核中沉淀出的文件规模、复杂度、依赖关系和架构气味检查抽象出来，用于检查普通 Python 项目的长期可维护性。后续也应使用这个工具反过来检查 `topology-kernel` 自身，确保内核代码不会逐步膨胀成难以维护的实现。

- [x] 支持对任意项目目录运行代码质量检查，不要求项目采用 node / nodeset 架构。
- [x] 检查每个代码文件是否超过最大行数，默认阈值为 500 行。
- [x] 检查每个代码文件的字节数、函数数量、分支数量和最大嵌套深度。
- [x] 检查单个函数是否过长、分支过多或嵌套过深。
- [x] 扫描 Python import 图，发现过长依赖链条。
- [x] 发现循环 import 或明显的双向模块依赖。
- [x] 检查是否存在过宽模块，例如单文件承担过多函数、类或公共 API。
- [x] 检查是否存在明显的重复逻辑信号，例如相似函数名、相似 AST 指纹或重复转换逻辑。
- [x] 检查是否存在隐藏副作用高风险代码，例如文件、网络、数据库、外部进程和环境变量访问。
- [x] 输出独立的质量报告 JSON，包含文件、函数、依赖链、规则编号、严重程度和建议修复类型。
- [x] 支持把检查结果以人类可读摘要输出到 CLI。
- [x] 为该工具增加自检入口，用于检查 `topology-kernel` 仓库自身。
- [x] 在 CI 或发布前流程中预留接入点，确保内核自身也接受同等代码质量约束。
