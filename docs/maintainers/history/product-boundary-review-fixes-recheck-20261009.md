# 职责边界审核修正的独立复核（2026-10-09）

结论：上次 R01—R05 的原反例及文档问题已经处理，但这轮 R03、R04 修正引入了两项可复现的漏检，暂不能认定整改完成。它们均属于已选择的有限质量政策，没有要求 VibeFlow 承担业务正确性、安全或完整语言语义证明。

审核对象是 HEAD `5b9f9763ab7051fc964a4d83a1419d87a621b4c9` 上的当前未提交整改。相对上次独立审核保存的 335 个产品文件哈希，本轮只改变了 `node_interface.py`、`input_tracking.py`、`visitors.py` 三个产品文件。审核期间产品源码没有变化。本次仅保存审核记录、反例和文档索引，没有修复产品或改写现有测试。

## 审核采用的职责边界

VibeFlow 限制 Node 间的实际关系和 Node 内部所选代码质量政策；它不证明算法、业务结果或代码安全，也不模拟所有异常、闭包和生成器执行路径。框架自己的规则识别、词法作用域、接口和调度仍须正确。

本次继续采用[完整整改规格](../product-boundary-refactor-spec-20261009.md)。明确共享状态修改与有限直接输入写入是其中保留的政策，须由所选 Rule 执行；空 Ruleset 不应秘密启用这些检查。条件语句结束后的不确定别名可以丢弃。互斥分支内部的直接输入根引用，与明确 `global` 名称的直接绑定，不需要跨函数推断、路径固定点或安全分析。

## 上次问题的处理情况

| 原问题 | 本次独立观察 | 判断 |
| --- | --- | --- |
| R01：嵌套生成器 helper 被当成生成器入口 | 普通嵌套 helper 放行；实际生成器入口仍拒绝。定义时的外层表达式也有新增回归。 | 原问题修复。 |
| R02：无值注解误报输入写入 | 无值注解放行；带值注解仍拒绝。新增回归保留注解目标内实际 pop 的拒绝。 | 原问题修复。 |
| R03：条件内已重绑定的本地对象误报 | 原条件重绑定反例放行；直接分支写入、直线别名写入仍拒绝。 | 原误判修复，但引入 R07。 |
| R04：global/nonlocal 声明一律当作共享状态修改 | 只读全局、只读 nonlocal、局部闭包修改放行；普通模块全局赋值仍拒绝。 | 原误判修复，但引入 R06。 |
| R05：活动手册及交付包保留旧政策 | 当前正文已改；新 wheel、双发行包和四份相关手册与工作区内容一致。 | 修复。历史证据中的旧包不作为当前交付物评价。 |

重跑上次保存的 38 个正式 CLI 项目，7 个误判由 FAIL 变为 PASS，其余 31 个状态和诊断代码保持不变。其中包含预期拒绝，不能把它描述为“38 项全部通过”。详见[独立结果比较](../evidence/index.md#artifact-b06f890de2f9dcd1)。

## R06 — P2：明确共享全局名称的其他绑定语法绕过效果限制

位置：[visitors.py:484](../../../src/vibeflow/targets/python/quality/source_analysis/visitors.py:484)，及同文件的赋值入口和定义入口。

当 Node 选择 `vibeflow.no_side_effects` 且 `effect_scope=none` 时，下面代码会写入模块共享变量，但当前正式 validate 返回 PASS：

```python
VERSION = 1

def run_pure(self, inputs, params):
    global VERSION
    for VERSION in [2]:
        pass
    return {}
```

原始最小项目见[反例](../evidence/index.md#artifact-5b04f61fa3434fb5)。不加载业务插件的独立最小执行观察中，模块 VERSION 从 1 变成 2。

同一缺口还通过正式 CLI 确认了四种写入：`with ... as VERSION`、`import math as VERSION`、`def VERSION(...)`、`class VERSION`。这五个项目在修改前均产生 `NODE.PURITY.GLOBAL_STATE`，本次修改后均 PASS。原生 Rule 在 Node、BaseLib、Plugin、python_source 四类上下文均未报告它们。

原因：删除 blanket global 声明拒绝是正确的，但新增 `_current_global_names` 的写入检查只接入 Assign、带值 AnnAssign、NamedExpr、AugAssign、Delete 和推导式目标。普通循环目标、with 绑定、导入及定义名称没有接入该检查。已有共享词法绑定资料可以识别这些名称，但没有将这些写入事件交给效果政策。

影响是同一个共享状态限制因 Python 写法不同产生不同结果，削弱 Node 间的状态隔离。不能通过恢复“出现 global 就拒绝”修复，否则会恢复 R04 的只读误判。

目标与停止点：沿用现有词法作用域与显式 global 名称，在实际直接绑定事件处应用同一效果规则；保留只读声明、普通局部绑定、Node 内局部闭包的放行。只补齐这些有限语法入口，不判断函数返回值归属、不证明未知对象是否共享、不扩展危险调用名单，也不新增路径推演服务。

对照：普通 `VERSION = 2` 仍拒绝；没有 global 的局部循环目标仍放行；只读 global 仍放行；选择 `global_state` 或空 Ruleset 时循环绑定放行。由此排除了 Rule 未执行、配置错误及恢复通用禁令的解释。

## R07 — P2：一个互斥分支的重绑定错误地影响另一分支

位置：[input_tracking.py:136](../../../src/vibeflow/targets/python/quality/source_analysis/input_tracking.py:136)。

Node 明确选择 `vibeflow.input_writes` 时，下面代码在 else 内直接修改入口 inputs，当前正式 validate 却返回 PASS：

```python
def run_pure(self, inputs, params):
    if params:
        inputs = {}
    else:
        inputs["x"] = 1
    return {}
```

原始最小项目见[反例](../evidence/index.md#artifact-454894fd611dba0b)。独立最小执行传入空 params 后，原 inputs 变成 `{"x": 1}`。同项目修改前产生 `NODE.PURITY.INPUT_MUTATION`，修改后 PASS。把 if 主体改成 pass，当前仍正确拒绝 else 的同一写入。

原因：为修复条件表达式重绑定，`_compound` 新增了按 AST field 删除 `before` 中身份的处理。遍历 If 的 body 后，它把该分支重新绑定的 inputs 从 `before` 删除；随后遍历互斥的 orelse 时，使用了被另一分支污染的身份集合。AST 字段的排列被当成顺序执行的语句。

影响是多加一个互斥分支中的局部赋值，会让原本正常识别的直接输入写入消失。这不是要求证明 if 条件真假：两个分支无需互相继承各自的写入事实。

目标与停止点：条件表达式对两个分支共同生效的重新绑定继续生效；分支内部保持有限直线扫描，互斥分支分别从共同入口身份开始；复合语句结束后仍可将条件性重绑定视为未知。不做分支结果合并、固定点、异常出口、跨函数输入传播或生成器消费分析。

对照：条件中明确将 inputs 换成本地对象的原 R03 反例仍须放行；没有重绑定的 else 写入须拒绝；空 Ruleset 放行。`if ...: inputs = {}; inputs['x'] = 1` 在整个复合语句之后的身份不确定，整改前后都 PASS，本报告没有把这种约定内的未覆盖行为算成问题。

## 验证证据与限度

- 独立运行受影响 Python 规则、新增 78 项回归及文档/发行测试，合计 **1934 passed，18.39 秒**。采用仓库测试入口准备的隔离 cwd、固定 src、禁用外部 pytest 插件和 bytecode；[完整日志](../evidence/index.md#artifact-e9aa8ec05b8d24ca)和[测试选择](../evidence/index.md#artifact-fee49f8dcc9c2893)保留。首次因审核者写错不存在的测试路径未执行，纠正入口后通过，没有修改产品或测试。
- 上次正式 CLI 38 项已独立重跑；补充 14 个最小项目分别运行修改前及当前源码，取得 **28 个 CLI 观察**。其中含六个新漏检反例，以及普通赋值、局部绑定、只读声明、权限和空 Ruleset 对照；见[原始结果](../evidence/index.md#artifact-7f59a1d9347ed821)。
- 补充原生 Rule 观察 67 项，覆盖四类共享效果上下文及输入规则；见[原生结果](../evidence/index.md#artifact-aa4b5d991efb8e33)。它们不是 67 项预期全部通过的测试。
- 修改前产品基线由当前源码与开发者保存的修改前文件组合，其 **335 个文件哈希全部匹配上次独立审核基线**；见[基线验证](../evidence/index.md#artifact-1bc18fa3087f6e42)。因此六个漏检例均有真实修改前后证据。
- 独立核验新 wheel 及双发行包嵌入的 kernel zip：各 335 个产品文件与当前源码逐字相同；四份相关使用者手册在两个包中也逐字相同，三个交付文件哈希匹配清单。见[包及输入核验](../evidence/index.md#artifact-95d061346b9ae0fc)。这也意味着源码中的两项漏检已进入这轮新包。
- 开发者完整批次记录确为 16/17；pytest 4097 passed / 1 failed，唯一失败为新增报告漏登记索引，之后 21 项文档/发行补验通过。本次比对其 2389 个输入，仅 docs/README.md 与完整运行快照不同，产品源码和随包手册未漂移；对应文档测试本次独立通过。没有把已有全量运行重写为 17/17，也没有独立重跑约 25 分钟完整批次。

可重跑补充项目：

```bash
python -I -B docs/maintainers/product-boundary-review-fixes-recheck-20261009/reproduce_cli.py \
  --product src --report /tmp/vibeflow-review-new-observation.json
```

[摘要与源码哈希](../evidence/index.md#artifact-826e3f1c777656d2)记录审核范围。证据不代表完整业务执行验收或穷尽全部缺陷。下一轮验收应补充上述有限语法反例及相应放行对照，确认修复没有恢复越界分析。
