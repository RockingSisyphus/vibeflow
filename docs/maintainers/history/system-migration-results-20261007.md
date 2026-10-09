# 统一资源接入与旧架构退役结果

本次在已有未提交工作上实施，不重置工作树。审计索引为 [R01–R19](system-migration-audit-20261007.md)。开发版本准备为 0.16.0；旧 API 直接退役，迁移入口见[用户迁移说明](../../../distribution/docs/user/rule-system-migration.md)。

本轮验收记录：2026-10-08 执行 `python tools/verify_project.py --full`，全部 **17/17** 项通过，退出码为 0。源码和 wheel 的明确退役清单审计亦通过；2360 个验收输入文件在完整批次前后哈希相同。摘要见[最终验证](../evidence/index.md#artifact-6ff4f2b6e9b2c9e7)。

**完成结论已校准**：[独立复核](system-migration-recheck-20261008.md)确认上述记录与源码一致，同时发现 S01–S04 四项清单及现有测试未覆盖的邻近残余。因此，本轮通过不能证明相关旧语义全部清零。补充整改及新的验收记录见[复核修复结果](system-migration-recheck-repair-20261008.md)；独立复核和本轮证据原样保留。

## 架构与删除范围

默认内置插件自动接入，与外部 SDK 插件共用 ContributionBuilder、冻结、来源、冲突和实现解析。Application 形成一次 Catalog；Core 只执行显式选中的规则。语言无关默认声明及判定位于 builtin，语言实现与配对位于各 Target。Python 绑定保留 canonical Descriptor；JS AOT 仅接受 WorkflowPlan 与必填 JavascriptBindingPlan。

| 处理方式 | 范围 |
| --- | --- |
| 直接删除 | 影子 rules.py、重复 imports.py、重复 RuleCatalog/model facade、旧 JS 独立 validator、私有死函数 |
| 替换调用者后删除 | BaseLib 自动扫描与旧模型、NodeInfo/NodeContract、metadata normalizer、Context/RegistryBase、资源转换、JS WorkflowSpec/parser、旧测试转换器与扫描器 |
| 保留为新机制 | 原生 Node/Nodeset/Loop、ABI、编译/runtime/lifecycle、canonical decoder/Descriptor、AST、调用闭包、图与指标算法 |
| 历史保留 | 审计、冻结旧输入、旧发行包和历史观察；不进入当前产品或活动夹具装配 |

删除审计为开发工具 `tools/audit_retired_architecture.py`，不参与业务启动。它检查明确的退役文件和符号，并可检查 wheel 文件。原有完整验收的 wheel probe 也检查包内不存在退役路径。

## R01–R19 对应实施

| 编号 | 新路径与处理 | 验收依据 |
| --- | --- | --- |
| R01 | Python source_ownership 与 Descriptor 的依赖/导出/实际位置统一判定；移除角色目录词与旧 BaseLib allowlist | 原审计 10 项顶层/方法导入正式 CLI 对照全部 PASS |
| R02 | BaseLib 支撑文件依 canonical ownership 检查 | 原审计 4 项支撑目录正式 CLI 对照全部 PASS |
| R03 | 删除 base_lib 名称触发的整模块扫描和 is_base_lib；调用者效果规则检查实际可达 helper | architecture_migration 的 unchecked library + print 反例与空 Ruleset 对照 |
| R04 | canonical PythonResourceBinding 直接保留 Descriptor | 自定义 rulesets、语言实现、来源字段不经 Registry adapter |
| R05 | JS 统一 decoder/SDK；移除私有自写 Plugin parser，保留 lifecycle binding | SDK 字段与实际 JS binding 回归 |
| R06 | 删除 JS 独立 quality 模型/validator | 所选 Ruleset 审查与真实 Host/Plugin/异步检查 |
| R07 | Node Schema 接受合法 examples.outputs | SDK/decoder/Schema 契约；Python 默认 interface 仍独立施加限制 |
| R08 | builtin implementation 判定使用有效 policy；Python 基础政策和局部覆盖合为完整有效 Rule 参数，判定只读 params | policy 1 与 1000 改变结果；配置、覆盖、正式报告与 preview 一致，有/无检查 session 仲裁回归 |
| R09 | 删除 quality→builtin→quality 固定小图循环与默认检查便利桥；纯判定直接调用算法。Python/JS 源码 Target 只产事实，Application 复用单次 Catalog 执行显式项目主题及可选效果 Rule | 独立 topic、实际综合主题执行记录、两文件仅贡献一次与各解析一次、0/1/2 workflow 的 JS 接入次数 |
| R10 | 保留综合主题完整范围；它不隐式调用可独立选择的 topic Rule | 文档明确组合语义，替换综合主题实际执行新实现 |
| R11 | 内置和外部均贡献资源并按来源/实现解析绑定，删除 ID 优先分支与重复默认注入。参数适配依据 callable、声明 schema 和真实贡献来源；外部复用声明保留自有默认值。普通 JS worker 通过事实边界接收当前闭包项目事实 | builtin_provider：默认可用、来源、冲突、替换执行；同 ID 外部普通实现、窄 schema 原生 alias、自有默认及 override、普通 worker 的 helper/unused 对照 |
| R12 | JS build/emitter 强制 WorkflowPlan + JavascriptBindingPlan；原生 I/O/调度/capability 迁入 canonical 契约，Target 显式提供异步执行事实 | 原生 AOT、异步、Loop、capability、conformance；Python 三执行模式的无输出 detached 任务与条件激活反例 |
| R13 | 退役旧 BaseLib API、metadata、NodeInfo/Contract、Context/RegistryBase | 源码/导出/wheel 删除审计及原生 ABI 回归 |
| R14 | PythonResources 与 canonical binding 替换 ConfigResources/旧资源 Registry；保留 lifecycle hook 顺序与 dispose | workflow SDK、资源展示与生命周期回归 |
| R15 | Host 只使用 workflow-level 选择；旧项目字段明确迁移拒绝 | JS Host 选择、配置样式与实际宿主运行 |
| R16 | 删除静态 info.rule_catalog、boundary_registry、health effective_policy 无效透传和不存在的豁免；清理跨语言旧兼容导出，更新旧诊断建议 | 空选择、实际 Catalog/execution 报告与源码检索；Application 的真实有效政策报告保留 |
| R17 | 按文件/符号删除重复、影子和兼容 facade；混合模块保留活跃职责 | 删除审计清单和安装包检查 |
| R18 | 删除审计列出的私有死函数、旧标记和无正式生产者的 JS driver source owner 分支；保留 RuleContext 的 source scope | 源码删除审计、调用链、34 项实际 driver 归属/效果定向回归与完整运行回归 |
| R19 | 活动测试与沙箱直接 author SDK/Descriptor/canonical plan；移除 converter 和 manifest 扫描，更新用户文档/模板/发行 | 活动引用审计、规则沙箱、wheel 隔离、双 profile smoke |

## 正式目录对照

再次直接执行原审计的 `reproduce_python_cli.py`，其创建独立临时项目并走正式 CLI，未使用测试夹具转换。结果为 **14/14 PASS**，见[完整观察](../evidence/index.md#artifact-d02ac9bfef763288)。与审计前相比，仅目录词和导入位置导致的差异消失；未声明依赖及真实效果反例由独立测试保留。

## 最终验证

第一轮完整验收已跑完全部步骤，记录见[完整报告](../evidence/index.md#artifact-5b839cdb5cfa5025)及[沙箱失败清单](../evidence/index.md#artifact-773b8bec943555cc)。首次 pytest 为 2035 passed、11 failed、1 collection error；失败包括未迁移的夹具、旧导入与 JS 异步执行事实遗漏。该批次运行期间冻结源码，结束后集中修复并完成对应定向回归，没有跳过失败项。

第二轮再次跑完全部 17 项，见[完整报告](../evidence/index.md#artifact-f66e5e825d563764)、[失败及通过摘要](../evidence/index.md#artifact-f24abda995329315)和[冻结输入记录](../evidence/index.md#artifact-bd1bc3b4001e8a3e)。前后 2360 个输入文件的哈希相同。规则对照 1219/1219、补充沙箱 680/680、JS 集成 67/67、适配 207/207，以及 browser、展示、性能和 wheel 隔离通过；pytest 为 2113 passed、3 failed，Python 集成有 58 项受同一未迁移形参及其派生报告缺失影响。

该批次暴露了原生 checker 的外部声明被注入窄 schema 未声明的默认参数、普通 JS worker 缺少当前闭包项目事实、预览入口跨层导入，以及沙箱旧形参和诊断文字。发行构建也被相同跨层导入检查阻挡。批次结束后集中修复，并补删只读核查发现的 JS driver 无生产者 `source` owner 分支；不会扩大源码扫描范围或放宽原有阈值。

第三轮跑完全部 17 项，见[完整报告](../evidence/index.md#artifact-be0303220a1f1bea)、[失败及通过摘要](../evidence/index.md#artifact-69e31d3a9c9999cc)和[冻结输入](../evidence/index.md#artifact-8f189b205365113d)。前后输入哈希相同；pytest 为 2126 passed、1 failed，唯一失败是删除三处旧 JS owner 分支后遗漏同步当前资源字节快照。其余 16 项全部通过，包括 Python 138/138、JS 67/67、规则对照 1219/1219、补充 680/680、适配 207/207、wheel 隔离和双发行 smoke。只更新当前 `test_codegen.py` 中这一项 SHA，其他资源快照与历史记录不变。

最终轮在仅同步当前资源快照后，再次完整执行 `python tools/verify_project.py --full`，所有 17 项通过，见[完整报告](../evidence/index.md#artifact-524a49d6fbf8c5f2)。运行期间冻结源码、测试、用户文档和发行配置；[逐文件输入记录](../evidence/index.md#artifact-524afc4e36a4513b)保存前后相同的 SHA-256 与文件指纹。完整批次结束后只整理本文及维护者证据文件。

| 验收面 | 最终结果与证据 |
| --- | --- |
| 仓库质量与源码编译 | 初始和最终 quality 均为零错误、零警告；compileall 通过 |
| 完整 pytest | **2127 passed**，零失败 |
| Python 实际集成 | **138/138**；路由、Loop、I/O、状态、异步、生命周期、异常与编译模式通过 |
| JavaScript 实际集成 | **67/67**，零跳过；最小 AOT、Node 与 browser 入口通过 |
| 规则与补充沙箱 | **1219/1219** [规则对照](../evidence/index.md#artifact-ab96e5732bb877f8)，**680/680** [补充案例](../evidence/index.md#artifact-cd0b6dd4b8908034)，零进程错误 |
| 适配、展示与性能 | **207/207** [适配案例](../evidence/index.md#artifact-8039441dd7d72c31)；实际 browser、布局、资源分区与审查性能均通过 |
| 原审计目录对照 | **14/14**，覆盖顶层/方法导入与四种支撑文件目录 |
| 隔离安装与发行 | wheel 隔离 Python/JS 入口和 collaborative、autonomous 两个发行 profile smoke 全部通过 |
| 退役删除 | [源码与 wheel 清单](../evidence/index.md#artifact-01d02f6099c3e8b0)通过：31 个退役产品文件、5 个旧内置声明路径、3 个活动测试转换桥、旧内置包命名空间与 50 个退役符号 |

内置声明的 5 个旧路径迁入 `builtin`，其有效机制保留；31 个退役产品文件及兼容实现不再存在。wheel 的 333 个产品文件与源码逐字节一致，314 个 Python 文件的独立 AST 检查亦没有退役符号。Node/Nodeset/Loop、ABI、编译和生命周期保留于新职责模块。旧公开 API 按 0.16.0 破坏性升级直接移除，替代入口与发行准备见[迁移说明](../../../distribution/docs/user/rule-system-migration.md)。

逐案例记录保存 ID、预期、主要观察及匹配结果；完整临时报告位置亦在记录中。wheel 的 SHA-256、大小与最终输入哈希保存在[验证摘要](../evidence/index.md#artifact-6ff4f2b6e9b2c9e7)。前面三次未通过的完整批次原样保留，不替代最终验收记录。
