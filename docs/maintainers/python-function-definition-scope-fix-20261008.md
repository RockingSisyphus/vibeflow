# Python 函数定义表达式作用域修正

本记录跟进[独立复核 F01](system-migration-remediation-review-20261008.md)：迁移后的共享效果遍历器先进入函数体的局部作用域，再检查整个函数定义，导致默认值里的宿主引用被同名参数或函数体绑定遮蔽。原审计、独立复核及第三批全量验收均保留其当时的观察，不改写为本次修复结果。原来的效果矩阵未覆盖此反例。

## 确认与实现

修复前重放原复核的 40 项矩阵，源码快照与保留的第三批 kernel 各有 28 项漏检。另通过正式 `validate --workspace --config --json` 检查 Node、BaseLib、Plugin，通过公开 Rule 编译与执行接口检查普通源码；同一 scope 下的导入别名与参数改名对照确认结果受局部名字影响。检查程序只解析被审查的效果代码，不执行其中的 I/O。

共享遍历现在先在外层作用域检查默认值、装饰器及已有静态注解表达式，再进入函数体。同步函数、async 与 lambda 使用一致的默认值边界；局部绑定只遮蔽函数体内的宿主身份，外层有效别名、闭包局部绑定、显式 global 与 nonlocal 的归属分别保留。模块别名快照由共享模块遍历推进，BaseLib 仅以回调提供自身结构政策及诊断适配。

Node 与 module helper 的输入归属也只在函数体入口切换：真实 `run_pure.inputs` 及解析的 helper 参数建立输入事实，闭包继承未被局部绑定遮蔽的输入别名，lambda 的同名参数能遮蔽外层输入。删除把任何名为 inputs 的变量直接认作业务输入的兜底。默认表达式访问模块 inputs 不再因此误报，函数体或嵌套定义表达式修改真实业务输入仍拒绝。

SourceContext 原来也使用函数体绑定解析签名，并将闭包局部引用误认作模块引用。它现在与效果 visitor 共用定义表达式和局部绑定的提取，签名使用外层绑定，函数体继承外层函数的绑定，显式 global 恢复模块归属。真实模块别名默认值不会再因参数改名改变源码依赖。

Lambda 默认值与函数体在引用解析中也分别使用外层和参数绑定，防止将参数调用误解析成同名的导入纯函数。简单模块函数别名通过实际 Name/Attribute 引用链获得函数体证明，global 依赖及结构诊断仍保留；函数调用的返回值、字面量或循环别名不会因此被当作已证明的函数。

Node helper 源码切片补入所选函数内部嵌套定义的已解析模块依赖及其赋值，避免 `global emit` 的真实模块别名被遗漏；依据修正后的 resolved references 建立依赖，不把同名局部变量直接当作模块依赖。资源身份、Rule 参数、诊断等级、权限和依赖政策均继续沿用原合同。

本次不扩展类命名空间、延迟注解或泛型参数的完整执行时机分析，不推断任意反射。已有函数体、ExitStack、真实 helper、Node 输出合同与资源结构检查继续保留。

## 本次验收

使用 `tools/run_tests.py` 运行新增作用域回归及现有效果、ExitStack、BaseLib 和导入政策测试；每批完整收集失败后集中修正。新增为 14 个测试函数展开的 389 个 pytest 参数组合（325＋64），该测试文件最终共 674 项。同步覆盖真实输入归属、helper 依赖及 lambda 引用证明，保留已有测试预期。

首批完整 17 阶段均已结束，15 阶段通过，pytest 为 2885 passed、1 failed；唯一测试失败是新增修复记录缺少文档索引，初始 quality 另因 tools/__pycache__ 生成缓存失败，末尾正式清理与 quality 已通过。工作流、规则对照、真实浏览器、性能、隔离 wheel 和两个 profile 构建均通过。首批冻结源码未在批次内修改；并行只读复核暴露的 lambda 引用证明遗漏在独立副本验证后，待首批结束集中修正并加入回归。

最终固定六个产品文件后重新执行完整批次，期间源码和测试未修改。最后源码的验收结果如下；旧第三批和此次首批均只作为历史记录。

| 验收 | 最终结果 | 证据 |
| --- | --- | --- |
| 定向测试及文档索引 | 962 passed，0 failed | [定向汇总](python-function-definition-scope-fix-20261008/targeted-tests.json) |
| 独立 `python -B quality/test.py` | 49 passed | 同上 |
| `python -B tools/verify_project.py --full` | 17/17 阶段通过；pytest 2950 passed | [最终完整批汇总](python-function-definition-scope-fix-20261008/full-02-summary.json) |
| Python / JS 集成 | 138/138、67/67；JS 最小端到端通过 | 同上 |
| 规则矩阵 / 边界 / 适配 | 1219/1219、680/680、207/207，零进程错误 | 同上 |
| 最终源码独立对照 | 72/72；原 F01 40/40，原 28 项漏检均修复 | [源码结果](python-function-definition-scope-fix-20261008/source-default-scope.json) |

完整批的[17 阶段原始结果](python-function-definition-scope-fix-20261008/full-02-verification.json)还记录真实浏览器观察、review 布局、资源展示、性能、隔离 wheel 安装与两个发行 profile 构建通过；末尾 quality 为 0 error、0 warning、0 info，清理检查为零项。首批 15/17 的记录仍见[首批结果](python-function-definition-scope-fix-20261008/full-01-verification.json)。修复前的源码和旧 kernel 对照保存在[基线摘要](python-function-definition-scope-fix-20261008/baseline-summary.json)。

完整批通过后，分别加载其隔离安装的 wheel、collaborative kernel 和 autonomous kernel，重新执行产品行为验收。三个产品各通过 72 项默认值对照、原复核 40 项、873 项 Python 效果、20 项输入合同、33 项 JS 参数案例，共 3114 项。162 个正式 CLI 子进程及各探针的产品加载来源均无混入。导入别名与参数改名成对结果一致；输入合同失败时业务 Node 调用和原生 trace 均为零。JS 的 A→B→A→C→B 参数切换保持预期拒绝结果及对应 effect_policy records，返回已缓存的 A/B 时不新增原生请求。[产品行为结果](python-function-definition-scope-fix-20261008/packaged-final-summary.json)记录逐产品数量、来源和切换事实。

wheel 文件、安装后的 wheel、两份 kernel、两份 profile ZIP 内嵌 kernel 的六个修改文件均匹配最终冻结源码；两份 kernel 字节一致。[构建与哈希记录](python-function-definition-scope-fix-20261008/final-artifacts.json)保存完整 SHA256；[源码变更清单](python-function-definition-scope-fix-20261008/source-changes.json)保存修复前后哈希。72 项正式接口对照的[复验程序](python-function-definition-scope-fix-20261008/default_scope_probe.py)接受 `--source`、`--kernel` 或隔离安装的 wheel，使用新的 `--work` 目录运行；原 40 项复核程序保持原样。

结果与构建哈希已汇集于本记录同名证据目录。详细原始日志在本地 `dist/python-default-scope-validation-20261008/`，早期定向批次日志在 `dist/unification-validation-20261008/`。本次未提交、推送、正式发布或覆盖默认发行目录。

后续[独立复核](python-function-definition-scope-review-20261008.md)确认这些默认值案例通过，但发现未覆盖的推导式词法作用域回归 F02。本记录保留当时结果；进一步修正与验收见[推导式作用域记录](python-comprehension-scope-fix-20261008.md)。
