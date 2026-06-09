# 当前实现状态

## 当前定位

当前仓库是 `topology-kernel` 的第一版严格内核原型。它验证了最核心的想法能运行，但还没有达到目标构想中的完整框架状态。

补充定位：该内核的最终目标是服务于人机协同开发，尤其是 LLM 深度参与编码的场景。内核需要通过硬性健康检查约束 LLM 生成的程序只能由小型、纯函数、低耦合 node 和显式 JSONC 拓扑组成。目前实现只覆盖了这一目标的基础原型，还没有形成完整的 LLM 协作治理体系。

## 已完成

### 基础包结构

已建立独立 Python 包：

```text
src/topology_kernel/
```

当前模块：

- `context.py`
- `node.py`
- `registry.py`
- `graph_config.py`
- `compiler.py`
- `runtime.py`
- `purity.py`
- `health.py`
- `mermaid.py`
- `cli.py`
- `config_loader.py`
- `config_schema.py`
- `policy.py`
- `base_lib.py`
- `boundary.py`
- `plugin.py`
- `runner.py`

已增加目标发布形态的轻量目录：

- `core/`：稳定核心 API 的 re-export。
- `plugins/`：插件协议与插件注册表的 re-export。
- `devtools/`：配置加载、schema 检查、纯度检查、Mermaid、`base_lib` 扫描等开发工具入口。
- `resources/schema/`：配置、policy、health report、node、nodeset、boundary 的结构定义资源。

### 纯函数 node 接口

已实现：

- `NodeInfo`
- `NodeContract`
- `PureNode` protocol
- 运行时通过 `run_pure(inputs, params) -> outputs` 调用 node
- node 不直接接触 `Context`
- 运行时检查 node 是否原地修改输入
- 运行时检查返回输出是否全部声明
- 运行时检查声明输出是否全部返回

### 拓扑编译

已实现：

- `pipeline.nodes`
- `pipeline.edges`
- `pipeline.inputs`
- `requires/provides` 自动推导 data edges
- explicit edges 与 data edges 合并为 effective edges
- 缺失 provider 会编译失败
- 重复 provider 会编译失败

### 显式有界环路

已实现：

- `pipeline.loops`
- 环路 `name`
- 环路 `edges`
- 环路 `nodes`
- 环路 `max_iterations`
- 环路 `until`
- 未声明环路会编译失败
- 声明环路后可以编译并执行
- 编译器输出依赖感知的 `loop_orders`
- loop `until` key 必须可解析
- loop 边可继承或覆盖执行上限
- 运行时记录每条边实际执行次数
- 运行时记录每个 loop 实际迭代次数
- 运行时记录 loop 停止原因：`max_iterations`、`until`、`node_failed`

### nodeset

已实现：

- `nodesets`
- `nodeset.<name>` 可作为普通 node 类型使用
- nodeset 内部可执行子图
- nodeset 通过 `exports` 暴露输出
- nodeset 元数据和契约 schema 检查
- nodeset 递归和间接递归健康检查
- nodeset 内部 key 作用域隔离和中间 key 泄漏检查
- 外部 pipeline 和嵌套 nodeset 引用点的契约一致性检查
- 健康报告中的 `info.nodeset_findings` 折叠视图，以及 errors / warnings 展开视图

### 纯函数静态检查

已实现初版：

- node 必须声明 `NODE_INFO`
- node 必须声明 `CONTRACT`
- node 必须提供 `run_pure`
- 禁止普通 `run(context, ...)`
- AST 检查部分禁止的导入
- AST 检查部分禁止的调用
- 源码行数限制
- 源码字节数限制

当前限制还不完整，尚未实现 node 间导入或调用依赖扫描，也没有完整 `base_lib` 纯函数扫描。

### LLM 协作治理

已具备的基础：

- node 源码行数和字节数限制。
- node 不允许直接接触 `Context`。
- node 输出必须符合声明。
- 图拓扑由配置组织，而不是 node 互相调用。
- node 内部私有 helper 调用链从 `run_pure` 开始计数，默认长度 4 警告，超过 4 硬失败。
- node 内部直接递归和间接递归会硬失败。
- node 到 `base_lib` 的依赖链会被扫描，默认超过 4 警告，超过 6 硬失败。

尚未形成完整能力：

- 未提供“拆成多个 node / 抽取 `base_lib` / 提升为 nodeset”的自动化建议。
- 未识别长期维护风险，例如契约漂移、重复逻辑、命名模糊、语义不一致。

### 全局边界

已实现：

- `GlobalBoundary` 协议。
- 独立 `BoundaryRegistry`，boundary 不能注册进 node registry。
- `before_run`、`after_run`、`before_iteration`、`after_iteration` 生命周期。
- 配置中声明 `boundary.type`、`config`、`consumes`、`provides`、`allowed_paths`。
- `effects.*` / `outbox.*` 请求 key 与 `io.*` 返回 key 的结构化约束。
- boundary 返回 key 必须在 `boundary.provides` 中声明。
- boundary 产物路径必须位于 `run_dir` 或显式 `allowed_paths`。
- 运行时写出 `boundary_trace.jsonl`。
- boundary 失败会进入 runtime trace 并阻断继续运行。

### 健康报告

已实现基础版：

- 编译失败报告。
- node 类型解析。
- 纯函数违规报告。
- 未消费输出警告。
- 有效边、数据边、显式边信息。

尚未实现完整目标中的语义和架构漂移等健康检查。

### 插件系统

已实现：

- `PluginRegistry` 和 `PolicyPlugin` / `CompilerPlugin` / `RuntimePlugin` / `BoundaryPlugin` 协议。
- 配置中的 `plugins` 显式加载机制。
- 插件优先级、作用域和冲突策略。
- `PolicyPlugin.extend_policy` 可以收紧策略，或在完整审计字段下放宽可降级规则。
- 插件不能放宽未被默认 policy 标记为可降级的绝对规则。
- `PolicyPlugin` 可追加 node、graph、nodeset、boundary 健康检查。
- `PolicyPlugin` 元数据 schema、契约 schema、纯函数规则扩展方法采用 fail-closed 调用。
- `CompilerPlugin`、`RuntimePlugin`、`BoundaryPlugin` 提供轻量钩子。
- 插件加载失败和执行异常都会产生 `ERROR`。
- 健康报告和 `effective_policy` 会显示插件参与结果。

### 正式运行与产物

已实现：

- `run_checked(...)` 正式运行入口。
- 每次正式运行生成 `run_id` 并创建独立 `run_dir`。
- 运行前强制执行配置 schema、policy 合并和完整健康检查。
- 健康检查 `FAIL` / `ERROR` 时拒绝执行 runtime。
- 写出 `input_summary.json`、`effective_policy.json`、`compiled_graph.json`、`health_report.json`、`graph.mmd`、`runtime_trace.jsonl`、`boundary_trace.jsonl`。
- trace 记录 node 执行、nodeset 进入和退出、耗时、失败原因、输入摘要和输出摘要。
- trace 默认只保存结构摘要，不保存原始输入输出。

### Mermaid 导出

已实现：

- 输出 `flowchart TD`
- 显示 node 名称和类型
- 显示有效边
- 显示 `max_executions`
- 显示环路名称
- 支持 nodeset 折叠显示
- 支持 nodeset 展开显示
- 显示 node / nodeset 的契约 key
- 显示配置中的描述、分类、版本等语义信息
- 显示 loop 名称、最大执行次数和 loop 摘要
- 显示全局 boundary 及其 consumes / provides key
- 显示 boundary 与 node 之间的输入输出端口连接
- 支持从健康报告标记错误节点和警告节点
- `run_checked(...)` 写出的 `graph.mmd` 与同次编译生成的 `compiled_graph.json` 使用同一个 `CompiledGraph`

### CLI

已实现：

```text
topology-kernel validate --config ...
topology-kernel validate --config ... --json
topology-kernel inspect-node --type ... --module ...
topology-kernel inspect-config --config ...
topology-kernel run --config ...
topology-kernel export-mermaid --config ...
topology-kernel export-mermaid --config ... --output ...
topology-kernel export-mermaid --config ... --expand-nodesets
topology-kernel quality-check --path ...
topology-kernel quality-check --self
topology-kernel quality-check --path ... --json
```

`run` 使用强制健康检查入口；未注册业务 node 或健康检查失败时会拒绝执行，并保留运行目录中的诊断产物。CLI 的配置错误输出包含稳定 `rule_id`，JSON 输出包含文件、行列和失败层级；文本验证输出也会显示文件、行列和规则编号。

### 发布形态和结构定义

已实现：

- `pyproject.toml` 提供 `topology-kernel = topology_kernel.cli:main` 命令入口。
- 顶层 `topology_kernel.STABLE_PUBLIC_API` 明确稳定公共 API 清单。
- `topology_kernel.resources.schema_text(...)` 可读取内置 schema 资源。
- 内置 schema 覆盖 JSONC 配置等价结构、policy、health report、node、nodeset、boundary。

### 通用代码质量检查工具

已实现：

- `topology-kernel quality-check --path ...` 可检查普通 Python 项目，不要求使用 `topology-kernel` 架构。
- `topology-kernel quality-check --self` 可检查内核仓库自身。
- 检查文件行数、文件字节数、函数数量、类数量、公共 API 数量、分支数量和最大嵌套深度。
- 检查单函数长度、分支数和嵌套深度。
- 扫描 Python import 图，发现过长依赖链、循环依赖和双向依赖。
- 检查相似 AST 指纹，输出重复逻辑信号。
- 检查文件、网络、数据库、外部进程、环境变量、动态执行等隐藏副作用风险。
- 支持 JSON 报告和人类可读摘要。
- 默认排除 `references/` 等外部参考资料目录，避免把第三方参考仓库纳入内核自检。

### 示例和失败样本

已实现：

- `examples/minimal_project/`：最小可运行项目，业务侧只提供 node、`base_lib`、policy 插件、nodeset 和 JSONC 配置。
- `examples/failure_cases/cases.jsonc`：典型失败样本 manifest，覆盖巨型 node、隐藏副作用、动态导入、node 互调、未声明环路、非法 boundary 和 `base_lib` 逃逸。
- 单元测试会运行最小示例，并物化失败样本确认内核输出稳定规则编号。

## 测试状态

当前测试文件：

```text
tests/unit/test_topology_kernel_strict.py
```

覆盖：

- 纯函数 node 元数据与 AST 检查。
- 源码大小限制。
- node 内部调用链和递归检查。
- node 到 `base_lib` 的依赖链深度检查。
- 数据边自动推导。
- 运行时执行。
- 未声明环路失败。
- 显式有界环路通过并执行。
- nodeset 可作为 node 使用。
- 健康报告。
- Mermaid 导出。
- 正式运行产物和 runtime trace。
- 插件加载、策略扩展、fail-closed 和运行钩子。
- 最小示例项目和失败示例集。
- Mermaid 展开/折叠一致性。
- 运行产物完整性交叉验证。
- 通用代码质量检查工具。

迁移到独立仓库后的验证：

```text
7 passed
```

Paperflow 清理内核副本后的验证：

```text
135 passed
```

## 尚未完成

当前主体功能已达到初步实现版。后续主要工作是持续收紧规则、降低误报、补充真实项目迁移反馈，并把 `quality-check --self` 接入 CI 或发布前流程。

## 当前风险

- 纯函数检查仍是工程约束，不是数学证明。
- 质量检查工具目前是轻量 AST 扫描和启发式检查，适合作为维护风险雷达，不等同于完整静态分析器。

## 下一步建议

1. 用 `quality-check --self` 的结果反向拆分过大的内核文件。
2. 将 `quality-check --self` 接入 CI 或发布前流程。
3. 用真实业务项目试迁移，收集误报和漏报。
4. 再把 Paperflow 逐步迁移为该内核的使用方。
