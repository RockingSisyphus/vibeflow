# VibeFlow 文档

VibeFlow 文档按读者和用途分层。使用者文档是发行包的规范正文；设计与维护者文档只服务于 VibeFlow 仓库开发。

## 项目介绍

- [项目概览](overview.md)：目标、核心模型、适用场景和能力边界。

## 使用者开发

- [快速开始](user/quickstart.md)
- [Workflow 与 Config](user/workflow-and-config.md)
- [Python 资源与插件 SDK](user/python-development.md)
- [JavaScript/TypeScript 资源与 AOT](user/javascript-development.md)
- [Nodeset 与 Loop](user/nodesets-and-loops.md)
- [Rule、Ruleset 与 Node 声明](user/rules-and-nodes.md)
- [Plugin 与宿主集成](user/plugins-and-integrations.md)
- [多文件资源、源码归属与展示](user/multifile-resources.md)
- [运行日志与状态接口](user/runtime-observation.md)
- [命令、产物与检查范围](user/commands-and-results.md)
- [人机协同协议](user/profiles/collaborative.md)
- [无人值守协议](user/profiles/autonomous.md)

## 系统设计

- [系统架构](design/system-architecture.md)：当前内核分层、插件装配与共享架构资料。
- [执行模型](design/execution-model.md)：原生路由、任务、规则入口与宿主生命周期。

## 设计演进与验收记录

以下记录保留各阶段基线、决定与验证资料。当前使用接口以使用者手册为准，当前内核机制见系统设计。

- [运行观测与类型注解修复记录](design/runtime-observation-results.md)
- [RuleContext 共享对象图修复](design/readonly-facts-results.md)

- [多文件资源、统一展示与沙箱验收](design/multifile-resources-plan.md)
- [多文件资源案例与迁移对应表](design/multifile-resource-cases.md)
- [多文件资源实现与验收](design/multifile-resources-results.md)
- [代码声明与统一插件接入重构](design/code-plugin-refactor-plan.md)
- [代码插件重构与验收](design/code-plugin-refactor-results.md)
- [代码插件案例迁移对应表](design/code-plugin-case-migrations.md)
- [Rule/Ruleset 初期重构](design/rule-system-refactor-plan.md)：JSONC 接入已演进为代码插件。
- [完整修复计划](design/rule-system-repair-plan.md)
- [完整修复验收与问题矩阵](design/rule-system-repair-results.md)
- [业务分类与领域规则旧方案](design/domain-node-extensions-plan.md)：业务含义现由完整 Node 与领域 Rule 表达。
- [0.16 统一资源接入与旧接口迁移](user/rule-system-migration.md)
- [基线规则总表](design/baseline-rule-inventory.md)
- [Core 规则盘点](design/baseline-rule-inventory-core.md)
- [Python 规则盘点](design/baseline-rule-inventory-python.md)
- [JavaScript 规则盘点](design/baseline-rule-inventory-javascript.md)
- [Tooling 规则盘点](design/baseline-rule-inventory-tooling.md)
- [第二次覆盖审计](design/baseline-rule-coverage-second-audit.md)

## 内核维护

- [系统迁移审计](maintainers/system-migration-audit-20261007.md)
- [Python 迁移审计详情](maintainers/system-migration-audit-20261007/python.md)
- [JavaScript 迁移审计详情](maintainers/system-migration-audit-20261007/javascript.md)
- [Core 与 Tooling 迁移审计详情](maintainers/system-migration-audit-20261007/core-tooling.md)
- [统一架构迁移实现与验收](maintainers/system-migration-results-20261007.md)
- [系统迁移修复独立复核](maintainers/system-migration-recheck-20261008.md)
- [独立复核残余修复与验收](maintainers/system-migration-recheck-repair-20261008.md)
- [多轮系统迁移全范围审计](maintainers/system-migration-wide-audit-20261008.md)
- [迁移残余整改与契约统一](maintainers/system-migration-remediation-20261008.md)
- [迁移整改代码独立复核](maintainers/system-migration-remediation-review-20261008.md)
- [函数作用域修复独立复核](maintainers/python-function-definition-scope-review-20261008.md)
- [Python 推导式作用域修正](maintainers/python-comprehension-scope-fix-20261008.md)
- [Python 推导式修复独立审核](maintainers/python-comprehension-scope-review-20261008.md)
- [Python 函数定义表达式作用域修正](maintainers/python-function-definition-scope-fix-20261008.md)
- [开发与验证](maintainers/development.md)
- [架构质检的阻断边界](maintainers/quality-boundaries.md)
- [Python 检查会话与展示资料](maintainers/python-check-sessions.md)
- [用户项目 SVG 的展示边界修正](maintainers/user-svg-boundary-20261006.md)
- [正式 SVG 分片资源泄漏修复](maintainers/review-layout-fix-20261006.md)
- [资源分区与 Nodeset 展示控制](maintainers/resource-sections-20261006.md)：实现文件与规则的 SVG 投影已撤销，保留历史验收；Nodeset 展示控制仍有效。
- [源码审查与架构生成性能验收](maintainers/python-review-performance-results.md)
- [SDK、Rule 与资源装配适配修复](maintainers/adaptation-repair-20261005.md)
- [JS/TS 检查会话与释放](maintainers/javascript-check-sessions.md)
- [发行与文档装配](maintainers/release.md)

完整仓库门禁使用 `python tools/verify_project.py --full`。用户项目的 `quality` 命令与仓库自检器职责不同，详见相应文档。

- [Tooling / JavaScript SDK and Rule adaptation audit](maintainers/adaptation-audit-20261005/javascript-audit.md)
- [Rule、SDK 与资源装配适配审查](maintainers/adaptation-audit-20261005.md)
- [适配修复：案例、接口与验收对应](maintainers/adaptation-repair-20261005/case-matrix.md)
