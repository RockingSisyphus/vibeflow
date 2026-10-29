# 用户文档原稿

这些手册随发行构建进入 `kernel/docs`。每份手册集中说明一个主题；关联文档通过定位链接导航。仓库开发资料见[开发文档](../../docs/README.md)。

| 目标 | 主要文档 |
| --- | --- |
| 了解 VibeFlow 的模型和能力 | [项目概览](overview.md) |
| 优先了解项目、root 与 workflow 的架构 | [架构阅读与维护](user/architecture.md) |
| 运行发行包中的示例项目 | [快速开始](user/quickstart.md) |
| 组织 root、目录、共享资源与治理配置 | [项目治理](user/project-governance.md) |
| 编写调用、公共契约与控制／数据连边 | [Workflow 与 Config](user/workflow-and-config.md) |
| 编写 Python 实现、异步生命周期与 AOT 部署 | [Python 开发](user/python-development.md) |
| 编写 JS/TS 实现、配置工具链与 AOT 构建 | [JavaScript 开发](user/javascript-development.md) |
| 定义可复用子图与循环 | [Nodeset 与 Loop](user/nodeset-types-and-loops.md) |
| 定义、组合、选择规则及效果政策 | [Rule 与 Node](user/rules-and-nodes.md) |
| 声明 Plugin、生命周期与宿主 API | [Plugin 与集成](user/plugins-and-integrations.md) |
| 登记实现文件、库依赖与样式 | [多文件资源](user/multifile-resources.md) |
| 配置分发、汇合、额度、取消与执行锁 | [普通图并发](user/graph-concurrency.md) |
| 配置命名入口、实例身份、调用与通信 | [Workflow 协同](user/workflow-coordination.md) |
| 读取日志、状态，提交业务进度 | [运行观测](user/runtime-observation.md) |
| 交付审核快照、浏览流程及历史 | [本地预览](user/local-preview.md) |
| 选择命令并解释检查和执行结果 | [命令与结果](user/commands-and-results.md) |
| 了解源码分析覆盖与工具链检查范围 | [产品检查范围](user/product-check-boundaries.md) |
| 迁移旧配置、接口与产物格式 | [迁移说明](user/rule-system-migration.md) |
| 采用实现前人工审阅 | [人机协同协议](user/profiles/collaborative.md) |
| 自主完成授权范围内的开发 | [无人值守协议](user/profiles/autonomous.md) |

## 目录用途与边界

仅用于：随发行包发布的用户文档原稿和阅读导航；开发设计、审核和实施记录归根目录 docs。

- 新文件按上述用途归属；新增子目录同时写明职责，不能作为临时收纳箱。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](../../docs/maintainers/directory-layout.md)。
