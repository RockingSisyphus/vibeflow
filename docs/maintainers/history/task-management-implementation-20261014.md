# 原生任务管理实施记录

状态：实施与第四轮固定版本全量验收完成（2026-10-14）。下文阶段记录保留当时状态与失败；最终结论见“第四个固定批次与交接收尾”。不发布版本，不升级 ERA/GSKO 嵌入内核。

采用 TaskRef 普通数据与普通数组、task_manager 身份、每次 workflow 的统一执行记录。TaskRef 字段为 run_id、task_id（字符串）；TaskOutcome 使用 task、status、outputs/error；StopAck 使用 task、state。管理 API 位于 context.tasks；普通 Node 只能取得自身信号、声明的 Capability 和 trace。Decision 不变。

TaskPlan ABI v6 保存管理调用、槽、已编译任务 Block 与执行器。请求停止不等于退出；最终通知发生在 Node 的实际执行、finally、SDK 操作和受管后代收尾之后。名单可复制、中转、筛选，框架不会修改名单或隐式等待其值。结果保留至本次运行结束；缓存成本为 O(累计任务数及其输出大小)，活跃信号、控制回调、线程池上下文不会作为最终结果保留。

Python 保留同步 Node 与线程池，管理目标使用独立控制线程，避免等待占用被管理的工作池。JS 保留事件循环，并跟踪每次 Node 调用的 SDK 操作，包括 Promise.race 的未完成操作。普通 Node 的 finally 可以在取消后调用和等待清理操作；启动新受管任务仍被拒绝。

管理 Node 默认浅玫红、原生 Mermaid dbl-circ，明确标注“任务管理”。原生 doubleCircle 的半径只依据宽度，详细标签会超出边界，因此渲染时增加原生 flowchart padding；没有截断标签或修改 SVG 形状。代价是图形留白增加。浏览器已实测中文长名称和完整字段位于内圆内；最终两 Target 状态与布局矩阵仍需验收。

## 阶段证据

- 最初底层 JS ESM 原型：B 失败后通知，A 的 40ms finally 完成后返回取消结果。
- Python 原型：plan/compiled/block 三模式通过；后续定向用例覆盖无等待停止、外部取消、底层操作不响应取消、排队停止、池饱和、未知与跨运行引用、规则关闭后普通 Node 控制拒绝。
- 正式 Python CLI 沙箱首次：12 项通过（四场景、三执行模式）；框架图重复逻辑提示为 CONCERNS，保留该状态。后续已增加意外异常和无取消能力的操作，须复验。
- 正式 JS 沙箱首次完整：12 项通过，Node.js、真实 Chrome/150.0.7871.24，esm-module 与 web-app；页面未处理异常为空。该批次未覆盖后续扩展场景，不能视为最终全量证据。
- JS runner 前三次尝试分别暴露 native TS 声明解析、HTML 入口标记和探针字符串替换错误，均保留原失败日志。修复后的通过不覆盖原失败。
- Core/portable/Python 执行锁局部旧测试批次：382 passed、21 failed、2 skipped。包含旧并发入口迁移、规则数量变化，以及一次嵌套 Runtime 入口 bug；后者已修复并定向通过。旧入口的正向验收目的仍待迁移，不能删除后宣称原测试全绿。
- 后续新机制定向测试：12 passed，含 SDK Capability race 的实际收尾、取消后 Capability finally 清理及 stopping 状态。此为定向结果，不代替源码/浏览器/完整仓库验收。

## 执行中的成本、目标与路线复核

剩余主要成本是旧配置与测试迁移、真实浏览器扩展矩阵、错误/警告身份与长标签布局、SDK/schema/手册同步，以及根目录完整验收。数组和统一执行记录足以支持目前原型，未引入 TaskGroup、名单登记表、轮询、提前失败通知或源码异常插桩。

下一复核点为旧并发用例迁移完成及接口定型前：检查是否仍有 pending/detached 执行容器、取消后收尾是否覆盖全部 SDK 入口、长时间反复启动短任务的最终结果缓存成本，以及原有并行/锁验收目的是否保留。依据实际结果复核维护负担与验证代价；不得静默退回提前返回或删除原有生命周期验收目的。

最终须运行两个沙箱及 python tools/verify_project.py --full，并分别报告旧批次失败、定向复验、新全量和真实浏览器结果。历史验收记录不改写。

## 后续迁移与复验（2026-10-14）

首次完整 pytest 固定批次：4224 passed、146 failed、22 skipped、26 errors，日志 /tmp/vibeflow-task-tests-01.log。此批次未开启 Mermaid renderer，不属于完整仓库验收。失败包含旧协议未迁移、开发包模板残留超时配置、新 JS 插件声明缺少 const；已修复后两项并继续逐项迁移。

两侧公开沙箱扩展结果：Python 18 项组合通过，JS 16 项构建／运行检查通过（真实 Chrome/150.0.7871.24，ESM 与 web-app）。证据 /tmp/vibeflow-task-python-public-02/report.json、/tmp/vibeflow-task-js-public-05/report.json。新增意外异常及不响应取消的操作；这些仍不涵盖最终全矩阵。

嵌套取消复验修正了收尾期间外部取消被当成成功的边界；root 在实际 drain 后再次检查取消。JS Task trace 记录管理调用路径。Python 的实际任务计数在 root 收尾后汇入限定路径摘要，同时重用普通 Nodeset Runtime 时更新任务归属，保持现有实例缓存。JS 插件工厂初始化失败及同步入口均移除调用的取消监听。任务等待 Promise 也属于管理 Node 自身操作。

Conformance 与配置迁移保留数值、分支、锁和实际工作线程目的；TaskPlan 改为明确目标与执行器，不再以 graph 的局部 entry_mode 推测 JS／Python 执行器。最新对照批次 126 passed、2 failed；最后两项为 JS 管理实现输出 ABI，已修复后定向 4 passed。Python Runtime 最近批次 105 passed、1 failed；最后一项旧迁移负例缺少系统调用合同，已补齐。源码质量检查 PASS。

当前仍有旧 CLI 并发退出、冻结产物、深度规则用例与沙箱 runner 需要迁移；仍未进行 python tools/verify_project.py --full，不能称实施完成。全量之前继续核查实际行为和矩阵覆盖，不因单项通过刷新历史分母。

第二次固定 pytest：4341 passed、53 failed、22 skipped（/tmp/vibeflow-task-tests-02.log）。包括因误加取消检查导致直接 CLI business exit 被当成取消的回归；已去除 business-exit 分支的该检查，正常路径仍在 drain 后再次检查外部取消。后续 60 项包文档／实际 JS 项目构建定向通过。

进一步定向：Native 资源绑定与 API 规则 107 passed，Python 任务归属与执行锁 36 passed。发现任务目标的 Python SourceCall 尚未进入调用点列表，已补齐递归收集，任务、执行锁及规则权限合并定向 45 passed。任务内 SystemExit 保留为带 exit_code 的结构化失败数据，示例管理 Node 明确决定是否转成父流程的 CLI 退出。

两个需要在接口最终复核前核查的合同：TaskTarget 的 all 基数输入是否完整复用原有 envelope 传递；源码异步归属检查对 Promise executor 中原生 interval／listener 和 Python 原生后台线程的覆盖。不要因常用 exactly_one 输入或简单计时样例通过而跳过这些边界。

## 接口定型前复核

第三批 pytest 为 4388 passed、15 failed、22 skipped（/tmp/vibeflow-task-tests-03.log）；运行过程中有后续源码调整，因此不能作为最终固定版本验收。JS integration 50/50。其中冻结产物已按 ABI v6 有限目标重新审查并更新；无消费输出的任务仍必须产生实际退出 trace；控制台线程探针补充 finally join。相关定向 40 passed。

公开沙箱最新结果为 Python 54 项（plan/compiled/block、普通与管理 Nodeset、单工作线程及排队停止），JS 46 项（Node.js、真实 Chrome/150.0.7871.24、ESM 与 web-app）。证据分别为 /tmp/vibeflow-task-python-public-05/report.json、/tmp/vibeflow-task-js-public-10/report.json。前两次新增嵌套配置尝试因使用已移除的 inline nodesets 和缺少终端入口失败，保留日志；改为正式 nodeset_imports、完整 Node/Nodeset 合同后通过。

两 Target 各正常、警告、错误的长中文管理标签由实际 Mermaid SVG 与 Chromium 检查，双圆形及类型标识保留，标签四角均位于内圆，3 个组合测试通过（/tmp/vibeflow-task-visual-matrix-01）。独立原生资源规则绑定/Promise executor 检查定向 22 passed。

all 基数嵌套复核发现 JS rawInputsForChild 仍取首个值；已改用内部 envelope 传递保留全部值，不改变公开名单或新增控制容器。Python与JS直接和Nodeset目标均验证空、单个、多个输入。相关合同、512 短任务缓存与执行资源回收、冻结产物和对照测试合计 76 passed（/tmp/vibeflow-task-final-contract-01.log）。缓存继续明确为 O(累计任务数及输出大小)，不得假称常量空间；已退出记录不再持有信号，root 收尾后不保留工作池或控制线程。

执行中的成本、目标与路线复核：数组足以实现跨 Node 控制和事件通知；原分散 pending/detached 运行容器已删除。实际执行、SDK race 操作、嵌套与 finally 的收尾边界已由公开探针和屏障支持。剩余成本是固定版本根目录全量、规则差距及发行包隔离验收；不会为了减少验证成本删除旧验收目的、放宽归属或恢复提前返回。原生双圆形可容纳完整标签，但增加 padding 带来更大留白，已记录并验证。接下来冻结源码运行完整批次；失败先保留并尽量跑完，集中修复、定向复验后再开新批次。尚未完成完整验收。

首个根目录 --full 批次在 pytest 中途遇到 /tmp 用户配额耗尽（实际写文件探针 Errno 122 Disk quota exceeded）。虽然 df 仍显示空闲，复制文件变为零字节，pytest 连错误汇总也未能写完，进程退出 120；该批次中断，不能给出可靠的最终测试分母，也未完成后续步骤。日志 /tmp/vibeflow-task-full-01.log 和 verification.json 保留。此前前置质量检查另有本次定向 pytest 留下 .pytest_cache 的失败，已按生成产物清理。

本次生成的 tests-02/tests-03 工作区移到 /home/rockingsisyphus/.cache/vibeflow-task-management-20261014，原 /tmp 路径保留符号链接。新批次将 TMPDIR 与 scratch 均放在该仓库外磁盘目录，避免继续消耗 tmpfs 配额。没有删除用户项目资产。

收尾复核同时补齐 Python 多次清理失败的保留：run_failed hook 的异常附加到主要错误，任务 drain、资源关闭和锁释放的错误累计保存，不互相覆盖。带父流程失败、工作任务 cleanup 失败及 run_failed hook 失败的实际运行探针通过；Python 合并定向 187 passed。JS 合同和原配额失败涉及的 domain fixture 在外部磁盘目录定向复验后，再冻结根目录新批次。

## 第二个全量批次及集中修复

full-02 的 18 个步骤均执行完毕。pytest 4438 passed、4 failed，无跳过；Python integration 104/104；适配 207/207；wheel isolation、两种开发包构建及 verify-kernel、最终质量与生成产物清理通过。本批仍有前置生成产物失败，且临时目录过长导致 Chromium Unix socket 启动失败，影响 JS 浏览器、运行状态、布局、资源图和 Python review 性能检查。全部原日志与报告位于 /home/rockingsisyphus/.cache/vibeflow-task-management-20261014/full-02，不以新通过覆盖失败。

规则对照 1219 项中有 38 项不匹配：旧并发元数据与新迁移诊断/入口数量、遗漏的 JS Plugin/Host Extension 异步规则入口，以及旧 JS 正向 TaskPlan fixture 未迁移。已补齐规则入口，不恢复 Node 的旧按名称拒绝；旧输入作为明确迁移负例保留，并增加/迁移有限任务目标正例。reference.json 历史观察未改。修复后 Core/Python 对照 619 项匹配，JS/配置 604/604 匹配；其中新 Core 用例保留条件/非条件数据路线、无结果消费者时的 workflow 所有权和普通 Node 禁止控制。

Core 现在对任务目标与 Nodeset 声明递归检查实际绑定身份、未知类型和旧入口；GraphConfigError 的迁移错误携带稳定 rule_id。相应 Core/配置定向 86 passed。JS 原生计时句柄保存于局部对象字段并在 finally 释放合法，清理另一对象的同名字段不会授予归属。

SDK 操作的退出错误探针原批次 2 failed（/sdk-cleanup-errors-01.log）：Node 已返回时，pending Capability 的实际清理失败会被 allSettled 忽略。现退出仍等待所有操作，并把收尾失败反馈到最终结果；原有 Node 错误保留、清理错误附加，不增加提前通知。相关机制与 Core/计划/Python任务合并 392 passed，后续 JS 构建/嵌套/CLI定向 148 passed、资源绑定及任务 31 passed。Python 管理线程起动与工作池提交在同一完成通知锁下登记，起动失败不会遗留活跃记录；单池/排队/锁及失败起动定向 42 passed。

短磁盘临时目录 /home/rockingsisyphus/.cache/vftm/tmp 修复 socket 长度限制。受影响的环境定向 5/5 步骤通过；JS integration 50/50；资源回归 475/475。最新公开 JS 46 项通过，真实 Chrome/150.0.7871.24；每个运行结束时原生计时器、interval 和 AbortSignal 监听计数均为零，页面未处理异常为空。证据 js-public-11/report.json 与 browser-proof.json。

执行中的成本、目标与路线复核：本批实践继续支持普通数组、单次运行统一记录、实际退出后通知及原生双圆形。增量修复针对实际丢失的收尾错误和遗漏检查入口，没有扩展 TaskGroup、轮询或控制通道。源码规则仍是实际绑定与有限归属模式检查，不是任意程序清理路径证明器。剩余工作是修正环境与固定源码的新全量；其结果必须独立报告。当前仍未完成验收，不发布版本。

## 第三个固定批次

full-03 完整执行 18 步，17 步通过。pytest 4452 passed，无失败无跳过；Python integration 104/104、JS integration 50/50；资源差距 680/680；运行状态、布局、两侧区块和性能、适配 207/207、wheel/两种开发包隔离、最终质量与清理均通过。记录 /home/rockingsisyphus/.cache/vibeflow-task-management-20261014/full-03/verification.json。

唯一失败为规则对照的 16 个配置负例：GraphConfigError 新增可选 rule_id 后，Core 报告适配器按属性存在与否取码，没有处理空值。实际配置仍被拒绝；原 Generic 错误名称被记录为空，属于报告回退问题。只修复两个适配器的取码逻辑（非空 rule_id、code、错误类型名依次回退），不改原输入、预期、分类或 reference.json 历史观察。定向确认后再冻结运行最终全量。full-03 的失败记录保留，尚不宣布全量完成。

## 第四个固定批次与交接收尾

原会话“核查 Node 计时资源接口”（01a134fa-7fbe-73f0-83f0-b65cfb9ff6d6）在第四轮期间发生 stream disconnected 错误，聊天最后仅报告到 Python integration 完成。磁盘报告与日志确认该批次随后完整结束，不能将聊天中断视为验收中断。第三轮的报告回退修复先经 Core 定向 328/328 匹配及质量检查通过，再进入第四轮固定批次。

第四轮 `python tools/verify_project.py --full` 的 18 个步骤全部通过，`failures` 为空，日志以 `VibeFlow verification: PASS` 结束。证据根目录为 `/home/rockingsisyphus/.cache/vibeflow-task-management-20261014`；完整报告为 `full-04/verification.json`，命令与输出为 `full-04.log`。原 full-01 中断及 full-02、full-03 失败证据保留，独立于本轮通过结果。

| 验收项目 | 第四轮结果 |
| --- | --- |
| 前置质量、compileall | 通过 |
| pytest（包含实际 Mermaid renderer） | 4452 passed，无失败、无跳过 |
| Python integration | 104/104 |
| JS minimal、JS integration | 通过；integration 50/50，无跳过，包含实际浏览器 |
| 规则对照 | 1223/1223 匹配，无进程错误 |
| 资源差距回归 | 680/680 匹配 |
| 浏览器运行状态、图形布局 | 通过 |
| Python/JS 资源区块与图形性能 | 通过 |
| 适配回归 | 207/207 匹配 |
| wheel isolation、两种开发包与 verify-kernel | 通过 |
| 生成产物清理、最终质量、clean-tree | 通过 |

交接时逐文件对照第四轮 `compile-source` 快照与当前 `src`、`tests`、`sandbox`、`distribution`、`tools`、`repo_check`：1778 个文件内容一致，无缺失或差异。这里的 clean-tree 是验收器的生成产物检查，开发改动在交接时仍未提交，不代表 Git 工作区已无修改。本次收尾只补记实施文档并将完成记录归入 history、更新导航，不改运行器、规则、配置或测试；复用第四轮完整验收。文档更新后的 `python -B repo_check/run.py --profile all` 通过（0 error、0 warning、0 info），`git diff --check` 通过；交付以本地 Git checkpoint 为边界，证据工作区和运行产物不纳入提交。

### 执行中的成本、目标与路线复核结论

原目标与公共合同保持不变：普通 TaskRef 数组、有限编译目标、管理 Node 决策、实际退出后通知和 workflow 统一收尾。JS 仍使用事件循环，Python 仍使用线程与完成通知；本次并发改造不意味着新增 JS Worker 多线程执行器。原型、公开沙箱与第四轮完整回归支持上述行为，交接未发现需要改变已批准路线的新证据。

结果保留到本次 workflow 结束，缓存成本仍为 O(累计任务数及输出大小)；常驻 workflow 无限累计短任务时不能承诺常量空间。原生双圆形通过 padding 容纳完整长标签，代价仍是更多留白。源码归属规则识别有限绑定与清理模式，不承诺证明任意程序的全部清理路径。这些边界已写入使用者手册，没有以额外容器、轮询或提前通知补偿。

本任务的实施与必要验收已完成；本地 checkpoint 保存开发成果。发行版本发布、push/tag、ERA/GSKO 嵌入内核升级不属于本次交付。未来若修改生命周期语义、任务缓存策略或图形身份，应重新核对相应验收目的；既有失败记录继续保留。
