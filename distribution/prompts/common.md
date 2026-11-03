# VibeFlow 开发入口

## 核心目标

把程序组织为可执行、可检查、可审阅的显式工作流，使业务职责、数据契约、控制关系和源码来源清晰可追踪。以小型 Node 承载单一职责，以 Nodeset 复用流程，保持架构视图与实际程序一致。

## 开发规范

- 开始开发先遵循[架构阅读与维护指南](kernel/docs/user/architecture.md)，再按任务修改真实源码。
- 从 `vibeflow_config.jsonc` 确定任务所属 root 和 Target，阅读该 root 的 README、项目配置及目标目录适用的 `AGENTS.md`。
- `DISTRIBUTION.json` 是只读发行身份记录；root 注册和改名按[项目治理](kernel/docs/user/project-governance.md)操作。
- 将执行关系、资源依赖和外部边界明确表达在工作流及资源声明中；相同业务职责优先复用已有 Node、Nodeset 或 BaseLib。
- 按当前开发协议推进，完成与修改相称的检查、构建和执行验证，分别报告机器检查、实际执行与业务验收结果。
- 同步维护受影响的调用、契约和项目说明，使文档、架构与最终行为一致。

## 按目标查阅

文档入口为 [用户手册](kernel/docs/README.md)。按当前任务选择：

| 目标 | 文档 |
| --- | --- |
| 了解模型与能力 | [项目概览](kernel/docs/overview.md) |
| 优先了解项目、root 与 workflow 的架构 | [架构阅读与维护](kernel/docs/user/architecture.md) |
| 首次运行项目 | [快速开始](kernel/docs/user/quickstart.md) |
| 组织项目、root 与共享资源 | [项目治理](kernel/docs/user/project-governance.md) |
| 编写 workflow、输入输出和连边 | [Workflow 与 Config](kernel/docs/user/workflow-and-config.md) |
| 开发 Python Node、BaseLib 或部署 AOT | [Python 开发](kernel/docs/user/python-development.md) |
| 开发 JS/TS Node 或构建 AOT | [JavaScript 开发](kernel/docs/user/javascript-development.md) |
| 复用子图与循环 | [Nodeset 与 Loop](kernel/docs/user/nodeset-types-and-loops.md) |
| 定义、组合或选择检查规则 | [Rule 与 Node](kernel/docs/user/rules-and-nodes.md) |
| 开发 Plugin、生命周期或宿主 API | [Plugin 与集成](kernel/docs/user/plugins-and-integrations.md) |
| 拆分实现文件、声明库依赖或设置资源样式 | [多文件资源](kernel/docs/user/multifile-resources.md) |
| 管理分支并发、汇合与取消 | [普通图并发](kernel/docs/user/graph-concurrency.md) |
| 配置命名入口、调用或通信 | [Workflow 协同](kernel/docs/user/workflow-coordination.md) |
| 接入日志、状态与业务进度 | [运行观测](kernel/docs/user/runtime-observation.md) |
| 生成审核材料、浏览流程与历史 | [本地预览](kernel/docs/user/local-preview.md) |
| 选择命令、读取检查与执行结果 | [命令与结果](kernel/docs/user/commands-and-results.md) |
| 了解静态检查的覆盖范围 | [产品检查边界](kernel/docs/user/product-check-boundaries.md) |
| 升级旧配置与产物 | [迁移说明](kernel/docs/user/rule-system-migration.md) |
