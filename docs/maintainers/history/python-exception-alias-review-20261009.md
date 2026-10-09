# Python 异常出口修复独立审核

结论：原 F05 的 16 项静态与 16 项正式 CLI 反例已修复，包括此前新增 helper 回归和 direct 既有漏检。但本轮异常采集引入了 **F06：遗漏语言操作的抛错出口后跳过 handler 输入事实（P2）**。独立新增矩阵中 **12 项原来拒绝的真实输入突变，现在通过**，已通过源码、新旧 kernel 正式 CLI 及 wheel 规则对照确认。因此不能整体认定此次修复无回归。

本次只审核和保存证据，没有修改产品代码、已有测试、原报告与原脚本，也没有提交、推送或发布。

## 审核对象

工作区 HEAD 仍为 `5b9f9763ab7051fc964a4d83a1419d87a621b4c9`。本轮对象是开发者未提交的 F05 修复；修前行为以[上一轮独立审核的完整产品快照](../evidence/index.md#artifact-afd6efd311afd60b)与当轮 kernel 为基线，不能把当前 HEAD 直接当成 F05 修前实现。

相对于该快照，5 个已有产品文件修改，并新增 `parameter_facts.py`，共 6 个实际差异文件：

- `rules/effects.py`：输入参数、精确字典及 builtin 证明的消费者。
- `source_analysis/bindings.py`：删除、异常变量等词法绑定。
- `source_analysis/input_tracking.py`：表达式异常出口、handler/finally 路径、名称绑定和生成器求值。
- `source_analysis/parameter_facts.py`：沿实际 SourceContext 调用传播参数证明。
- `source_analysis/visitors.py`：共享输入与类型事实。
- `source_context.py`：透明控制块内函数索引。

路径相对于 `src/vibeflow/targets/python/quality/`。当前产品共 335 个文件，只有一个新增产品文件。源码、wheel、两个直接 kernel、两个发行 ZIP 的内嵌 kernel 已逐字节独立核对；修前 kernel 也再次与上一轮 334 文件快照核对一致，见[产物证明](../evidence/index.md#artifact-74455b4f333e20fa)。

## 原 F05 修复有效

原表达式 `((alias := inputs), params['missing'], (alias := {}))` 的查询抛错前状态现在被保存。原脚本及期待不变：源码、最新 kernel 和 wheel 的静态矩阵各 **16/16**；源码、新 kernel 的正式 CLI 各 **16/16**。先清除再查询的安全控制也保留允许结果。

开发者 164 项冻结异常控制在新 kernel **164/164**；同一当前源码的 335 文件冻结副本也 **164/164**，没有修改其数据或期待。该探针显式拒绝直接选取 checkout `repo/src`，第一次尝试在入口被阻止，未生成验收结果；随后使用字节匹配其最终清单的冻结源码副本及最新 kernel 成功重放。没有把入口失败计作产品错误或测试成功。

原 F01 默认值 40 项、F02 推导式 180 项在当前源码均通过。原 F03/F04 静态 36 项的普通未知 `write()` 四项历史期待差异继续单列，不算本轮新缺陷。

关键假设复核：按求值时点保存异常状态支持 F05；但“没有采到出口就可以不检查 handler”的假设不成立。采集器还没有覆盖所有会抛错的已允许语言操作，因此其空集合不能作为不抛错的证明。这个缺口违背既定输入不可突变合同，不需要用户裁决不同目标或放宽政策。

## F06：抛错点覆盖不完整，使异常分支的输入保护消失（P2，新回归）

定位：`source_analysis/input_tracking.py:511–525`，尤其 `522–523` 的 `if not unmatched: break`。相关缺口包括：没有 `visit_Set` 与 `visit_Assert` 的出口登记；推导式结果插入、赋值解包和未绑定删除也没有相应异常状态。

最小例子：

```python
class Task:
    def run_pure(self, inputs, params):
        alias = {}
        try:
            {(alias := inputs)}
        except Exception:
            alias.pop("seed", None)
        return {}
```

对普通字典输入，赋值先发生，集合插入随后因字典不可哈希而抛出 TypeError。此时 `alias` 指向原输入，异常分支实际删掉输入的 `seed`。旧 kernel 的正式 CLI **FAIL**，正确报告输入突变；当前源码和新 kernel **PASS**，没有其他错误阻断。将最后一行改成 `sink(alias)`，由 `sink(payload)` 执行同一 `payload.pop(...)`，结果同样从拒绝变成允许。

不是集合的输入身份解析错误：对照 `{(alias := inputs): 1}` 的普通字典字面量，新版能捕获哈希 TypeError 并拒绝输入突变。真正差异是集合字面量没有登记哈希出口；`body_errors.states` 为空，`visit_Try` 便跳过该 handler 的事实遍历。后续直接读取没有输入引用标记，helper 调用也没有输入参数种子。

独立矩阵发现以下六类触发操作，每类都有 direct/helper 两条路径，共 **12 个新增漏检组合**：

| 操作 | 代表代码 | 实际异常 |
| --- | --- | --- |
| 集合字面量元素哈希 | `{(alias := inputs)}` | TypeError |
| 集合推导式结果哈希 | `{(alias := inputs) for item in (0,)}` | TypeError |
| 字典推导式键哈希 | `{(alias := inputs): 1 for item in (0,)}` | TypeError |
| 赋值解包 | `alias = inputs; a, b = (1,); alias = {}` | ValueError，清除不执行 |
| 断言 | `alias = inputs; assert False; alias = {}` | AssertionError，清除不执行 |
| 删除未绑定局部名 | `alias = inputs; del missing; alias = {}` | UnboundLocalError，清除不执行 |

断言语义证明使用普通未优化 Python；本次测试和 CLI 也没有开启 `-O`。其他五类不依赖优化模式。

全部 12 项均在旧 kernel 被正确拒绝，在新源码、新 kernel 的正式 CLI 中 PASS。新 wheel 的静态原生规则结果一致。它们属于一个异常出口覆盖根因，不计作十二个独立问题。此前明文 `raise`、查询、调用的出口修复不能覆盖这些由语言本身触发的异常。

整改应补齐这些操作的求值／插入／绑定出口，并确保尚未证明安全的操作不会仅因缺少专门 visitor 就让 handler 失去事实。也应保留已证明安全路径的清除能力；不能恢复“任何历史输入别名都永久污染”的旧误报。

## 独立控制与验证

新增矩阵一共 **20 项**，结果分类为：

- 12 项从旧版正确拒绝变为新版漏检，全部是 F06。
- 2 项“明确清除后构造安全集合”的旧误报，本轮正确允许。
- 6 项前后均正确，包括普通字典哈希负控、安全集合，以及集合所有元素先求值再哈希的清除控制。

最后一种控制特意按真实 Python 求值顺序核实：`{(alias := inputs), (alias := {})}` 会先求值两个元素，再执行集合构建。抛错时 alias 已经指向新字典，不会修改原输入。调查阶段曾暂按另一种顺序设置期待；纯字典语义验证推翻该假设后，最终矩阵已纠正并重新运行，未把它计成问题。原 F05 脚本和期待没有变化。

所有最终 20 项都用无 I/O 的合成 Python 实际验证了输入字典是否被修改及异常类型，见[语言证明](../evidence/index.md#artifact-86f3de5ef275b1a7)。这里不执行项目运行时、用户业务或宿主操作。

| 本次实际检查 | 结果 |
| --- | --- |
| 原 F05 静态 16 项 | 源码 / 新 kernel / wheel 各 16/16 |
| 原 F05 正式 CLI 16 项 | 源码 / 新 kernel 各 16/16 |
| 开发者 164 项异常控制 | 字节冻结源码副本 / 新 kernel 各 164/164 |
| 原 F01 / F02 | 当前源码 40/40、180/180 |
| 新增独立静态 20 项 | 旧 kernel 2 项旧误报；源码 / 新 kernel / wheel 各 12 项新漏检 |
| 新增正式 CLI 20 项 | 源码 / 旧 kernel / 新 kernel 与静态逐案一致 |
| 相邻与新增活动测试 | 2416 passed，隔离 launcher、4 workers |
| quality 自测 | 49/49 |
| quality 全 profile | 0 error、0 warning、0 info |
| 全部产品字节 | 五份归档的 335 文件全部等于当前源码 |

当前源码的产品字节在审核期间保持不变。开发者声明的完整 17 阶段、4534 项 pytest、浏览器、JS、性能和发行构建没有在本次重跑；不将这些记录写成独立完成的验收。活动测试及已有控制通过，没有消除新增反例揭示的回归。

## 证据与复现

- [独立汇总](../evidence/index.md#artifact-d41fda6a87ad1761)。
- [20 项脚本](../evidence/index.md#artifact-10647a814eb71164)：复用上一轮独立静态／CLI 引擎，只替换本次新增 CASES；旧引擎未修改。
- [当前源码](../evidence/index.md#artifact-701601ee6dd97538)、[旧 kernel](../evidence/index.md#artifact-bed7c6e06e1a960b)、[新 kernel](../evidence/index.md#artifact-ad894b43f81fd6b8)、[wheel](../evidence/index.md#artifact-7c3b32014f2327d9) 的静态逐案结果。
- [源码 CLI](../evidence/index.md#artifact-824b7d1af24ec218)、[旧包 CLI](../evidence/index.md#artifact-0a88a3e1aa859274)、[新包 CLI](../evidence/index.md#artifact-b22bd740eace60bd)，包括完整 findings、PASS/FAIL、项目位置及隔离产品来源。
- [164 项源码副本重放](../evidence/index.md#artifact-e4c0cb761e4dad56)、[164 项 kernel 重放](../evidence/index.md#artifact-1efc56ef226f54bd)。
- 原反例、测试日志、完整 CLI stdout/stderr 与冻结源码副本在 `dist/python-exception-alias-independent-review-20261009/`；持久逐案结果在本文同名证据目录。

从仓库根目录重放静态矩阵：

```bash
python -I -B docs/maintainers/python-exception-alias-review-20261009/reproduce_implicit_exceptions.py \
  --product src --report dist/implicit-exceptions-replay.json
```

正式 CLI 再传 `--cli` 与不存在的新 `--work` 目录。旧 kernel 为 `1ac8515508917da0393657fd931be9745ffbc4d162127cb9bfdbe532144ed4d0`，新 kernel 为 `304f7c89955d68dc125d612eaad4c8c0bee5776924917c652a888a8efd912aaa`，完整路径及字节证明见同名 evidence 的 `source-and-artifacts.json`。

建议认可原 F05 的具体修复，但在 F06 关闭前，不接受本轮整体无回归的结论。
