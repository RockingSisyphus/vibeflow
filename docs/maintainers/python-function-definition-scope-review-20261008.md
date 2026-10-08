# 函数作用域修复独立复核

日期：2026-10-08。复核当前未提交 0.16.0 工作树；HEAD 仍为 `9c443f3`，开始时有 549 项既有 Git 状态记录。以[上次独立审核](system-migration-remediation-review-20261008.md)保存的全产品哈希和旧 kernel 为基线，审查[开发者本轮修复](python-function-definition-scope-fix-20261008.md)。

**F01 默认参数漏检已修复，但本轮新增了 F02 推导式作用域漏检（P2），同时保留一类相关的纯 helper 误报。不能接受“已解决且未引入新问题”。** 这些判断来自修复前后同一代码的对照，不是仅看新增测试是否通过。

本次增加报告、复现脚本和证据、文档索引；未改动产品或活动测试，未提交、推送或发布。

## F02：推导式变量被错误地提升为整个 lambda 的局部变量（P2）

新增调用点：[bindings.py 56–57 行](../../src/vibeflow/targets/python/quality/source_analysis/bindings.py#L56)。`_function_scope_bindings` 开始对 lambda.body 使用 `_FunctionBindingCollector`，后者默认遍历推导式，将其 target 的所有 Store 名称收进 lambda 局部绑定。推导式有自己的名称作用域，不能这样提升。

消费该错误事实的有 `_EffectVisitor._visit_scoped_body`、Node/Module 的 `_visit_function_body` 输入归属，以及 [SourceContext 的 lambda 引用遍历](../../src/vibeflow/targets/python/quality/source_context.py#L354)。错误覆盖了宿主判定、输入保护及实际调用事实，不能只修某个诊断名称。

### 新引入的宿主访问漏检

```python
import sys

def helper():
    return (lambda: (sys.argv, [sys for sys in ()]))()
```

第一项 `sys.argv` 读取的是模块 sys；第二项空推导式里的 sys 只属于推导式。它不会改变第一项的身份，且空推导式没有任何迭代。当前把 sys 收进整个 lambda 的局部名称，丢掉模块别名，错误放行第一项。

| 同一代码 | 修复前 kernel | 当前源码 / 本轮最终 kernel |
| --- | --- | --- |
| `lambda: (sys.argv, [sys for sys in ()])` | 拒绝 argv 访问 | 无诊断 |
| 只把推导式 target 改为 item | 拒绝 argv 访问 | 拒绝 argv 访问 |
| set / dict / generator 的同名 target | 拒绝 argv 访问 | 无诊断 |
| `lambda: [sys for sys in sys.argv]` | 拒绝 argv 访问 | 无诊断；首个 iterable 也被错误遮蔽 |

普通源码、Node、BaseLib、Plugin，在五种 scope 下均复现，形成 **100 项新漏检**。进程 argv 访问本应在这些 scope 下全部拒绝；这不是权限选项差异。

正式 `validate --workspace --config --json` 也复现：BaseLib / Plugin 的同名 target 为 PASS，改名控制为 FAIL；Node 的修复前同名 / 改名都 FAIL，当前同名 PASS、改名 FAIL。见[BaseLib / Plugin CLI](python-function-definition-scope-review-20261008/comprehension-cli-current.json)及[Node 前后 CLI](python-function-definition-scope-review-20261008/node-cli-comprehension.json)。CLI 只做 validate，没有运行被检查的业务节点。

### 新引入的业务输入突变漏检

在真实 `run_pure.inputs` 或由 run_pure 调用的 `helper(inputs)` 内：

```python
fn = lambda: (inputs.pop('seed', None), [inputs for inputs in ()])
fn()
```

`pop` 作用于外层业务输入，推导式 target 不会使这个调用成为其他对象上的操作。当前输入归属切换却把 inputs 从真实输入别名中移除，导致突变保护失效。

method / helper 两种位置与 list / set / dict / generator 四种形态共 **8 项新漏检**。修复前全部检出，当前源码和新 kernel 均不检出。正式 Node CLI 对同名推导式也从旧版本 FAIL 变为当前 PASS；改名控制仍 FAIL，见上述 Node CLI 证据。

实际 Python 的[安全对象对照](python-function-definition-scope-review-20261008/python-evaluation-proof.json)确认：推导式外读取仍使用外层对象；pop 确实修改外层临时字典。没有读写文件、网络或用户业务数据。

### 仍保留的相关纯 helper 误报

另外一个独立跨文件对照定义真实可见的纯 `close(): return 1`，调用方为：

```python
from helper import close

def task():
    return (lambda: (close(), [close for close in ()]))()
```

推导式外 close() 仍调用导入的纯函数。四类资源却都报效果调用禁止；target 改为 item 后均通过。旧 kernel 也有这四项误报，**不是本轮新引入**。新 SourceContext 的 lambda 局部事实仍错误覆盖导入函数，未消除这类作用域问题。它与 F02 的修复边界相关，但不计为第二类新增回归。

### 修复边界及可重放证据

应正确区分函数 / lambda 与推导式的词法绑定，首个 iterable 使用外层作用域，其余推导式表达式使用实际推导式作用域；同步效果、输入归属与源码引用事实。处理赋值表达式时也应遵循其实际绑定规则。

不能只跳过所有推导式或禁止同名变量。有效控制 `lambda: [sys.argv for sys in ()]` 的 sys 是推导式局部对象，当前正确允许，旧 kernel 会误报；这 **20 项改善案例应保留**。仅从绑定收集中删除 target、仍把推导式内部引用当成模块对象，也会重新破坏这些控制项。

[独立复现脚本](python-function-definition-scope-review-20261008/reproduce_comprehension_scope.py)只解析被审查代码，不导入或执行它。180 项矩阵在三个产品中分别重放：

| 产品 | 总案例 | 不符预期 | 对照解释 |
| --- | --- | --- | --- |
| 修复前 kernel | 180 | 24 | 20 项推导式内部局部对象误报，4 项纯 close 误报 |
| 当前源码 | 180 | 112 | 108 项新增漏检，4 项既有纯 close 误报 |
| 本轮最终 kernel | 180 | 112 | 与当前源码逐案一致 |

108 是同一词法作用域缺陷的多种触发组合，不是 108 个独立缺陷。证据为[修复前结果](python-function-definition-scope-review-20261008/comprehension-previous.json)、[当前源码结果](python-function-definition-scope-review-20261008/comprehension-current.json)、[新 kernel 结果](python-function-definition-scope-review-20261008/comprehension-new-kernel.json)。

## 已确认修好的 F01 与本轮验证

共享函数遍历现在先检查定义表达式，再进入函数体；Node 与 helper 输入归属在函数体入口切换。原普通源码 / Node / BaseLib / Plugin 的 **40 项原反例与控制全部通过**，在当前源码和新 kernel 中均为 0 mismatch，原 28 项漏检已消除。见[源码](python-function-definition-scope-review-20261008/original-40-source.json)与[kernel](python-function-definition-scope-review-20261008/original-40-kernel.json)。

重新执行开发者提供的默认参数正式接口程序，当前源码 **72/72**，导入别名及参数改名的判断一致；其中资源使用正式 CLI，普通源码使用公开 Rule 编译执行。见[正式接口结果](python-function-definition-scope-review-20261008/default-formal-source.json)。这些用例修复成立，但没有覆盖 F02。

独立回归包含新增作用域测试及现有效果、真实 helper、ExitStack、资源、输入、绑定等十文件，**902 passed、2 skipped**；quality 工具自身 **49 passed**。见[回归日志](python-function-definition-scope-review-20261008/tests.log)、[quality 日志](python-function-definition-scope-review-20261008/quality-tests.log)。通过的既有测试不能抵消独立反例。

以最近审核的 334 文件哈希精确比较，本轮只改动六个产品文件：bindings.py、visitors.py、input_tracking.py、source_context.py、base_lib_effects.py、effects.py。没有出现已退役主入口被恢复或另外新增产品文件。`_function_bindings` 仍供 ExitStack 分析使用，不属于无消费者旧桥。

逐字节核对当前所有 **334 个产品文件**与本轮 wheel、两份 kernel、两份 profile ZIP 内嵌 kernel：无缺失、多余或内容差异，archive 大小与 SHA256 匹配开发者记录。F02 已进入生成产物，不能解释为拿旧包测试当前源码。见[独立源代码与产物核对](python-function-definition-scope-review-20261008/source-and-artifacts.json)。复核期间 334 个产品文件没有变化。

开发者本轮 17/17、pytest 2950、完整浏览器 / 工作流结果是已核对的既有记录；本次没有重新跑全量 17 阶段，两个 skip 不作为验收通过。本次未扩展类命名空间、延迟注解或任意反射分析；F02 属于基本推导式词法作用域，已有简单新旧对照即可确认。正式源码探针产生的 109 个字节码文件经时间窗口核对后已清理，仅移除本次自生成产物；最终仓库 [all profile](python-function-definition-scope-review-20261008/quality-final.log)通过，0 error / warning / info。

[独立汇总](python-function-definition-scope-review-20261008/independent-summary.json)记录新增、保留及改善案例的分类。完整隔离运行目录保存在本地 `dist/function-scope-independent-review-20261008/`。F02 修正后应先重放本报告的三组控制，再重跑对应回归和生成包入口。
