# 简单数学沙盒整合与验收

日期：2026-10-09。保留两 Target 的 comprehensive_math，本轮增加四类场景、五个独立入口，只移除 integration runner 中的重复正常任务。tests 和 tests/fixtures 的独立回归不退役；最初限定不改 Core、SDK 和质量规则，保护工作区已有修改。规则故障修复的后续授权见下文。

范围补充：首轮完整验证暴露保留的规则专项故障后，用户明确选择“允许修复规则机制故障并完成验收”。因此本轮后续可修复对应 Core/Target 机制问题，保留原有质量阈值和检查断言；不覆盖工作区其他规则重构改动。修复后先跑失败专项，再进行阶段全量。

## 场景与通过条件

| 入口 | 简单计算与使用条件 | 必须观察的表现 |
| --- | --- | --- |
| Python cli_addition | 文件/文档中的 2、3，stdin 的 4；三种适配配置 | 2+3+4=9；stdout 为 sum=9 加换行；stderr 为 writer=pathlib/open 加换行；文件为 9 加换行；退出码 0；argv、效果范围、节点次数、退出摘要正确；核心日志不含业务数据；架构导出不写输出文件 |
| Python object_addition | 两个原生对象 Box、Counter；单次、覆盖参数、固定四次、嵌套条件两次 | 单次 5、覆盖 10、固定 14/历史 [5,8,11,14]、条件 8/历史 [5,8]；两个对象仍是原对象；报告保留对象、集合及 NaN；子计划顺序/绑定/导出正确；carry/collect、终止、qualified 路径与 trace 次数正确；固定循环的 plan/block/compiled 结果一致 |
| Python plugin_addition | 多文件 Node/BaseLib/Plugin；默认和局部覆盖；修改 helper 后重新加载 | 默认 5，覆盖 6；修改、恢复得到 5→6→5；新解释器隔离源码缓存；编译钩子、嵌套调用、Node 前后钩子和运行结束钩子精确匹配；重复输入隔离；实现 helper 归属正确 |
| JS plugin_addition | 同上，通过正式 AOT 构建后调用 | 同样的数值对照；同步调用直接返回；每次调用的运行钩子成对并验证次数；active/declared/planned、ABI、已有来源字段、编译 annotations 正确；编译和 planned 插件不进入运行代码；helper 归属正确 |
| JS async_addition | 两次调用用相同 key、独立 Capability；先释放右边；持续 Port 处理两对数字后等待 | 释放前均未完成；右侧先得到 30，左侧仍等待，随后左侧得到 5；请求各一次，trace 独立且 add 各一次；持续 Port 接收三次、发送 5/30 两次；导入不创建 Host，create/start/stop 各一次；停止挂起调用为 VF_ABORTED，重复 stop 幂等；browser ESM 构建成功 |

所有 Python 已检查运行还验证 health 无 error、架构/图产物存在及 SVG 是合法 XML。期望数值写在测试驱动或共享输入表中，不通过业务函数生成。共享支持文件仅负责工作副本、依赖复用、CLI/报告与产物读取；业务实现各自独立。源码和生成报告存放在工作副本中，实际执行永远走 VibeFlow 的正式检查、执行或构建链路。

## 18 项逐项替代记录

Python 名称省略 valid: 前缀。下面的检查都已经在新驱动中明确断言，旧用例名称和原始驱动另外保存于外部验收证据。

| Target | 退役任务 | 新检查位置 | 保留的旧检查含义 |
| --- | --- | --- | --- |
| Python | delegate-cli:native_process | cli_addition/run_all.py，yaml | argv/文档、stdout/stderr、退出码、报告、核心日志隔离 |
| Python | delegate-cli:numeric_pathlib | cli_addition/run_all.py，pathlib | 文件和标准输入、字节输出、作用范围、节点次数与导出无副作用 |
| Python | delegate-cli:numeric_streams | cli_addition/run_all.py，streams | input()/readline()/open/Path/print/标准流的旧路径分别在三个变体覆盖 |
| Python | training_nodeset_object_flow | object_addition/assert_result，single | 两对象身份/属性、Nodeset、对象/集合/NaN 报告 |
| Python | loop_stop_after_nodeset_training | object_addition，fixed-plan | 四次 carry/collect、结果与历史、完整运行摘要及 qualified 路径 |
| Python | loop_stop_after_nodeset_training_block | object_addition，fixed-block | block 循环事件、次数和 qualified 路径 |
| Python | execution_plan_nodeset_subplan | object_addition，override | 子计划绑定 delta=8；实际 2+8=10 |
| Python | execution_plan_training_nodeset | object_addition，single | 明确的多节点子计划顺序、对象及报告 |
| Python | nodeset_loop_subplan_reuse | object_addition，conditional | 嵌套 Nodeset 两次调用、stop_when、迭代路径及进入/退出次数 |
| Python | nodeset_reference_exports | object_addition，single | 显式导出清单、对象/报告内容和身份 |
| Python | plugins | plugin_addition/consumer.py | Plugin 注册、Node/BaseLib/Nodeset 执行；补充精确数值与编译/运行钩子断言 |
| JS | async:promise-and-capability | async_addition/scenario_driver.mjs，finite | Promise、请求参数和次数、响应传递与数学输出 |
| JS | capability:concurrent-isolation | async_addition，finite | 同 key 两个注入实现、逆序完成、独立结果/请求/trace |
| JS | host-extension:async-permanent-port-cleanup | async_addition，stream | 生命周期、持续收发、挂起停止、重复 stop、browser ESM 构建 |
| JS | plugin:manifest-and-planned | plugin_addition/run_all.py | 原 manifest ABI、active/declared/planned、来源信息与 completion |
| JS | plugin:policy-compiler-hooks | plugin_addition/run_all.py | 编译钩子顺序/annotations、运行代码不包含编译与 planned 插件 |
| JS | plugin:runtime-repeat | plugin_addition/run_all.py | 同步 ABI、直接返回与不同输入重复运行 |
| JS | plugin:runtime-concurrent-isolation | plugin_addition/run_all.py | 原任务实际上是顺序调用；明确称为重复调用隔离，真实并发由 async_addition 承担 |

登记任务数：Python 132→124（退役 11、增加 3），JS 58→53（退役 7、增加 2）。任务数不等于内部观察次数或代码覆盖率。

## 保留与清理

- 保留异常输入、缺失能力/取消/超时、detached 清理、锁、全局状态、普通 callback、特殊分支调度、循环边界、编译源码与 block 结构、TypeScript、真实浏览器 Host/profile、布局和资源归属/文件变更专项。
- pass_training_nodeset_object_flow.jsonc 及其资源被全局状态 pytest 引用，保留文件，只移除重复运行任务；直接 training_object_flow、training_non_json_metrics、block/compiled_linear_training 仍保留。
- JS 原 plugins/async_capability/Host 配置与源文件还被 pytest、类型、执行模型或浏览器专项使用，继续保留。仅删除专属的 plugin_cases 驱动与已无调用的函数。
- Python 删除无运行引用的九个顶层配置及七个仅为它们导入的 Nodeset 文件；共用 Node/BaseLib/Plugin 声明仍供其他专项使用，保留。
- 新项目不更改 quality_enabled 或质量规则；临时依赖、源码修改与运行产物默认在仓库外。

## 执行中的成本、目标与路线复核

首个 CLI/对象原型、插件修改/恢复、异步等待/并发与删除前分别复核：数学仍很简单，旧检查可以迁移，新增复杂度主要是 SDK 声明与观察驱动，未形成小应用或新测试框架。复用已安装依赖和同配置执行计划；每次业务调用创建独立对象/状态。参数覆盖只在插件基线检查，修改/恢复阶段各重建默认配置，避免重复验证同一条件。Python after_run 会对内层和根运行各调用一次，JS 运行钩子按自身 ABI 验证；不强行统一两 Target 的实现语义。

源码阶段每次重建、加载，保证修改不被缓存掩盖。JS 相比七个旧正常任务增加了修改/恢复与受控等待检查，组耗时可能增加；因此分别记录任务减少、覆盖增强与耗时样本，不用登记数量代表提速。若实践要求扩展业务或舍弃检查，按 critical-fork 说明证据和路线，必要时征求用户决定，继续独立工作并更新本记录。完成/确需用户介入时沿用 codex-task-alert 的资格规则。

完成后的维护量复核：五个入口的驱动合计约 457 行，共享准备/报告支持约 90 行；实现与 SDK 声明合计约 413 行，声明配置约 2171 行。体积主要来自正式资源和图配置，业务仍是加法、对象更新及计数，没有加入实际小应用。原检查逐项迁移，保留难以由正常加法证明的专项；源码修改阶段需要多次重建，所以入口数量减少的同时，不能承诺同等比例的耗时下降。异步驱动还清理了成功后未取消的 watchdog，避免额外等待两秒。

首轮全量暴露的规则故障由用户授权扩展范围后修复，未降低阈值或取消断言。第一份固定副本完成验收后，同一工作区中的另一项规则重构继续修改框架。为防止将旧源码成绩当成当前成绩，本轮保存了第二份固定副本并重跑相关检查与两个沙盒批次。此额外验证成本来自共享源码变化，独立记录，不算作数学场景自身的运行耗时。

## 实际验收

完整批次使用仓库外的固定源码副本，保存源码清单和原始报告，避免并行编辑改变批次中途的行为。未把前一次不完整运行、未运行的命令或另一任务的测试成绩计入本轮通过数。

| 验收项 | 实际结果 | 原始记录 |
| --- | --- | --- |
| Python 完整 integration | 124/124 通过；失败 0；跳过 0；退出码 0；501.352 秒 | [汇总位置](../../evidence/index.md#external-65bdc7f6b9dfb374) |
| JavaScript 完整 integration | 53/53 通过；失败 0；跳过 0；退出码 0；137.472 秒；包含真实浏览器专项和 52 项嵌入式质量 pytest | [汇总位置](../../evidence/index.md#external-c0463e5f0fa01f08) |
| 相关 pytest | 222 通过，87.07 秒；涵盖沙盒集成、对象/观察、Rule graph、输入记录、选择边界、Nodeset、资源配置及审查 | [日志位置](../../evidence/index.md#external-466798745f4a9b80) |
| 后续规则修改专项 | 128 通过，82.42 秒；与上行有重叠，不相加计算独立用例总数 | [日志位置](../../evidence/index.md#external-9c7c54d6ec1c71eb) |
| quality all | 当前工作区和补验副本通过：0 error、0 warning、0 info | [日志位置](../../evidence/index.md#external-6999a0ad380a32a6) |
| 后续五个独立数学入口 | 全部通过；CLI 3、对象 6、Python 插件 3、JS 插件 3、异步 2 组观察 | [结果位置](../../evidence/index.md#external-384da8301cda12b7) |

两个完整批次和 222 项 pytest 对应 [完整验收源码清单位置](../../evidence/index.md#external-01a3d72a867b3269)，后续专项与五入口对应 [补验源码清单位置](../../evidence/index.md#external-6a244a371842e7d5)。副本保存在同一证据目录，可以核对实现、配置和驱动，而不依赖后来变化的工作区。当前工作区仍有另一任务的规则重构；本记录不声称其后续所有改动已经跑过本轮完整批次，也不声称整个仓库所有 pytest、发行或性能专项均已执行。

### 暴露问题与处理

首轮 Python 批次 120 通过、4 失败；其中 3 项机制问题涉及 Nodeset 覆盖警告、子图编译失败的诊断和递归检查，另 1 项为缺少健康报告的连带产物审计失败。首轮 JS 批次 51 通过、2 失败，涉及综合场景和内嵌质量专项；相关 pytest 另暴露 4 项输入 Record 不可用路径的问题。全部完整批次先保留结果，再集中修复并验证失败项，没有通过删除检查解决失败。

本轮修复包括：

- 输入 Record 不可用时不再因诊断去重访问缺失条目而触发 KeyError，消费者保持阻断并给出 RULE.INPUT.UNAVAILABLE。
- 未被调用的 planned Nodeset 仍进行声明检查；内置分析保留关系、宽度、深度与递归信息，遵守显式空选择边界。JS build 补齐未调用声明的编译事实，有限图数据编码避免递归序列化。
- Python 子图编译失败转为结构化健康诊断，其他声明规则仍可执行；恢复调用方覆盖父全局和 Nodeset 内全局配置的警告。
- JS 原生质量测量保留声明实现绑定及 BaseLib 事实。Node 代码复杂度使用自身符号/引用范围，物理文件行数、字节数另行保留，避免裁剪后掩盖源码大小限制。增加显式空边界和文件末尾空白/注释达到、超过大小阈值的回归。

第一次固定副本的完整 JS 为 53/53，相关 pytest 为 218 通过；Python 的一次尝试中途收到 SIGTERM、退出码 143，没有最终汇总，终止原因未确定，未算作完整通过。随后独立进程重跑 Python 124/124。共享源码变化后再次固定副本，得到上表第二轮完整成绩。最新 JS 测量变更曾让 3 项物理源码大小检查失败，已修复并补充回归；一次带相对 node-id 的验证命令没有找到测试，纠正入口后纳入正式复验，不计入通过数。

副本复制时还缺少 references 规范目录和历史外部证据相对链接；补齐目录别名后继续检查，没有修改框架判断来适应副本路径。工作区测试生成的已完成状态产物已保存到外部证据目录，再用标准 clean_workspace 清理可再生缓存和运行目录；保留源代码、发行资产及其他任务改动。

### 耗时样本

环境：Python 3.13.13、Node v24.18.0、npm 10.9.9。删除前运行旧驱动，依赖已预热，18 个旧任务全部通过；同时记录新入口的独立运行。它们是同机顺序样本，不是多次统计或稳定性能承诺。

| Target | 旧组 | 初次完成的新组 | 第二轮完整批次中的新组 |
| --- | --- | --- | --- |
| Python | 11 任务，79.071 秒 | 3 入口，63.603 秒（38.574+12.226+12.803） | 70.100 秒（38.331+17.032+14.737） |
| JavaScript | 7 任务，6.190 秒 | 2 入口，7.875 秒（4.071+3.804） | 6.405 秒（4.503+1.902） |

[原始样本位置](../../evidence/index.md#external-d528ed995558227e)保留每项结果。后两列包含不同阶段的规则修复、断言完善和运行负载，不能据此计算可靠的统一提速比例。JS 新组增加了真实修改/恢复与等待观察，watchdog 清理又消除了成功后的额外等待；数学整合的确定收益是入口和重复驱动减少，覆盖迁移有明确对应关系。
