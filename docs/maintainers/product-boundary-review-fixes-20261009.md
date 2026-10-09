# 产品职责边界审核修正（2026-10-09）

依据 [独立审核](product-boundary-remediation-review-20261009.md) 修正 R01—R05。审核判断成立：两项新增误判、两项旧逻辑收缩不完整，以及活动文档和交付包说明残留。原 full-4 的 17/17 与 4020 项测试是原版本的真实成绩，但既有测试遗漏了这些反例；首次整改结果已明确更正，旧交付包保留为历史证据。

当前状态：用户指出的两项保留规则退化已修复并完成本地交付。最终源码全套 pytest 为 4213 passed；正式 CLI 23 项对照符合预期，打包后的 wheel 结果相同，原 38 项审核观察保持不变。上一轮“完成”结论已由新反例推翻，下方旧验收及旧包仅作历史记录。本轮验收证明这些有限规则和已执行场景符合期待，不声称穷尽所有缺陷。

## 后续两项退化的修正与复核

共享状态规则现在以当前词法作用域内的实际名称绑定为依据：Name(Store/Del) 覆盖循环、with、普通赋值与 walrus；导入别名、函数/类定义、异常别名和 match 捕获等字符串形式绑定复用同一检查。进入函数、类及推导式时保持正确的作用域，global 声明本身、同名推导式变量及局部定义不作为模块写入。

直接输入规则分别检查 if、条件表达式、match 及异常处理的互斥正文。条件/subject 中的重新绑定先执行，互斥正文从各自选择前的身份开始；一个正文把 inputs 换成本地对象不会让另一个正文的原始输入写入漏检。match 的模式/guard、except 的类型表达式可能在继续选择下一项前执行，其中可能重新绑定的名称在后续选择中成为未知；异常别名则仅在选中时绑定。复合语句结束后，条件性绑定仍成为未知，没有引入路径合并、复杂别名、helper 行为或业务正确性证明。

本轮执行中的成本、目标与路线复核：用户两个反例推翻了“已见重新绑定可以跨互斥分支累积”及“赋值专用 handler 已覆盖全局写入”的实现假设，但没有改变 B01—B11 的职责边界。维护范围是两个现有遍历器，复用现有词法绑定组件；最终新增 115 项语法/正反对照覆盖四类资源，定向共 2053 passed。正式 CLI 的 16 个违规案例全部拒绝、7 个正常案例全部放行，修改前其中 15 个违规被放行，另一个同名推导式误判消除；原 38 项 CLI 观察逐项保持不变。实际 Python 执行证实 16 个违规案例确实修改模块或原始输入，并对照两个选择表达式重绑定的正常案例。新 fixture 首次缺少项目 target 配置、定向首命令错写测试路径的日志原样保留，修正测试调用后复验，没有修改原有测试期待。

由于共享效果遍历同时影响 Node、BaseLib、Plugin 和普通源码，本轮在定向通过后固定源码运行完整验收，步骤耗时合计 1544.78 秒（25.75 分钟）。首批真实结果为 14/17、4211 passed：报告汇总脚本写错上一轮证据文件名，判断文件未生成便启动验收，造成两次质量及发行构建因同一失效链接失败。这是收尾错误，原记录保持失败。运行中还以实际 Python 确认两个选择表达式的误判；整批结束后才集中补齐记录并修正有限前缀处理。新写的模式捕获对照按“可能部分绑定后成为未知”的既有边界校正，原有测试未调整。首批 2367 个源码、测试及使用者文档输入没有中途变化。

随后固定最终版本，重新运行全套 pytest、Python Rule 对照、Python 边界补充以及项目现有编译、wheel 隔离、清理、双发行和质量步骤，全部通过。第二阶段只修改直接输入遍历和本轮新增测试，效果遍历、JS、浏览器、运行协议及随包手册均未变，因此不再重复约 12 分钟的资源展示整组；对应历史实测及本轮最终实测分开记录。两次源码固定检查和交付内容核对均落实。实践支持继续有限规则路线，没有需要改变目标的分叉；后续新证据仍依 critical-fork 说明并按通知资格提醒。

| 本轮最终验收 | 结果与证据 |
|---|---|
| 源码及 wheel 正式 CLI | 23 项：16 个预期拒绝、7 个预期放行，诊断代码逐项核对；wheel 结果相同。原 38 项观察不变。见 [CLI 判断](product-boundary-followup-fixes-20261009/cli-assessment.json)、[实际 Python 对照](product-boundary-followup-fixes-20261009/runtime-witnesses.json)。 |
| 最终源码测试 | 2053 项定向、4213 项全套 pytest 通过，无跳过。见 [定向日志](product-boundary-followup-fixes-20261009/targeted-tests-final.log)、[全套日志](product-boundary-followup-fixes-20261009/final-pytest.log)。 |
| 最终 Python 规则场景 | parity 291/291、当前边界 11/11，见 [parity](product-boundary-followup-fixes-20261009/final-python-parity.json)、[边界](product-boundary-followup-fixes-20261009/final-python-gaps.json)。 |
| 最终交付步骤 | 7/7：两次质量、compileall、wheel 隔离、生成物清理、双发行真实启动及内容检查、清洁检查。见 [步骤记录](product-boundary-followup-fixes-20261009/final-delivery-gates.json)。 |
| 首批实测，保留原失败 | 14/17；Python 138/138、JS 67/67、规则 1219/1219 和 680/680、真实浏览器/布局/资源/性能、适配 207/207 通过。三个失败来自记录链接缺项；选择表达式补修前的结果不能冒充最终源码全量。见 [首批步骤](product-boundary-followup-fixes-20261009/full-verification.json)。 |
| 包内容及退役检查 | 335 个产品文件与 wheel、两包内核逐字一致，四份随包手册一致，退役审计通过。见 [包审计](product-boundary-followup-fixes-20261009/package-audit.json)、[退役审计](product-boundary-followup-fixes-20261009/final-retirement-audit.json)。 |

本轮最新交付保持 0.17.0、ABI v5、manifest v2。旧同版本文件内容不同，按路径与 [SHA-256 清单](product-boundary-followup-fixes-20261009/local-distributions/manifest.json) 区分：

- [最新 wheel](product-boundary-followup-fixes-20261009/local-distributions/vibeflow-0.17.0-py3-none-any.whl)
- [最新 collaborative 包](product-boundary-followup-fixes-20261009/local-distributions/vibeflow-distribution-0.17.0.zip)
- [最新 autonomous 包](product-boundary-followup-fixes-20261009/local-distributions/vibeflow-distribution-autonomous-0.17.0.zip)

[本轮证据](product-boundary-followup-fixes-20261009/) 保留修改前原文及哈希、源代码补丁、CLI fixtures、实际写入见证、全部测试日志及生成的诊断图。所需证据压缩后，检查没有活动进程引用及子挂载，删除唯一专用目录 /tmp/vfp-followup-20261009，回收约 2.23 GiB；见 [清理记录](product-boundary-followup-fixes-20261009/cleanup.json)。没有提交、推送或远端发布。

## 上一轮 R01—R05 的历史记录

下文的验收数字及交付链接属于本轮补修之前，保留用于追溯；最新结果与新包见上文。

## 修正范围与停止点

| 项目 | 修正 | 保留的拒绝对照 |
|---|---|---|
| R01 | 入口 ABI 遍历跳过新函数、lambda、类的主体；定义时在外层执行的默认值、装饰器等表达式仍属于外层。正常嵌套同步/异步生成器 helper 放行。 | 真正入口中的 yield/yield from，以及在入口执行的定义表达式中的 yield 仍拒绝。 |
| R02 | 无赋值值的 AnnAssign 不作为输入写入；仍遍历目标中实际调用，避免把显式 pop 等操作藏在注解目标里。 | 带值的注解赋值、普通赋值、删除、所选变异方法仍拒绝。 |
| R03 | 复合语句按已遇到的重新绑定丢弃旧身份，后续 AST field 不复活它；条件内重新绑定后的本地对象放行。条件性或复杂绑定成为未知。 | 未重新绑定的直接分支写入、直线别名写入，以及循环目标绑定前在 iterable 中的真实输入变异仍拒绝。 |
| R04 | global/nonlocal 声明不直接报告 mutation；复用共享词法绑定记录，检查当前作用域中真正写入的 global 名称。局部闭包读写保持本地，类主体不继承外层函数的 global 声明。 | 模块全局赋值/注解赋值/增量赋值/删除/解包赋值、嵌套函数或类中明确 global 写入仍受所选 scope 约束；已识别宿主模块的实际修改仍拒绝。 |
| R05 | 改正 rules-and-nodes、rule-system-migration 及相邻 execution-model/workflow-and-config 的旧政策正文；不保留“默认 importlib 禁止、时间/随机禁令、命名重叠及 outputs 示例禁止”等矛盾说明。 | 实际入口、声明、运行输出协议、所选导入政策和真实架构限制保留。新包将纳入相同手册。 |

没有恢复参数污染、异常出口、返回值构造、复杂闭包、固定点或安全分析器；不把未知变成硬错误，也不把真正违规统一降为 warning。

## 执行中的成本、目标与路线复核

结果目标仍是正确约束 Node 关系、接口与选中的有限质量规则。关键假设是误判可以借现有 AST/词法身份消除，不需要证明 helper 的业务行为或所有控制路径。首次真实 CLI 复跑支持该假设：38 项中 7 个误判转为 PASS，另外 31 项结果和诊断保持原样。它们是观察，不能写成 38 项全部 PASS，因为其中包含预期拒绝。

新增 78 项回归覆盖正常反例与真实拒绝，并在共享效果遍历的四类资源上下文对照。受影响七文件回归合计 1938 passed；新测试开发阶段的导入路径及诊断代码断言错误已修正，日志原样保留，原有测试期待未改。局部闭包引用宿主模块的实际修改仍被拒绝，因此修正没有取消外部操作边界。

维护代价为三处现有 handler/遍历器的小修改及活动文档同步，没有新事实服务、路径合并或审批机制。共享遍历涉及四种上下文，因此修复后实际执行了一次完整批次，步骤耗时合计 1503.23 秒（25.1 分钟），其中规则对照/渲染组 696.2 秒。结果仅暴露新增报告缺少索引，未发现产品源码失败。结束后只修改 docs/README.md；2389 个原输入中的源码和随包使用者文档均未漂移，见 [输入复核](product-boundary-review-fixes-20261009/input-assessment.json)。因此补验对应文档和发行场景、重建两个包，不为索引变更再重复约 25 分钟的浏览器/SVG 整批。

复核节点已落实到正式 CLI 修正结果、完整批次结束、包内容核对与交付前。完整运行中没有修改源码；文档索引失败保留证据后补齐。文档补验首次遗漏可写 npm cache 环境，遇到沙箱内用户缓存只读的 EROFS；改用本轮专用可写 cache 后通过，未修改产品或放宽测试。实践支持继续既定有限规则路线，没有需要改变产品边界的分叉。后续新证据若推翻关键假设，仍按 critical-fork 解释后商讨并依通知资格提醒。

## 实际验收结果

| 验收 | 结果与证据 |
|---|---|
| 正式 CLI | 38 项观察，7 个误判转为 PASS，其余 31 项状态和诊断代码保持不变；包括真正生成器入口、输入写入、模块全局写入、文件 I/O 和 Node 耦合的拒绝对照。见 [结果判断](product-boundary-review-fixes-20261009/cli-assessment.json)。 |
| 受影响源码定向回归 | 1938 passed，包含新增 78 项原生 Rule 回归；见 [日志](product-boundary-review-fixes-20261009/targeted-tests-fixed.log)。 |
| 完整批次 pytest | 4097 passed / 1 failed，无跳过；唯一失败为新增报告索引缺项。见 [完整日志](product-boundary-review-fixes-20261009/full-verification.log)。 |
| 完整批次其他步骤 | 16 项通过：质量、compileall、Python 138/138、JS 最小真实 AOT及集成 67/67、parity 1219/1219、当前边界 680/680、真实浏览器、布局/资源/性能、适配 207/207、wheel 隔离、清理及双发行。见 [原始步骤结果](product-boundary-review-fixes-20261009/full-verification.json)。 |
| 索引修正后的文档/发行回归 | 21 passed；覆盖文档索引、两种发行内容、独立入口及实际 JS 渲染；见 [补验日志](product-boundary-review-fixes-20261009/documentation-regressions.log)。 |
| 最终记录与清洁检查 | 报告更新后的索引/重复正文 2 项通过，仓库质量 0 error / 0 warning，清理预览 0 项，git diff --check 通过。见 [记录检查](product-boundary-review-fixes-20261009/final-document-index.log)、[质量](product-boundary-review-fixes-20261009/final-quality.log)、[清理预览](product-boundary-review-fixes-20261009/final-clean-workspace.log)。 |
| 重新打包与内容审计 | 两种发行包重新生成；335 个产品文件与 wheel 和两包内核逐字一致；规则手册、迁移手册、工作流手册与职责边界说明一致，未打包维护者/设计报告。见 [包审计](product-boundary-review-fixes-20261009/package-audit.json)、[退役审计](product-boundary-review-fixes-20261009/final-retirement-audit.json)。 |

## 修正后的本地交付

保持本轮尚未发布的版本 0.17.0、Workflow ABI v5 和 AOT manifest v2；以下新文件包含审核修正。旧整改证据目录中的同版本包仍是旧版本内容，不能混用；以路径和 [SHA-256 清单](product-boundary-review-fixes-20261009/local-distributions/manifest.json) 区分。

- [wheel](product-boundary-review-fixes-20261009/local-distributions/vibeflow-0.17.0-py3-none-any.whl)
- [collaborative 发行包](product-boundary-review-fixes-20261009/local-distributions/vibeflow-distribution-0.17.0.zip)
- [autonomous 发行包](product-boundary-review-fixes-20261009/local-distributions/vibeflow-distribution-autonomous-0.17.0.zip)

## 证据与临时环境

[证据目录](product-boundary-review-fixes-20261009/) 保存修改前原文及哈希、before/after CLI、CLI 结果判断、定向测试和完整批次日志。审核原文、审核 fixtures、历史基线和旧包保持原貌；没有提交、推送或远端发布。主要机器报告压缩保存，实际生成证据及辅助脚本归档为 generated-evidence.tar.gz；新包保存后清理本轮专用 scratch、npm cache 和辅助脚本，目录占用约 2.00 GiB，逐项路径及结果见 [清理记录](product-boundary-review-fixes-20261009/cleanup.json)。PASS 仍不证明业务正确性、安全、通用执行语义、确定性或全部副作用排除。
