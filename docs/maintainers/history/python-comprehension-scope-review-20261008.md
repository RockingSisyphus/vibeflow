# Python 推导式修复独立审核

结论：上一轮 F02 的推导式目标泄漏、真实输入漏检及纯 `close()` 误报已修复，更早的 F01 默认值问题没有回退。本轮检查没有确认新增回归。但“相关作用域与输入归属问题已全部解决”仍不能验收：新增独立对照发现 **2 个既有问题仍然存在**，均可通过正式 CLI 复现，旧 kernel 同样存在。不能把它们计为本轮引入的问题，也不能用原反例全部通过来排除它们。

本次只审核、记录证据，没有修改产品代码、原有测试或此前报告，没有提交、推送或发布。

## 审核对象与方法

工作区 HEAD 为 `9c443f3111e65e6f99842d86d983416a745d391b`；审核的是未提交工作区，相对于[上轮独立审核快照](../evidence/index.md#artifact-8211bdb26f655b68)，334 个产品文件中只有以下 4 个发生变化，没有新增或删除产品文件：

- `source_analysis/bindings.py`：函数绑定收集及推导式求值分段。
- `source_analysis/visitors.py`：效果检查及推导式内外别名恢复。
- `source_analysis/input_tracking.py`：实参输入身份、闭包与声明归属传播。
- `source_context.py`：调用引用与推导式局部名称解析。

以上路径均相对于 `src/vibeflow/targets/python/quality/`。核对[开发者本轮修复说明](python-comprehension-scope-fix-20261008.md)，重放历史独立脚本，并另写局部别名外逸、直接突变与 helper 突变的对照。待审查的业务代码仅解析或 validate，没有执行；另用无 I/O 的合成 Python 核实实际语言语义，见[身份证明](../evidence/index.md#artifact-1242e20c9867b1ef)。

关键假设复核：共享推导式求值分段确实消除了原 F02，函数默认值仍在外层环境检查；但“所有消费者已共享变量身份”尚不成立。效果别名仍可丢失局部身份，直接突变 visitor 与 helper 实参传播仍有差异。这不需要改变用户目标或权限政策，属于当前审核范围内的实现缺口。

## F03：推导式局部对象经别名外逸后，仍会冒认宿主对象（P2，既有）

定位：`visitors.py:352–356` 的 `_record_effect_assignment_aliases`，以及 `285–299` 的推导式外层别名恢复；`ast_rules.py:73–87` 的名称解析为相关根因。

```python
import sys
def task(objects):
    [(alias := sys) for sys in objects]
    return alias.argv
```

这里推导式的 `sys` 是调用者提供的局部对象，`alias` 指向同一个局部对象。当前源码、wheel、新旧 kernel 都仍报告 `banned process argument access: sys.argv`。只把推导式目标 `sys` 改为 `item`，判断便恢复允许；直接在推导式内部读取 `sys.argv` 的局部对象控制也允许。

进入推导式虽然移除了导入 `sys` 的别名，但 `qualified_reference_name` 对未解析的局部 Name 回退为文本 `sys`。赋值记录随后把这个文本当成已解析身份保存为 `alias -> sys`；离开推导式又将它带出，外层读取因此命中宿主策略。`sys.stdout` 的局部属性外逸也有同类误报，嵌套推导式和 lambda 默认值不能消除此问题。

独立矩阵中，该根因覆盖普通 Python source、Node、BaseLib、Plugin 的 **16 项误报**。正式 SDK→RulePlan→CLI 对照确认 Node、BaseLib、Plugin 同名目标均 FAIL，改名目标均 PASS。它会阻断合法局部数据处理，让重命名改变规则结果。

这是旧 kernel 已有的缺陷；本轮没有新增，但修复说明中“不能把推导式局部身份带出”的边界尚未完整成立。整改需要保留局部/导入身份的区别，不能通过豁免 `alias.argv` 或放宽宿主策略解决。

## F04：声明归属只修复 helper 传播，直接输入突变仍漏检（P2，既有）

定位：`visitors.py:524–540` 的 Node `_visit_function_body`；module helper 的同类进入/退出处理也存在分离的状态。新 `_InputCallFacts` 的声明归属尚未成为直接突变检查的共同事实。

```python
def run_pure(self, inputs, params):
    alias = {}
    def inner():
        nonlocal alias
        alias = inputs
    inner()
    alias.pop("seed", None)
    return {}
```

在 `effect_scope=global_state` 下，这个 Node 通过正式 CLI，未报告输入突变。`global alias` 变体同样通过。合成 Python 证明两者均实际删除原输入字典的键；`global_state` 的可变状态权限并不取消业务输入不可突变的合同。

对照仅把最后一行换成 `sink(alias)`，其中 `sink(payload)` 执行同一个 `payload.pop(...)`，便在正式 CLI 被拒绝并报告 `module helper must not mutate inputs via pop`。

新 `_InputCallFacts` 已将 nested nonlocal/global 的写入事实传播到 helper 实参，所以 helper 对照正确。但直接 visitor 退出内层函数时恢复先前 `_input_aliases`，没有按声明归属将事实写回。两条检查链由此对同一变量身份给出相反判断。这里的 `inner` 是同一个 `run_pure` AST 内的嵌套函数，不能用修复说明保留的“独立 callee 写回摘要不扩展”边界解释。

独立矩阵为 **2 项漏检**；正式 SDK→RulePlan→CLI 确认 direct 两项 PASS、helper 两项 FAIL。旧 kernel 的这四项结果与当前相同，因此也属于既有遗漏，不是本轮引入。整改应将声明归属事实用于直接读取和突变检查，并保留同名局部字典及 lambda 参数的独立身份。

## 独立验证结果

| 检查 | 当前结果 | 说明 |
| --- | --- | --- |
| 原 F02 180 项 | 源码 / 新 kernel / wheel 各 180/180 | 原独立脚本未修改 |
| 原 F01 40 项 | 源码 / 新 kernel / wheel 各 40/40 | 默认值问题未回退 |
| 推导式正式 CLI 原 89 项 | 89/89 | 重跑既有项目构造脚本，含同名/改名、纯 close、输入突变 |
| 默认值正式接口 72 项 | 72/72 | 重跑既有脚本，导入别名和参数改名结果一致 |
| 新增独立静态对照 36 项 | 源码 / 新 kernel / wheel 各 18 符合、18 不符 | 16 项 F03、2 项 F04；旧 kernel 19 项不符，多出的 1 项本轮已修复 |
| 新增正式 CLI 对照 10 项 | 源码 / 新旧 kernel 各 5 符合、5 不符 | 3 项 F03、2 项 F04；其余是改名和 helper 控制 |
| 相邻分析、输入、效果测试 | 1471 passed | 使用仓库隔离测试入口，4 workers |
| quality 独立自测 | 49/49 | 不代替业务语义验收 |
| 产品文件逐字节核对 | 334/334 | wheel、两个 kernel、两个 profile ZIP 内嵌 kernel 均等于当前源码 |

本次重跑的原案例共 821 项均匹配预期（源码 381、新 kernel 220、wheel 220）。新增对照按相同脚本在旧 kernel 与当前产品逐案比较：**没有出现旧版正确、当前错误的案例**；静态对照有一项旧漏检被修复，正式 CLI helper 对照也确认新增声明归属处理的正确结果。

这不是项目全量回归或所有可能 Python 语义的证明。本次没有重新执行开发者声明的完整 17 阶段、3589 项 pytest、浏览器或 JS 验收；这些仍属于开发者提供的记录。也没有重新审计全部历史版本的所有模块。本次覆盖本轮实际 4 个产品文件、相邻消费者、原 F01/F02 及新增反例，未确认本轮引入新问题。

## 可复查证据

所有逐案报告与独立脚本见[证据目录](../evidence/index.md)：

- [源码与五份产物哈希](../evidence/index.md#artifact-6e8d9d10d60ae07a)。新 kernel SHA256 为 `6be7bcabb626abc067da8208b43220a62a3bd3d079642ea83da61332dcfb5373`；旧 kernel 为上一轮审核的 `54d848c1dfc5e6143d1414882e996f141c9b721a15d49a0694fa26b72ed58117`。
- [36 项独立脚本](../evidence/index.md#artifact-0d20e380eea41365)、[当前源码](../evidence/index.md#artifact-88d5942ce7956c2d)、[旧 kernel](../evidence/index.md#artifact-589e0c1eed88995d)、[新 kernel](../evidence/index.md#artifact-d0e97b62870a2624)、[wheel](../evidence/index.md#artifact-00134fca3a6d3dff)。
- [正式 CLI 独立脚本](../evidence/index.md#artifact-97d8e70b9c0f9ef3)、[源码结果](../evidence/index.md#artifact-99e061689dbb5e38)、[旧包结果](../evidence/index.md#artifact-e10a4b3d01e85d3f)、[新包结果](../evidence/index.md#artifact-2396f3537865af3c)。脚本复用开发者既有项目构造函数，仅生成独立 scratch 项目；实际规则通过隔离进程加载指定产品执行。
- [原正式 CLI 89 项](../evidence/index.md#artifact-da27f49fe1e4dac4)、[默认值接口 72 项](../evidence/index.md#artifact-adc7eb8a96a7b0dc)。
- 测试、项目完整 stdout/stderr 和运行 scratch 在 `dist/python-comprehension-independent-review-20261008/`；摘要见[独立验收记录](../evidence/index.md#artifact-58caccc4568cb9d3)。

建议接受原 F01/F02 的具体修复，同时将 F03/F04 作为明确的剩余项跟踪；在它们关闭前，不将“全部相关问题已解决”作为最终结论。
