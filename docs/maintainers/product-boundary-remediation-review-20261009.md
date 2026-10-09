# 产品职责边界整改独立审核（2026-10-09）

**结论：主要整改真实生效，但不能认定已经全部完成。发现 5 项需要修正的问题，其中 2 项经整改前后源码对照确认是新引入的误判；另有旧误判和公开说明残留。**

本审核沿用[职责边界与整改规格](/home/rockingsisyphus/projects/VibeFlow/docs/maintainers/product-boundary-refactor-spec-20261009.md)：VibeFlow 限制 Node 关系和 Node 内代码质量，不证明业务正确性、代码安全性或通用执行语义。下面的问题是限制器自身认错检查对象、越过已约定边界或交付说明不一致，不要求开发者继续修通用业务语义分析器。

本次只审核、验证并记录结果，没有修改产品源码、已有测试或发行包，也没有提交、推送或发布。不能将定向测试通过解释为不存在其他缺陷。

## 审核基线与已确认的实质改动

审核对象是 HEAD 5b9f9763ab7051fc964a4d83a1419d87a621b4c9 加当前未提交整改，声明版本 0.17.0、Workflow ABI v5、AOT manifest v2。

审核开始时，独立核对开发者 full-verification-4-input.json 中的 2388 个输入文件，全部匹配；读取本地 wheel 的 335 个产品文件，与当前源码逐字一致。因此本次发现的问题也存在于开发者已验收、已打包的版本，不是审核期间源码漂移导致。随后仅新增审核文档、证据及文档索引，产品源码保持不变。

开发者的完整记录确实有 17 个步骤全部通过。本次没有重跑整个完整批次，也没有将开发者的 4020 项 pytest 成绩冒充独立重跑结果。

已核对的主要整改：

| 规格项 | 实际情况 |
|---|---|
| B01 有限输入写入 | 通用参数污染／异常／闭包／生成器消费分析退出，改成独立有限 Rule；仍有 R02、R03 的误报 |
| B02 输出构造推断 | 静态字典／返回键推断删除，helper 构造放行；实际 Mapping／输出键协议保留 |
| B03 动态分派 | 专用分析器、模型字段、plan、portable adapter 和展示消费者已退役；实际协调机制保留 |
| B04 算法循环／递归 | 默认 while 和私有递归硬拒绝已移除；对应原反例通过 |
| B05 字段与对象赋值 | 名称黑名单和任意对象赋值拒绝已移除；普通 client 字段、Box 属性和 setattr 对照通过 |
| B06 效果规则 | 叶名猜测、FFI／动态求值安全禁令及静态 ExitStack 补偿退出；仍保留 R04 的声明即违例逻辑 |
| B07 JS 确定性 | Date、Math 动态成员和随机数原反例放行；不是继续默认承担确定性证明 |
| B08 接口命名与示例 | 重叠命名、Decision 名字和 examples.outputs 三项旧拒绝删除；新增入口检查存在 R01 |
| B09 lock 资格 | 构建、ToolchainInfo 和 publish 的强制 lock 字段删除；真实构建／执行／替换发布通过 |
| B10 Rule 归位 | architecture、input_writes、effects、interface 独立选择，使用既有 SourceContext；正式 CLI 证明空选择不隐式补回架构规则 |
| B11 退役与说明 | 主体退役有效，not_checked 已补充职责排除；活动使用者正文及两种发行包仍有 R05 的旧规则说明 |

## R01　[P2] 新入口检查误把嵌套 helper 的生成器当成 run_pure

**性质：本次新增回归。**

位置：[node_interface.py：入口检查](/home/rockingsisyphus/projects/VibeFlow/src/vibeflow/targets/python/quality/rules/node_interface.py:37)，根因在[_entry_body_nodes](/home/rockingsisyphus/projects/VibeFlow/src/vibeflow/targets/python/quality/rules/node_interface.py:87)，尤其是直接对 method.body 中每个 statement 调用 walk 的路径。

合法例子：run_pure 内定义 values()，values() 使用 yield；run_pure 调用 list(values()) 后正常 return {}。当前正式 validate 报 NODE.CONTRACT.GENERATOR_RUN_PURE 并失败。原生 Rule 还确认嵌套 async generator 也会被误判。

walk 只在遍历 child 时跳过新函数／类作用域。但 statement 自身恰好是 FunctionDef 时，先进入 walk，再遍历其 body，因而把嵌套函数的 yield 算到了入口函数中。它不是在识别 run_pure 自身的调用接口。

整改前归档源码的同一正式 CLI 例子 PASS；当前 FAIL，确认属于新引入问题。对照案例中，入口自身包含 yield 仍会被当前规则拒绝，这个真实 ABI 限制应保留。

**需要修改到什么程度：** 修正遍历边界，让嵌套函数／类主体不归入入口自身。不能删除实际生成器入口的 ABI 校验，也不需要推断 helper 的返回值或消费语义。正常嵌套 helper PASS、真正的生成器入口 FAIL，即为本项停止点。

证据：[正式 CLI 对照](product-boundary-remediation-review-20261009/followup-cli-results.json)、[整改前对照](product-boundary-remediation-review-20261009/before-cli-results.json)、[原生补充](product-boundary-remediation-review-20261009/native-followup-results.json)。

## R02　[P2] 有限输入规则将无赋值的类型注解当作输入写入

**性质：原本已有的误判，在新实现中保留；不是新增回归。**

位置：[input_tracking.py：visit_AnnAssign](/home/rockingsisyphus/projects/VibeFlow/src/vibeflow/targets/python/quality/source_analysis/input_tracking.py:55)。

inputs['x']: int 只有注解，没有赋值值。当前分支在 node.value 为 None 时仍调用 _target，产生 NODE.PURITY.INPUT_MUTATION。正式 validate 因此 FAIL；有实际赋值的 inputs['x']: int = 1 对照同样 FAIL，规则没有区分两种情况。

本项不需要通用类型分析：AST 已直接提供有没有赋值值。将它表述成“输入被写入”超出实际依据。读取整改前归档并运行同一案例也会 FAIL，所以应列作收缩不完整的旧误判。

**需要修改到什么程度：** 无赋值值的注解不作写入诊断；仍保留真正的注解赋值、普通赋值、删除和所选变异调用限制。若其他必要检查需要遍历注解或目标表达式，按其自己的明确职责处理，不恢复类型证明或输入污染分析。

证据：[正式 CLI 对照](product-boundary-remediation-review-20261009/annotation-cli-results.json)、[原生补充](product-boundary-remediation-review-20261009/native-followup-results.json)、[整改前对照](product-boundary-remediation-review-20261009/before-cli-results.json)。

## R03　[P2] 复合语句重置旧别名，重新绑定后的本地对象仍被判为输入

**性质：本次新增回归。**

位置：[input_tracking.py：_compound](/home/rockingsisyphus/projects/VibeFlow/src/vibeflow/targets/python/quality/source_analysis/input_tracking.py:113)，尤其是每个 AST field 开始时重新设置 self.references 的处理。

正式 CLI 对照：

| 写法 | 当前结果 |
|---|---|
| if (inputs := {'local': True}): 内对 inputs['x'] 赋值 | FAIL，INPUT_MUTATION |
| 先 inputs = {'local': True}，再 if inputs: 内作同样赋值 | PASS |

前者条件表达式已经重新绑定 inputs 为本地字典。scanner 在访问 test 时清除了输入身份，但访问 body 时又恢复 compound 进入前的 references，使旧输入身份“复活”。这里无需判断字典内容是否正确、是否执行某种业务；问题是检查器丢掉了已见到的重新绑定。

整改前源码的前者正式 CLI PASS，当前 FAIL。另有直接分支内输入写入案例仍应 FAIL；不能为了消除此误报跳过整个复合语句。

**需要修改到什么程度：** 保留有限规则，不合并复杂路径；已明确重新绑定的名称不得在随后语句中恢复旧身份。复杂绑定可以成为未知，不因此产生硬错。继续遍历未重新绑定的直接输入引用，保留其真正写入检查。不要为此恢复异常类别、闭包、固定点或所有控制路径证明。

证据：[非空字典正式 CLI 对照](product-boundary-remediation-review-20261009/followup-cli-results.json)、[直接分支与直线别名对照](product-boundary-remediation-review-20261009/cli-results.json)、[整改前对照](product-boundary-remediation-review-20261009/before-cli-results.json)。

## R04　[P2] global／nonlocal 声明仍被直接视为外部状态修改

**性质：原逻辑未退役，职责收缩不完整。**

位置：[visitors.py：visit_Global／visit_Nonlocal](/home/rockingsisyphus/projects/VibeFlow/src/vibeflow/targets/python/quality/source_analysis/visitors.py:447)。这两个方法与整改前归档对应逻辑一致。

当前只要看见 global 或 nonlocal，且 scope 不是 global_state，就产生 NODE.PURITY.GLOBAL_STATE；不要求出现赋值。

正式 CLI 已确认：

- 仅 global VERSION 后读取常量，也报 global mutation。
- Node 内 value = 1 的局部闭包，仅 nonlocal value 后读取它，也报 nonlocal mutation。
- Node 内计数器闭包修改自己的局部 value，也被当作需要 global_state 的外部状态操作。
- 对真实模块变量赋值的对照会失败；这类明确共享状态边界仍需保留。

前两种连“修改”都不存在；第三种是本次 Node 调用内部状态，不等同于跨 Node 模块共享状态。这与放行本地对象操作、只限制明确外部关系的定位不一致。让用户删一个合法声明来避开误报，或把整个 Node 放到 global_state 下，不是合理整改。

**需要修改到什么程度：** 不因声明本身报告 mutation，不把 Node 内局部闭包统一升级为外部状态。保留有限可识别的真实模块／共享状态写入和所选导入政策。若无法识别复杂闭包归属，不作通用行为证明，也不把未知当硬错误。项目确需禁用这类语法时，用明确的风格政策表达，不能继续藏在效果分类中。

证据：[正式 CLI global／局部闭包例子](product-boundary-remediation-review-20261009/cli-results.json)、[只读 nonlocal 正式 CLI](product-boundary-remediation-review-20261009/annotation-cli-results.json)、[原生只读对照](product-boundary-remediation-review-20261009/native-followup-results.json)。

## R05　[P2] 活动手册与发行包仍把已退役的规则写成当前要求

**性质：B11 的说明清理未完成；源码与用户指引冲突。**

准确位置：

- [rules-and-nodes.md:122](/home/rockingsisyphus/projects/VibeFlow/docs/user/rules-and-nodes.md:122)：仍称 JavaScript 继续执行时间／随机数检查。
- [同文件:126](/home/rockingsisyphus/projects/VibeFlow/docs/user/rules-and-nodes.md:126)：仍称 effects 默认根禁止 importlib；当前 normalized_import_policy 已删除此默认禁止。
- [rule-system-migration.md:92](/home/rockingsisyphus/projects/VibeFlow/docs/user/rule-system-migration.md:92)：仍重复默认禁止 importlib。
- [同文件:96](/home/rockingsisyphus/projects/VibeFlow/docs/user/rule-system-migration.md:96)：仍称默认检查 Decision 名字、契约重叠，且 Python 接口 Rule 禁止 examples.outputs。

新 product-check-boundaries.md 写了相反的正确目标，但上述活动正文只改了 ABI 版本，没有同步清理行为说明。读取 collaborative／autonomous 两个 0.17.0 ZIP，确认这些旧段落也已打包进去，不能仅称其为仓库中的历史说明。

它们会误导使用者继续改写正常代码、扩大效果 scope，或怀疑合法资料“不符合框架”；也会把后续维护重新引向已明确退休的目标。

**需要修改到什么程度：** 改正活动手册的上述事实，并核对相邻政策说明与当前 Rule 职责。历史报告保持原貌，活动文档不能靠末尾追加免责声明覆盖冲突正文。更新交付包内同一手册；不要为让旧说明再次成立而恢复旧检查。

## 独立验证结果与边界

| 本次实际执行／核对 | 结果 |
|---|---|
| 项目隔离入口的受影响 pytest 文件 | 1947 passed，34.45 秒 |
| 复用本次隔离依赖的真实 AOT 定向验收 | 8 passed，87 deselected；包含无 lock／yarn／pnpm 的构建、工作流执行、manifest 与替换发布，以及动态求值、真实 ABI 反例等 |
| 当前正式 validate CLI | 38 项观察；包括原 13 项限制例子、正常对照、预期拒绝和上述误判 |
| Python 原生 Rule 补充 | 4 项观察 |
| JS 原生 Rule | 5 项，Math／Date／random 原反例不再报旧错 |
| lock API | 3 项，实际尝试工具启动；错误是刻意不存在的 Node 命令，已无 lock 资格错误 |
| 整改前归档正式 CLI | 3 项，区分新回归与旧误判；提取的 335 个产品文件与归档 baseline 哈希匹配 |
| 完整验收输入版本／wheel 内容 | 2388 个输入未漂移；335 个源码文件与 wheel 相同 |

38 项 CLI 不是“38 项全部 PASS”的测试成绩：其中包括真正应该拒绝的直接输入写入、明确文件 I/O、选中架构规则的 Node 耦合，以及不应该拒绝却被拒绝的反例。

真实 Node 耦合的独立对照中，选中 architecture 时另一 Node 调用和内部读取 FAIL；普通节点 PASS。显式空 Ruleset 下上述源码限制不执行，符合既定选择机制，不能把空选择的 PASS 当作架构漏洞。

[审核摘要及当前源码哈希](product-boundary-remediation-review-20261009/summary.json)、[真实 AOT 日志](product-boundary-remediation-review-20261009/aot-tests.log)、[架构选择](product-boundary-remediation-review-20261009/architecture-selected.json)、[空选择](product-boundary-remediation-review-20261009/architecture-empty.json)、[JS 结果](product-boundary-remediation-review-20261009/js-results.json)均已保存。正式 CLI 的最小项目和 stdout 保存在 fixtures 目录。记录中的临时执行路径是原始现场元数据；隔离依赖和整改前解包副本用完即清理。

[CLI 复现脚本](product-boundary-remediation-review-20261009/reproduce_cli.py) 使用已保存的最小项目、隔离子进程和指定产品 src；可传入 --product /home/rockingsisyphus/projects/VibeFlow/src 复测。本次已实际重跑脚本的 38 项，状态和诊断代码与首次观察全部一致，见[重跑结果](product-boundary-remediation-review-20261009/reproduced-cli.json)。[临时目录清理记录](product-boundary-remediation-review-20261009/cleanup.json)确认只清理本次创建的隔离环境和解包副本。

## 后续修正边界

这轮不需要推翻整体整改，也不需要恢复已经删除的三套分析器。R01、R02、R03 都应以短小、明确的语法／词法规则修正；R04 继续收缩声明即违例的效果政策；R05 同步活动说明和交付内容。

先验证每项正常反例与保留的真实拒绝对照，再按实际改动执行相关回归。不要为这些问题重新创建输入污染、异常路径、返回值或安全绕过分析器，也不要用“全部改成 warning”掩盖真正架构限制。

开发者的完整测试通过成绩是真实记录，但现有案例没有覆盖上述反例；它不能支持“全部整改完成且没有引入问题”的结论。本审核也不声称穷尽所有语法和第三方插件行为。
