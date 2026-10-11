# Rule、SDK 与资源装配适配审查

本页源码位置保留审计时的历史路径；当前文件归属见[仓库目录职责](../directory-layout.md)。

本轮在当前工作区确认了 10 个问题主题，另记录 3 个优化／简化项，其中贡献装配已有计数依据。Node 与 Rule 的来源不一致归为同一主题；多个入口的重复检查也归为同一主题。这些数量不表示已经确认相同数量的独立根因。

审查沿着公开 SDK、插件贡献、源码资料、规则执行、编译、绑定和命令输出展开。正式复现使用 VibeFlow 自身的临时项目；源码、测试和现有未提交修改保持原状。源码的 336 个文件与上一轮验收冻结版本一致，SHA256 为 `ae80abf25296130cfde83239c6a4b6cf42632353cbb927d561a3711b5f1d7d34`。本报告是一轮有证据的调用链审查，未执行新的全量或发行验收。

## 已确认的问题

| ID | 主题 | 实际观察 | 需要适配的旧假设 |
| --- | --- | --- | --- |
| A01 | Python SDK 声明与绑定来源不一致 | Node 审查 `Safe` 的源码，实际执行另一类中的 `print`，validate 和 checked run 均通过；Rule 也能执行与声明不同的函数 | 文件定位声明和直接绑定可以各自决定实现 |
| A02 | Python 编译插件释放后再次调用 | 正式 validate 记录 `before → after → dispose → before`，随后因实例已释放报 `GRAPH.COMPILE` | 健康检查可以再次走包含生命周期 hook 的编译入口 |
| A03 | JS 编译插件把原生图递归展开 | 含 Nodeset 的配置 validate 通过，build 报 `maximum recursion depth exceeded` | 每个 dataclass 都可以完整展开成 JSON 树 |
| A04 | 补充源码查询改写当前检查范围 | 未调用 Nodeset 的实现查询替换当前 Node 的加载状态；validate 通过，run 绑定报缺少真实源码状态 | 查询某个实现可以顺便修改 Registry 的当前上下文 |
| A05 | quality 的导入分层未适配多文件与插件声明 | 已登记 Node 支撑文件的 Python validate 通过、workspace quality 误报；JS 同时误报 Node 支撑、BaseLib 支撑和插件声明导入贡献 Node | Node 只能导入 BaseLib；插件声明和生命周期实现是同一种代码 |
| A06 | inspect-config 保留重复装配入口 | 8 Node／1 BaseLib 的 workspace inspect 执行调用级 Rule 16 次，validate 为 8 次；project inspect 还反复解析同一源码 | 检查一次、再加载用于展示一次是独立工作 |
| A07 | inspect-node 没有使用 workflow 的有效参数 | 同一 28 行 Node，workflow 明确设置 10 行上限；validate 拒绝，inspect-node 通过 | 资源检查可以另行从项目位置构造一份默认 policy |
| A08 | RuleRecord 冻结重复展开共享结构 | 12 个不同 tuple 转为 4,095 个；RuleContext 对照保持 12 个 | 输出资料只需检查循环，不需要保留共享子对象 |
| A09 | JS 插件释放失败会中断后续清理 | 真实 worker 的 dispose 抛错后，进程、stdin、临时资源和 stderr 仍保留 | 第一个释放错误可以立即抛出，后面的清理无需继续 |
| A10 | JS 构建在审查后才展开 Host 依赖 | validate 拒绝依赖 Host 的 501 行支撑文件，review-rules 显示所选规则；正式 AOT build 却通过并包含该 Host，规则执行资料只有直接 Host | 审查资源集合和最终构建资源集合可以分别计算 |

### A01：让声明、检查和执行指向同一个实现

公开 `@node`／`@rule` 接口允许 `implementations` 与被装饰对象同时存在。SDK 保存了显式实现声明，也保存了直接对象；Target 建立源码资料时使用前者，实际绑定优先使用后者。

Node 对照保留 `vibeflow.process`。显式声明另一份安全实现时，审查指标显示该实现的 3 行源码，真实运行打印了实际类的 marker；删除显式 implementations 后，SDK 正确定位实际类，validate 和 run 均报 `NODE.EFFECT.CALL_FORBIDDEN`。插件声明采用合法的 `declaration_rulesets=[]`，不能依靠插件的可选健康规则补偿 Node 声明契约缺陷。

Rule 的三个正式对照也明确区分了实际 handler：混合声明执行当前函数；自动定位执行当前函数；单独延迟 source 执行所声明函数。BaseLib、生命周期和 JS 的同类问题尚未确认。

位置：[SDK 构造](../../../src/vibeflow/targets/python/sdk/resources.py)、[Node 绑定](../../../src/vibeflow/tooling/application/python/project/declarations.py)、同文件的 Rule handler 加载。直接定义应由 SDK 的实际对象确定位置，延迟定义应由 locator 绑定；不一致组合应产生明确声明错误。检查、缓存、Architecture 和运行消费同一实现身份。

### A02、A04、A09：把生命周期和资料查询分开

Python 的 `_prepare_workspace_graph` 首次编译后释放 compiler 插件，却把该 Registry 返回给 `validate_graph_health`，后者再次调用相同 hook。此缺陷在上一轮性能修复前冻结的源码和当前源码中均正式复现。释放过的对象不能通过重新创建实例来掩盖重复变换：compiler hook 的生命周期应属于实际编译／变换阶段，后续规则事实编译使用该阶段的结果。

`GraphCompiler._runtime_dispatch_fact` 查询缺少资料的实现时，调用了有副作用的源码收集器。它只恢复 `source_context_snapshot`，未恢复 `source_load_states`；当前实现还改写了 `session.sources`。查询合法的未调用 Nodeset 后，主流程 Node 的状态资料被替换。这也在冻结基线和当前正式 validate／run 中复现。

源码分析应返回指定范围的资料，由调用方明确决定是否成为本次 workflow 的当前资料；补充查询可以复用 session 的解析缓存，不能改变正在使用的范围。这个调整不扩大未调用 Nodeset 的检查范围，也不伪造调用。

JS 的 `JavascriptPluginSession.__exit__` 在 dispose 首错处抛出，跳过 worker 和临时资源的释放。真实 worker 探针保存了失败后仍存活的状态，之后只清理了该探针自己创建的进程。清理应继续完成全部本实例资源，并在结束后报告释放错误；原有检查错误仍保留其根因。

位置：[Python 准备阶段](../../../src/vibeflow/tooling/application/python/workspace_service.py)、[健康编译](../../../src/vibeflow/targets/python/quality/workflow/validation.py)、[补充分析](../../../src/vibeflow/targets/python/project/compiler.py)、[源码收集](../../../src/vibeflow/tooling/application/python/project/declarations.py)、[JS Session](../../../src/vibeflow/targets/javascript/build/plugin_session.py)。

### A03、A08：区分共享内存结构与 JSON 输出

原生 Nodeset 子图共享定义表，合法图中存在回指。JS compiler hook 的 `json_projection` 按 dataclass 全字段递归转换，因而不能运输该图。应复用现有规则运输的有限图投影：定义保存一次，关系用引用表达；继续保留原生 Nodeset／Loop 的结构与语义。

RuleRecord 的 `_record_snapshot` 只有正在访问路径的循环集合，没有转换完成的 memo。共享 tuple 和混合 mapping／list／tuple 会重复转换；当前只读性、输入隔离和循环拒绝对照均正常。修复需要保留这三项语义，并复用完成的子对象。

内部缓存键也调用 `record.to_dict()` 和 `plain()`。即使修好冻结，内部指纹仍可能展开共享结构，需单独适配并验收类型及输入差异。最终 JSON 本身不表达共享引用，真实输出量仍可能很大；本轮没有测量整条 records 流程的端到端收益。

位置：[JS 图投影](../../../src/vibeflow/targets/javascript/build/plugin_hooks.py)、[records 冻结](../../../src/vibeflow/core/rules/models.py)、[规则缓存键](../../../src/vibeflow/core/rules/execution.py)。

### A05、A06、A07、A10：让正式入口消费同一份有效资料

quality 已经通过 Rule 引擎执行，问题在于默认结构 Rule 的资料和判断仍沿用目录分层。Python 角色装配主要登记 BaseLib 入口，JS 也遗漏支撑文件并混合插件包与生命周期。Core 的旧分层判定随后把合法支撑关系报成未声明导入。

Python 合法对照只把同一个已登记支撑文件从 `parts` 移到传统 `base_lib` 目录，validate 和 quality 就都通过。JS 对照把示例放进 `src` 排除了根目录文件数量错误，剩余三项均是目标导入误报。这说明需要把已有资源所有权、源码角色和真实导入关系接入结构 Rule，不能通过改目录或提高阈值解决。各资源仍使用自己的规则选择，共享文件不合并成最宽权限。

workspace inspect-config 先 validate，再通过 export 装配并检查一次；project 路径没有检查会话，并在健康检查后再次编译。它们应消费一次准备／检查的 graph、compiled、resources 和 report。inspect-node 也应复用所属 workflow 的参数解析结果，保留该命令自己的 Node 范围。

JS 构建准备审查直接选择的 Host，之后才通过 `host_extension_closure` 展开实例依赖；正式 validate 则在审查前展开。依赖 Host 的默认 Ruleset 因而可能没有在构建中执行。独立对照中，501 行支撑文件被 validate 正确拒绝，构建准备及正式 `build --target node --profile esm-module` 仍通过，最终使用集合包含父子两个 Host，规则执行 subject 只有父 Host。应提前确定实际资源闭包，供审查、绑定、架构和打包共同消费；这保持 Host 的原有依赖与实例协议。

位置：[Python 结构资料](../../../src/vibeflow/tooling/application/python/project/quality.py)、[JS 结构资料](../../../src/vibeflow/tooling/application/javascript/cli.py)、Core 分层 Rule（历史源码位置：`src/vibeflow/core/quality/root_structure.py`）、[workspace inspect](../../../src/vibeflow/tooling/application/python/cli/__init__.py)、[project inspect](../../../src/vibeflow/tooling/application/python/cli/config.py)、[Node inspect](../../../src/vibeflow/tooling/application/python/cli/node.py)、[JS 构建装配](../../../src/vibeflow/tooling/application/javascript/build.py)、[JS 正式审查](../../../src/vibeflow/tooling/application/javascript/audit.py)。

## 可以同步简化的适配层

一个固定 Ruleset 从公开 SDK 创建 Plugin、生成贡献、组合 Catalog 到生成 facts，descriptor 的 `to_dict()` 被调用 8 次。多处仅为了读取 kind 就序列化整个声明，Plugin 初始化、contributions 和 replace 还重复构造验证结果。计数确认了重复工作，尚未证明它是主要耗时。

可在固定资源冻结时完成一次声明校验与来源记录，组合时处理跨插件冲突；直接读取资源种类，只有运输和报告边界才转成普通容器。workflow 参数继续分别校验和冻结。准备阶段的多项 tuple 返回值也适合收口为一个内部结果，明确区分声明、分析、编译、健康报告和展示资料，减少调用者重新拼装这些信息。

JS `_AnalysisCache` 按完整请求缓存，包括规则主题和 subject；Node 与 workflow 阶段又分别建立 `_RuleSession`。未命中时启动独立分析进程。同一份源码因此仍可能在不同主题和阶段重复解析。可共享同次检查的不可变语法、导入和指标资料，同时分别执行对象权限和调用级判断；实际调用次数、阶段耗时和收益尚需补独立计数。位置：[JS 分析缓存](../../../src/vibeflow/targets/javascript/build/rule_session.py)、[分析进程](../../../src/vibeflow/targets/javascript/build/toolchain.py)。

JS Session 还保留按 raw 插件字典的 `rulesets` 触发独立预审的分支。它重新构造缺少支撑文件和 BaseLib 资料的声明；正常 SDK 编译绑定没有该字段，不经过这条路径。这是可以收敛的维护分支，本轮未把它计为正常 SDK 缺陷。处理时应核对真实内部调用者，然后让原生绑定边界消费已经装配好的规则资料。

## 建议实施与验收顺序

1. 先补并修复实现来源一致性、编译生命周期、补充分析范围、Host 闭包与释放失败清理。这些直接影响审查真实性或正式入口成败。
2. 接通资源事实与结构 Rule，统一 inspect 的参数、会话和检查结果。
3. 修复有限图运输、records 冻结和内部指纹；分别计数，最终 JSON 成本单独观察。
4. 收敛贡献装配与内部准备结果，移除被替代的重复调用，再执行现有完整验收及分发包验收。

新增沙箱应覆盖功能组合：SDK 直接／延迟绑定＋实际执行；compiler＋Nodeset／Loop＋dispose；未调用 Nodeset＋延迟绑定＋自定义导入 Rule；多文件资源＋quality 结构 Rule；Host 实例依赖＋逐文件规则＋构建；不同检查入口＋相同有效参数；共享 records＋依赖 consumer。每项保留同入口合法对照、目标诊断和确定性次数。

本次不需要改变公开 SDK、配置或 ABI，也不需要改变原生执行拓扑、现有命令范围或质量阈值。修复后的核心维护目标是：声明只有一个实际实现身份，分析查询不修改活动范围，判断经所选 Ruleset 执行，编译和展示各消费明确阶段的结果。

机器报告与本轮原始结果见 [证据索引](../evidence/index.md#artifact-d001d54305e74a82)。
