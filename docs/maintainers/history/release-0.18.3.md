# VibeFlow v0.18.3

## 中文更新说明

本次说明以 GitHub 上一次正式发行 `v0.13.2`（`39295b4`）为基线，覆盖其后到 `v0.18.3` 的 Git 历史；中间的 0.14–0.18 本地版本没有单独发布为 GitHub Release。本次包含公开 API 的破坏性迁移，旧项目升级时请参照包内 `kernel/docs/user/rule-system-migration.md`。

### 主要改动

- **统一 Rule / Ruleset 体系。** 规则可以声明依赖、参数、阶段入口和负责范围，多个检查通过结构化 Record 共享结果；Workflow、Nodeset 和 Node 调用可显式选择或替代默认规则。Core 提供通用机制，Python / JavaScript 的具体规则、规则组合和节点声明归各自 Target 所有。
- **资源改为代码插件声明。** Python `Plugin` 与 JS/TS `definePlugin` 贡献 Node、Rule、Ruleset、BaseLib、DataSchema、Capability 和 HostExtension，Workflow 显式选择插件。移除旧项目注册表、JSONC 资源 bundle、ID-only 插件选择及旧接口适配层；资源声明和原生实现使用统一装配路径。
- **支持完整的多文件资源审查。** Node、BaseLib、Plugin 和 Host 可登记 `implementation_files`、依赖与展示信息。资源查询、规则预览、Architecture 和 SVG 使用共同的所有权与来源信息，保留支撑文件和有效规则选择；SVG 资源区仅展示当前 Workflow 使用的资源。
- **收窄检查边界并修复误报。** 检查围绕声明的架构、原生运行协议和已选择的有限源码规则，不推断任意业务算法的正确性。修复 Python 函数定义、生成器/推导式、输入身份和效果分析等问题，以及 JavaScript `python_io` 动态宿主槽读取误报。初始输入按调度边识别；汇合检查保留祖先路径条件，减少能由图证明互斥的分支误报。
- **规则事实视图与职责拆分。** Python 和 JavaScript 共用准备后的事实视图身份管理，减少重复摘要与缓存身份计算；拆分语言分析、检查会话和共享算法。Python 固定输入验证显示耗时改善，JavaScript 尚未证明稳定的端到端提速。
- **完善发行与真实项目回归。** 独立仓库检查工具迁至 `repo_check/`；pytest 使用隔离工作目录，支持并行运行。永久 Python / JavaScript 沙箱覆盖公开 SDK、CLI、规则与插件、多文件资源、嵌套 Workflow 和执行轨迹；两个发行 profile 共用内核、最小项目和用户文档。

### 本次包含的近期修复

- **Architecture 新鲜度误报：** 排除临时解包 SDK 对用户源码事实的污染，补齐解包资源目录，并固定 Nodeset 首次引用顺序。覆盖生成后立即 `--check`、重复导出和不同 `PYTHONHASHSEED` 下的稳定性；真实 Workflow 改动仍能检出。
- **同端点条件边丢失：** 仅合并完整 `EdgeSpec` 相等的声明，不再按两个端点合成条件或角色。不同 `when`、`schedule`、`transfer` 的路线完整保留；Python 数据投递使用自己的传输路线。多条匹配路线仍避免重复执行和重复接收同一 envelope，并加入永久 JavaScript 沙箱回归。
- **嵌套插件配置导出失败：** 修复内层只读映射无法写入 `compiled_graph.json`、导致业务节点尚未执行就失败的问题。独立公共模块 `vibeflow.core.descriptors.json_values` 提供 `freeze_json`、`freeze_mapping` 和 `thaw_json`；只读配置保持受保护，导出或编辑使用独立普通 JSON 副本。

### 升级注意事项

- 当前协议为 **Workflow ABI v5、Rule ABI v2、Plugin ABI v3**。
- 用所属语言的 SDK 声明资源，并通过顶层 Workflow 的 `plugins` 显式选择；不要继续使用旧 `descriptors` / registry / bundle 资源发现。
- Node 直接声明自己的 `rulesets` 和展示信息；旧 Node category 与 `NodeInfo` / `NodeContract` 等入口已退役。`flow_kind` 不再自动赋予副作用权限，权限由有效 Ruleset 表达。
- 每项 `pipeline.inputs` 必须明确填写布尔值 `required`；Host 选择统一放在 `workflow.host_extensions`。
- Rule 与 Ruleset 参数、替代和图范围有明确的新契约；迁移后用 `review-rules` 检查有效选择，再执行 validate、quality 和实际运行。Architecture 是生成物，修改真实配置或声明后重新生成。

### 发行资产与验证

- `vibeflow-distribution-0.18.3.zip`：人机协作开发包。
- `vibeflow-distribution-autonomous-0.18.3.zip`：无人值守开发包。
- `SHA256SUMS-0.18.3.txt`：两个 ZIP 的 SHA256。

两包由项目工具 `python -B distribution/build.py` 构建。构建自检 0 error / 0 warning / 0 info，最小 Python 项目验证与实际运行通过。发布前重新核对两包与当前源码、用户文档、profile 和发行树的一致性。

2026-10-13 发布前的发行相关回归：**54 passed，0 skipped**。2026-10-11 完整源码回归：**4385 passed、22 skipped**；新 ZIP 的嵌套插件配置实际运行共 **36 项通过**（每包 6 类配置 × plan / compiled / block）。该完整回归含跳过项目，不能视为所有 SVG / 浏览器环境均已覆盖；上述测试也不代替下游项目业务验收。

### Git 历史依据

- `788a1ab`、`28ebb58`、`1b0aa73`：声明式规则、Target 迁移及规则执行修复。
- `3ee7396`、`1febc99`、`2ed8fc0`：代码资源声明、多文件资源和 SDK 指南。
- `9c443f3`、`5b9f976`、`ae20da4`：JSON 默认值、规则契约、产品边界和源码分析修复。
- `665e06e`、`b096ec2`、`1b7b297`、`6b7b92c`：目录整理、0.18 规则选择、事实视图及 Target 规则归属。
- 本版提交：Architecture 稳定性、条件路线、汇合检查、嵌套配置与永久沙箱回归。

[完整提交比较：v0.13.2 → v0.18.3](https://github.com/RockingSisyphus/vibeflow/compare/v0.13.2...v0.18.3)

## English release notes

This release compares against the previous GitHub release, **v0.13.2 (`39295b4`)**, and includes the intervening local 0.14–0.18 development history. It contains breaking public API changes. Existing projects should follow `kernel/docs/user/rule-system-migration.md` in the distribution.

### Highlights

- Unified declarative Rules and Rulesets with dependencies, parameters, phase entrypoints, explicit scopes and shared Records. Workflow, Nodeset and Node calls can select or replace defaults. Core owns the generic mechanism; concrete rules, rulesets and node declarations belong to their Python or JavaScript Target.
- Replaced legacy resource registries and JSONC bundles with Python `Plugin` and JS/TS `definePlugin` declarations selected explicitly by each Workflow. Both SDKs contribute Nodes, Rules, Rulesets, BaseLibs, schemas, capabilities and host extensions through a common assembly path.
- Added audited multi-file resources through `implementation_files`, dependencies and presentation metadata. Resource inspection, rule previews, Architecture and SVG share ownership and provenance information; SVG resource sections show resources used by the current Workflow.
- Limited checks to declared architecture, native execution protocols and selected finite source rules. Fixed Python scope, input identity and effect-analysis issues, JavaScript dynamic host-slot false positives, initial-input qualification and branch-join analysis.
- Introduced shared prepared fact-view identity management and separated analysis, sessions and shared algorithms. Fixed-input Python measurements improved; a stable end-to-end JavaScript speedup has not been established.
- Moved the independent repository checker to `repo_check/`, isolated and parallelized pytest, and expanded permanent Python / JavaScript sandboxes covering public SDKs, CLI, plugins, rules, multi-file resources, nested workflows and traces.

### Recent fixes included

- **False stale Architecture reports:** exclude materialized SDK inputs from user-source facts, preserve the required SDK resource layout and deterministic Nodeset reference order. Regression coverage checks immediate freshness, repeated exports, cross-process hash seeds and detection of real workflow changes.
- **Lost conditional routes:** collapse only identical `EdgeSpec` declarations. Routes with different conditions or scheduling/data-transfer roles remain separate; Python data delivery follows the transfer route itself. Matching routes still avoid duplicate execution and envelope delivery. Permanent JavaScript sandbox cases cover this behavior.
- **Nested plugin configuration export:** recursively convert read-only nested values before writing `compiled_graph.json`. The standalone public `vibeflow.core.descriptors.json_values` module exposes `freeze_json`, `freeze_mapping` and `thaw_json`, preserving protected runtime settings and independent editable / serializable copies.

### Migration

The current contracts are **Workflow ABI v5, Rule ABI v2 and Plugin ABI v3**. Declare resources using the language SDK and select them through Workflow `plugins`. Retired registry / bundle discovery, Node categories, `NodeInfo` and `NodeContract` interfaces require migration. Nodes declare rulesets directly; `flow_kind` no longer grants effect permissions. Each pipeline input requires an explicit boolean `required`, and host selection belongs in `workflow.host_extensions`. Review effective rules with `review-rules`, then validate, check quality and execute the actual project. Regenerate Architecture from real declarations and configuration.

### Assets and validation

The collaborative and autonomous ZIPs share the kernel and minimal projects. Both were built with `python -B distribution/build.py`; repository checks, minimal Python validation and execution passed. Before publication, both archives were compared with current source, user documentation, profiles and distribution trees. A checksum file is attached.

Release-related regression tests on 2026-10-13 reported **54 passed, no skips**. The complete source regression on 2026-10-11 reported **4385 passed, 22 skipped**. The new ZIPs passed **36 real nested-plugin-configuration runs**, covering six configurations in plan / compiled / block modes per profile. Skipped checks and downstream business acceptance remain separate from these results.

[Full Git comparison: v0.13.2 → v0.18.3](https://github.com/RockingSisyphus/vibeflow/compare/v0.13.2...v0.18.3)
