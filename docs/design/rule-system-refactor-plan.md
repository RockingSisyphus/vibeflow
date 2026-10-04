# Rule/Ruleset、Node 与插件系统重构

基线 `f169429`，目标版本 `0.15.0`。本文记录已确认的设计与迁移清单；实际完成情况以测试和发行验证为准。

本页保留初期 JSONC 声明与 bundle 方案。接入方式随后由[代码插件重构](code-plugin-refactor-plan.md)替换，多文件与展示能力见[资源重构计划](multifile-resources-plan.md)；当前公共接口见[使用者手册](../README.md#使用者开发)。

## 已确认的机制

用户项目的审查约束全部成为 Rule，包括副作用、声明、源码、架构和领域判断。首版按完整主题组织，每条规则可以产生多个诊断码。规则稳定 ID 与诊断码分离，例如 `vibeflow.no_side_effects` 产生相关 `NODE.EFFECT.*` 诊断。

Node 的完整声明与 Ruleset 选择决定约束。`flow_kind` 保留原生执行身份；Node 自己声明 ID、契约、实现、规则和展示，不再提供 category 资源或默认值继承。自由的 tags/metadata 由领域规则解释，不再由身份隐式授予副作用权限。默认 Process 明确选择无副作用规则，空规则选择如实表示未约束。external/trusted 不自动绕过审查。

Python 和 JS 使用同一种 JSONC Node 声明，先读取声明和规则，再绑定实现。声明是元数据、契约、配置、实现定位和规则选择的唯一权威，实施类只承担原生调用协议。本次允许断代迁移，不保留长期兼容桥；compiler/runtime 的生命周期与变换保留。

原生 Node/Nodeset/Loop 的路由、组合和执行保持原有职责。模型识别、归属与一个功能块的判断由领域规则负责，不预设模型拓扑。命令范围保持，不新增项目级领域启用、孤立源码扫描、持久资格或历史检查门槛。独立 `quality/` 保持标准库且不导入内核。

## 实际源码迁移清单

| 主题 | 基线入口及原作用 | 修改后的作用 |
|---|---|---|
| Node 声明与契约 | Python project/node、registry、quality；JS descriptors/frontend：执行类后读取重复元数据、配置 | JSONC NodeDescriptor 唯一声明；Rule 使用声明及实际绑定事实 |
| 副作用 | Python source_analysis/effects/preflight、project/policy；JS toolchain_driver：flow_kind 派生权限、external 绕过和不可覆盖分支 | Ruleset 的副作用 Rule 参数与 records 表达允许范围，删除第二套隐式权限 |
| 架构、数据和连边 | core/quality/workflow、workflow_rules；Target workflow：原生图和执行计划审查 | 判定进入 Rule，图解析、符号绑定与计划算法仍提供真实成功或失败事实 |
| Nodeset 深度与递归 | core/nodeset_dependencies、quality/nodesets；Target nodesets | 共用图算法，规则参数决定审查限制 |
| 大小、复杂度 | core/quality/evaluator、implementation；Target AST 指标 | 主题 Rule 使用一次分析产生的指标 |
| 依赖、重复和结构 | core/quality/dependencies、duplicates、structure | Rule 使用导入、指纹、目录及距离事实，保留既有诊断码 |
| 导入归属、顶层副作用 | Python source preflight；JS source audits | import 入口先于实现加载，失败不制造成功事实 |
| policy 插件 | Python policy hooks、JS Plugin ABI v1 | bundle 贡献 Rule/Ruleset，选中即按需加载；移除旧审查 hooks 和无实际效果的 schema hooks |
| 展示 | 两个 Mermaid presenter：系统状态与调用 style | 共用展示解析，Architecture 保存有效值和来源 |

保留诊断主题 `NODE.*`、`GRAPH.*`、`NODESET.*`、源码指标、BaseLib 与导入归属等。现有测试是迁移依据；解析与实际 Target 能力失败不允许通过覆盖伪造产物。

## 资源与公开接口

项目 `descriptors` 提供 `rules/rulesets/bundles`，复用原有目录与 Catalog。2026年10月03日决定移除 category 机制，具体修复与验收见 [完整修复计划](rule-system-repair-plan.md)。

| 资源 | 内容 |
|---|---|
| RuleDescriptor | ID、说明、实现位置、具名 inputs/outputs、参数 schema/defaults |
| RuleImplementationDescriptor | 执行语言与源码位置，不包含用户程序的业务 targets |
| RulesetDescriptor | 局部 calls、typed relations、import/static/run entrypoints |
| NodeDescriptor | ID、原生身份、契约、配置、实现、Ruleset、默认展示与 tags/metadata |
| ContributionBundle | 资源文件引用，相对 bundle 文件解析，复用 Catalog 的冲突及来源记录 |

Node 的 `rulesets` 未填写或明确为 `[]` 都表示不应用 Node 审查规则。BaseLib、Plugin、HostExtension 使用同一明确选择机制；内置和示例资源声明自己的默认 Ruleset。资源选择不自动开启同包 compiler/runtime hooks。

```python
def check(context, inputs, params) -> RuleResult:
    ...
```

RuleContext 只读提供当前范围、声明、调用、源码、符号、导入、实际实现与 helper 归属。AST 留在 Target 查询服务中，只在本次检查复用。规则是受信扩展代码，公共只读契约不是操作系统沙箱。helper 被引用不等于获得归属，共享 helper 不继承最宽权限。

VibeFlow 审查只负责源码和架构健康度，不增加通用业务代码正确性检查。真实解析、编译、原生协议绑定仍由实际 Target/工具链完成；缺失分析或执行事实不能通过覆盖制造。Python 默认导入 Rule 保留模块声明结构约束，包括拒绝模块级 try/match；放宽通过替换 Rule 完成。

Rule 的执行实现按 Target 能执行的语言族选择，JS/TS 属于同一族且至多一个实现。用户程序的 Node.js/Browser 目标作为资料提供，由规则自身决定检查方式；核心不注入双平台审查策略。

RuleResult.state 是 completed/failed/unavailable；records 保存具名且有类型的事实；findings 保留规则、诊断码、对象、文件、行号、原因及严重度。有诊断也可能提供有效 records，有效空列表也算可用资料；失败或缺失输出不能伪造成功。

## 规则图

`A → B` 表示 A 对 B 做什么：includes 包含 B，requires 读取 B 的具名输出且 B 先执行，overrides 局部覆盖 B 参数或实现。定义 ID 是可复用资源，call ID 是一次使用，覆盖不改共享定义。

编译先展开组合、解析覆盖，再校验输入输出并生成依赖计划。参数覆盖先于执行；替换保持目标调用身份并兑现其接口。同值合并、不同字段分别合并；同字段不同值且没有明确优先关系报冲突。优先级由覆盖链决定，不由文件加载顺序或 requires 决定。

三种关系分别检查循环，不要求混合图整体无环。依赖以 records 可用为条件，不以没有 findings 为条件。规则不能事后删除其他规则诊断。规则图使用独立检查计划，复用算法及 Mermaid/SVG 展示，不借用业务 Edge 的传输/调度语义。

static 入口执行选中的审查；run 保留原有执行检查集合，新领域规则默认静态；import 在实现导入前执行。review-rules 按 workflow 和调用位置展示有效规则图，不执行业务 Node。

## 批次及验收

1. 完整盘点调用链、诊断、资料、默认配置、入口与测试，替换旧 check_sources 方案。
2. 中立资源、Catalog、图解析、局部覆盖、依赖执行与结果汇聚；先验证纯事实图。
3. 两个 Target 声明装配，Python 延迟绑定替换 registry discovery，导入前审查；保留全 workspace 用于兄弟 root 解析。
4. 迁移全部内置审查主题，删除隐式 effect、external/trusted 绕过和不可覆盖分支。
5. bundle、Rule ABI v1、Plugin ABI v2、quality/validate/review/build 接入，run 使用明确入口；Workflow ABI v4 不变。
6. native → Node → status → call 展示级联及来源，模型 Node 自己声明浅蓝色，review-rules、Python/JS 真实数值与数据变换示例。
7. 迁移仓库项目、插件、测试、文档与 0.15.0 发行资源，完成全量验证。

验收包括嵌套、多路径共享、局部覆盖、无序冲突、替换接口、独立循环；有效空输出、有诊断但资料可用、解析失败和缺失输出；同 flow_kind 只改规则组合允许 print，显式空选择未约束；导入违规时顶层副作用尚未发生；同文件不同符号、共享/未知 helper、Nodeset/Loop、多次调用与跨 root CLI 范围；正式诊断、退出码和 review 失败不发布图；新静态领域规则不扩大 run。

真实验收包括 Python/JS 数值计算和原生串行、分支、Nodeset、Loop，实际 Mermaid/SVG 的颜色、形状、语义与来源，wheel、两个发行 profile、发行入口与 verify-kernel。

领域示例位于 `sandbox/python/domain_rules` 和 `sandbox/javascript/domain_rules`。两者用明确的 `model_forward` / `modelForward` 约定检查模型定义归属，并通过原生连边组合模型乘法块和数据变换加法块，真实计算 `3 × 2 + 1 = 7`。

```bash
npm_config_cache=/tmp/vibeflow-npm-cache python tools/verify_project.py --full
python quality/test.py
```

后续语言、包自动发现、热加载和自动修复不在本期。中间批次不作为完整新架构发布。
