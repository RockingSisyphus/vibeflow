# Python 别名事实修复独立审核

结论：上轮 F03 的局部对象冒认宿主和 F04 的 nested global/nonlocal 直接输入突变漏检，**原报告中的具体反例已修复**。但本轮引入了 **F05：异常分支中的 helper 输入突变新漏检（P2）**，已通过正式 CLI、新旧 kernel 对照确认。因此不能将这次修改整体认定为已完全解决问题、且没有引入回归。

本次只审核、保存证据，没有修改产品代码、已有测试、历史报告及其复现脚本，也没有提交、推送或发布。

## 审核范围

基线为本地提交 `5b9f9763ab7051fc964a4d83a1419d87a621b4c9` 的 Git 对象。334 个产品文件与[上一轮独立审核快照](../evidence/index.md#artifact-6e8d9d10d60ae07a)完全相同；当前审核的是这个基线上的未提交修复。

实际只有三个产品文件变化：

- `src/vibeflow/targets/python/quality/rules/effects.py`：用实际函数 AST 和 SourceContext 调用目标传递输入种子。
- `src/vibeflow/targets/python/quality/source_analysis/input_tracking.py`：统一实参与直接引用的输入事实，处理路径清除、调用写回及求值顺序。
- `src/vibeflow/targets/python/quality/source_analysis/visitors.py`：局部效果来源标记，以及共享输入事实的直接消费。

新增的两个活动测试文件和 `tests/fixtures/rule_parity/python/ownership_variants.py` 的期待迁移也已查看。本次独立验证包括原始反例、开发者持久保存矩阵、新增异常路径对照、相邻测试、质量检查和产物字节核对。没有重跑全部 17 阶段业务、浏览器及发行验收。

关键假设复核：局部来源标记及共用输入采集器支持原 F03/F04 修复；但“共用采集器就能保证所有读取点身份一致”的假设仍不充分。采集器必须保留异常发生时的表达式中间状态，不能只保留正常完成状态。F05 属于既定输入不可突变合同的实现回归，不需要改变权限政策或请用户接受不同目标。

## 原问题已修复的证据

原 10 项 SDK→RulePlan→正式 CLI 对照在源码与新 kernel 中均 **10/10**：局部 `sys` 及改名目标都允许；真实输入经 nested nonlocal/global 写回后，直接 `pop()` 与 helper `pop()` 都被拒绝。

开发者新增 128 项正式矩阵也在源码、新 kernel 中各 **128/128**，包括 27 项 public Core 路由、101 项 CLI 路由。真实宿主负控和普通 I/O 策略没有因局部来源标记而被放宽；103 项输入写回／求值矩阵在当前源码 **103/103**。

需要纠正上轮原 36 项脚本的一个验收期待：它把局部对象的 `alias.write()` 在 `none` 下设为完全无 finding，这四项期待过宽。当前四种资源都报告普通未知 I/O 的 `banned call: alias.write`，并未冒认 `sys.stdout`。按项目既有保守 I/O 合同，这是正常拒绝；在 `python_io` 下的许可和真实宿主身份负控由 128 项矩阵另行确认。原脚本及历史期待没有改写，raw 结果仍如实记录为 **4 项不匹配**，不将其算成未修复缺陷。

## F05：语句内部异常状态丢失，helper 输入突变由拒绝变为允许（P2，新回归）

定位：`src/vibeflow/targets/python/quality/source_analysis/input_tracking.py:419–429` 的 `_InputCallFacts.visit_Try`。相关表达式遍历只为函数写回保存出口，没有为当前 try 的局部输入别名保存每个可能抛错点的状态。

```python
def sink(payload):
    payload.pop("seed", None)

class Task:
    def run_pure(self, inputs, params):
        alias = {}
        try:
            ((alias := inputs), params["missing"], (alias := {}))
        except Exception:
            sink(alias)
        return {}
```

当 `params` 没有 `missing` 键时：第一项先让 `alias` 指向真实输入；第二项抛出 KeyError；第三项清除根本没有执行。异常分支收到的仍是原输入，`sink(alias)` 会删掉它的 `seed`。

旧 kernel 在正式 CLI 中 **FAIL**，报告 `module helper must not mutate inputs via pop`；当前源码和新 kernel 均 **PASS**、没有错误。新 wheel 的静态正式规则调用也给出相同漏检。旧 kernel 的全部 334 产品文件已与 Git 基线逐字节核对，确定这是本轮引入的退化。

根因是 `visit_Try` 只在 `self.visit(statement)` 完成后，把语句结束状态合并到 `exceptional`。本例语句进入和正常结束时 `alias` 都是普通字典；真正异常发生时的 `alias -> inputs` 中间状态被遗漏。随后 helper 实参没有输入种子，直接突变与 helper 检查共用的采集器都无法恢复这个身份。已有 `_capture_writeback_exit` 处理的是外层声明写回，并不能代替 try 内局部变量在查询／调用抛错点的状态。

独立 16 项矩阵包含元组、列表、字典、赋值 RHS、明确抛错调用和属性查询，以及 direct/helper 两条路径。逐案结果如下：

| 分类 | 数量 | 旧 kernel | 当前源码 / 新 kernel / wheel |
| --- | --- | --- | --- |
| helper 的表达式中途异常 | 6 | 全部检出 | 全部漏检，新增回归 |
| direct 的同类异常 | 6 | 全部漏检 | 仍全部漏检，既有遗漏 |
| 清除发生在查询之前 | 2 | direct 正确、helper 误报 | 两项正确，本轮改善 |
| 拆成三条独立语句 | 2 | direct 漏检、helper 正确 | 两项正确，本轮改善 |

上述 16 项又通过独立 canonical SDK 项目和正式 CLI 分别在源码、旧 kernel、新 kernel 重放，结果一致。新源码／新包的 6 个 helper 反例都是 PASS；没有被其他错误意外阻断。相同纯字典与异常语义的无 I/O 合成程序实际验证了全部 16 项预期，见[语言语义证明](../evidence/index.md#artifact-c0f63a1e459aacb5)。这不执行项目运行时、用户业务或宿主操作。

这 6 个组合属于一个根因，不计作六个独立问题。建议在统一采集器中按真实求值时点，为可能抛错的查询／调用记录适用异常处理器的别名状态，同时保留明确覆盖为局部值时的清除能力。不能简单恢复“凡历史上成为输入就永久标记”，否则会重新引入本轮已修复的覆盖误报。

## 独立验证与边界

| 项目 | 本次实际结果 |
| --- | --- |
| 原 F03/F04 正式 CLI 10 项 | 源码 / 新 kernel 各 10/10 |
| 原静态 36 项 | 源码 / 新 kernel / wheel 各 raw 4 项差异，均为上述普通 write 期待 |
| 开发者正式别名矩阵 128 项 | 源码 / 新 kernel 各 128/128 |
| 开发者写回／求值矩阵 103 项 | 当前源码 103/103 |
| 原 F01 40、F02 180 | 源码 / 新 kernel / wheel 各 220/220，共 660/660 |
| 新增独立异常矩阵 16 项 | 新源码 / 新 kernel / wheel 各 12 项漏检；其中 6 项是新回归 |
| 新增正式 CLI 异常矩阵 16 项 | 源码 / 旧 kernel / 新 kernel 逐案结果与静态矩阵一致 |
| 相邻与新增活动测试 | 2221 passed，隔离 launcher、4 workers |
| quality 自测 | 49/49 |
| quality/run.py --profile all | 0 error、0 warning、0 info |
| 五份产物全部产品文件 | 各 334/334 与当前源码逐字节一致 |

没有因为活动测试和开发者完整验收通过而忽略 F05。测试未覆盖这个“同一语句内先赋输入、可能抛错、再清除”的异常路径；新增的反例直接否定了整体无回归的结论。本次未独立重跑开发者声明的完整 4330 项 pytest、浏览器、JS、性能和打包过程，这些仍属开发者验收记录。

## 证据与重放

独立证据目录为 [python-alias-facts-review-20261008/](../evidence/index.md)。

- [修前 Git、当前源码及五份新产物证明](../evidence/index.md#artifact-afd6efd311afd60b)。新 kernel SHA256 为 `1ac8515508917da0393657fd931be9745ffbc4d162127cb9bfdbe532144ed4d0`；旧 kernel 为 `6be7bcabb626abc067da8208b43220a62a3bd3d079642ea83da61332dcfb5373`。
- [独立静态脚本](../evidence/index.md#artifact-a0a61e2fa5c1d778)，以及 [源码](../evidence/index.md#artifact-d02641e96b6fada6)、[旧 kernel](../evidence/index.md#artifact-80dff5d1afe63029)、[新 kernel](../evidence/index.md#artifact-d8457ff375d1e905)、[wheel](../evidence/index.md#artifact-a000e8edde532c99) 的逐案结果。
- [独立正式 CLI 脚本](../evidence/index.md#artifact-1339ec5caf11aec9)，以及 [源码](../evidence/index.md#artifact-b9195a38343eb4e3)、[旧包](../evidence/index.md#artifact-c34e4a8965d14489)、[新包](../evidence/index.md#artifact-6b72207349036b23) 的逐案结果与无外部产品模块来源证明。
- [开发者 128 项源码重放](../evidence/index.md#artifact-6e0bf3450f486e9d)、[kernel 重放](../evidence/index.md#artifact-2f0c80fe5c0eccac)、[103 项源码重放](../evidence/index.md#artifact-287b0e3e97b69823)。
- [独立汇总](../evidence/index.md#artifact-8401d06c2b835f50)。原案例、完整 CLI 项目、stdout/stderr 与测试日志保存在 `dist/python-alias-facts-independent-review-20261008/`。

从项目根重放静态新增矩阵：

```bash
python -I -B docs/maintainers/python-alias-facts-review-20261008/reproduce_exception_alias.py \
  --product src \
  --report dist/exception-alias-replay.json
```

正式 CLI 脚本使用 `python -B`，另传一个不存在的新 `--work` 目录；它的 CLI 子进程使用 `-I -B` 从唯一指定产品加载，待审查业务只 validate。

建议将原 F03/F04 的具体修复与 F05 新回归分开追踪；在 F05 关闭前，不接受本轮整体无回归的结论。
