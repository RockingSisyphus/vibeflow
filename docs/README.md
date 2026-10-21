# VibeFlow 文档

VibeFlow 文档按读者和用途分层。使用者文档是发行包的规范正文；设计与维护者文档只服务于 VibeFlow 仓库开发。

## 项目介绍

- [项目概览](../distribution/docs/overview.md)：目标、核心模型、适用场景和能力边界。

## 发行资源中的用户文档

用户手册的唯一原稿在 [distribution/docs](../distribution/docs/README.md)，随发行构建进入包内的 kernel/docs。这里维护当前内核设计、开发流程和待执行任务。


## 系统设计

- [系统架构](design/system-architecture.md)：当前内核分层、插件装配与共享架构资料。
- [执行模型](design/execution-model.md)：普通图调度、显式汇合、规则入口与宿主生命周期。
- [普通图并发设计](design/graph-concurrency.md)：当前 ABI 编译链路、分发局部额度、两侧执行器、取消收尾与维护验证。
- [Rule 机制设计](design/rule-system.md)：统一选择、资料与负责范围、协作、复用及维护边界。
- [Workflow 异常处理与资源收尾计划](design/workflow-error-handling-plan.md)：未来能力，待设计；包含报错、取消和浏览器监听收尾。

## 功能与迁移

- [多入口与通信](../distribution/docs/user/workflow-coordination.md)
- [本地预览实现与验收职责](maintainers/local-preview.md)


- [当前配置与接口迁移](../distribution/docs/user/rule-system-migration.md)

- [产品检查边界与 0.17 格式迁移](../distribution/docs/user/product-check-boundaries.md)

## 当前维护说明

- [项目准备与资源事实](maintainers/project-preparation.md)：完整清单、声明唯一性、依赖打包和 workflow 采用关系。

- [用户项目治理与目录规范](../distribution/docs/user/project-governance.md)：独立 root、资源所有权与四级规则。

- [综合数学沙箱说明](maintainers/comprehensive-math-sandbox.md)
- [开发与验证](maintainers/development.md)
- [架构质检的阻断边界](maintainers/quality-boundaries.md)
- [Python 检查会话与展示资料](maintainers/python-check-sessions.md)
- [JS/TS 检查会话与释放](maintainers/javascript-check-sessions.md)
- [发行与文档装配](maintainers/release.md)
- [目录职责与产物约定](maintainers/directory-layout.md)


## 文档维护

当前规范在上面的设计与维护手册中定义；退役计划、报告和代码直接删除，历史溯源使用 Git。唯一归档例外是带版本标识的压缩分发包。

- [路线与目标决定](goal-decisions.md)
- [目录职责与产物约定](maintainers/directory-layout.md)
