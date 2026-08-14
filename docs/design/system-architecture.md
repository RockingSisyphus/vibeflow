# 系统架构

本文面向 VibeFlow 内核设计与维护人员，说明稳定分层和信息来源；用户项目开发使用 `docs/user/`。

## 分层

```text
Tooling → targets/python ──────┐
        → targets/javascript ─┴→ Block Compiler → Core
```

- **Core**：语言无关模型、契约、有效图、图算法、finding 和 quality policy。
- **Block Compiler**：把已验证 workflow 编译为公共 `WorkflowPlan` / `BlockPlan`。
- **Python Target**：Registry 适配、源码事实、BindingPlan 和 Runtime。
- **JavaScript Target**：descriptor catalog、源码事实、BindingPlan、AOT emitter 与工具链协议。
- **Tooling**：workspace 文件、CLI、架构展示和 Target-specific Application 编排。

依赖只沿图中方向流动。语言实现、Python callable、JavaScript source 和 bundler 配置不进入 Core 公共模型。

## 唯一有效图

Core 在拓扑分析前解析调用契约：

- implemented Node 从 Registry 或 descriptor 继承；
- Nodeset 调用从定义继承；
- planned 与系统调用使用 Config 契约。

编译结果携带有效图和编译拓扑。Runtime、AOT、review、Architecture 和静态检查消费同一份有效事实，避免调用点与类型登记形成两套真相。

## 公共计划

Workflow ABI 为 `vibeflow.workflow.v4`。公共计划只保存稳定 ID、可移植值、端口、路由、合流、TaskPlan、Loop、SourceRef、effect scope 与 execution-lock 事实。Target BindingPlan 保存语言实现。

Python 和 JavaScript Target 使用相同 Core 语义，但分别声明可执行 feature。Target 不支持的 implemented 语义以稳定 finding 拒绝；planned 内容仍可进入架构审核。

## 架构事实

Architecture 从真实 Config、Nodeset、Node 类型、资源登记和编译事实确定性生成。生成文档不是可执行配置，也不是可编辑 source。新鲜度检查通过重新生成并比较 canonical bytes 完成。

公开状态范围模型位于 Core/Tooling 共享边界，使 Python 与 JavaScript presenter 使用相同 coverage ID，同时只报告本次命令实际完成的检查。
