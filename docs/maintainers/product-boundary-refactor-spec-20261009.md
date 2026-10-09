# VibeFlow 职责边界与整改规格（2026-10-09）

本文用于开发整改和后续审核：先定义 VibeFlow 应负责什么，再逐项列出当前偏离、源码位置、目标逻辑、修改范围及验收停止点。核心目标是使项目稳定地承担**代码架构限制器和代码质量限制器**的职责，降低维护成本，避免为了补齐业务语言语义而长期扩展分析器。

**状态：职责定义依据用户明确要求；具体实施细则为整改建议，尚未实施。本文不是修复完成报告，也不授权自动执行全部产品改动。** 不能把本规格中的目标行为描述成当前已有能力。开发者实施后，应以实际代码和对应验收重新核对。

本规格承接[职责边界审核](history/product-boundary-audit-20261009.md)，保留 B01—B11 编号。历史反例和旧审核报告保留原貌；本文重新界定哪些问题属于当前产品责任，不改写历史事实。

## 一、完整职责定义

### 1. 已确认的产品定位

用户明确：VibeFlow 只关注 Node 之间的关系和 Node 内的代码质量，是代码质量限制器、代码架构限制器；不关注业务代码正确性或代码安全性，不是编译器或代码安全检查器。

这里的“不是编译器”指：VibeFlow 不自行建立通用业务语言的执行语义模型，不证明算法、表达式、异常路径或业务结果正确。它仍需生成和执行自己的工作流计划，也可以调用 Python、TypeScript、esbuild 等原生工具完成目标接入。这些构建和接入能力服务于框架协议。

“只关注”并不免除框架自身的正确性责任。VibeFlow 必须正确解析声明、识别资源、构图、绑定端口、调度任务、处理异步生命周期、释放自己管理的资源、生成诚实的诊断。框架把另一个同名局部变量认成宿主、把一个普通整数认成资源，仍是框架应修正的问题；但不应为消除误判再引入完整类型推断器。

### 2. 属于职责范围的内容

| 范围 | 应限制或检查什么 | 应止步在哪里 |
|---|---|---|
| Node 与资源身份 | 唯一 Descriptor、Catalog 登记、实际实现绑定、声明来源及冲突 | 不依据目录名、字段名或函数名猜资源身份 |
| Node 之间的关系 | 显式边、数据传输、调度关系、路由、合流、可达性、跨资源依赖、直接 Node 调用和内部访问 | 不证明隐藏在任意第三方算法、闭包或动态对象中的全部可能关系 |
| 工作流结构 | Config、Nodeset、显式 Loop、有限计划、任务消费、支持的同步／异步协议 | 不要求把 Node 内每个算法循环或函数递归改成工作流结构 |
| Node 内代码质量 | 行数、函数数、分支、嵌套、依赖层级、调用链、重复结构及明确选择的风格约束 | 不证明算法会终止、一定无异常、结果符合需求或不存在安全风险 |
| 明确的接口合同 | 实现入口、签名、声明字段、端口、支持的 completion、实际返回 Mapping 和输出键 | 不预测所有返回路径及业务输出数值；不要求唯一代码构造方式 |
| 已选择的边界政策 | 明确导入政策、实际源码归属、可识别的外部操作、显式共享状态、有限直接输入写入规则 | 不因“不知道接收者是什么”“无法证明无副作用”默认拒绝业务 |
| 框架执行与宿主接入 | 明确的 Capability／Host、声明的协调与锁、实际构建错误、任务取消和收尾 | 不扩展为安全沙箱、预测性资源准入或默认全局串行化 |
| 结果与架构资料 | 如实报告当前所选规则、实际构建／执行结果、生成结构和检查范围 | PASS 不表示业务正确、安全、确定性或所有副作用都已排除 |

源码分析是手段，不是独立产品目标。AST、词法作用域、导入别名和原生 symbol 服务可以保留，用于找到真实接口、资源和依赖。分析应围绕**有限、明确、可解释的检查对象**展开；不能以“迟早补齐所有语法”作为成立条件。

### 3. 明确不承担的内容

不承担业务算法和需求符合性证明、任意返回值预测、所有异常出口建模、跨函数输入污染的通用证明、闭包与生成器完整执行推演、算法终止和收敛证明、默认确定性证明、恶意代码防护、反射／FFI 安全绕过穷举、包管理器资格认证。

这些问题可以由业务测试、语言工具、项目自己的领域规则和实际执行环境处理。VibeFlow 不以新增运行时沙箱、对象冻结、深拷贝、权限系统或全项目预检来补偿被删掉的静态推断。

### 4. 推荐的诊断和规则边界

以下是对既定定位的实施建议，并非用户已经逐项批准的数值或语法细节：

- **硬错误**用于确定的声明／接口冲突、确定的架构违例，以及当前 Ruleset 明确选择的质量上限或风格规则。
- **非阻塞提示**用于结构相似、命名习惯、可能的维护困难等启发式意见。
- **未知业务行为**不自动转成硬错误，也不能反过来标成“已经证明没有问题”。只陈述实际检查范围，不为每个未知表达式输出噪声。
- 规则选择不等于无限分析授权。选中 no_side_effects 不能自动承担安全性和任意程序行为证明；其名称与文档必须说明实际政策范围。
- 项目可以明确选择“不用递归”“不用 eval”等风格政策。它们在明确的局部政策中可以属于代码质量要求，不能伪装成所有项目都必须遵守的架构物理条件。
- 保留现有 Rule／Ruleset、参数、局部覆盖和 records 机制。不能再造第二套默认权限／检查系统；空规则选择不得暗中补回质量门禁。
- 删除的是越界逻辑，不能通过“把所有规则降为 warning”消除问题。真实架构限制和已选择的质量上限仍应生效。

## 二、当前基线、证据与阅读方式

源码基线为 HEAD **5b9f9763ab7051fc964a4d83a1419d87a621b4c9**，包含当时工作区中的未提交修复。源码链接的行号依据当前工作区核对；实施后行号会移动，应同时按本文列出的函数和字段定位。

先前职责审核保存了 335 个产品文件的状态，见[源码状态](evidence/index.md#artifact-d655cb92522f3056)。现有行为证据为：

| 证据 | 实际覆盖 | 限制 |
|---|---|---|
| [Python CLI 结果](evidence/index.md#artifact-2ac0ffdf07bbff35) | 13 项 SDK → Ruleset → 正式 validate 案例，8 项拒绝、5 项对照通过 | 加载声明和检查源码，没有执行业务 Node |
| [JS 原生 Rule 与 lock API 结果](evidence/index.md#artifact-740f7a052f53d806) | 5 项原生 Rule 案例、3 项工具链 API 案例 | 不是完整 workflow 构建；lock 案例确认的是工具启动前拒绝 |
| [Python 接口 Rule 结果](evidence/index.md#artifact-4297044948174fc1) | 4 项原生接口 Rule 案例 | 不是完整 workflow 运行验收 |
| [审核摘要](evidence/index.md#artifact-2a460472d79d47fa) | 记录执行范围与未实施状态 | 不代表本规格中的目标行为已验证 |

本文编写时补查了消费者和源码位置，没有为文档重新执行全量测试、发行构建或业务验收。不能用上述探针宣称未来修改已经安全完成，也不能宣称穷尽全部第三方 Rule。

下面每项的“验收”是**实施后的要求**。示例“应允许”仅指不得因该项旧限制拒绝；其他已选择的质量规则、真实接口或架构违例仍可使整个检查失败。

## 三、逐项整改

### B01　输入写入检查：收缩语言执行模型

**源码位置及调用关系**

- [input_tracking.py：_input_reference_facts](../../src/vibeflow/targets/python/quality/source_analysis/input_tracking.py:102)、[_ExceptionAliases](../../src/vibeflow/targets/python/quality/source_analysis/input_tracking.py:111)、[_InputCallFacts](../../src/vibeflow/targets/python/quality/source_analysis/input_tracking.py:138) 是主分析实现；[visit_Try](../../src/vibeflow/targets/python/quality/source_analysis/input_tracking.py:511) 建模异常与 handler 状态。
- [parameter_facts.py：source_parameter_facts](evidence/index.md#artifact-2ee797c99fa41c0b) 沿调用传播输入参数、字典事实和 builtin 事实。
- [effects.py：参数事实装配](../../src/vibeflow/targets/python/quality/rules/effects.py:83) 将结果交给 Node／Module visitor；[visitors.py：_visit_input_scoped_body](../../src/vibeflow/targets/python/quality/source_analysis/visitors.py:241) 再调用局部分析。
- [source_input_parameters](../../src/vibeflow/targets/python/quality/source_analysis/input_tracking.py:81) 是参数分析的转接入口；[_tainted_helper_parameters](../../src/vibeflow/targets/python/quality/source_analysis/input_tracking.py:786) 服务跨函数传播。

**当前逻辑**

为了识别输入是否被修改，维护异常出口、异常类别、精确字典、变量可能未绑定、builtin 遮蔽、闭包写回、生成器创建与消费时点，并在 helper 参数间传播事实。input_tracking.py 当前 862 行，parameter_facts.py 当前 250 行；体量是维护成本线索，不是删除行数指标。

**目标逻辑**

保留一个有限的“直接输入写入”质量检查。推荐识别入口 inputs 的直接子引用上的赋值、删除，以及明确配置的变异方法。若保留局部别名，只识别单函数内明确的简单赋值，正确处理作用域遮蔽和重新绑定；复杂控制流不能靠永久污染历史同名变量维持所谓保守性。

建议将最小识别范围固定为下表，而不是继续按新反例扩展解释器：

| 对象 | 建议支持范围 | 不支持时的处理 |
|---|---|---|
| 输入根 | 当前入口的 inputs 参数绑定，不能仅按字符串同名判断 | 被遮蔽的名称不当作入口输入 |
| 子引用 | 从已识别根连续进行属性／下标访问，不跨任意函数调用推断返回对象 | 调用返回值归属未知，不拒绝，也不证明是副本 |
| 简单别名 | 如保留，只处理同一函数内直线语句的名称赋值；重新赋值清除旧事实 | 分支合流、循环写回和闭包传播不作路径证明 |
| 写入 | 已识别引用上的赋值、增量赋值、删除，以及规则明确列出的变异方法 | 不依方法名推断任意其他对象的行为 |
| helper | 仍可分析其结构和实际依赖，但不沿参数传播输入污染 | 不把未知 helper 宣称为无副作用 |

即使不推断分支别名，分支内直接写 inputs 的语句仍在有限语法检查范围内；不以“分析不支持复杂路径”为由停止遍历整个函数。是否保留简单别名属于实施选择，需与实际规则文档和验收一致，不能继续无上限扩展。

**修改范围与停止点**

删除异常类别／catch 匹配、逐表达式出口、精确字典及未绑定证明、跨函数污染固定点、闭包写回、生成器消费推演，以及仅为这些功能提供的参数、缓存和消费者。消费者迁出后退役 parameter_facts.py；input_tracking.py 应收缩／重写为单一有限检查，不能只关闭 handler 分支却继续维护整个状态机。

不要整文件删除共享词法、源码归属和 helper 依赖事实：它们仍可能服务真实架构检查。有限语法范围应写在规则文档中；不分析第三方函数是否修改输入，不证明任意路径上对象都保持不可变。

**为什么这样改**

直接写入上游传来的数据，会增加 Node 间的隐含关系，有限规则与架构和代码质量有关。通用异常、对象状态和跨函数污染证明则要求解释业务语言执行，超出产品边界。目标保留可解释的质量约束，同时消除“发现一种语义组合，就再补一层状态机”的维护循环。

**实施后验收**

已承诺的直接 inputs 子项赋值／删除／变异调用应被所选规则识别；明确局部重新绑定、同名局部变量不能误报。复杂 helper、异常和生成器组合不再要求证明不可变。历史 F06 的复杂漏检矩阵保留为历史观察，不再作为必须全部补齐的产品目标。

### B02　输出检查：删除返回值构造推断，保留真实端口合同

**源码位置及调用关系**

- [visitors.py：NodePurityVisitor.visit_Return](../../src/vibeflow/targets/python/quality/source_analysis/visitors.py:631) 根据推断出的键集合拒绝返回语句。
- [input_tracking.py：_track_output_literal](../../src/vibeflow/targets/python/quality/source_analysis/input_tracking.py:801)、[_track_output_key_assignment](../../src/vibeflow/targets/python/quality/source_analysis/input_tracking.py:810)、[_record_output_key](../../src/vibeflow/targets/python/quality/source_analysis/input_tracking.py:815)、[_return_keys](../../src/vibeflow/targets/python/quality/source_analysis/input_tracking.py:851) 保存和读取输出键；[visitor 初始化](../../src/vibeflow/targets/python/quality/source_analysis/visitors.py:544) 建立 _output_dicts。
- 应保留的实际接口：[Python Runtime._validate_outputs](../../src/vibeflow/targets/python/runtime/node_mixin.py:267)、[JS node_contract_check](../../src/vibeflow/targets/javascript/frontend/build_contracts.py:61)。

**当前逻辑**

run_pure 的返回值无法被静态识别为字典键集合时，报 NODE.PURITY.DYNAMIC_OUTPUT_KEY；局部字典构造还会累计键。正式 CLI 中 helper 返回空字典再 return result() 被拒绝，而 result = {}; return result 通过。

**目标逻辑**

允许用户通过变量、helper 或组合函数构造输出。声明层保持 provides 的合法结构；运行时检查实际 Mapping 和输出键；JS 原生生成的 ABI／端口接口继续工作。不预测业务返回值或所有返回路径。

**修改范围与停止点**

删除 _output_dicts 状态、上述键追踪方法及消费者，删除“推断不出来就拒绝”的返回检查。建议连当前逐返回语句的缺键／多键硬判断一并迁出：它依赖不完整键推断。若保留直接字面量与声明明显不一致的提示，只作非阻塞建议，不再添加 helper 返回值分析。

不删除实际输出合同校验，不新增所有路径的 return 证明，也不要求输出数值符合 examples。

**为什么这样改**

框架需要知道真实输出能否接入下游，这是接口责任。要求源码以某种方式构造字典，是对业务实现方式的额外干涉；继续补 helper 推断会形成局部返回值解释器。目标把检查放在声明和实际接口边界，既保留可运行的工作流，也不限制正常代码组织。

**实施后验收**

两个空字典构造方式不再因动态输出推断产生不同结果。实际返回非 Mapping 或输出键与 provides 不一致，仍由实际接口校验报告；不因允许 helper 返回值而删掉此检查。

### B03　动态分派推断：退役分析器及整条自动元数据链

**源码位置及调用关系**

- [runtime_dispatch.py：analyze_runtime_dispatch](evidence/index.md#artifact-2ee797c99fa41c0b)、[analyze_source_runtime_dispatch](evidence/index.md#artifact-2ee797c99fa41c0b)、[_RuntimeDispatchAnalyzer](evidence/index.md#artifact-2ee797c99fa41c0b) 构成约 919 行的推断器。
- [效果规则入口](../../src/vibeflow/targets/python/quality/rules/effects.py:177) 产生 NODE.EFFECT.RUNTIME_DISPATCH.UNDECLARED warning；[Python 编译适配入口 _runtime_dispatch_fact](../../src/vibeflow/targets/python/project/compiler.py:228) 也执行推断。
- 编译装配另见[_refresh_rule_facts](../../src/vibeflow/targets/python/project/compiler.py:135)、[_adapt_implementation_facts](../../src/vibeflow/targets/python/project/compiler.py:159)。

**当前逻辑**

追踪输入中的 callable、模块状态、函数参数绑定、闭包和局部调用，生成 runtime_dispatch 元数据。它当前参与警告和展示；没有证据表明它决定锁权限、改变拓扑或业务调度。不能把本项描述成“删除自动锁”。

**目标逻辑**

默认编译和质量检查不执行通用回调行为推断。实际可解析的 Node 调用和跨资源依赖继续由共享 SourceContext 支持。若领域项目明确限制回调输入，使用现有显式 Rule 检查其声明或有限直接语法。

**修改范围与停止点**

删除两条推断调用、整个专用分析器及公开导出，并同步退役自动字段和展示消费者：

| 消费者 | 需要清理的位置 |
|---|---|
| 实现事实与编译图 | [ImplementationFact.runtime_dispatch](../../src/vibeflow/core/models.py:28)、[CompiledGraph.runtime_dispatches](../../src/vibeflow/core/compiler.py:44)、[_node_runtime_dispatches](../../src/vibeflow/core/compiler.py:827) |
| BlockPlan 与序列化 | [BlockPlan 投影](../../src/vibeflow/block_compiler/compiler.py:420)、[NodePlan 字段](../../src/vibeflow/block_compiler/model.py:325)、[字典输出](../../src/vibeflow/block_compiler/model.py:391) |
| Python 可移植适配 | [portable_adapter.py 投影](../../src/vibeflow/targets/python/runtime/support/portable_adapter.py:232) |
| JS 事实装配 | [frontend/facts.py](../../src/vibeflow/targets/javascript/frontend/facts.py:94) 及同文件另一构造位置 |
| Core 架构资料 | [inspection/architecture.py 标签函数](../../src/vibeflow/core/inspection/architecture.py:127) 及记录生成 |
| Python 文档与 SVG | [architecture_document.py](../../src/vibeflow/tooling/application/python/presentation/architecture_document.py:329)、[mermaid/__init__.py](../../src/vibeflow/tooling/application/python/presentation/mermaid/__init__.py:709) 中字段、文本与各布局消费者 |
| JS audit 与 review | [audit.py](../../src/vibeflow/tooling/application/javascript/audit.py:458)、[review.py](../../src/vibeflow/tooling/application/javascript/review.py:775) 中记录、标签与文本消费者 |
| 共享展示与导出 | [展示标签解析](../../src/vibeflow/tooling/presentation/mermaid.py:216)、[source_analysis 导出](../../src/vibeflow/targets/python/quality/source_analysis/__init__.py:4)、[旧诊断映射](../../src/vibeflow/targets/python/quality/source_analysis/types.py:191) |

涉及公开计划／报告格式时，明确版本和迁移说明。若确需有限过渡，可以输出“未分析”占位，但必须指定移除版本，不能保留旧分析器暗中运行。不扩展为动态调用安全检查，不移除共享源码依赖解析。

**为什么这样改**

解析明确资源关系符合架构限制器职责；推演任意 callable 从哪里来、经过哪个闭包、会执行什么，进入程序行为推断。即便目前只给 warning，分析和跨层元数据仍有维护成本。目标减少 Core、Target、计划和展示对业务推断的耦合。

**实施后验收**

默认编译／Rule 不再调用该分析器；计划和各展示格式按同一新版本一致处理字段。真实直接 Node 调用反例仍能报告。没有新增隐藏开关、旧版回退或第二套回调解释器。

### B04　Node 内循环与函数递归：取消默认结构替代要求

**源码位置**

[NodePurityVisitor.visit_While](../../src/vibeflow/targets/python/quality/source_analysis/visitors.py:615)；[check_node_implementation 中 recursive_paths 的硬拒绝](../../src/vibeflow/builtin/implementation.py:85)。

**当前逻辑**

run_pure 内任何 while 都要求改成 topology Loop；Node 内 helper 的递归调用链报 error。正式 CLI 中有限三次 while 被拒绝、等价 for 通过；Node 私有 factorial helper 递归被拒绝。当前指标没有在探针中拒绝模块级 factorial，不能夸大为“所有函数递归都会被拦”。

**目标逻辑**

Node 可以完成正常局部算法；工作流 Loop 表示跨 Node 的重复调度。保留分支、嵌套、规模和调用链质量指标。递归可以给非阻塞维护提示，或由项目明确选中的风格政策禁止，取消普遍硬禁令。

**修改范围与停止点**

删除 visit_While 的默认 internal_loop 拒绝及改 Config 建议；移除 recursive_paths 的默认 error 路径。共享调用图和递归结构信息有其他质量用途时可保留。普通工作流边的非法环、显式 Loop 结构、Nodeset 递归／有限计划限制继续保留。

不证明算法终止或收敛，不自动展开算法，不为了维持旧调用深度数字模拟递归执行。质量指标对递归的计算方式需有限且诚实。

**为什么这样改**

循环和递归可以是合适的算法表达。把它们一律拆成工作流，会人为增大 Node 数量和数据传递成本。原限制也不是必然越界的“所有风格规则”：问题是默认将某种编码风格提升成架构必要条件。目标允许算法选择，同时继续限制真正的复杂度和图关系。

**实施后验收**

有限 while／for 和私有递归不再因旧默认禁令失败；复杂度超限、非法工作流环仍按所选政策失败。不要求证明这三个算法示例的业务正确性。

### B05　资源字段和对象赋值：删除名称黑名单与无差别拒绝

**源码位置**

[RESOURCE_FIELD_NAMES](../../src/vibeflow/targets/python/quality/source_analysis/types.py:60)、[_assigns_resource_field](../../src/vibeflow/targets/python/quality/source_analysis/helpers.py:39)、[Node visitor 的字段判断](../../src/vibeflow/targets/python/quality/source_analysis/visitors.py:583)、[_check_monkey_patch_call](../../src/vibeflow/targets/python/quality/source_analysis/visitors.py:654)、[Module visitor 对 setattr／delattr 的判断](../../src/vibeflow/targets/python/quality/source_analysis/visitors.py:756)、[_check_assignment_target](../../src/vibeflow/targets/python/quality/source_analysis/input_tracking.py:837)。

**当前逻辑**

self.client = 1 因字段名被判成资源持有，self.value = 1 通过。对非 self 的直接对象属性赋值，以及任意 setattr／delattr，报 monkey patch；函数中新建 Box 后写 box.count 也被拒绝。

**目标逻辑**

允许普通字段命名、本地对象构造和属性操作。真实 Node 身份、其他 Node 内部访问和资源关系使用 Descriptor／Catalog／SourceContext；输入直接写入使用 B01 的有限规则。

**修改范围与停止点**

删除资源字段名称黑名单及消费者；删除“非 self 属性即外部对象”的拒绝和任意 setattr／delattr 的 blanket 拒绝。保留明确的另一 Node 内部访问／调用约束，以及框架自身声明和调度接口的协议保护；已有明确共享状态政策按真实对象处理。

不再建立完整对象所有权、类型或逃逸分析来证明本地对象属于自己；不把删除名称误判换成未知类型拒绝。

**为什么这样改**

变量叫 client 不说明它是客户端；对象属性写入不说明它是跨 Node 修改。原逻辑用写法猜身份，既误报，又迫使开发者改名规避，破坏限制器可信度。目标围绕真实资源关系限制耦合，保留正常封装。

**实施后验收**

整数的 client/value 两种命名、本地 Box.count、普通 setattr 不再触发旧判断；明确访问另一 Node 内部的反例仍被选中架构规则拒绝。

### B06　效果检查：保留显式边界，删除行为猜测和安全黑名单

**源码位置及调用关系**

- [effects.py：硬禁导入与 FFI 集合](../../src/vibeflow/targets/python/quality/source_analysis/effects.py:47)、[call_violation](../../src/vibeflow/targets/python/quality/source_analysis/effects.py:313)、[_is_python_io_call](../../src/vibeflow/targets/python/quality/source_analysis/effects.py:543)。
- [ambient_state_call_name](../../src/vibeflow/targets/python/quality/source_analysis/effects.py:395)、[_looks_like_ambient_container](../../src/vibeflow/targets/python/quality/source_analysis/effects.py:430)、[dynamic_namespace_reference](../../src/vibeflow/targets/python/quality/source_analysis/effects.py:441)、[_dynamic_reflection_call_name](../../src/vibeflow/targets/python/quality/source_analysis/effects.py:577)。
- [visitor 效果调用消费者](../../src/vibeflow/targets/python/quality/source_analysis/visitors.py:435)、[ExitStack 分析装配](../../src/vibeflow/targets/python/quality/source_analysis/visitors.py:202)、[exit_stacks.py：analyze_exit_stacks](evidence/index.md#artifact-2ee797c99fa41c0b)。
- JS 同类边界实现为[auditHostIo](../../src/vibeflow/targets/javascript/resources/toolchain_driver.mjs:1821)、[auditModuleStateWrites](../../src/vibeflow/targets/javascript/resources/toolchain_driver.mjs:1454)，应按同一职责定义检查，不机械复制 Python 语法。

**当前逻辑**

未知对象的 write/close 等叶名会触发 I/O 判断；模块函数的 set/reset 等前缀和容器名会触发共享状态判断；ctypes/cffi 和 FFI loader 被硬禁；部分反射、动态命名空间和 callback 被当成无法接受的行为。为修复 close 的误报，又增加 ExitStack 实例、partial 和 callback 的专用分析。

正式 CLI 中，纯内存 StringIO.write 被拒绝；在 python_io 下仅导入 ctypes 仍被拒绝。它们证明当前限制行为，不证明任何实际安全风险。

**目标逻辑**

效果规则仅表达已选择的有限政策：显式允许／禁止的导入、可识别的外部文件／网络／终端操作、明确的共享状态和执行协议。使用实际 import／symbol、简单别名和正确词法遮蔽定位，不声称识别全部副作用。

**修改范围与停止点**

| 逻辑 | 目标处置 | 限定 |
|---|---|---|
| 未知接收者只凭 write/close/read 等叶名报 I/O | 删除猜测及相关报错路径 | 已识别的真实外部操作仍可按所选政策限制 |
| set/reset 前缀、cache/config 等容器名猜共享状态 | 删除名称猜测 | 明确的模块共享对象写入、实际全局赋值可保留有限规则 |
| ctypes/cffi、CDLL/dlopen 等统一硬禁 | 删除不可覆盖的安全黑名单与叶名匹配 | 用户显式导入政策仍生效；不能一并删除声明的资源依赖 |
| 泛化反射、动态命名空间、callback 禁令 | 从默认效果检查删除“防绕过”路径 | 动态资源绑定确实违反当前声明／构建协议时，按那个协议报告 |
| 动态代码调用 | 去掉仅凭无法证明安全作出的默认硬拒绝 | profile 无法构建的实际情况和项目显式风格政策可保留，不增加绕过证明 |
| ExitStack 专用语义补偿 | 删除专用分析器、stack_cleanup 参数和仅为豁免 close 的消费者 | 与已保留规则共享的词法事实应留在共同来源，不能误删运行时资源释放 |

不要把所有 process、builtin/prototype 或共享状态约束自动视作越界。明确破坏框架生命周期、宿主协议或跨 Node 协调的操作，仍可按实际执行模型限制。不要扩展“危险调用”名单以承担 OS 安全职责。

effects.py 当前约 610 行，exit_stacks.py 163 行。目标是删除原因和补偿的组合，不是将两份代码移到新目录后继续默认运行。未知第三方函数不按名称推断 I/O，也不遍历整个依赖库证明无副作用。

**为什么这样改**

显式外部操作和共享状态会影响 Node 间的协调，是合理的架构政策。未知调用名称和 FFI／反射的风险推演则把限制器变成不完整的安全及行为分析器。误判造成特殊豁免，特殊豁免又要求更复杂分析。目标保留明确可解释的边界，移除这条维护链。

**实施后验收**

内存 StringIO.write、普通对象 close 和仅导入 ctypes 不再仅因旧猜测／安全黑名单失败；明确 open、宿主 I/O、所选导入禁令和实际共享状态反例仍按对应政策报告。框架资源收尾继续正确；不能把删除静态 ExitStack 分析误实施为删除 Runtime 的 cleanup。

### B07　JS 时间与随机数：取消默认确定性限制

**源码位置**

[auditHostIo 的 nondeterministicGlobals](../../src/vibeflow/targets/javascript/resources/toolchain_driver.mjs:1837)、[reportNondeterminism](../../src/vibeflow/targets/javascript/resources/toolchain_driver.mjs:1899)、[Math 和动态成员判断](../../src/vibeflow/targets/javascript/resources/toolchain_driver.mjs:1994)。

**当前逻辑**

Date、performance、crypto/webcrypto 和 Math 的部分使用与宿主权限混在一起。在原生 Rule 探针中，Math.max 通过；Math[params.operation]、Date.now、Math.random 在 none 下被拒绝，Date 在 python_io 下通过。

**目标逻辑**

默认不要求 Node 算法确定性。时间读取、随机数和 Math 对象／动态成员不自动等于文件／网络或宿主 I/O。项目确需可重复计算时，可显式选择有限领域 Rule。

**修改范围与停止点**

去掉默认确定性分类、相关别名分支和报错消费者。不能整段删除 process：其中另有实际宿主和进程生命周期逻辑；crypto 中实际宿主行为也不能仅因删除确定性分类而全局豁免。保留真实 fetch、fs、DOM／Host 与 Capability 关系，以及正确原生 symbol／遮蔽识别。

不证明任意算法确定性，不扫描第三方库的随机源，不因 Math 动态成员未知而拒绝。两个 Target 统一的是职责，不要求语法实现完全相同。

**为什么这样改**

算法可重复性是领域目标，不是所有工作流的架构必要条件。当前逻辑迫使用户为了读时间放开更广的 I/O 政策，混淆权限含义。目标让外部关系政策保持准确，避免增加无关维护限制。

**实施后验收**

上述 Math／Date 示例不再因默认确定性政策失败；实际宿主 I/O 仍按所选边界处理。不得把这一变化描述成“已证明 JS 没有副作用”。

### B08　接口规则：删除命名空间互斥、路由命名和示例输出禁令

**源码位置**

[node_interface.py：contract_overlap、Decision 命名和 examples.outputs](../../src/vibeflow/targets/python/quality/rules/node_interface.py:61)、[_looks_route_key](../../src/vibeflow/targets/python/quality/rules/node_interface.py:91)；[Node schema 的 examples 定义](../../src/vibeflow/tooling/project/schema/node.schema.json:124)。

**当前逻辑**

输入 type 与输出 key 同名时拒绝；Decision 输出必须命中 route/decision/branch 等名称；examples 含 outputs 时拒绝。原生接口 Rule 探针分别确认这些结果。中立 schema 已允许 examples.outputs，因此资料格式与 Python Rule 不一致。

**目标逻辑**

不同命名空间可合法同名。Decision 的关系由实际图和 when 声明表达。examples.outputs 可以作为文档资料存在，不执行、不比较业务数值、不用于证明正确性。

**修改范围与停止点**

删除这三项 hard finding 和专用命名函数；不将它们换成另一套强制命名门禁。命名风格若保留，只能作为明确风格政策或非阻塞提示。

保留入口签名、实现 symbol、单一执行入口、支持的 completion、合法声明字段和语义说明覆盖。保留[Core 的 Decision 路由条件检查](../../src/vibeflow/core/compiler.py:761)及实际端口绑定；不由输出名称猜业务路由。不要声称此处新增了尚未实现的所有 when 表达式语义校验。

**为什么这样改**

输入类型名、输出键和示例资料不直接证明架构冲突。名字像 route 也不保证路由正确；名字为 status.ok 不说明不能路由。目标以真正的接口和边关系限制架构，同时允许合理命名和文档。

**实施后验收**

同名输入 type／输出 key、status.ok 输出及带 outputs 的 examples，不再因三项旧禁令失败；错误入口签名、声明结构、真实路由条件缺失仍按对应规则报告。examples 不成为业务验算入口。

### B09　JS 工具链：移除 npm lock 资格检查及发布格式依赖

**源码位置及调用关系**

[probe_toolchain](../../src/vibeflow/targets/javascript/build/toolchain.py:90)、[run_build_driver](../../src/vibeflow/targets/javascript/build/toolchain.py:122) 都调用[_lock_identity](../../src/vibeflow/targets/javascript/build/toolchain.py:281)与[_validate_lock_tool_versions](../../src/vibeflow/targets/javascript/build/toolchain.py:319)。[ToolchainInfo 字段](../../src/vibeflow/targets/javascript/build/toolchain.py:43)携带 lock_sha256／lock_files。

补充消费者：[publish.py 的 _TOOLCHAIN_KEYS](../../src/vibeflow/targets/javascript/build/publish.py:37)、[_validate_toolchain](../../src/vibeflow/targets/javascript/build/publish.py:359) 强制要求这两个字段。只删构建前调用会留下发布格式残余。

**当前逻辑**

实际工具调用前要求唯一 package-lock.json，拒绝 yarn／pnpm；实际安装的 TypeScript／esbuild 版本还必须与 lock 精确一致。API 探针确认无 lock、yarn lock、双 lock 先失败，尚未启动实际工具链。

**目标逻辑**

依赖安装由项目选择的包管理器处理；VibeFlow 使用实际可解析的 Node、TypeScript、esbuild，检查适配器必要的兼容范围，并报告实际构建结果。存在 lock 不是运行或构建的普遍资格条件。

**修改范围与停止点**

删除两个 helper 及其调用、lock 专用报错、精确版本资格比较和仅服务该比较的辅助函数。清理 ToolchainInfo 的强制 lock 字段、发布格式强制键和相应消费者；公开产物格式按版本迁移，不能让已退役字段仍成为 publish 的前置条件。

保留 package root、实际依赖解析、必要版本兼容范围、Target／profile 支持和实际工具诊断。模板可以继续推荐 npm ci，项目可以自行保留任意 lock。其他摘要若服务缓存、模块身份或实际产物关系，不按名字批量删除；本项不授权删除所有 manifest 校验和发布逻辑。

不新增依赖一致性认证、安装前全量 dry-run 或另一个包管理器。不能仅放宽 yarn 白名单而保留一套新的 lock 资格系统。

**为什么这样改**

真实工具兼容影响 Target 接入，是框架责任；选哪种 lock 和依赖怎样安装是项目工程选择。强制 npm 及逐 lock 版本核准没有直接限制 Node 关系或代码质量，却引入构建与发布耦合。目标保留必要接入条件，移除多余资格流程。

**实施后验收**

实际依赖齐备且版本兼容的无 lock／yarn／pnpm 项目，不再因 lock 政策提前拒绝。需要实施后执行真实最小构建与对应 publish 格式验证；现有 API 探针不能替代这一验收。依赖缺失或真实构建错误仍应清楚报告。

### B10　规则职责归位：避免 no_side_effects 成为混合规则入口

**源码位置及调用关系**

[内置 Rule／Ruleset 装配 builtin_effect_resources](../../src/vibeflow/builtin/effects.py:7)、[Python 效果规则参数与 visitor 装配](../../src/vibeflow/targets/python/quality/rules/effects.py:83)、[NodePurityVisitor](../../src/vibeflow/targets/python/quality/source_analysis/visitors.py:529)、[ModulePurityVisitor](../../src/vibeflow/targets/python/quality/source_analysis/visitors.py:684)。

**当前逻辑**

no_side_effects 的共同 visitor 同时负责效果、输入污染、输出键、资源字段、循环和 Node 耦合。关闭一种政策会连带影响其他目标，增加改动范围和测试解释难度。

**目标逻辑**

复用当前 Rule 图与同一份 SourceContext，让检查按实际职责归位：接口归 node_interface，指标归 maintainability，真实依赖／归属／Node 耦合归架构检查，effects 只管明示效果政策。B02、B04、B05 的默认禁令应删除，不是拆成新的默认门禁集合。

**修改范围与停止点**

理顺保留规则的消费者、参数和 records，移除已删除能力对应的 visitor 分支。共享 AST／symbol 事实保留在既有来源，不引入第二套服务，不在 Core 读取业务 AST，不在 Target 隐藏规则选择之外的质量硬限制。

有限直接输入写入可以作为清楚描述的质量规则存在，必须说明如何选择。迁移规则选择时说明原 ID 和新职责的对应关系，不能把原本需要选择的规则静默升级成不可覆盖的 Core 错误。

声明期“声明与初始化分开”约定可以保留；不证明任意 import、decorator 或 metaclass 无副作用。no_side_effects 若保留名称，应解释其有限政策；需要改名时作明确接口迁移，不保留两个同等权威的永久入口。

**为什么这样改**

本项主要是架构健康度问题，并不是所有共享 visitor 都越界。现有混合入口让职责、参数和删改范围相互绑住。目标围绕同一事实源和明确 Rule 组织代码，使选择、诊断和维护范围可预测，符合限制器的可组合定位。

**实施后验收**

每个保留 finding 都有明确 Rule 归属；删除或关闭某个效果政策不会错误改变无关指标的含义。空 Ruleset 不暗中执行质量门禁；框架必要 ABI 不依赖用户是否选择某个质量 Rule。没有新旧两套长期双跑。

### B11　退役清理与报告语义：消除死调用和旧目标残留

**源码位置及当前逻辑**

[input_tracking.py：_check_params_get_call](../../src/vibeflow/targets/python/quality/source_analysis/input_tracking.py:828) 仍被[NodePurityVisitor.visit_Call](../../src/vibeflow/targets/python/quality/source_analysis/visitors.py:607) 调用，但其最终调用的 _check_params_key_node 只删除局部参数，没有判定效果。

[core/result_scope.py：_NOT_CHECKED](../../src/vibeflow/core/result_scope.py:38) 已排除业务正确性等项目，但尚未明确列出代码安全性和通用程序行为证明。旧活动测试、parity 与文档还可能把被退役能力当作通过条件。

**目标逻辑**

退休能力不再留下活调用、格式强制字段、导出和活动验收目标。报告只陈述所选结构／质量检查及实际执行结果。历史资料保存历史事实，不能成为继续扩展分析器的产品承诺。

**修改范围与停止点**

删除空方法及调用。按 B01—B10 清理专用 imports、flags、记录、序列化、展示、缓存和文档；确认共享事实确有剩余消费者再保留。不要仅改报错文字或加 skip 开关。

活动测试按新边界更新，至少逐项审查以下文件／区域：

| 旧能力或消费者 | 测试与资料位置 | 处置方式 |
|---|---|---|
| 异常／写回／参数推断 | [test_input_exception_states.py](evidence/index.md#artifact-2ee797c99fa41c0b)、[test_input_writeback.py](../../tests/targets/python/test_input_writeback.py)、[test_source_parameter_facts.py](evidence/index.md#artifact-2ee797c99fa41c0b) | 删除专用语义证明期待；共享作用域或有限规则案例按新目标保留 |
| 动态分派 | [test_runtime_dispatch.py](evidence/index.md#artifact-d5548768dfd7a91a)、[test_source_effect_parameters.py](../../tests/targets/python/test_source_effect_parameters.py) | 退役专用推断测试；检查是否混有真实依赖／效果测试 |
| ExitStack 静态豁免 | [test_exit_stack.py](evidence/index.md#artifact-d5548768dfd7a91a) | 退役语义补偿期待；不删除运行生命周期验收 |
| Plan 与展示 | [test_block_compiler.py](../../tests/block_compiler/test_block_compiler.py)、[strict_portable_plan.py](../../tests/block_compiler/strict_portable_plan.py)、[strict_architecture_document.py](../../tests/tooling/strict_architecture_document.py)、[strict_mermaid_cli.py](../../tests/tooling/strict_mermaid_cli.py) | 更新退休字段与格式，保留真实计划／展示功能 |
| JS 事实与 AOT | [test_implementation_facts.py](../../tests/targets/javascript/test_implementation_facts.py)、[strict_aot_project_build.py](../../tests/targets/javascript/strict_aot_project_build.py)、[strict_aot_publish.py](../../tests/targets/javascript/strict_aot_publish.py) | 更新字段和 lock 期待，继续验证实际工具接入与发布 |
| 旧 parity | [tests/fixtures/rule_parity/reference.json](../../tests/fixtures/rule_parity/reference.json)、[python/node_specs.py](../../tests/fixtures/rule_parity/python/node_specs.py) 及两种语言案例 | 按新职责更新活动基线，不用旧 PASS 数量裁决新目标 |

表列的是本次核对到的入口，不是实施时可以省略消费者搜索的声明；不得仅按文件名整文件删除混合测试。原 F01—F06 仍可记录当时发现的事实；真实身份、明确外部操作和词法识别问题依然有效，复杂行为证明不再要求补齐。

在公开 not_checked 和说明中明确：不检查代码安全性和通用业务执行语义，不证明确定性或全部无副作用。checked 只能表示实际所选范围；原有默认范围名称也应与具体选择核对。保留 FAIL／CONCERNS 的诚实区分，不新增“免责资格”或证明产物。

**为什么这样改**

死调用和旧格式残余增加理解成本；旧测试若继续强制语义证明，开发者会被引导回原分析器。目标让实现、选择、文档和验收对齐同一产品职责，防止“新实现接入了，旧系统仍删不掉”的长期共存。本项是清理与一致性整改，不把每个死方法都称为职责越界。

**实施后验收**

退休逻辑无默认活入口，无隐藏回退，无发布／计划强制依赖。历史报告仍可查；活动测试不再要求新目标明确排除的能力。PASS 文案不能解释为业务正确性或安全性通过。

## 四、不能误删或换一种方式补回的部分

| 应保留的机制 | 为什么保留 | 常见错误整改 |
|---|---|---|
| Descriptor／Catalog、明确源码归属和实际绑定 | 确定资源身份与关系，是主架构基础 | 删除真实 symbol 检查，改靠目录名／字符串认身份 |
| 共享 SourceContext、必要词法作用域与简单导入别名 | 给保留的接口、依赖和质量检查提供同一事实 | B01 退役时把共享作用域修复全部回滚 |
| Config／Nodeset／Loop／TaskPlan 与有限计划 | 表达并执行工作流自己的关系 | 将“不是编译器”解释成删除流程编译器 |
| 现有 Rule／Ruleset 和配置质量指标 | 支持用户选择的限制，而不是取消限制 | 一律降为 warning，或换成不可覆盖的新 Core 门禁 |
| 实际 ABI／Mapping／输出键与生成契约文件 | 框架必须能调用并传递数据 | B02 删除静态键推断时连运行接口一起删除 |
| 原生 TypeScript／esbuild 与必要工具兼容 | 服务真实 Target 构建 | B09 取消 lock 后取消依赖解析和真实构建错误 |
| 明确锁、异步生命周期、Capability／Host 与 cleanup | 服务 Node 间协调和框架执行 | 用减少检查为由删除实际收尾，或新增预测性串行化补偿 |
| 缓存／身份用途的摘要和确有需要的产物字段 | 不属于 npm lock 资格检查 | 搜到 SHA／manifest 就一律删除 |
| profile 的明确开发协议 | 既有协作方式，不自动等于运行时安全准入 | 无证据撤销 collaborative 的人工架构协议 |

JS driver 的[auditContracts 普通诊断范围](../../src/vibeflow/targets/javascript/resources/toolchain_driver.mjs:2377)针对生成契约文件；不能只看 strict 配置便认定它在强制证明整个业务项目类型正确。此处保留的是接入合同，不是新增完整业务编译检查。

去除某项静态推断意味着不再提前报告它曾试图发现的部分业务风险；这是职责收缩的实际后果，应诚实记录。不能为了恢复同样“覆盖率”再添加沙箱、输入冻结、深拷贝、预运行、全依赖扫描或历史报告准入。

## 五、实施顺序、公共接口迁移与最终验收

### 1. 推荐实施顺序

1. 把第一节边界作为活动整改和审核依据，更新各项验收目标。暂停继续补齐 F06 类通用语义组合；不以历史测试数量作为目标。
2. 先处理明确的默认误判和多余前置：B04、B05、B08、B09；连同专用消费者一起清理。
3. 收缩或退役 B01、B02、B03、B06、B07，并按 B10 将保留检查归位。共享词法／源码事实保留一份。
4. 执行 B11，对照公开计划、结果、AOT 产物和展示消费者完成格式迁移、活动文档与测试清理。
5. 用实际实现执行验收，形成新的结果报告。规格文档本身不表示整改完成。

步骤可以按开发依赖调整；不可先删除使用者仍需要的公共字段，再静默解释为兼容。涉及公开字段、Rule ID 或产物 schema，应说明哪个版本改变、旧资料如何读取及过渡何时结束。过渡只服务格式迁移，不能使旧分析器继续成为第二套权威。

### 2. 必须共同满足的验收

| 目标 | 必须看到的结果 |
|---|---|
| 正常 Node 算法和封装 | B02/B04/B05/B07/B08 的例子不再仅因旧默认限制失败 |
| 架构限制仍有效 | 明确直接 Node 耦合、实际未声明关系、非法图和错误接口仍按对应机制报告 |
| 质量限制仍有效 | 当前选中的规模、分支、嵌套、依赖和调用链上限继续执行；启发式结果不冒充确定证明 |
| 未知行为边界 | 不因无法证明安全／不可变／确定性拒绝，也不输出“已经证明没有问题” |
| 完整退役 | 主调用、参数、导出、格式、展示、专用缓存与活动测试不依赖退休实现，无长期旧回退 |
| 跨 Target 一致定位 | Python／JS 遵守同一职责；必要原生接入可以各不相同 |
| 框架本身正确 | 实际调度、输入输出绑定、异步收尾、资源释放和报告没有因删改退化 |
| 工具链接入真实验证 | B09 的最小真实构建及受影响 publish 验收完成，不能只凭早期 API 不拒绝 |
| 诚实交付 | 报告清楚列出执行过的检查和未验证范围；没有把静态探针称为业务运行成功 |

按实际改动复用有意义的现有测试，先执行受影响范围；公共模型和两个 Target 交付前按项目既有流程做适用的完整验证。不要新增任意语言语义排列组合测试，也不要为每个已删除判断另建资格证明。

### 3. 审核停止线

每条保留的规则都应能回答：限制的是哪一种质量或架构关系？实际依据是什么？明确不覆盖什么？为什么需要阻断而非提示？如果必须先证明任意业务代码如何执行才能回答，应收缩检查。

整改完成不以删除多少行、旧测试全绿或所有未知都消失为准，而以**职责一致、边界清楚、真实限制仍有效、退休逻辑确实退出维护**为准。不能将本规格扩展成重写整个内核、回滚统一资源架构或新建安全系统的计划。
