# 用户文档原稿

这些手册随发行构建进入 kernel/docs。仓库开发资料见 [开发文档](../../docs/README.md)。

- [overview](overview.md)
- [quickstart](user/quickstart.md)
- [命名入口与 Workflow 通信](user/workflow-coordination.md)：接口、授权、宿主、消息、目标展开和原生 IO 迁移。
- [workflow-and-config](user/workflow-and-config.md)
- [python-development](user/python-development.md)
- [javascript-development](user/javascript-development.md)
- [普通图并发](user/graph-concurrency.md)：1.0.1 的局部额度、排队补位、独立汇合、断路错误和旧配置迁移。
- [nodesets-and-loops](user/nodesets-and-loops.md)
- [plugins-and-integrations](user/plugins-and-integrations.md)
- [multifile-resources](user/multifile-resources.md)
- [Rule、Ruleset 与 Node](user/rules-and-nodes.md)：两种默认、三处配置选择，以及 Python/TypeScript 插件定义与接入。
- [rule-system-migration](user/rule-system-migration.md)
- [runtime-observation](user/runtime-observation.md)
- [本地预览与历史](user/local-preview.md)：离线页面、结构化展开、分类时间线和跨 workflow 关联。
- [commands-and-results](user/commands-and-results.md)
- [product-check-boundaries](user/product-check-boundaries.md)
- [collaborative](user/profiles/collaborative.md)
- [autonomous](user/profiles/autonomous.md)

## 目录用途与边界

仅用于：随发行包发布的用户文档原稿和阅读导航；开发设计、审核和实施记录归根目录 docs。

- 新文件按上述用途归属；新增子目录同时写明职责，不能作为临时收纳箱。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](../../docs/maintainers/directory-layout.md)。
