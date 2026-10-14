# 原生任务管理：编译、执行与维护

本文面向内核维护者，描述 0.19.1 当前实现。公开声明、配置与调用示例见[使用手册](../../distribution/docs/user/task-management.md)；阶段失败和 full-04 验收见[实施记录](../maintainers/history/task-management-implementation-20261014.md)。历史记录不代替当前设计。

## 目标与边界

父流程启动多个任务后，可以先收到任一任务的最终结果，决定停止哪些兄弟任务，再等待全部实际退出。最终结果的通知边界包括 Node 执行、finally、SDK 操作和受管后代。普通 Node 可转交引用；只有管理 Node 能控制任务。失败不自动取消兄弟任务，业务策略保留在管理 Node 或现有 Decision 中。

公共名单是 TaskRef 数组，不包含 Promise/Future 或控制方法，不引入强制 TaskGroup。引用传递不激活隐式等待，引用持有者也不改变任务归属。每次 workflow 的统一记录提供最终收尾保证：父流程没有走到显式等待点，也不能遗留所属执行。JS 并发由事件循环承担，未引入 Worker 执行器；Python 使用线程。

## 配置到执行的链路

| 层 | 实现入口 | 职责 |
| --- | --- | --- |
| Core | `core/flow.py`、`core/tasks.py`、`core/compiler.py` | 保存 task_manager/task_targets；递归枚举目标调用，核对真实声明身份和旧入口；构造有限任务图 |
| Block Compiler | `block_compiler/compiler.py`、`block_compiler/model.py` | 编译任务目标 Block，输出 Workflow ABI v6 与 TaskPlan，保留槽与调用位置 |
| Python Target | `targets/python/runtime/planning.py`、`tasks.py` | 绑定任务执行计划、context、线程执行及完成通知 |
| JS Target | `targets/javascript/frontend/`、`resources/task_helpers.mjs` | 发射有限槽的执行器，连接生成流程与任务记录、Node 操作归属 |
| Tooling | `tooling/presentation/task_targets.py`、project schema、两侧 presenter | 配置合同、Architecture 启动关系、管理身份和图形 |

上述路径相对 `src/vibeflow/`。Core/公共计划不保存语言 callable、线程、AbortController 或 Promise。TaskPlan 字段为 id、manager_node_id、key、block_id、executor；executor 由 Target 明确提供 thread/event_loop，不根据某个子图 entry_mode 猜测语言。

`task_graph` 将单个声明目标编译为独立调用图。目标复用原 Node/Nodeset 的 requires/provides、配置与实现，不能在运行时查找任意 Node 或传入回调。目标 requires 的类型成为任务输入键；exactly_one 对应必填，all 保留完整 envelope 集合。嵌套目标的内部传递不能取首值代替多值。

旧 async/result_key/detached 被解析与编译层作为迁移错误拒绝，原 pending/detached 执行容器已删除。旧测试名称可以保留，但正向目的必须用新配置继续覆盖，不能删除并行、锁或生命周期验证目的来消除失败。

## 单次运行的任务记录

两 Target 的 TaskRegistry 都按 run_id/task_id 保存归属、实际执行、停止请求、退出顺序、最终 outcome 和 observed 状态。start 返回独立引用，每次启动产生新实例。select 验证当前运行及已知任务，按首次出现顺序去重。引用数组没有登记表；复制、筛选、合并不改变记录归属。

Python 阶段为 queued/running/stopping/exited，JS 为 running/stopping/exited；阶段表达执行进度，TaskOutcome 的 succeeded/failed/cancelled 仅在最终退出时确定。requestStop 只发信号，排队任务仍须进入退出处理；不响应取消的操作继续保持未退出。不得通过取消 Future/Promise 的观察者来宣称底层工作已结束。

waitAny 在已结束的候选中按 exitOrder 取最早结果，否则等待完成通知；waitAllExited 按名单顺序返回。两者取得结果时标为已观察，重复等待仍可读取结果。未观察失败在所属执行 drain 时汇总为 VF_TASK_UNOBSERVED；正常取消不作为未消费业务失败。控制 context 仅在当前管理 Node 调用活跃期间有效，关闭规则不授予控制权。

## Python 执行与退出

Runtime 为本次 workflow 共享 TaskRegistry，当前 task ID 建立父子关系；复用 Nodeset Runtime 时刷新本次归属。start 构造目标 Runtime、独立 CancellationSignal、完整调用路径并复制线程上下文，保留执行锁 lease。没有管理调用的目标进入按 Runtime 上下文组织的有界工作池；包含管理调用的目标使用控制线程，避免 wait 占满它监督的工作池。

Condition 保护记录与完成通知。管理线程启动/工作池提交在同一锁下登记，启动失败转为退出失败并释放信号订阅及锁，不留下不可等待的活跃记录。wait_any 在等待期间响应管理调用取消；wait_all_exited 和 drain 不被同一取消信号提前截断。

执行目标后依次处理其后代 drain、线程池上下文关闭、锁 lease 释放和信号退订，再确定 outcome、清空活跃 signal、分配 exit_order 并唤醒等待者。root 统一停止并等待所属任务，合并限定路径 trace、关闭工作池并 join 控制线程。正常路径 drain 后重新检查外部取消；CLI business exit 保留自身语义，任务内请求退出先转成结构化失败数据供管理 Node 决定。

普通旧二参 run_pure 仍可绑定，可选第三参提供 context；管理 Node 必须接收第三参。NodeRunContext.close 发出本次调用退出信号并收集取消回调清理错误，不把它当成所属任务全部退出。

## JavaScript 执行与退出

AOT 为每个管理调用生成 taskExecutors 槽映射。start 使用独立 AbortController，订阅当前执行的取消信号，保存 parent ID 并异步执行目标。目标执行与后代 drain 完成后退订父信号、释放 controller，再保存最终 outcome 和退出顺序。root finish 设置 closing，必要时报告 stopping，停止并等待所属任务。

每次 Node 调用另有内部 NodeExecution，跟踪该调用发起的 SDK Promise 操作。它不是公开任务组，不能随数据连边传递。Promise.race 已返回时，落败但未完成的操作仍属于该执行记录；exit 请求停止后持续等待 operations 集合清空。取消观察者不能删除实际操作归属。任务管理等待 Promise 同样由该 Node 调用持有。

Node 自身 finally 可以在取消后等待清理操作；收尾期间禁止 start 新受管任务。退出等待使用 allSettled 收集结果，但不能忽略清理失败；保留已有 Node 主错误并附加 cleanupErrors。Host.stop、Plugin 释放、状态结束与锁释放以实际收尾为边界。

## 错误、资源与记录保留

TaskOutcome 是可传递数据。失败保留 code/message、调用路径与 source_location，并按实际错误保留 cause、任务错误、清理错误及业务 exit_code；不传原始异常对象。主错误和后续 drain、资源释放、run_failed hook 错误不能互相覆盖。取消伴随清理失败应报告失败，而不是纯 cancelled。

已退出记录保留结果到本次 workflow 结束，成本为 O(累计任务数及输出大小)，不是 O(活跃任务数)。活跃 signal/controller、监听订阅、工作池和控制线程不作为最终结果保留。长时间反复启动任务仍可能积累结果；任何改变结果保留期限的设计都会影响先结束后等待及重复等待合同，需要另行讨论。

## 规则与图形

Python `rules/node/async_lifecycle.py`、JS `rules/node/handlers.py` 及 toolchain 源码分析分别检查控制身份与原生后台工作归属；Target Ruleset 负责选择入口，图关系检查保留在图层。管理身份不自动豁免副作用、质量或依赖规则。

JS 的活跃调用集合与源码审查集合分别由 node_type_calls/source_node_calls 表达：后者包含独立 Nodeset 声明中已实现的 Node，调用路径为空，不赋予执行身份。audit/build 的归属策略和 run_javascript_rules 必须共同消费该源码集合，登记相应 BaseLib 与传递依赖，不能只把 Node 加入审查却遗漏它的依赖归属。该区别尤其影响跨 root、planned 管理调用及未使用 Nodeset 声明，回归位于 task_management/run_ownership.py。

检查应依据真实绑定和有限的拥有/释放模式：同名用户方法不是原生计时器；局部对象字段保存的原生句柄必须由同一对象释放；Python 线程/进程在 finally join、池在 context manager 或 finally 等待 shutdown。源码规则不是任意程序清理路径证明器，运行器也不能自动接管用户遗留的原生后台资源。

taskManagerNode 的默认形状为 dbl-circ，填充 #FCE7F3、边框 #BE185D、文字 #831843，标签含“任务管理”。状态可覆盖颜色，但保留形状与身份。Mermaid doubleCircle 半径只依宽度，需要原生 flowchart padding 让完整长标签四角位于内圆；代价是留白增加。两侧 Architecture、Mermaid/SVG 和 ASCII 消费共同身份与目标事实，颜色不授予权限。

## 维护验证与路线复核

公开使用场景位于根目录 `sandbox/python/task_management/` 与 `sandbox/javascript/task_management/`；细粒度回归见 `tests/targets/python/test_task_management.py`、`test_task_ownership_rules.py`、`tests/targets/javascript/test_task_management.py`、`tests/tooling/test_task_manager_visuals.py`，输入/计划跨 Target 对照见 conformance。维护变更按受影响目的定向验证，必要时再运行 `python tools/verify_project.py --full`。

生命周期变更应核对：finally 早于通知、无等待停止早于 cleanup 但 workflow 晚于 cleanup、SDK race 落败操作仍收尾、单工作池与排队停止无死锁、嵌套所有权、all 输入、未消费与并发清理错误、跨运行引用和规则关闭后的控制拒绝。展示变更核对两 Target 的正常/警告/错误与长中文标签。

交付前复核实现与验证成本、双 Target 维护负担，以及“普通数组足够、实际执行可持续跟踪、通知统一在收尾后、双圆形可容纳标签”的假设。保持现有公共行为的修复自主处理；若准备改变结果保存、通知时机、生命周期所有权或图中可见边界，先用同一场景说明差异，再由用户决定。失败记录、定向复验、完整固定批次和真实浏览器证据分别保存。
