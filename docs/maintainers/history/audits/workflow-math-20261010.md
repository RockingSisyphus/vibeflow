# Python/JS 嵌套、循环和执行矩阵的数学整合

新增两个独立 workflow_math 入口，业务保持可手算；以实际执行、计划、事件和诊断证明框架行为。Python 接替 13 项，JS 接替 6 项，共退役 19、增加 2。两个 runner 登记由 167→150：Python 114→102，JS 53→48。任务数不等于内部观察数。

## 场景及通过条件

Python 是 retry 连加、包裹循环、两种内外层停止位置，以及 `(4+6)*2+5=25` 的统一执行矩阵。双层循环只做每次加 1，3×2 和 2×3 都得到 6；停止旗标、历史、摘要和全限定路径分别检查。详细常量和条件见 [Python 说明](../../../../sandbox/python/workflow_math/README.md)。

JS 复用简单加减乘、嵌套参数覆盖、异步倍增，增加 2×3 的 +1 循环得到 10。真实 AOT 构建后验证 trace 三档、调度/数据边、同步/异步 ABI、TaskPlan、超限错误和嵌套异步超时。原辅助断言被直接复用，原常量和错误路径要求保留。详细条件见 [JS 说明](../../../../sandbox/javascript/workflow_math/README.md)。

## 逐项替代

Python 名称省略 valid:。新入口的正式检查与 SVG 对每个配置执行一次，所有后续调用都有独立状态。

| Target | 旧任务 | 新检查位置及保留条件 |
| --- | --- | --- |
| Python | loop_while_nodeset_retry | retry/plan：结果 7、carry、三次停止、完整摘要、迭代路径 |
| Python | loop_while_nodeset_retry_compiled | retry/compiled：loop_block 进入/退出、三次迭代、qualified 路径 |
| Python | loop_while_inside_nodeset | wrapped_retry：嵌套包裹中的循环、结果及完整路径 |
| Python | loop_nested_outer_after_inner_when_accumulate | outer_fixed/plan：外层固定、内层条件停止；carry/collect、属性、历史和路径 |
| Python | loop_nested_outer_after_inner_when_accumulate_block | outer_fixed/block：四对 loop_block 事件、九个迭代事件和路径 |
| Python | loop_nested_outer_when_inner_after_accumulate | outer_condition/plan：外层条件、内层固定停止；历史、旗标、输出和路径 |
| Python | loop_nested_outer_when_inner_after_accumulate_compiled | outer_condition/compiled：三对 loop_block 事件、八个迭代事件和路径 |
| Python | compiled_semantic_nodeset_arithmetic | nested/compiled-boundary：子计划顺序、factor=2、导出、块节点、生成源码、输出和摘要 |
| Python | runtime_boundary_trace | nested/plan-boundary：忽略类型解析辅助事件后的精确边界事件顺序 |
| Python | runtime_trace_off | nested/*-off：只有 runtime_summary；结果、completed 与终点正确 |
| Python | runtime_node_hooks_off | nested/full：before_node/after_node 不触发，after_run 仍触发 |
| Python | compiled_trace_full | nested/compiled-full：节点事件数量、结果和完整摘要；真正进入编译块 |
| Python | compiled_with_node_hooks | nested/compiled-boundary：两个编译块、钩子开启后的实际回调及停止摘要 |
| JS | execution:sync-async-taskplan-metadata | task_metadata：completion/schedule/executor、任务列表、同步非 Promise、异步释放前等待、能力请求及结果 |
| JS | routes:schedule-transfer-split | edge_roles：route 分类、数值 22、精确顺序、防止 sentinel 传入消费者 |
| JS | nodeset:nested-qualified-override | nested_override：19/11、不同层与同级的调用路径、覆盖隔离 |
| JS | nodeset:nested-deferred-detached | nested_async：TaskPlan、14、qualified 事件、超时位置和失败后复用 |
| JS | loop:bounded-carry | loop：7、三次迭代和路径；新增 nested_loop 同时检验双层循环 |
| JS | loop:max-iterations-error | loop_max_failure：VF_MAX_STEPS、workflow/node/block 路径、两次迭代、end 不执行 |

逐项退役关系见上表；重复机器清单已删除。保留取消、独立后台清理、锁、浏览器宿主、构建/profile、配置资源与特殊错误调度专项；它们的独特条件未由此矩阵取代。

## 资源清理与复核

Python 已核查引用并删除八个无执行方的旧顶层配置及其专属 Nodeset 配置。共享实现、声明和 tests/fixtures 未删除。JS 原 edge_roles/loop/nested_override/loop_max_failure 配置由 pytest 使用，nested_async 还被项目架构登记和 review 使用，全部保留；仅移除旧 runner 任务、无引用的构建别名和导入。

## 执行中的成本、目标与路线复核

关键假设：数学只负责承载框架条件；期望用手写常量；停止位置和 trace/编译证据不能用最终数字替代。首个原型确认 Python 17 组、JS 八组观察均可通过，业务没有发展成应用，观察器仍复用已有 API 和辅助函数。Python 五个配置的 checked run 各一次；JS 各配置 AOT 各一次，运行矩阵共享构建。

原型接入中修正了依赖裁剪遗漏的 JS Node、Schema 和工作区架构登记，并按真实接口区分 Python 类型解析事件和 JS trace 事件。Node 与 BaseLib 可有同名 id，裁剪必须按资源类别处理；没有改变核心机制或放宽 Rule。JS 的自定义领域 Rule 仍由原专项验证，新数学声明选择标准 process。删除前发现 JS 配置有 pytest/review 执行方，按原约定保留资源。这里没有需要改变用户目标的取舍。

Python 双层循环原业务是累加 outer+inner+1，本轮简化为每次 +1：两种拓扑都从 15 改为手写期望 6，框架的停止时机、carry/collect、路径与事件数量不变。retry 保持每次 +2。这是业务简化，不改变验收的调度条件。代码与配置量主要来自 SDK 契约和显式配置；不再添加新的测试抽象框架。

## 验收

证据根目录：`/home/rockingsisyphus/projects/VibeFlow-evidence/workflow-math-20261010`。没有修改 Core、SDK 或质量规则，保留工作区此前改动。

| 验证 | 实际结果 | 证据 |
| --- | --- | --- |
| Python 新入口，最终断言 | 17/17，通过；22.366 秒 | python-standalone-final/report.json |
| JS 新入口 | 八组全部通过；5.717 秒 | javascript-standalone/report.json |
| Python 完整沙盒 | 102/102，通过；403.851 秒 | python-batch/reports/summary.json |
| JS 完整沙盒，最终批次 | 48/48，通过；失败 0、跳过 0；166.847 秒 | javascript-batch-final/reports/summary.json |
| 相关 pytest | 152 passed；37.93 秒 | pytest.log |
| quality all，最终复验 | PASS，0 error / 0 warning / 0 info | quality-final.log |
| 当时任务清单 | Python 102、JS 48，任务名及顺序与完整报告逐项一致 | [中文任务表](sandbox-task-inventory-workflow-20261010.md) |

Python 完整批次后补强了所有模式的根节点执行顺序、当前终点、step_count、node_runs 和 edge_executions 精确断言，并补入原 retry 的 SVG 文本断言。新入口在最终源码上重新通过；同样的摘要断言对完整批次保存的 17 组实际结果逐项通过（python-batch-summary-audit.json）。没有把批次之后增加的断言说成该批次当时已执行。

JS 首个完整批次是 44 passed / 4 failed / 0 skipped；全部失败来自运行环境把 TMPDIR 设置为过长的证据路径，导致 Chromium SingletonSocket 超出路径限制。保持原浏览器断言，将 TMPDIR 恢复 `/tmp`，四项定点复验通过，再重跑完整 48 项全部通过。首批日志、报告和定点记录保留。quality 初次还发现尚未生成的任务清单链接，以及仓库中的旧 runs 产物；完成清单并将未跟踪的旧 runs 移至证据根目录的 preexisting-repository-runs 后复验通过，没有删除原运行记录。

相关 pytest 范围：Python strict_runtime、strict_graph_runtime_guardrails、test_runtime_integration；JS test_javascript_sandbox、test_bound_emission。本轮未声称运行所有 pytest 或发布验证。

最终复核：新增 Python 22 个文件、2877 行；JS 40 个文件、2912 行，主要是显式 SDK 声明、配置和 Schema。驱动分别 153/66 行，Python 数学节点实现 77 行；JS 保留公共辅助断言以降低重复维护。准备、构建和渲染已按同配置复用，独立调用保持独立状态。未进行同环境预热的旧 19 项对照测速，上述时间仅为本轮样本，不据任务数下降宣称提速比例。正常加法未证明的取消、锁、宿主、特殊错误等条件仍保留专项。

完整现存任务名见 [当前清单](sandbox-task-inventory-workflow-20261010.md)，167 项版本继续保留为历史快照。
