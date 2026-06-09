# Current Implementation Status

## 当前定位

当前仓库是 `topology-kernel` 的第一版严格内核原型。它验证了最核心的想法能运行，但还没有达到目标构想中的完整框架状态。

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

### 纯函数 node 接口

已实现：

- `NodeInfo`
- `NodeContract`
- `PureNode` protocol
- runtime 通过 `run_pure(inputs, params) -> outputs` 调用 node
- node 不直接接触 `Context`
- runtime 检查 node 是否原地修改输入
- runtime 检查返回 output 是否全部声明
- runtime 检查声明 output 是否全部返回

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

已实现原型：

- `pipeline.loops`
- loop `name`
- loop `edges`
- loop `nodes`
- loop `max_iterations`
- loop `until`
- 未声明 cycle 会编译失败
- 声明 loop 后可以编译并执行

当前 loop runtime 仍是简化版本：按 `loop.nodes` 顺序重复执行节点，还没有实现边级执行计数报告和更复杂的调度策略。

### nodeset

已实现基础版：

- `nodesets`
- `nodeset.<name>` 可作为普通 node type 使用
- nodeset 内部可执行子图
- nodeset 通过 `exports` 暴露输出

当前 nodeset 仍是基础实现，还没有完整递归检测、作用域隔离和展开式健康报告。

### 纯函数静态检查

已实现初版：

- node 必须声明 `NODE_INFO`
- node 必须声明 `CONTRACT`
- node 必须提供 `run_pure`
- 禁止普通 `run(context, ...)`
- AST 检查部分 banned imports
- AST 检查部分 banned calls
- source 行数限制
- source 字节数限制

当前限制还不完整，尚未实现 node 间 import/call 依赖扫描，也没有完整 base_lib purity 扫描。

### Health Report

已实现基础版：

- 编译失败报告。
- node type 解析。
- purity violation 报告。
- unconsumed output warning。
- effective/data/explicit edge 信息。

尚未实现完整目标中的 schema、semantic、loop execution、nodeset scope、plugin policy 等健康检查。

### Mermaid 导出

已实现基础版：

- 输出 `flowchart TD`
- 显示 node name/type
- 显示 effective edges
- 显示 `max_executions`
- 显示 loop 名称
- 支持基础 `expand_nodesets`

尚未实现完整的 contract key、semantic、policy finding、boundary port 可视化。

### CLI

已实现：

```text
topology-kernel validate --config ...
topology-kernel export-mermaid --config ...
```

当前 CLI 只做结构解析和编译 smoke，不是完整 validator。

## 测试状态

当前测试文件：

```text
tests/unit/test_topology_kernel_strict.py
```

覆盖：

- pure node metadata 与 AST 检查。
- source size limit。
- data edge 自动推导。
- runtime 执行。
- 未声明 cycle 失败。
- 显式 bounded loop 通过并执行。
- nodeset 可作为 node 使用。
- health report。
- Mermaid 导出。

迁移到独立仓库后的验证：

```text
7 passed
```

Paperflow 清理内核副本后的验证：

```text
8 passed
```

## 尚未完成

高优先级缺口：

- 全局出入口 `GlobalBoundary` 接口。
- plugin policy 系统。
- node metadata schema 扩展机制。
- contract schema 扩展机制。
- 完整 JSON schema。
- node 间 import/call 禁止扫描。
- base_lib purity 扫描。
- nodeset 递归检测。
- nodeset key 作用域隔离。
- loop 边级执行次数统计。
- loop runtime 调度策略细化。
- Mermaid 完整展开和边界可视化。
- 完整 CLI validator。

## 当前风险

- 纯函数检查仍是工程约束，不是数学证明。
- AST banned list 还很短。
- runtime loop 模型仍简化。
- nodeset scope 还不够严格。
- plugin 目前还没有实现。
- 全局出入口还没有实现。

## 下一步建议

1. 先实现完整 validator，把严格规则变成硬失败。
2. 实现 `GlobalBoundary`，但保证它不进入 node registry。
3. 实现 `PolicyPlugin`。
4. 加强 AST/import/call 检查。
5. 强化 nodeset scope 与递归检测。
6. 完善 loop execution report。
7. 再把 Paperflow 逐步迁移为该内核的使用方。
