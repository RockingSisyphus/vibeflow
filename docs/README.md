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
- [Plugin 与宿主集成](user/plugins-and-integrations.md)
- [命令、产物与检查范围](user/commands-and-results.md)
- [人机协同协议](user/profiles/collaborative.md)
- [无人值守协议](user/profiles/autonomous.md)

## 系统设计

- [系统架构](design/system-architecture.md)
- [执行模型](design/execution-model.md)

## 内核维护

- [开发与验证](maintainers/development.md)
- [发行与文档装配](maintainers/release.md)

完整仓库门禁使用 `python tools/verify_project.py --full`。用户项目的 `quality` 命令与仓库自检器职责不同，详见相应文档。
