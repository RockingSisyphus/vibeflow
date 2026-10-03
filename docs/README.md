# VibeFlow 文档

VibeFlow 文档按读者和用途分层。使用者文档是发行包的规范正文；设计与维护者文档只服务于 VibeFlow 仓库开发。

## 项目介绍

- [项目概览](overview.md)：目标、核心模型、适用场景和能力边界。

## 使用者开发

- [快速开始](user/quickstart.md)
- [Workflow 与 Config](user/workflow-and-config.md)
- [Python Node 与 BaseLib](user/python-development.md)
- [JavaScript/TypeScript Node 与 AOT](user/javascript-development.md)
- [Nodeset 与 Loop](user/nodesets-and-loops.md)
- [Rule、Ruleset 与 Node 声明](user/rules-and-nodes.md)
- [Plugin 与宿主集成](user/plugins-and-integrations.md)
- [命令、产物与检查范围](user/commands-and-results.md)
- [人机协同协议](user/profiles/collaborative.md)
- [无人值守协议](user/profiles/autonomous.md)

## 系统设计

- [代码声明与统一插件接入重构](design/code-plugin-refactor-plan.md)
- [系统架构](design/system-architecture.md)
- [执行模型](design/execution-model.md)
- [Rule/Ruleset、Node 分类与插件重构](design/rule-system-refactor-plan.md)
- [业务分类与领域规则旧方案](design/domain-node-extensions-plan.md)：已由 Rule/Ruleset 方案替代。

- [完整修复计划](design/rule-system-repair-plan.md)
- [完整修复验收与问题矩阵](design/rule-system-repair-results.md)
- [代码插件重构与验收](design/code-plugin-refactor-results.md)
- [代码插件案例迁移对应表](design/code-plugin-case-migrations.md)
- [0.15 声明与规则迁移](user/rule-system-migration.md)
- [基线规则总表](design/baseline-rule-inventory.md)
- [Core 规则盘点](design/baseline-rule-inventory-core.md)
- [Python 规则盘点](design/baseline-rule-inventory-python.md)
- [JavaScript 规则盘点](design/baseline-rule-inventory-javascript.md)
- [Tooling 规则盘点](design/baseline-rule-inventory-tooling.md)
- [第二次覆盖审计](design/baseline-rule-coverage-second-audit.md)

## 内核维护

- [开发与验证](maintainers/development.md)
- [架构质检的阻断边界](maintainers/quality-boundaries.md)
- [发行与文档装配](maintainers/release.md)

完整仓库门禁使用 `python tools/verify_project.py --full`。用户项目的 `quality` 命令与仓库自检器职责不同，详见相应文档。
