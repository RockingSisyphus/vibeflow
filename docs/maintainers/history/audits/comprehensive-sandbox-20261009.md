# 双 Target 综合数学沙箱整合归档

日期：2026-10-09。基线：0.17.0 / `665e06e71725990be7a83d7e5c65d5897b051e89`。本次只调整沙箱和对应说明，不改变 Core、Target 或发行资源。整合前的全测试分类快照保留在 [测试盘点](test-inventory-20261009/README.md)。

两个新项目均为独立 `comprehensive_math`，被各自 integration runner 自动调用。详细公式、六组输入、十二类通过判定及运行方式见 [案例说明](../../comprehensive-math-sandbox.md)。它们用同一组预先计算的期望值核对两套独立业务实现，避免业务实现同时充当判分答案。

## 大表：逐项替代关系

“移除”指取消旧 integration 任务，复用项目文件按其他引用决定保留。旧任务的关键覆盖进入新案例或保留的专项；源位置、阈值、后端、错误、平台等有独立语义的其他任务继续保留。

| Target | 移除的旧任务 | 原模拟条件 / 通过依据 | 新案例承担的检查 | 文件处理 |
| --- | --- | --- | --- | --- |
| Python | linear | 顺序 Node 算出 14；portable 普通 Node 为 immediate/inline/current，无任务 | 数值矩阵；实际 portable 内层 block 的三个节点策略和无任务 | 删除无引用 pass_linear 配置 |
| Python | nodeset_simple | 单层 Nodeset 输入 1 得到 6 | 内层 affine Nodeset 正确输出、传到外层；qualified trace | 删除无引用 pass_nodeset_simple 配置 |
| Python | nodeset_nested | 嵌套 Nodeset 输入 1 得到 11 | 两层 prepare.inner.affine，整条公式与子图导出一致 | pass_nodeset_nested 保留给登记 review/架构刷新 |
| Python | port_math | 注入 receive=5，业务库运算得 21，send 参数精确匹配 | 原生 receive/send；六输入矩阵均检查次数、端口、最终发送值 | 删除无引用 pass_port_math 配置和专属注入分支 |
| Python | semantic_nodeset_arithmetic | 输入 4、6 得到 20/25；顺序、子图节点、factor、导出及 trace 正确 | 直接/嵌套参数绑定、子图顺序及导出、精确根顺序/执行次数/stop_reason、最终值 | 配置保留给 compiled 版本及其他契约检查 |
| Python | execution_plan_bound_params | seed/add/multiply 绑定 4/9/2，输出 26 | 实际 plan affine gain/shift=3/2，subtract amount=3，公式结果证明生效 | 删除无引用配置 |
| Python | join_policy_all | 两分支各提供不同数据，all 汇合得 8，顺序正确 | companion 与条件选中结果在 join all 汇合，各执行一次，计算 r+c | 删除无引用 pass_join_policy_all 配置 |
| JS | math:linear-base-lib | Node→纯 BaseLib 得 15，输出 envelope 无内部数据 | registered 多文件 BaseLib、独立手算结果、严格 public 输出 key 集合 | 原配置被 profile/ABI/prepare/review 等继续使用 |
| JS | abi:optional-input | offset=7 / 未提供时得到 17 / 10 | 同入口 x=4 得 487 / 480，省略 offset 按 0 处理，不跨运行残留 | 原配置保留给严格 TS 声明及 prepare |
| JS | abi:repeat-isolation | 同模块两次调用得 0 / 8 | 同模块六输入顺序调用，结果/history/可选 offset 不串值 | 原 linear 配置仍有其他引用 |
| JS | abi:concurrent-trace-isolation | 两调用并发，full/boundary 结果与 trace 各自独立 | 并发正负分支结果 480/20，独立 Port/trace，full 精确节点顺序，boundary 无 node 事件 | 删除重复运行函数，linear 配置保留 |
| JS | math:fanout-all-join | 同一输入扇出，分支得 11/9 | q 与 c 双支路经过 join all 汇合；结果与次数精确匹配 | 原配置保留给 prepare 测试 |
| JS | branch:any-active-positive | 非负时只运行 positive | 正、零输入与 q=0 临界：只跑 square，any_active 一次 | 原配置保留给 prepare 测试 |
| JS | branch:any-active-negative | 负值时只运行 negative | x=-3：只跑 negative，any_active 一次，结果 20 | 与上一项共用的原配置保留 |
| JS | nodeset:nested-math | Nodeset 结果 13；boundary trace 有 enter/exit | 两层 Nodeset qualified 路径、正确数值；boundary 保留 enter/exit | 原配置保留给 prepare 测试 |
| JS | loop:stop-when-carry-collect | 从 1 增至 4，history=[2,3,4]、三次循环 | body 条件退出、值/计数 carry、三元素 history 与三次 iteration | 原配置保留给 prepare 测试；固定次数/上限失败专项仍运行 |
| JS | io:receive-node-base-lib-send | async receive=5，计算 17，send 17 | 两 Target 原生 IO 端口/次数/值；JS 额外 held receive 验证等待，Node/browser 都运行 | 原配置保留给 prepare/Host 相关使用 |

Python 从 57 个普通合法运行任务中移除 7 项，另加综合专项一项；登记总数从 138 降为 132。JS 从 67 项移除 10 项再加综合一项，登记总数为 58。新专项内部有多次独立观察，因此 runner 任务数量不等于断言数或源码覆盖率。

## 小表：整合后可以怎样理解

| 类别 | 怎么制造测试条件 | 什么表现才算通过 |
| --- | --- | --- |
| 真业务链 | 端口收到正数、负数、零、边界值以及可选 offset | 计算、分支、汇合、循环、history、发送值与手算答案一致 |
| 自定义 Rule | 插件要求实现源码至少 10 个 t，square 实际只有 6 个 | 两条预期 warning 带正确 Node/Rule/文件行列/原因；没有 error，业务继续 |
| Rule 的正常对照 | 临时源码额外加 10 个 t，再次校验/构建 | 自定义 warning 消失，原生 warning 保留，证明不是固定输出或旧缓存 |
| 真实运行宿主 | Python 三种后端；JS Node.js 与真实浏览器 | 同公式得到同样答案；浏览器真实 DOM 输出；异步依赖未释放时保持等待 |
| 生命周期内的隔离 | 同入口连续运行、两次并发、不同 trace 设置 | 不串输入、输出、收发记录或执行事件 |
| 保留专项 | 错误/Schema/导入违规、分离调度数据边、任务与清理/取消、Host、发布/布局等 | 仍由原任务独立检查它们的正反预期 |

没有把全部 Rule 人为改成 warning。许多规则专门检查“必须拒绝”的情况，或没有 warning 分支；数学成功运行无法证明它们的阻断正确。Python 的 semantic_decision_branch_left/right 因检查调度/数据语义保留，JS nested-qualified-override 因检查同级调用局部覆盖不泄漏保留；新案例的嵌套覆盖不能代替这种独立隔离条件。tests 中的单元、边界与历史回归未删除。

## 实际验证与效率

本次最终全批结果见随附的 [验证记录](../../../../../VibeFlow-evidence/comprehensive-sandbox-20261009/results.json)。运行两个完整 integration 批次，JS 使用真实 Puppeteer 浏览器，Python 使用真实 Mermaid/Puppeteer 渲染；另运行受影响的 JS 预处理、规则插件与 Python runtime/Nodeset/默认参数回归及仓库质量检查。没有把该范围写成完整 `verify_project.py --full`、全 pytest 或发布包验收。

| 本次验证 | 实际成绩 |
| --- | --- |
| Python 完整集成沙箱 | 132/132 通过，约 284 秒 |
| JS 完整集成沙箱 | 58/58 通过，0 skipped，包含真实浏览器 |
| 五个相关 pytest 文件 | 104/104 通过，20.36 秒 |
| 最终仓库 quality all | PASS，0 error / warning / info |
| 最终目录调整后的两个集成 callback | 分别重新执行综合专项，都通过；JS 再次包含真实浏览器 |
| 新增与修改的 Python 源码 / 差异检查 | 23 个文件 AST 解析通过，git diff --check 通过 |

共享的判分资料位于 `tests/fixtures/support/comprehensive_math.py`，共用案例说明位于 `docs/maintainers/comprehensive-math-sandbox.md`，业务项目仍各自位于对应 Target 的 sandbox。最初仓库质检发现共用文件放在 sandbox 根目录违反现有职责，以及运行期间产生的默认 runs/工具 bytecode；搬到既定目录、在仓库外保留这些临时产物后复查通过。没有修改 quality 的目录约束或排除规则。

原始日志、修正前后 health、两套独立案例产物和源文件指纹保存在仓库旁 `VibeFlow-evidence/comprehensive-sandbox-20261009`，不把运行证据混入案例源文件。

单次本机对照使用预安装的锁定依赖，排除 npm 安装；旧 Python nested 先做真实 runner 所需的登记 review，排除这一步前置准备。旧任务逐项正常执行后计时求和，新案例包含整个运行、修正源码对照和诊断断言：

| 对照范围 | 旧任务累计秒数 | 新综合专项秒数 | 说明 |
| --- | --- | --- | --- |
| Python 七项 | 31.157 | 4.723 | 新专项包含 13 次数值观察、两个 SVG 与源码修正对照 |
| JS 十项 | 6.195 | 4.147 | 新专项额外执行真实浏览器八次观察及 held receive/源码修正 |

旧 Python 七项分别为 linear 4.339、nodeset_simple 4.553、nodeset_nested 5.457、port_math 3.744、semantic_nodeset_arithmetic 5.195、execution_plan_bound_params 3.976、join_policy_all 3.893 秒；全部通过。旧 JS 十项全部通过后累计 6.195 秒。最早隔离测量 nested 时缺少其 review 前置，报 DOCUMENT.MISSING，修正测试准备后才取得上表的通过时间；未把缺少准备的失败算进对照。

JS 初版新案例约 7.1 秒，反而慢于旧十项，因构建和修正各开检查会话。复核后使用现有 Target 的 `check_scope` 复用解析资料，保留源码修正后的失效检查，最后约 4.1 秒。Python 在首次 checked run 后复用图，减少七项各自重复的检查/渲染。两者都没有修改产品内核以迎合计时。

这是单次、本机、已准备依赖的样本；不承诺跨机器速度，也未测整合前后完整 batch 的严格 A/B。其他保留任务仍会构建部分相同配置，不能把专项节省秒数直接当作整批固定节省。

维护成本也有变化：每个 Target 保留十二个小 Node 和三个 Nodeset 来表达同一业务链，金值与报告断言共用，业务实现独立。修改公式时需要同步两套实现并重新手工核对金值；综合专项失败时用 code/位置/trace 定位阶段。局部与失败专项继续保留，避免所有回归都只能从一条长链中定位。
