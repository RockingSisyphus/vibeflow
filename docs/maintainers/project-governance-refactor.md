# 项目治理与资源分层重构实施记录

状态：实施与必要验收完成。用户选择方案 B；本任务未提交、推送或发布，正式发行资产未更新。

## 最终验收

最终固定版本正式完整门禁：`python -B tools/verify_project.py --full --workers 12`，18/18阶段通过，合计约1252.30秒。pytest为4653/4653，无跳过；规则对照1116/1116、补充194/194、适配173/173。Python真实沙盒103/103、JavaScript50/50、真实浏览器、布局与资源视图、两端性能、sdist到wheel安装隔离、两个profile构建与解压搬移执行、最终质检与清理均通过。

最终原始记录为仓库旁证据区的 `full-03/verification.json`、`full-03/full.log`及矩阵观察，定位见[验证索引](evidence/project-governance-20261021.md)。前两轮失败及定向复验均原样保留，没有改写冻结参考或降低验收门槛。

已完成独立root、项目共享/私有资源、四级治理与项目架构；NodeType/业务Node/调用及NodesetType/Nodeset分层；Plugin整包所有权；Host Extension退役与显式节点生命周期；HTML包级资源视图及发行集成。当前开发格式为Workflow ABI v10、AOT v4、Plugin ABI v4、Rule ABI v3、预览v3，旧配置与AOT需迁移重建。

最终复核：保持方案B的项目准备边界，Core、BlockPlan、执行器和协同协议主体继续复用。实践成本主要在夹具/示例迁移、Target模块身份统一、浏览器与发行验收；以操作/Bundle拥有的Python导入作用域替换全局模块清除补偿，同源声明与实现状态一致，并保留标准包资源读取。没有新增长期缓存服务或全局业务执行锁。当前无已知未完成验收项。

以下按实施顺序保留阶段记录，其中未完成描述仅表示当时状态。

## 确认的边界

- 项目必须注册独立子目录 root；不保留独立 root 回退。
- 业务 Node 从 nodes/ 声明发现，Plugin 提供 NodeType；Plugin 贡献、实现和支持代码整包归属。
- NodesetType 定义子图，图中的调用使用独立身份；不增加中间业务实例文件。
- 四级 Rule 共用引擎；规则等级与 call/source 缓存范围独立。
- Host Extension 完全退役，关键环境生命周期由普通节点表达，保留 Capability 和 workflow 协同。
- 旧配置、ABI、快照不提供兼容路径；旧 AOT 重建。

## 已实施的基础切片

- 项目清单保留损坏配置诊断；真实项目加载取代合成 root。
- ResourceOwner 分离 project/root/Plugin 所有权，独立资源不再伪装成 Plugin。
- NodeType 与业务 Node 分离；两端从标准目录读取声明，准备时应用默认规则和样式。
- 公共资源准备移至 tooling/project/resources；语言加载仍在 Target 内。
- Rule 增加 level；project/root 配置复用既有编译、执行和 Record。
- 操作内 ProjectPreparation 复用资源与清单，统计不同 root 的声明使用，生成项目架构文档。
- 调用标识改为 definition_id，业务 Node 声明标识改为 id，NodeCallSpec/NodesetTypeSpec 区分调用与定义。
- Workflow/Plugin/Rule/AOT 与快照版本已开始切换；消费者、夹具与文档仍须迁移。

## 验证记录

所有测试在 AI 专用临时区中运行，子进程临时环境随调用设置，结束清理。

- 初始清单及拓扑：8 项通过。
- 所有权与规则基础：74 项通过。
- 第一次正式 12 并发定向批次：68 项通过，12 个 worker 报告同一收集错误（资源种类增加后测试参数未同步）。没有视为通过。
- 补齐 NodeType 枚举后：正式隔离入口、12 并发，80 项通过，含真实 JS 声明读取。
- 新命名及 14 种形状切片：120 项通过。
- 项目准备切片：35 项通过、1 项失败；失败是新测试把既有直接 Rule 调用 ID 错写成 $self，实际为 rule。已修正，待复验。
- 后续综合切片：123 项通过、1 项失败；新增严格等级后，旧图规则单测缺少 graph 上下文等级，待修正及复验。

- 命令接入前的两端 AOT 切片：10 项通过；包含 Python/JS 实际执行、新快照 v3、旧 AOT 拒绝及 Host 工厂删除。
- 质量配置退役及准备层切片：13、31、16 项分别通过；覆盖统一 quality-check、项目架构、root 全源事实及局部构建范围。
- 扩大到 Core：302 通过、7 失败、3 收集错误；后续 321 通过、8 失败（同一收集错误由 12 个 worker 报告）。保留为失败批次。
- 迁移部分旧夹具后：364 通过、9 失败、3 跳过；错误诊断和旧字段用例已修正，支持文件迁移暴露的相对路径问题继续修复。
- 对应复验：88 通过、2 失败、3 跳过；修复 SDK 声明目录变化后的支持路径，最新相关切片 23 项通过。

这些是阶段定向证据，不代表正式完整门禁或发行验收。

## 后续实施与复核

继续完成命令接入、旧质量配置删除、Host Extension 迁移与删除、全部夹具/沙盒/文档迁移、离线浏览器与发行验证，最后执行 12 并发完整门禁。

在首个完整两端绑定、跨 root 共享、浏览器宿主迁移和发行定型前，复核实际成本、验证代价、维护负担和关键假设。保留现有编译执行主体，不静默扩大到方案 C。需要改变用户可观察行为时，先给出证据和中文路线说明，再按 critical-fork 讨论；通知遵循 codex-task-alert。

## 扩大验证（未通过）

- Core 与准备层切片：377 通过、3 跳过；共享资源源码与搬移 AOT 切片18通过。
- JS 生成与显式生命周期切片13通过、2跳过。锁定 Puppeteer 的实际浏览器3通过，覆盖双实例、取消、正常结束与错误清理。
- 首次扩大 pytest 全测试批次（12并发）：1974失败、2602通过、32跳过、100错误，耗时75.62秒。该批次保留为失败，不能视为完整门禁通过。主要共同原因包括旧 root 布局、SDK 业务 Node 放进 Plugin、旧字段/Host测试和移动文件的夹具路径；同时继续核查产品接入缺陷。

## 第二轮扩大验证与当前复核

- 第二次扩大 pytest（12 并发）：849 失败、3646 通过、32 跳过、133 错误，69.30 秒。分组证据保存于 project-governance-pytest-02.json；不以定向通过覆盖该失败批次。
- 公共 source 参数、严格 scope 与准备层切片776通过；AOT 与 SDK 合并切片142通过但仍有1失败和1收集错误，随后修复架构路径不稳定与退役导入。
- 两端真实领域示例、共享资源、默认提供者切片最新44通过9失败（73.43秒）；剩余包含旧 quality-check 参数、旧 Rule 等级、Rule/业务定义 ID 混写和图级自定义详情字段。对应修复后继续验证。
- 共享 JS Plugin 的工具链使用消费 root，代码所有者仍是项目共享目录；修复了这两个职责混用。Python Plugin 包内相对导入改用所有者命名空间，AOT 固定绑定初始化按 bundle 复用，runtime 工厂保持每次独立。

复核：主体编译器与执行计划继续保留，没有扩展成方案 C。当前主要成本已从新功能转为夹具、沙盒、文档和发行接入迁移。恢复默认治理后暴露的失败需修复真实示例，不能通过默认关闭规则作为交付。仍须验证全部发现路径、四级事实边界、类型样式来源、浏览器与解压发行物；当前没有完整验收结论。

## 后续切片与机制修复

- 第三次扩大 pytest：552 失败、4024 通过、32 跳过、50 错误，130.52 秒；分组证据为 project-governance-pytest-03.json。
- 聚焦迁移批次04：165通过48失败；批次05：264通过26失败；批次06：218通过7失败。对应 JSON 保存失败明细，均不代表完整门禁。
- 实际修复：JS 策略记录拆分规则 definition_id 与 node_definition_id；JS 生命周期选择接受已校验的 scope；静态 SVG 资源组移除 Host 后遗留的空 tuple 已删除。
- 解压分发包连续导出定位到临时 SDK 类型文件路径泄漏；改为在架构序列化时保存稳定的内核资源引用。批次06的两种 profile 重复导出、即时检查及跨 hash seed 检查通过。
- 类型绑定保留原始声明、有效规则来源和各展示字段来源；原始 NodeType、业务 Node 与调用覆盖可区分。新增嵌套 root 容器旁支目录及顶层 workflow 发现测试。
- AOT 并发首次运行验证：固定 Plugin 定义初始化复用，八个运行的生命周期实例独立，批次05/06相关用例通过。没有锁住业务执行，也没有引入运行组或自动清理。
- 发现 Python 命令汇集曾丢弃 root 质量 Rule 返回的合法公共 Finding：规则执行已报错，旧汇集仅接受 HealthFinding，导致错误未进入命令结果。已统一边界并新增 validate/build/source-run 拒绝用例，待当前扩大批次确认。

### 退役测试的责任迁移

旧 Plugin 内部按业务 Node/生命周期逐资源限制包内导入的三个纯算法测试已删除；它们假定 Plugin 贡献业务 Node，与本轮整包所有权冲突。独立资源导入限制继续保留，包内可复用、包外拒绝由 resource_preparation/shared_resource_execution 覆盖。Host 专属目录/样式运输断言删除；普通 Capability、Plugin 卡片样式和显式浏览器生命周期覆盖保留。旧应用 policy 注入默认值测试退役，显式 Rule 参数与覆盖的现行测试继续执行。历史失败批次和冻结参考证据不能被这些迁移改写。

## 声明发现、命令边界与增量复验

- 聚焦批次11：336通过、9失败、3跳过；12：361通过、34失败、7跳过；13：305通过、21失败、5跳过；14：134通过、1失败。失败明细保留在相应 focused JSON 中，不能与后续通过合并为一次通过批次。
- 批次15：25通过。未调用的 NodesetType 也完成其声明体中资源绑定；不将其加入实际运行调用路径。重复调用仍由完整调用路径区分。
- 批次16：149通过、12失败、1跳过；17：109通过、5失败、1跳过。JavaScript 真实 AOT 的普通及符号链接导入负例通过：可见但未调用的 Node 保留归属身份供导入规则识别，不进入执行或检查入口集合。默认 SVG 不参与数据准备。
- Python 包内延迟 Rule 相对导入、JavaScript project/root 治理上下文均已通过；治理 Plugin 不自动成为业务 Plugin。
- 构建入口将正式配置诊断转换为 ProjectBuildError，保留原诊断编号与位置；项目元数据错误仍保留 WorkspaceConfigError。源码运行不再支持私有 registry 注入绕过项目准备。

复核：核心编译器、BlockPlan 与执行器仍沿用，工作没有扩大为方案 C。实际剩余成本主要为旧独立验收脚本与夹具迁移、离线浏览器和发行回归。旧脚本中的 Host Extension、业务 Node 贡献进 Plugin、root 为 `.` 和隐式 policy 注入均不能作为新版本期望恢复；有效行为须保留或迁入现行验收。新增完整资源卡片形状浏览器用例尚待实测，不能以模型断言替代浏览器结论。

### Host 专属验收退役

删除 adaptation 的 Host 工厂、依赖闭包、planned/disabled Host 和 Host 支持文件用例：js.A05.structure.host_support.registered, js.A05.structure.host_support.unregistered, js.A10.health.child500.build, js.A10.health.child500.validate, js.A10.health.child501.build, js.A10.health.child501.validate, js.A10.health.explicit501.build, js.A10.health.two300.build, js.A10.health.unconstrained501.build, js.A10.health.unselected501.validate, js.A10.preview.dependency_rules, js.A10.state.cycle, js.A10.state.disabled_dependency, js.A10.state.disabled_planned_dependency, js.A10.state.planned_dependency, js.A10.state.planned_only, js.A10.state.shared_dependency, js.A10.state.unknown_dependency。这些机制已删除，不改写为通过；普通 Capability 与显式 open/receive/close 的正常、取消、错误清理由 tests/tooling/test_explicit_lifecycle.py 的真实浏览器用例覆盖。

旧 policy 配置发现／合并用例退役：A07.python.policy.discovered-denied.inspect-node, A07.python.policy.discovered-denied.validate, A07.python.policy.explicit-wins.inspect-node, A07.python.policy.explicit-wins.validate, A07.python.policy.inline-allowed.inspect-node, A07.python.policy.inline-allowed.validate, A07.python.policy.inline-denied.inspect-node, A07.python.policy.inline-denied.validate, A07.python.policy.inline-wins.inspect-node, A07.python.policy.inline-wins.validate, A07.python.policy.nested-discovery.inspect-node, A07.python.policy.nested-discovery.validate, A07.python.policy.rule-params-win.inspect-node, A07.python.policy.rule-params-win.validate, A07.python.policy.unrelated-node.inspect-node, A07.python.policy.unrelated-node.validate。旧字段现在明确拒绝；Rule 参数、类型默认规则、Node 与调用覆盖分别由 test_rule_sessions、test_rule_selection、test_node_type_separation 和 project_governance 验收，不恢复隐式政策注入。


### 规则参数与当前验收职责

删除 `runtime.nodeset_max_depth`／`javascript.nodeset_max_depth` 以及按原生 handler 身份投影深度参数的路径。深度属于显式 Rule 参数；RuntimeOptions、项目配置、规则预览和正式检查不保留旧注入。参数 schema 验证正整数，覆盖仍由普通 Ruleset 关系完成。

扩大 pytest 第五批：4592 通过、19 失败、34 跳过，190.94 秒；原始失败记录保留。定向第 25 批：69 通过、1 失败；独立验收第 7 批：70/71。第 26 批：405 通过、10 失败；独立验收第 8 批：93/96。后两批暴露了夹具遗漏，以及 root 检查把未选业务定义当作当前对象、全局治理结果重复污染各 workflow 报告的问题；修复后仍须复验。这些不是完整门禁通过证据。

旧 `rule_gaps/resources` 六族矩阵退役，删除对应生成器与两个浏览器脚本。它依赖 Plugin 贡献业务 Node、按资源拆装包和 Host Extension。有效职责迁移如下，不能把旧场景数量记成新版本通过：

| 旧职责 | 当前覆盖 |
| --- | --- |
| 资源登记、冲突、来源和包内归属 | project_preparation、resource_preparation、node_type_separation、shared_resource_execution、SDK identity |
| Rule 选择、参数与源码/调用缓存 | rule_selection、rule_sessions、rule engine 及 adaptation core_sdk |
| 修改 Node 外观与规则不串调用 | workflow_preview、resource_preparation、node_type_separation |
| 14 种外框、包级 Plugin 与独立 BaseLib | local_preview 的真实 28 张资源卡片形状验收及流程形状浏览器用例 |
| Node、库和 Plugin 执行及 AOT 搬移 | runtime integration、shared_resource_execution、multifile integration 与发行隔离验收 |
| Host 自动生命周期 | 原机制删除；explicit_lifecycle 的真实浏览器 open/receive/close、取消与错误清理 |

`javascript.bundle.native_resources` 的 11 个旧整体装配用例同样绑定已退役 Host，删除生成路径；普通 Capability 注入、Plugin hook、业务执行和重复贡献由上表当前机制覆盖。冻结 reference、RESULTS 和历史失败报告保留。Python `python.source.formal_effects` 只验证已删除全局 quality CLI 开关，退役；纯源码 effects 分析和显式 Node Rule 的效果检查保留，其他正式 root source 检查迁到 root Rule 参数。


## 独立脚本与绑定身份复核

规则矩阵分阶段复验：Python 290/290、Tooling 331/331、JavaScript 169/169；Core 原始批次暴露旧源码集合和参数名后，最新 326/326。补充场景第二批 191/194，三个旧来源字段修正后 JS 26/26；未修改冻结参考。定向 29 批 117 通过，30 批 45 通过，31 批 74 通过（含真实浏览器）。排版 4/4、JS 资源展示14/14、Python隐藏错误定位复验通过。Python 性能矩阵通过，80 Node/8库约4.5秒为本机阶段观察，不是跨机器阈值。JS 性能计数通过。

沙盒 Python 99/103、后续102/103；JavaScript45/50的失败批次均保留。迁移了仍把业务Node放进Plugin的示例；完整项目审查的正例输入与故意损坏的负例分开，未关闭产品默认规则来追绿。修正调用帧旧字段、JS诊断归属字段和SDK NodeType声明识别。

102/103 中剩余的数值差异来自同源模块被重复装载：生命周期修改的私有状态与Node读取的私有状态不属于同一模块。小型原型验证同次准备的直接及延迟导入一致、不同操作隔离。改为Target拥有的导入命名空间，由同次资源准备复用；AOT保存可见导入根，执行不扫描项目。删除旧全局模块清除补偿。新绑定切片141通过1失败；失败暴露构建依赖收集仍暗中依赖全局模块缓存，已改为优先解析当前资源路径，待复验。

该修复留在声明、绑定与AOT装载边界；没有改写Core、BlockPlan、业务执行器或协同协议。剩余主要成本为沙盒复验、真实根预览重建、发行及正式完整门禁。当前仍未完成验收。

## 完整门禁前复核

定向33批142通过；随后补齐标准 Python 包资源读取，定向34批53通过1失败（无初始化文件的包），修正目录包 loader 后35批54通过。两端真实沙盒分别 Python 103/103、JavaScript 50/50；Python完整性能矩阵通过，80 Node/8库约4.69秒。静态05仅为包装命令错误，没有执行检查；06发现本轮生成的缓存与测试日志，清理后07所有 profile 零问题。所有原始批次保存在[证据索引](evidence/project-governance-20261021.md)。

真实离线较大图为80个业务定义、8次Nodeset调用：快照968,506字节，生成约22.80秒，首次显示约224毫秒，逐一展开全部666个调用约1.22秒，无页面错误或网络请求。根目录6条新版真实审查/构建/运行记录均可加载。数值为本机单次观察，不是性能保证。

复核结果：共享事实与准备结果足以支撑既有链路；声明/实现共用Target导入作用域，AOT保存作用域信息而不扫描项目。普通节点已在真实浏览器验证显式监听和清理。继续保持方案B，未改写Core/BlockPlan/执行器或协同协议。后续成本集中于正式完整门禁和发行隔离；此刻仍不得宣布整项验收通过。

## 首轮完整门禁与集中修复

首轮18阶段全部完成：15通过，pytest、distribution、repository-quality-final未通过。pytest为4648通过、5失败：两个目录负例受父级测试项目影响，一个浏览器测试误把文件路径交给目录宿主，两个Rule SVG测试仍写旧Rule路径。修复为显式项目边界、真实HTTP浏览器宿主及包内实现路径；移除已无用途的测试全局模块清理。未放宽预期。

规则对照1116/1116、补充194/194、适配173/173，Python103/103和JS50/50真实沙盒、监控浏览器、布局/资源、两端性能、sdist/wheel隔离均通过。发行被错误放入文档目录的原始证据拦下；原件已移至现有仓库外持久证据区，文档只留索引，不修改目录规则。

只读审查发现JS监控仍有仅供已删除Host使用的父观察器分支和启动选项，已删除；逐次运行继续独立记录状态。同步修正运行监控、系统架构、Node/NodesetType用语及失效文档链接。对应定向验证和发行隔离通过后，仍须对最终固定版本完整复验。

集中修复后：定向36批57/57、真实监控浏览器及两种profile发行隔离全部通过；静态08零问题。修正文档中已失效的五个章节锚点，补充仍在使用的Ruleset局部覆盖写法。最终固定版本重新执行完整18阶段门禁，不能用本次定向结论替代。

第二轮完整门禁：17/18阶段通过，pytest为4652通过、1失败；唯一失败是新增证据索引未列入docs总目录。两端沙盒、规则/补充/适配矩阵、真实浏览器、性能、sdist/wheel、两个发行profile、最终质检及清理均通过。已补齐总目录，并删除AOT测试中对旧node(type_key=...)形式的无效字符串替换（原本不产生任何行为）。定向复验后执行最终固定版本完整门禁，保留前两轮原件。
