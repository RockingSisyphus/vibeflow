# 综合数学应用沙箱

Python 和 JavaScript 的 `comprehensive_math` 是两个独立项目，分别声明自己的 Plugin、Node、Rule、Ruleset、多文件 BaseLib 和 JSONC workflow。只有测试输入、手工计算的期望值和报告断言共用；业务公式不共用实现。两个集成 runner 已调用它们，`tools/verify_project.py --full` 因而也会执行。

## 模拟的应用

应用从注入的 `vibeflow.port` 收到 x，经过两层 Nodeset、配置覆盖、条件分支、两种汇合及循环，最后向另一端口发送结果。它使用普通 SDK 端口节点、`vibeflow.loop.while` 和原生工作流/过程规则；业务运算由 SDK 声明的 Node 和纯 BaseLib 实现。

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

| 检查内容 | 模拟条件 | 通过判定 |
| --- | --- | --- |
| 数学运算与配置绑定 | 六组输入，默认参数被直接/限定路径覆盖 | 结果、完整 history、迭代数精确匹配；Python 额外检查实际 ExecutionPlan 参数、子图顺序及导出契约 |
| 源码 Rule 和资料传递 | square 选中 `math.source_rules`；t 数量不足；advice 通过 requires 接收 typed record | 恰有 `MATH.MIN_T` 和 `MATH.T_ADVICE` 两个自定义 warning；都报告 actual=6、minimum=10，后者使用 `math.t_count.v1` |
| 原生 Rule | 包装 `vibeflow.process`，局部覆盖源码行数 warning 阈值为 4 | `NODE.PURITY.SOURCE_NEAR_LIMIT` 包含 affine、step 等实际 Node；阈值/实际行数正确，errors 为空，health 为 CONCERNS |
| 诊断详情 | warning 定位到真实 Node 定义与 graph 调用 | 检查 code、severity、definition_id、math.square、square 文件、准确行列、原因、阈值及 square 调用关联 |
| 正反源码对照 | 只在临时项目的 square 实现中增加 10 个 t，再重新检查/构建 | 两个自定义 warning 消失，原生 warning 仍存在，errors 仍为空；原案例源码不修改 |
| 分支与汇合 | 正、负、零边界；any_active 和 all 组合 | 未选分支不执行；choice/join 各执行一次；根图执行顺序精确匹配 |
| Nodeset 与循环 | 两层 Nodeset；同时携带值和计数，body 第三次返回 done | qualified 路径包含 prepare.inner.affine；step/loop_iteration 各三次，history 逐项一致 |
| 普通端口 Capability | 测试注入 receive/send，不连接外部网络 | 恰一次 receive(math.in) 和 send(math.out, result)，参数和值精确匹配 |
| 复用与并发隔离 | 连续使用同一入口；正负两组同时运行 | 不串结果、offset、history 或 trace；JS 一组 full、一组 boundary，boundary 不出现 node_start 且保留 Nodeset 边界 |
| Python 执行与架构产物 | checked run；再以 plan/block/compiled 执行 | 三后端正负结果一致；Architecture JSONC、结构化快照和 HTML 入口存在；不安装或启动 Mermaid |
| JS AOT 与真实浏览器 | Node/browser single-esm；浏览器实际导入执行 | 两宿主执行同一组断言、public envelope 只有声明的输出；浏览器 DOM 显示正确值 |
| JS 异步等待 | 暂不释放真实注入 Port 的 Promise | workflow 保持 pending；释放后得到 480；Node 与浏览器都检查 |

Python 共 13 次数值观察：首次 checked run、同一个 runtime 的六组输入、block/compiled 各两组、两个独立 runtime 并发。JS 每个宿主有八次数值观察（六组顺序、两组并发），另有一次 held receive。一次 runner 的 PASS 要求所有断言满足；程序算对最后一个数字仍可能测试失败。

## 自定义规则怎样定义

入口是各项目 `code_plugin.py` / `code_plugin.ts`，把 `math.min_t`、`math.t_advice`、`math.source_rules` 和 Node 一起注册。square 显式选择该 Ruleset；Core 调度 Rule 并把其 finding 合并到报告。

`project/rules/min_t.py` / `min_t.ts` 从 Target 提供的源码事实定位当前声明的实现符号，直接计数。Python 数 class 的源码段，JS 数导出 function 的源码段，包含这段内部的字符串与注释，不包含外面的 SDK 装饰器/声明，也不扫描别的 Node。输出 warning 与 typed record，advice 从 record 生成第二条带原因的诊断，不重复读取/统计源码。

本案例刻意使用 warning，因此运行可以继续。它覆盖两条自定义规则、选中的原生源码规则和装配执行链，**不代表检查了所有 Rule 的 warning/error 分支**。独立的错误阻断、权限/导入违规、阈值边界、异步任务/清理/取消、Host 生命周期、发布故障与布局专项仍保留。

## 运行与效率

```bash
python sandbox/python/comprehensive_math/run_all.py
python sandbox/javascript/comprehensive_math/run_all.py
```

默认复制到临时目录并自动清理。两者接受 `--work-dir /仓库外/新目录` 保留项目、health、trace/build 和 `report.json`；目录须为新目录。JS 可用 `--toolchain-root`（其下有锁定版本 node_modules）和 `--puppeteer-root` 复用依赖。JS `--skip-browser` 明确记录 REDUCED，不算完整浏览器验收。

Python 首次检查与数据导出后复用组装图测试输入矩阵；JS 在同一检查会话内复用解析资料，每个 Target 构建一次，再复用生成物执行矩阵。源码修正后再检查/构建，检验资料确实随源码失效。这样减少重复解析、启动进程和重复检查，同时保留上述独立观察。

原案例的逐项替代与实际验证成绩见 [整合归档](history/audits/comprehensive-sandbox-20261009.md)。
