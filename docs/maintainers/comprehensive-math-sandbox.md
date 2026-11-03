# 综合数学应用沙箱

Python 和 JavaScript 的 `comprehensive_math` 是两个独立项目，分别声明自己的 Plugin、Node、Rule、Ruleset、多文件 BaseLib 和 JSONC workflow。只有测试输入、手工计算的期望值和报告断言共用；业务公式不共用实现。统一的 `tests/e2e/test_comprehensive.py` 驱动它们，已纳入完整验收。

## 模拟的应用

应用从应用通过普通运行输入提供的队列收到 x，经过两层 Nodeset、配置覆盖、条件分支、两种汇合及循环，最后向另一端口发送结果。它使用项目自己的收发节点、`vibeflow.loop.while` 和原生工作流/过程规则；业务运算由 SDK 声明的 Node 和纯 BaseLib 实现。

公式为：

```text
q = 3 × (x + 2) - 3
r = q²           当 q ≥ 0
    -q + 3       当 q < 0
c = 2 × x + 1
v₀ = r + c
vᵢ₊₁ = vᵢ + 2   执行三次，以 body 输出 done=true 退出
result = 2 × v₃ + offset   未提供 offset 时为 0
history = [v₁, v₂, v₃]
```

```mermaid
flowchart LR
  start[显式 terminal] --> receive[普通 SDK Port receive] --> prepare[两层 Nodeset: q]
  receive --> companion[BaseLib: c]
  prepare --> route{q ≥ 0?}
  route -->|是| square[q² / 自定义 Rule]
  route -->|否| negative[-q + 3]
  square --> choice[any_active 汇合]
  negative --> choice
  choice --> join[all 汇合: r+c]
  companion --> join
  join --> loop[原生 while / carry / collect]
  loop --> finish[2v + offset]
  offset[可选输入] --> finish
  finish --> send[普通 SDK Port send] --> end[显式 terminal]
```

Node 的 gain=2、shift=1、amount=1 默认值被 config 的 `inner.affine` 和 `subtract` 覆盖为 3、2、3。期望值预先写死，不通过再次调用业务公式算出，避免两边犯同一个错误仍通过。特别加入 x=-1：此时 q=0，能发现把 `≥` 错写为 `>` 的错误。

| 输入条件 | 预期分支 | history | 最终结果 |
| --- | --- | --- | --- |
| x=4，未提供 offset | square | [236, 238, 240] | 480 |
| x=-3，未提供 offset | negative | [6, 8, 10] | 20 |
| x=0 | square | [12, 14, 16] | 32 |
| x=4，offset=7 | square | [236, 238, 240] | 487 |
| 同一个运行入口再次输入 x=1 | square | [41, 43, 45] | 90 |
| x=-1，使分支条件恰好为零 | square | [1, 3, 5] | 10 |

## 如何认定框架正确

通过正常 CLI 构建后，由普通应用的队列输入 x，检查收到和发出的实际消息、history 与最终输出。六组独立预期在两个语言工程分别执行，另有源码修改后 warning 消失的对照。一次数字正确不能代替其他场景、清理或浏览器验收。

## 自定义规则怎样定义

入口是各项目 `code_plugin.py` / `code_plugin.ts`，把 `math.min_t`、`math.t_advice`、`math.source_rules` 和 Node 一起注册。square 显式选择该 Ruleset；Core 调度 Rule 并把其 finding 合并到报告。

`project/rules/min_t.py` / `min_t.ts` 从 Target 提供的源码事实定位当前声明的实现符号，直接计数。Python 数 class 的源码段，JS 数导出 function 的源码段，包含这段内部的字符串与注释，不包含外面的 SDK 装饰器/声明，也不扫描别的 Node。输出 warning 与 typed record，advice 从 record 生成第二条带原因的诊断，不重复读取/统计源码。

本案例刻意使用 warning，因此运行可以继续。它覆盖两条自定义规则、选中的原生源码规则和装配执行链，**不代表检查了所有 Rule 的 warning/error 分支**。独立的错误阻断、权限/导入违规、阈值边界、异步任务/清理/取消、Host 生命周期、发布故障与布局专项仍保留。

## 运行与效率

```bash
python tools/run_tests.py -- tests/e2e/test_comprehensive.py
```

每个真实工程正常构建一次，随后复用产物运行不变输入矩阵；源码变化后正常重新检查和构建。依赖与输出使用统一入口的隔离工作区。完整验收见[开发与验证](development.md)，性能观察另由 test_performance.py 负责，不检查内部解析或缓存次数。
