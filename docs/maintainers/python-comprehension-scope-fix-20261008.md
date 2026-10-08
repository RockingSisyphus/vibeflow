# Python 推导式作用域修正

本记录跟进[独立复核 F02](python-function-definition-scope-review-20261008.md)。上一轮函数默认值修复引入了推导式 target 向整个 lambda 泄漏的问题，同时保留跨文件纯 `close()` 的相关误报。原审计与上一轮验收记录保持原来的观察；原有 40 项默认值反例和 72 项正式接口对照并未覆盖此问题。

## 复现与作用域合同

修复前完整保存了 334 个产品文件，并逐字节核对上一轮最终 kernel。两个产品重放原报告的 180 项均有 112 项不符预期：108 项新增宿主/输入漏检、4 项既有纯 helper 误报。另以正式 CLI 验证 89 项，两个产品逐案一致，37 项不符预期；所有检查仅解析待审查代码，没有运行其中的业务 I/O。

推导式 target 属于推导式自身，不能成为包含它的 def/lambda 的局部绑定。最外层 iterable 使用外层环境；其余 target、条件、后续 iterable、结果表达式属于推导式环境。所有迭代 target 在该环境中都是词法局部名称，尚未赋值的后序 target 也不能回退成同名模块或导入 helper。嵌套推导式、lambda 的默认值与函数体分别沿用各自的实际环境。

因此 `lambda: (sys.argv, [sys for sys in ()])` 应检出外层宿主访问，`lambda: [sys for sys in sys.argv]` 应检出最外 iterable 的访问；`lambda: [sys.argv for sys in ()]` 的 sys 属于推导式局部对象，应保留允许结果。真实 `inputs.pop(...)` 与推导式 target 也遵循同样边界；纯 `close()` 的外部调用使用实际 helper 函数体证明，内部同名局部 callable 不获得这个证明。

## 实现与保留边界

共享 bindings 提供推导式求值分段，效果 visitor 与 SourceContext 都消费这份词法事实。函数绑定收集跳过推导式 target 的 Store，保留实际绑定到包含函数的赋值表达式；嵌套函数/lambda 的定义表达式使用包含环境，函数体不向外泄漏局部变量。解包 target 包括 Starred。

效果遍历进入推导式时同时切换宿主别名和输入别名，离开后恢复外层。Node 与 module helper 的输入事实使用同一作用域字段；walrus 建立的外层别名按可能发生的赋值保留，不能把推导式局部身份带出。最外 iterable 始终在切换前检查，推导式内部的实际效果也继续检查。

SourceContext 对每段使用对应绑定，保留模块引用、依赖与 ownership 事实。它不因函数叫 `close` 授予或拒绝效果：可解析 helper 根据函数体检查，未知局部 callable 不借用同名导入的证明。资源身份、有效 Rule 参数、诊断等级与权限政策均沿用原合同。

增量验证还确认，`alias := inputs` 传给 helper 时，既有整棵 AST 的名字收集遗漏了真实输入事实。helper 输入传播已改为按调用处记录实参归属，复用共享词法分段；局部推导式 target 和 lambda 参数不能冒认业务输入，同一 helper 真正收到业务输入时继续保护其突变。正式 resolved helper 链与低层入口使用同一份事实；原生方法的隐含 self/cls 位置、关键字参数及原有分支、循环和闭包的保守别名保护保留。

首轮完整批期间，独立终审确认这次输入事实调整遗漏了 nested `nonlocal/global alias = inputs` 写入的真实归属，属于新回归；同根 walrus 外逸也有既有漏检。修正通过共享函数绑定事实确定一个声明归属：nonlocal 写入最近的外层函数，global 写入模块；只有读取同一变量身份的作用域收到输入事实。调用者同名局部字典、推导式 target、lambda 参数和 lambda 函数体内的赋值保持独立，默认值表达式仍在包含环境中处理。

新活动文件另保存 39 项声明归属回归，包括正式 effects 结果、resolved/fallback helper 输入传播、AST 不变与合法语法控制。输入事实仍保持原有的可能别名保守分析；不新增独立 callee 的 global/nonlocal 写回摘要、动态反射或完整运行时实参绑定器，不扩展类头与延迟注解的执行时序承诺。

交付前按更新的关键分叉规则复核目标与假设：反例否定了“同名 Store 可以作为整个函数的绑定或输入身份”的假设，支持在各消费者之间共享真实词法分段与声明归属。当前修正恢复既定判断，不需要改变 scope 权限、执行合同或上述分析边界；没有尚待用户裁决的目标取舍。

## 本次验收

新增活动测试在独立文件保存，原有断言和独立复核脚本保持不变。最初 428 个参数组合完整红灯为 146 passed、282 failed；后续 160 项增量为 156 passed、4 failed，四项失败均为 walrus 真实输入别名经 helper 的突变漏检。再补入 12 项 helper 调用处身份控制，共 600 个参数组合。独立 SourceContext 副本的 41 项引用事实及原 180 项矩阵已通过，尚不作为最后产品的验收结论。

第一批定向为 1561 passed、2 skipped，600 项新增回归全部通过；同一 334 文件快照的原 180、正式 CLI 89、默认参数 40/72 共 381 项全部匹配。首轮完整批 17/17 通过、pytest 3550 passed，冻结输入无变化，但因上述独立终审发现而不作为最终接受版；其记录保留。声明归属修正副本的 39 项活动回归为 39 passed（前一版 26 passed、13 failed），另 1296 项既有及新增分析测试、7 项输入检查通过，均核对真实模块来源。

声明归属修正集中合入后，[最终定向](python-comprehension-scope-fix-20261008/targeted-summary.json)为 **1600 passed、2 skipped**，独立 quality 自测 **49/49**。最终 334 文件快照的[源码重放](python-comprehension-scope-fix-20261008/after-source-summary-r2.json)共 **415/415**：原 F02 180、正式 CLI 89、原 F01 40、默认值正式接口 72、声明归属 SDK→RulePlan 34。原脚本和断言保持不变，同名/改名及默认值参数改名判断一致；所有加载来源都属于所选快照。

[第二轮完整验收](python-comprehension-scope-fix-20261008/full-02-verification.json) **17/17 阶段通过**，pytest **3589 passed**；Python 集成 **138/138**、JS 集成 **67/67**、[规则对照](python-comprehension-scope-fix-20261008/rule-parity-summary.json) **1219/1219**、[规则缺口](python-comprehension-scope-fix-20261008/rule-gaps-summary.json) **680/680**、[适配回归](python-comprehension-scope-fix-20261008/adaptation-regressions-summary.json) **207/207**。真实浏览器观察、布局、资源展示、缓存性能、隔离 wheel 与两个 profile 构建均通过。最终完整批和包级重放期间，2848 个冻结输入逐一比较，无变化。

[新产品行为验收](python-comprehension-scope-fix-20261008/packaged-final-summary.json)从新 wheel、协作 kernel、自主 kernel 分别执行以下案例，原七组共 **3921/3921**，额外声明归属 **102/102**，合计 **4023/4023**：

| 每个产品 | 案例数 | 结果 |
| --- | --- | --- |
| 原 F02 矩阵 / 正式 CLI | 180 / 89 | 全部匹配；保留推导式内部局部对象允许结果，纯 close 误报消除 |
| 原 F01 矩阵 / 正式默认值接口 | 40 / 72 | 全部匹配；导入别名与参数改名判断一致 |
| Python 效果 / 输入合同 / JS 参数 | 873 / 20 / 33 | 全部匹配；输入拒绝时 native/JS Node 执行 0，native trace 0 |
| 声明归属 SDK→RulePlan | 34 | 全部匹配；另核对外部 nonlocal 选定函数根的两个调用身份与语法控制 |

包级 JS 参数顺序 A→B→A→C→B 的判断、cache entries 和 native 请求增量均符合原合同。实际 JS driver SHA256 与冻结清单一致。全部 **334 个产品文件**（含 19 个非 Python 文件）与 wheel、两个独立 kernel 及两个 profile ZIP 的内嵌 kernel 逐字节一致，均无外部产品模块混入；原审计及复现脚本字节未变。完整[产物与源码哈希](python-comprehension-scope-fix-20261008/final-artifacts.json)保存于同名证据目录。

详细逐案 JSON 与日志保存在本地 `dist/python-comprehension-scope-validation-20261008/`，构建保存在仓库外的独立缓存目录；两个独立 kernel 与内嵌 kernel 的 SHA256 均为 `6be7bcabb626abc067da8208b43220a62a3bd3d079642ea83da61332dcfb5373`。本次不提交、推送、正式发布或覆盖默认发行目录。
