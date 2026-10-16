# 分段数学沙盒替代 11 项工作流任务

本轮新增 Python `piecewise_math` 一个独立入口，替代 integration runner 的 11 个重复正常任务。保留 tests、tests/fixtures 和其他专项。未改 Core、SDK 或质量规则；工作区此前已有改动保持原样。

## 公式、输入与通过判定

`u=a+b`，`v=c+d`；`u>=v` 时 `w=u+1`，否则 `w=v-1`；最终 `result=w+u`。

| 输入 a,b,c,d | u,v | 选中分支 | w,result |
| --- | --- | --- | --- |
| 2,3,1,2 | 5,3 | left | 6,11 |
| 1,1,2,3 | 2,5 | right | 4,6 |
| 1,2,1,2 | 3,3 | left | 4,7 |

期望值为手写常量，未调用被测函数生成。四种配置共享 SDK 声明与简单加法 BaseLib：linear 验证 `(2+3)+1-1=5` 的纯串行链；split 验证分段函数的不同终点；join 验证相同类型、不同 key 的互斥汇合；bypass 验证 `u+(u+1)=11` 的数据旁路与主线时序。配置及运行方式见 [独立入口说明](../../../../sandbox/python/piecewise_math/README.md)。

所有配置验证 plan/full、compiled/boundary、compiled/full，共 24 组运行观察，另外有四次 checked run 验证健康、架构和 SVG。新入口不是只比较最终数值：中间值、节点顺序/次数、停止原因、终点、完整 trace 的边次数、类型来源、未选中分支均有明确断言。compiled 必须有真实 block，block 节点顺序和保存后的生成源码均被检查；没有 block 会直接失败。边界模式要求没有 node 事件，完整模式要求每个实际执行节点恰好一个 node 事件。

## 旧检查条件 → 新检查位置

下面名称省略报告中的 `valid:` 前缀。共同的 health、正式运行与架构产物检查在每个配置的 checked run 完成。

| 旧任务 | 新配置/模式 | 迁移的检查 |
| --- | --- | --- |
| semantic_linear_arithmetic | linear / plan-full | 中间值与最终值；六节点执行顺序；边次数、node_runs、step_count、终点与 completed |
| compiled_semantic_linear_arithmetic | linear / compiled-boundary | 数值、六节点顺序/摘要；一个块进入/退出；完整块节点清单；生成源码必要/禁用调用 |
| compiled_full_semantic_linear_arithmetic | linear / compiled-full | 上述全部；六个 node 事件、完整边次数 |
| semantic_decision_branch_left | split / plan-full / left | 左分支数值、独立左终点；顺序、边次数、节点次数和停止摘要 |
| semantic_decision_branch_right | split / plan-full / right | 右分支数值、独立右终点；顺序、边次数、节点次数和停止摘要 |
| compiled_semantic_decision_branch_left | split / compiled-boundary / left | 左分支结果/终点；块事件、块内两个分支/终点的完整清单与生成源码 |
| compiled_full_semantic_decision_branch_left | split / compiled-full / left | 上述全部；完整节点和边事件；inactive 分支无运行记录 |
| compiled_semantic_decision_branch_right | split / compiled-boundary / right | 右分支结果/终点；块事件、摘要、块清单与生成源码 |
| safe_or_join_mutually_exclusive_left | join / plan-full / left | any_active 汇合；selected_w exactly_one；左 provider 的原始 key、结果与顺序 |
| safe_or_join_mutually_exclusive_right | join / plan-full / right | 同上，右 provider；未选中分支没有执行 |
| mainline_data_bypass | bypass / plan-full | 原始 u 直接传给 finish；finish 等待中间节点；结果与顺序；独立导出及运行 Mermaid 的指定旁路虚线 |

新场景还补充等号边界、右分支 compiled/full、汇合与旁路的 compiled 运行以及明确的 inactive 分支检查。没有为减少入口而取消旧编译源码检查，也没有将多终点和统一汇合混为一种拓扑。

## 退役与保留

删除 runner 中上述 11 项登记，接入一个 `piecewise_math`。Python 124→114，JavaScript 仍为 53，两 runner 合计 177→167。此口径是最外层报告任务数，不是 pytest 数，也不是内部运行观察数。

全部当前任务名见 [2026-10-10 清单](sandbox-task-inventory-20261010.md)及同名 JSON；10 月 9 日清单保持历史快照。

旧配置先做引用核查，仅删除不再有执行方的四个配置：`pass_semantic_linear_arithmetic.jsonc`、`pass_semantic_decision_branch.jsonc`、`pass_safe_or_join_mutually_exclusive.jsonc`、`pass_mainline_data_bypass.jsonc`。同时移除仅由这些配置使用的四个 Node 声明与实现（left/right_key_adjust、left/right_branch_end）。历史审计文档保留原记录。其他 semantic 实现与 Plugin 还被 Nodeset、循环、异常/编译专项使用，继续保留；不改 tests/fixtures 的历史回归资源。

## 执行中的成本、目标与路线复核

关键假设是用少量整数足以表达正常调度检查，配置重用能够减少检查和渲染成本。首个完整原型验证了四种拓扑、三种模式共 24 组观察；编译块和源代码均真实产生。保留四个小配置是为了审查不同拓扑，而不是增加业务应用：每个计算节点只有一个比较或一次加法，期望常量可手算。

原型中使用函数生成装饰器契约触发 import Rule 的拒绝，已改为标准的字面量 SDK 声明，没有绕过规则。另修正驱动对公开输入和按类型导出的结果格式的使用。这些是新案例接入错误，不是框架机制缺陷。删除前再次核对迁移矩阵与实际报告；没有需要改变用户目标或降低验收的路线分叉。

同一份源码、同一已安装渲染依赖下分别测量旧 11 项和新入口，仅作为一次样本。新入口复用同配置的检查/渲染和每种模式的计划，每次调用创建独立 Runtime。不能从任务数的减少直接推导覆盖率或固定提速比例。

## 验收结果

| 验证 | 实际结果 | 证据 |
| --- | --- | --- |
| 新入口独立执行 | 24/24 组观察通过，26.682 秒 | [逐项报告位置](../../evidence/index.md#external-fc168f14d77caaa8) |
| 退役前旧 11 项同环境对照 | 11/11 通过，88.494 秒 | [逐任务耗时位置](../../evidence/index.md#external-0c063f3624cb3b26) |
| Python 完整 integration | 114/114 通过，失败 0、跳过 0；退出码 0；498.547 秒 | [完整汇总位置](../../evidence/index.md#external-f9255b0468cc48b9)、[日志位置](../../evidence/index.md#external-c26c10369db3de8a) |
| 新入口在完整 runner 中执行 | 24/24 组观察通过，26.706 秒 | [逐项报告位置](../../evidence/index.md#external-1059691b6f6f8ce5) |
| 相关 pytest | 114 通过，失败 0、跳过 0；32.40 秒 | [日志位置](../../evidence/index.md#external-d15cb3c5c3269848) |
| quality all | 0 error、0 warning、0 info；退出码 0 | [日志位置](../../evidence/index.md#external-2251f592a932ca89) |

相关 pytest 使用既有 `tools/run_tests.py` 的仓库外运行环境，范围为 Python `strict_runtime.py`、`strict_graph_runtime_guardrails.py`、`test_runtime_integration.py`。Python 完整报告的名称与顺序已逐项核对今天的任务清单。

本轮没有改动 JavaScript，53 项为登记数量，本轮未重跑 JS 完整批次；未执行仓库全部 pytest、发行或性能专项。原型的接入错误均在最终独立入口和完整批次前修正；正式验收批次没有失败，不把早期未通过的原型算作通过。耗时表仅说明这一环境中的样本，不承诺固定提速比例。
