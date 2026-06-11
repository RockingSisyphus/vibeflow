# 代码质量与架构检查工具参考

本目录存放若干开源工具的浅克隆副本，用于参考代码质量、import 依赖图、模块边界、分层架构、仓库结构分析等设计。

这些仓库只是本地参考资料，不是 `topology-kernel` 的 vendored dependency，也不会参与当前包的运行。

## 已克隆仓库

| 工具 | 本地路径 | Commit | 主要参考价值 |
| --- | --- | --- | --- |
| Import Linter | `references/code_quality_tools/import-linter/` | `c6ed24d` | 基于 Python import graph 的声明式架构 contract。 |
| Grimp | `references/code_quality_tools/grimp/` | `977b7f0` | Import Linter 底层使用的可查询 Python import graph 库。 |
| Tach | `references/code_quality_tools/tach/` | `7e5aa4d` | 模块边界、显式依赖、公共接口、分层架构、依赖图输出。 |
| Pydeps | `references/code_quality_tools/pydeps/` | `56c60ff` | Python 依赖图可视化、聚类、循环依赖展示。 |
| IntentGraph | `references/code_quality_tools/IntentGraph/` | `082e0ec` | 仓库结构快照、依赖查询、聚类、面向 agent 的机器可读缓存。 |

## 对 `topology-kernel` 的参考价值

### Import Linter

建议优先查看：

- `import-linter/.importlinter`
- `import-linter/docs/contract_types/layers.md`
- `import-linter/docs/contract_types/protected.md`
- `import-linter/src/importlinter/contracts/`

可借鉴点：

- 将架构检查表达为具名 contract。
- 规则应声明式、可解释、可审计。
- 支持 layers、acyclic siblings、forbidden imports、independence、protected modules 等契约类型。
- 支持 containers，让同一套层级规则套用到多个父 package 下。
- 基于 import graph 事实报告违规，而不是依赖主观语义判断。

对本项目的启发：

- 后续 `QUALITY.STRUCTURE.*` 可以逐步形成“结构 contract”。
- `quality-check --self` 可以保留自动推断，同时允许未来增加显式结构规则配置。

### Grimp

建议优先查看：

- `grimp/README.rst`
- `grimp/src/grimp/application/graph.py`
- `grimp/src/grimp/domain/analysis.py`

可借鉴点：

- 先构建一个可查询 import graph，再让规则在 graph 上运行。
- 支持 children、descendants、direct imports、upstream modules、shortest chain、import details 等查询。
- 保留 import 的文件和行号信息，方便 finding 可操作。

对本项目的启发：

- 当前 `quality-check` 已经有 dependency graph，但还可以继续增强为 directory graph、cluster graph。
- 未来结构规则应尽量复用同一份 graph，不要每条规则重复扫描源码。

### Tach

建议优先查看：

- `tach/docs/usage/configuration.md`
- `tach/docs/usage/interfaces.md`
- `tach/docs/usage/layers.md`
- `tach/python/tests/example/*/tach.toml`
- `tach/src/checks/`
- `tach/src/config/`

可借鉴点：

- 模块声明和公共接口声明分开。
- 模块可以声明 `depends_on`、`cannot_depend_on`、`visibility`、`utility`、`unchecked`。
- 支持 layered architecture，同时仍允许显式依赖声明。
- 支持 JSON dependency map 和本地图输出。
- 将 public interface bypass 作为一等架构违规。

对本项目的启发：

- 阶段 3 的“公共入口与内部模块边界”可以参考 Tach 的 interface 模型。
- `purity.py`、`health.py`、`devtools/code_quality.py` 这类聚合入口可以被看作 public interface。
- 目录外模块绕过入口直接 import 内部 helper，可以成为 `QUALITY.STRUCTURE.PUBLIC_ENTRY_BYPASSED`。

### Pydeps

建议优先查看：

- `pydeps/README.rst`

可借鉴点：

- 依赖图输出可以控制最大距离、外部依赖、cluster/collapse。
- 支持只展示循环依赖的模式。
- 对大型图使用 cluster 概念降低噪声。
- Bacon number / hop distance 思路可用于依赖距离规则。

对本项目的启发：

- 阶段 4 的“文件位置与依赖距离匹配”可以参考 max-bacon / hop distance。
- 后续 Mermaid 或 JSON 报告可以增加结构图/目录图的简化输出。

### IntentGraph

建议优先查看：

- `IntentGraph/README.md`

可借鉴点：

- 一次分析，多次查询。
- 输出稳定 JSON，便于工具和 agent 消费。
- 支持 minimal / medium / full 多级输出。
- 支持 analysis / refactoring / navigation 等不同聚类模式。
- 支持 deterministic snapshot，便于后续做结构 diff。

对本项目的启发：

- `quality-check --json` 可以逐步扩展为稳定结构快照。
- 未来可以考虑缓存分析结果，避免大型仓库重复扫描。
- 结构检查的输出应服务人类阅读，也应服务后续 AI/工具查询。

## 与本地计划的对应关系

相关本地计划：

- `docs/file_structure_quality_plan.md`

各阶段最直接的参考来源：

- 阶段 1：目录图和结构摘要
  - 参考 Grimp、Pydeps、IntentGraph。
- 阶段 2：前缀功能簇识别
  - 参考 Pydeps 的 cluster 思路、IntentGraph 的聚类输出。
- 阶段 3：公共入口与内部模块边界
  - 参考 Tach interfaces、Import Linter protected contracts。
- 阶段 4：依赖距离与远距离内部 import
  - 参考 Pydeps max-bacon / distance filtering、Grimp shortest chains。
- 阶段 5：结构重组建议
  - 参考 Tach `report`、IntentGraph 结构化查询输出。

## 源仓库链接

- Import Linter: https://github.com/seddonym/import-linter
- Grimp: https://github.com/seddonym/grimp
- Tach: https://github.com/tach-org/tach
- Pydeps: https://github.com/thebjorn/pydeps
- IntentGraph: https://github.com/Raytracer76/IntentGraph
