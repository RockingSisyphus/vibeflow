# VibeFlow 文档

VibeFlow 文档按读者和用途分层。使用者文档是发行包的规范正文；设计与维护者文档只服务于 VibeFlow 仓库开发。

## 项目介绍

- [项目概览](../distribution/docs/overview.md)：目标、核心模型、适用场景和能力边界。

## 发行资源中的用户文档

用户手册的唯一原稿在 [distribution/docs](../distribution/docs/README.md)，随发行构建进入包内的 kernel/docs。这里维护内核设计、开发流程、审核结论和历史证据。

## 系统设计

- [系统架构](design/system-architecture.md)：当前内核分层、插件装配与共享架构资料。
- [执行模型](design/execution-model.md)：普通图调度、显式汇合、规则入口与宿主生命周期。
- [普通图并发设计](design/graph-concurrency.md)：ABI v8 编译链路、分发局部额度、两侧执行器、取消收尾与维护验证。
- [Rule 机制设计](design/rule-system.md)：统一选择、资料与负责范围、协作、复用及维护边界。

## 设计演进与验收记录

以下记录保留各阶段基线、决定与验证资料。当前使用接口以使用者手册为准，当前内核机制见系统设计。

- [本地预览实现与验收](maintainers/local-preview.md)

- [运行观测与类型注解修复记录](design/history/runtime-observation-results.md)
- [RuleContext 共享对象图修复](design/history/readonly-facts-results.md)

- [多文件资源、统一展示与沙箱验收](design/history/multifile-resources-plan.md)
- [多文件资源案例与迁移对应表](design/history/multifile-resource-cases.md)
- [多文件资源实现与验收](design/history/multifile-resources-results.md)
- [代码声明与统一插件接入重构](design/history/code-plugin-refactor-plan.md)
- [代码插件重构与验收](design/history/code-plugin-refactor-results.md)
- [代码插件案例迁移对应表](design/history/code-plugin-case-migrations.md)
- [Rule/Ruleset 初期重构](design/history/rule-system-refactor-plan.md)：JSONC 接入已演进为代码插件。
- [完整修复计划](design/history/rule-system-repair-plan.md)
- [完整修复验收与问题矩阵](design/history/rule-system-repair-results.md)
- [业务分类与领域规则旧方案](design/history/domain-node-extensions-plan.md)：业务含义现由完整 Node 与领域 Rule 表达。
- [0.16 统一资源接入与旧接口迁移](../distribution/docs/user/rule-system-migration.md)
- [基线规则总表](design/history/baseline-rule-inventory.md)
- [Core 规则盘点](design/history/baseline-rule-inventory-core.md)
- [Python 规则盘点](design/history/baseline-rule-inventory-python.md)
- [JavaScript 规则盘点](design/history/baseline-rule-inventory-javascript.md)
- [Tooling 规则盘点](design/history/baseline-rule-inventory-tooling.md)
- [第二次覆盖审计](design/history/baseline-rule-coverage-second-audit.md)

- [产品检查边界与 0.17 格式迁移](../distribution/docs/user/product-check-boundaries.md)

## 当前维护说明

- [综合数学沙箱说明](maintainers/comprehensive-math-sandbox.md)
- [VibeFlow 职责边界与整改规格](maintainers/product-boundary-refactor-spec-20261009.md)：完整职责定义、11 项源码定位、当前与目标逻辑、删改停止点和实施后验收。
- [双语言 AOT 与维护整理实施记录](maintainers/aot-unification-implementation.md)
- [1.0.2 发布说明](maintainers/history/release-1.0.2.md)：普通并发节点的双圆图形修复。
- [1.0.1 发布说明](maintainers/history/release-1.0.1.md)：并发迁移、局部队列与真实沙箱验收。
- [1.0.0 发布说明](maintainers/history/release-1.0.0.md)
- [开发与验证](maintainers/development.md)
- [架构质检的阻断边界](maintainers/quality-boundaries.md)
- [Python 检查会话与展示资料](maintainers/python-check-sessions.md)
- [JS/TS 检查会话与释放](maintainers/javascript-check-sessions.md)
- [发行与文档装配](maintainers/release.md)
- [目录职责整改计划](maintainers/directory-remediation-plan-20261009.md)
- [历史证据索引](maintainers/evidence/index.md)
- [目录职责与产物约定](maintainers/directory-layout.md)
- [目录整改结果](maintainers/directory-remediation-results-20261009.md)
- [目录清理与删除原则](maintainers/directory-cleanup-20261010.md)

## 历史审核与实施记录

- [跨 root 任务目标源码归属复现与根因](maintainers/history/task-ownership-reproduction-20261014.md)：静态回归、正式修复与原项目复验。
- [任务结果一次交付与回收](maintainers/history/task-result-delivery-20261014.md)：0.20.0 消费语义、长期 workflow 任务卡回收与独立全量验证。
- [0.20.0 中英文发布说明](maintainers/history/release-0.20.0.md)：相对上次正式分发版本 v0.18.3 的 Git 历史变化。
- [0.19.0 发布包构建与验证](maintainers/history/release-0.19.0.md)
- [原生任务管理实施与验收记录](maintainers/history/task-management-implementation-20261014.md)：ABI v6、双 Target 并发管理、历史失败与第四轮完整验收。
- [0.18.3 历史发行记录](maintainers/history/release-0.18.3.md)
- [Rule 机制统一重构目标与实施记录](maintainers/history/rule-mechanism-refactor.md)
- [Rule 机制统一重构实施与验证结果](maintainers/history/rule-mechanism-refactor-results.md)
- [测试审核大表](maintainers/history/audits/test-inventory-20261009/大表.md)
- [测试审核分类小表](maintainers/history/audits/test-inventory-20261009/分类小表.md)
- [沙箱任务盘点（2026-10-09）](maintainers/history/audits/sandbox-task-inventory-20261009.md)
- [沙箱任务盘点（2026-10-10）](maintainers/history/audits/sandbox-task-inventory-20261010.md)
- [工作流沙箱任务盘点（历史 150 项）](maintainers/history/audits/sandbox-task-inventory-workflow-20261010.md)
- [工作流数学沙箱迁移记录](maintainers/history/audits/workflow-math-20261010.md)

- [简单数学沙盒整合](maintainers/history/audits/addition-sandboxes-20261009.md)：五个独立入口、18 项替代关系、断言迁移与实际验证。
- [分段数学与工作流整合](maintainers/history/audits/piecewise-math-20261010.md)：一个入口替代 11 项正常调度任务，保留编译源码、trace、互斥汇合和数据旁路检查。

- [综合数学沙箱与重复案例整合](maintainers/history/audits/comprehensive-sandbox-20261009.md)：双 Target 独立项目、逐项替代关系、诊断/运行通过条件及本次真实验证。
- [测试审核与分类记录（2026-10-09）](maintainers/history/audits/test-inventory-20261009/README.md)：tests、sandbox 与独立 fixtures 的当时条件、执行层级、通过判定及阅读工作簿；当时只收集，没有重跑成绩。
- [职责边界整改独立审核](maintainers/history/product-boundary-remediation-review-20261009.md)：确认主要整改生效，记录 5 项问题及整改前后对照，其中 2 项为新引入误判。
- [产品职责边界整改执行计划](maintainers/history/product-boundary-remediation-plan-20261009.md)
- [产品职责边界首次整改结果](maintainers/history/product-boundary-remediation-results-20261009.md)：原批次成绩与旧包的历史记录，后续缺陷见独立审核。
- [职责边界审核修正](maintainers/history/product-boundary-review-fixes-20261009.md)：R01—R05 修正、正反对照、实际验收边界及新交付物。
- [审核修正的独立复核](maintainers/history/product-boundary-review-fixes-recheck-20261009.md)：确认原问题修复，记录两项新增有限规则漏检及修改前后证据。
- [两项保留规则退化修复的独立审核](maintainers/history/product-boundary-followup-review-20261009.md)：确认 R06、R07 修复，记录全套测试覆盖、正常对照及最新包核验。

- [VibeFlow 职责边界与收缩建议](maintainers/history/product-boundary-audit-20261009.md)：按代码质量／架构限制器定位重新分类现有规则，列出保留、收缩与退役范围。
- [系统迁移审计](maintainers/history/system-migration-audit-20261007.md)
- [Python 迁移审计详情](maintainers/history/system-migration-audit-20261007/python.md)
- [JavaScript 迁移审计详情](maintainers/history/system-migration-audit-20261007/javascript.md)
- [Core 与 Tooling 迁移审计详情](maintainers/history/system-migration-audit-20261007/core-tooling.md)
- [统一架构迁移实现与验收](maintainers/history/system-migration-results-20261007.md)
- [系统迁移修复独立复核](maintainers/history/system-migration-recheck-20261008.md)
- [独立复核残余修复与验收](maintainers/history/system-migration-recheck-repair-20261008.md)
- [多轮系统迁移全范围审计](maintainers/history/system-migration-wide-audit-20261008.md)
- [迁移残余整改与契约统一](maintainers/history/system-migration-remediation-20261008.md)
- [迁移整改代码独立复核](maintainers/history/system-migration-remediation-review-20261008.md)
- [函数作用域修复独立复核](maintainers/history/python-function-definition-scope-review-20261008.md)
- [Python 推导式作用域修正](maintainers/history/python-comprehension-scope-fix-20261008.md)
- [Python 推导式修复独立审核](maintainers/history/python-comprehension-scope-review-20261008.md)
- [Python 别名事实修复独立审核](maintainers/history/python-alias-facts-review-20261008.md)
- [Python 异常出口修复独立审核](maintainers/history/python-exception-alias-review-20261009.md)
- [Python 别名事实与输入突变统一](maintainers/history/python-alias-facts-fix-20261008.md)
- [Python 异常出口中的输入别名修复](maintainers/history/python-exception-alias-fix-20261008.md)
- [Python 函数定义表达式作用域修正](maintainers/history/python-function-definition-scope-fix-20261008.md)
- [用户项目 SVG 的展示边界修正](maintainers/history/user-svg-boundary-20261006.md)
- [正式 SVG 分片资源泄漏修复](maintainers/history/review-layout-fix-20261006.md)
- [资源分区与 Nodeset 展示控制](maintainers/history/resource-sections-20261006.md)：实现文件与规则的 SVG 投影已撤销，保留历史验收；Nodeset 展示控制仍有效。
- [源码审查与架构生成性能验收](maintainers/history/python-review-performance-results.md)
- [SDK、Rule 与资源装配适配修复](maintainers/history/adaptation-repair-20261005.md)

完整仓库门禁使用 `python tools/verify_project.py --full`。用户项目的 `quality` 命令与仓库自检器职责不同，详见相应文档。

- [Tooling / JavaScript SDK and Rule adaptation audit](maintainers/history/adaptation-audit-20261005/javascript-audit.md)
- [Rule、SDK 与资源装配适配审查](maintainers/history/adaptation-audit-20261005.md)
- [适配修复：案例、接口与验收对应](maintainers/history/adaptation-repair-20261005/case-matrix.md)

- [整改执行计划](maintainers/history/product-boundary-remediation-plan-20261009.md)
- [已批准的七文件测试迁移](maintainers/history/product-boundary-remediation-20261009/test-retirement-review.md)
- [首轮全量后的混合测试迁移审查](maintainers/history/product-boundary-remediation-20261009/additional-test-migration-review.md)


- [原多文件资源沙盒记录](maintainers/history/multifile-resource-sandbox.md)

## 目录用途与边界

仅用于：VibeFlow 开发设计、维护记录和资料导航；提供给用户的文档原稿归 distribution/docs。

- 新文件按上述用途归属；新增子目录同时写明职责，不能作为临时收纳箱。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](maintainers/directory-layout.md)。
