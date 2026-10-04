# VibeFlow 项目概览

VibeFlow 把 AI 参与开发的程序组织成一张可执行、可检查、可生成架构视图的显式流程图。业务逻辑位于小型 Node 中，Config 声明控制流，端口契约声明数据流，Core 在运行或构建前验证结构。

## 核心模型

```text
terminal start → input I/O → process / nodeset → output I/O → terminal end
```

- **Node**：具有明确职责和端口契约的原子处理单元。
- **Nodeset**：由 Node、其他 Nodeset 或 Loop 组成的可复用流程块。
- **Config**：声明调用实例、显式 edge、公共输入输出和资源选择。
- **Rule / Ruleset**：用普通代码定义检查逻辑，用规则图组合依赖与覆盖关系；资源选择自己的审查规则。
- **Plugin**：以 Python 或 JS/TS 代码声明固定资源，由 workflow 显式启用；也可提供编译与运行生命周期。
- **BaseLib / Host**：辅助库提供共享实现；JS/TS Host 管理宿主生命周期、Capability 和即时事件。
- **Architecture**：从真实 Config、资源声明及源码依赖生成的审查视图。
- **Target**：执行或生成工作流的语言后端。当前正式 Target 为 Python Runtime 和 JavaScript AOT。

Node 类型信息是端口契约和语义的来源；Config 中的 `display_name` 与 `description` 说明一次调用在当前工作流中的用途。已实现 Node 和 Nodeset 调用从类型定义取得契约，planned 与系统调用在 Config 中显式声明必要结构。

## VibeFlow 提供什么

- 配置、登记与契约形状检查；
- 显式控制流、数据可达性和合流检查；
- 可组合的源码、架构和领域 Ruleset；
- Node、BaseLib、Plugin 与 Host 的多文件实现、源码归属和逐文件质量检查；
- Python 运行时和 JavaScript/TypeScript AOT 构建；
- 保存规则及样式来源的 Architecture JSONC，以及展示工作流和资源依赖的展开 SVG；
- 可追踪的运行产物与工作流执行探针。

VibeFlow 检查工程结构、源码健康度与所选领域约束。项目测试与真实环境验证负责业务结果、需求符合性和外部接口行为。

## 两个开发 profile

- **collaborative**：使用变更清单、planned 架构审核、正式 SVG 和人工批准门。
- **autonomous**：AI 直接维护真实 source，自动更新架构并完成适用门禁。

两个 profile 使用同一 Core、quality policy、项目模板和 Workflow ABI `vibeflow.workflow.v4`。profile 只改变开发协议、提示词和随包文档选择。

从发行包开始开发时，先阅读[快速开始](user/quickstart.md)，再按任务进入对应接口文档。
