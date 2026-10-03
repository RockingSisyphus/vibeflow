# JavaScript / TypeScript 基线规则盘点与真实入口对照

基线为 `f169429`；本轮的 current 是 Rule/Ruleset 重构后的工作树。此文件只记录规则、检查范围、测试和观察，不授权删减规则，也不修复生产实现。测试模块为 `sandbox/rule_parity/javascript/cases.py`，由根比较器分别在独立 Python child 中加载两版 kernel。模块顶层不导入 VibeFlow；项目 manifest 使用各自合法的 ABI / descriptor 形式，工具链由根 runner 按 lock 提供。

## 入口及范围

| 入口 | 基线实际路径 | 本轮测试范围 |
| --- | --- | --- |
| 正式 `audit` | Application `audit_javascript_project` → Target `run_audit_driver` → `auditContracts` | workflow 真正使用的 Node、启用 BaseLib、选中 Plugin/Host；不是单独调用 AST 判定函数 |
| 正式 `build` | Application `build_project_aot` → 源码审查、契约检查、esbuild 构建 | Node ABI、独立 Plugin、独立 Host；正常产物另用 Node 真正执行，输出 `4` |
| 正式 `quality-check` | JavaScript CLI `main` → workspace 质量扫描和资源审查 | 正常 Plugin、Plugin 宿主访问、Host/Node 顶层执行；与纯文件质量入口分开 |
| 普通文件质量 | Target `scan_javascript_quality` → TS AST facts → Core 数值/重复判定 | 文件长度、真实 TS syntax、AST 指纹 warning、函数/参数/分支指标 |
| Runtime Plugin worker | `JavascriptPluginSession.open` → 实际 Node worker `loadPlugin` | 独立工厂绑定、模块状态、宿主访问、Promise、timer、immediate async hook；不能代替 audit/build 结果 |

所有业务对照使用同一数值实现和声明合同。Node 声明为原生 terminal 边界角色，以满足默认 workflow 的起止判定；current 显式选择 `vibeflow.process`，副作用来源仍是所选 Ruleset。单独的空选择案例明确写 `rulesets: []`。两版 async 构建产物都调用真实 `runWorkflowAsync`。Plugin 工厂上下文 ABI 基线为 `vibeflow.plugin.v1`，current 为 `vibeflow.plugin.v2`，都合法。

## 基线实际判定

以下行号属于基线 `src/vibeflow/targets/javascript/resources/toolchain_driver.mjs`。它使用 JavaScript Target 自己的 TypeScript Program、TypeChecker、AST 和真实路径，未借用 Python AST。`auditContracts` 在 2207–2263 对到达且属于当前 root/owner 的非 `.d.ts` 文件调用这些主题；同一文件的多个实现 owner 另逐一检查 completion。没有到达当前检查范围的文件不能据此声称经过审查。

| 主题 / 基线位置 | 实际触发条件、允许项和所属资源 | 主要诊断 | 本轮代表案例 |
| --- | --- | --- | --- |
| 动态源码，190–268 | `import` / `require` 缺静态字符串参数；引用/调用 `eval`、Function 系列；字符串 timer。不是任意计算都禁止 | `VF_IMPORT_DYNAMIC`, `VF_IMPORT_DYNAMIC_CODE` | `js.node.dynamic-import`, `.require-dynamic`, `.dynamic-code` |
| 包和本地归属，461–615 | 真正解析导入：无法解析；未申明 external package；realpath 越 package_root；本地文件无 direct owner。Node builtin 留给平台构建解析 | `VF_IMPORT_RESOLVE`, `VF_IMPORT_EXTERNAL`, `VF_IMPORT_PACKAGE_ROOT`, `VF_IMPORT_OWNER` | `js.node.unowned-import`, `.unresolved-import`, `.external-undeclared`, `.package-root`；同一已有工具链包的合法对照为 `.external-declared.normal` |
| Node 导入归属，461–615 | Node→其他 Node；Node→未启用 BaseLib；Node→Plugin/runtime/registry/capability | `VF_IMPORT_NODE_TO_NODE`, `VF_IMPORT_BASE_LIB`, `VF_IMPORT_LAYER` | `js.node.other-node-import`, `.undeclared-base` |
| BaseLib 导入归属，461–615 | BaseLib→Node/Plugin/runtime/registry/capability；BaseLib→未声明依赖的另一 BaseLib | `VF_IMPORT_LAYER`, `VF_IMPORT_BASE_LIB` | `js.base.reverse-import`, `.undeclared-dependency`；两个 BaseLib 都启用，缺的是它们之间的关系声明 |
| Host 导入归属，461–615 | Host→非 Host；Host→另一 Host 但未声明 dependencies | `VF_IMPORT_LAYER`, `VF_IMPORT_HOST_EXTENSION` | `js.host.node-import`, `.undeclared-dependency`；两 Host 真正选中 |
| Plugin 导入归属，461–615 | Plugin→非 Plugin；Plugin→另一 Plugin 但未声明 dependencies | `VF_PLUGIN_IMPORT_POLICY` | `js.plugin.node-import`, `.undeclared-dependency`；两 Plugin 真正选中 |
| 导入时纯净，800–843 | Node/BaseLib/Plugin/Host/source：顶层只允许绑定名的 import、导出、类型/函数声明、指令及安全类/不可变 const initializer。装饰器、执行调用、可变绑定、危险静态类初始化拒绝；不是只检查某几个函数名 | `VF_IMPORT_SIDE_EFFECT` | `js.node.top-call`, `.mutable-module`, `.class-static`, `js.base.top-call`, `js.host.top-call`, `js.plugin.top-call` |
| 实际 completion，924–1052 | 实现 export 经 checker 定位：immediate 实际 async / Promise 返回；suspend 实际同步。Host 工厂须 immediate，start/stop 可以 suspend；Plugin 工厂必须同步，immediate hooks 不可 async/Promise | `VF_COMPLETION_IMMEDIATE_PROMISE`, `VF_COMPLETION_SUSPEND_NON_PROMISE`, `VF_PLUGIN_FACTORY` | `js.node.immediate-async`, `.suspend-sync`, `.suspend-async.normal`, `js.host.async-factory`, `js.plugin.immediate-async-hook` |
| Node 异步归属，1054–1174 | Node export 内丢弃 Promise 表达式/chain/void、listener/timer，兼用真实 Promise 类型和语法；嵌套函数边界停止。TaskPlan 从调用元数据生成，并非这里存在公开 TS 构造器 | `VF_PROMISE_UNOWNED`, `VF_NODE_LONG_LIVED_LISTENER` | `js.node.discarded-promise`, `.void-promise`, `.timer`；第二轮 `js.variant.completion.*` 和 `task.*` 验证真实完成协议、计划与旧分析边界 |
| Plugin 异步归属，924–1052 | Plugin 工厂中 listener/timer/on/once；表达式丢弃 then/catch/finally；checker 证明 void Promise | `VF_PLUGIN_LONG_LIVED_LISTENER`, `VF_PLUGIN_PROMISE_UNOWNED` | `js.plugin.listener`, `.timer`, `.discarded-promise`, `.void-promise`；其中 timer/chain 另有正式 build |
| RegExp 隐藏状态，1176–1227 | Node/BaseLib/Host/Plugin/source 模块持有 g/y RegExp 的状态使用 | `VF_MODULE_STATE` | `js.node.regexp-state` |
| 模块状态写入，1229–1540 | 上述 owner 的模块绑定、对象别名、原型/全局状态变异；依真实 symbol 和引用归属识别，不靠变量名猜测 | `VF_MODULE_STATE` | `js.node.module-write`, `js.plugin.module-write`, `js.host.module-write`；Plugin 另有 build |
| BaseLib 宿主和非确定性，1542–1659 | BaseLib 引用真实未遮蔽宿主全局、Node IO builtin、Date/performance/crypto/process、Math.random/computed Math 等；局部同名符号有 checker 排除 | `VF_BASE_LIB_HOST_IO` | `js.base.host-global`, `.nondeterministic`；shadow control 为 `js.node.console-shadow` |
| Plugin 宿主 IO，1661–1697 | Plugin 读取未遮蔽 globalThis/window/process/fetch/document 等；Host 正常宿主职责不在此禁止 | `VF_PLUGIN_HOST_IO` | `js.plugin.host-global` 及 `.build` / `.quality-cli`；正常 Host 为 `js.host.global.normal` |
| 无分类源码异步归属，1698–1765 | owner=source 的 listener/timer、Promise chain/void；不是所有普通文件无条件扫描 | `VF_SOURCE_LISTENER_UNOWNED`, `VF_PROMISE_UNOWNED` | 已盘点；当前矩阵未强行把未声明 helper 先绕过 ownership 拒绝 |
| 单 ESM 原生约束，110–187 | single-esm 中动态 worker/module resource/WASM 和运行期资源访问的产物能力约束 | `VF_BUILD_SINGLE_ESM_*` 等 | 本轮 build 确实使用 single-esm；未逐一新建所有资源负例 |
| TS 实际 ABI，2078 起及 Application 契约检查 | 实际 run 类型与 generated 输入/输出声明、schema 相容；esbuild 平台和 TS errors 仍是原生事实 | `VF_TYPESCRIPT` + 原 TS 诊断 | `js.node.abi-output`；正常 build-run 另证明业务执行 |

`js.node.undeclared-base` 的基线是 `VF_IMPORT_OWNER`：基线只给当前启用资源建 owner；current 从完整目录识别实际 BaseLib 后给 `VF_IMPORT_BASE_LIB`。同一非法导入的拒绝期望不变，这一有证据的诊断细化不是放宽规则。

## 数值、复杂度、重复代码

基线 driver 的质量 facts 在 1789–2076：真实源码行数/字节、TS 函数、参数、分支/嵌套、public API、AST 节点种类指纹，以及从实现 export 到 helper 的静态调用链。Node/BaseLib 适配器把这些事实和 descriptor params/contracts 交给中立判定算法，未改用 Python 源码分析。

| 实际判断 | 默认及配置边界 | 本轮案例 |
| --- | --- | --- |
| Node 长度/字节 | 默认 >500 行 / >60000 字节 error；>=450 行 / >=54000 字节 warning | `js.node.source-lines`；字节和 warning 等值边界已盘点、未在新矩阵逐一覆盖 |
| Node 函数/分支/嵌套/参数/合同键 | 仅配置了相应限值才比较实际值；不是无条件把所有复杂函数拒绝 | 本轮 facts `js.quality.metrics` 验证 function_count=1、params=2、branch_count=2；各数值限值由 Core/Python 对照矩阵另覆盖 |
| Node 实际 helper 链 | 默认链长 >4 error、>=4 warning；真正递归路径 error | `js.node.call-depth`, `.recursive-helper` |
| BaseLib 长度/字节/复杂度 | 默认 >500 行 / >60000 字节 error；可配置 functions/branches/nesting | `js.base.source-lines` |
| Node→BaseLib 模块依赖链 | 默认 >6 error、>4 warning；使用实际模块导入链事实，公开指标包括起始 Node | `js.base.dependency-chain.2` 合法且 sources=3；`.7` 要求 error 及实际链指标 8；未逐一新增所有等值/warning 边界 |
| 普通文件质量 | QUALITY.FILE 数值阈值、真实 parse diagnostics；资料缺失不能伪造空 AST | `js.quality.file-lines`, `.syntax`, `.metrics` |
| 重复逻辑 | 函数达到最小行数后，TS AST 节点种类指纹相同产生 warning；并非任意语义等价代码识别 | `js.quality.function-duplicate`，接受 CONCERNS 并要求 warning 诊断 |

current 的这些度量仍由 JavaScript Target 提供 TS facts，再由 Rule handler 调用中立算法。项目主题经 `vibeflow.quality.project` 默认组合，参数可覆盖；Node `vibeflow.maintainability` 输出 `vibeflow.node_metrics.v1`。数值默认不等于另一个不可覆盖权限系统。

## 独立 worker 基线及 current 调度

基线 `plugin_worker.mjs:206–250` 禁止有副作用的 module import、可变/执行性顶层状态；277–318 用 checker 检查宿主全局；320–375 还检查 listener/timer、非字面量动态 import/require、丢弃 chain、immediate 的 async/Promise 函数。`loadPlugin:378–477` 收集实际本地依赖闭包、调用这些判断及 TypeScript 检查后才绑定工厂。worker 的模块守卫比 audit 中的 module-write 算法更窄；本轮 worker 状态负例用 `let shared=0`，不声称旧 worker 能检查所有对象写入。

current `plugin_worker.mjs` 的绑定保留 esbuild/import、真实同步工厂对象和调用期 completion 协议，但旧独立源码审查已不在 `loadPlugin` 中。worker 正常绑定 PASS 不能证明旧源码约束保留。五个独立 worker 负例保留基线拒绝期望。

current driver 的原主题函数仍在，但 `toolchain_driver.mjs:2220–2249` 按请求 `ruleTopics` 调用。`build/rule_session.py:254–307` 映射为：

| Rule | 请求的真实 TS 主题 |
| --- | --- |
| `vibeflow.import_side_effects` | purity、imports、ownership |
| `vibeflow.node_interface` | completion（含 Node Promise 工作归属） |
| `vibeflow.no_side_effects` | module_state；根据明确 effect_scope 决定 host_io |
| `vibeflow.maintainability` | TS facts + 中立数值判断 |

默认 Node import/static 选集仍有这些主题；允许副作用来自实际所选规则参数，不再来自 flow_kind。current 加入 Process/none 的 console 检测，`js.node.console` 明确标为 new_feature；显式空 Ruleset 的自由度为 approved_change。不能据此把所有独立 Plugin/Host 检查消失标为已批准变化。

Application audit/build 的剩余全资源 driver 请求未提供 ruleTopics，默认 Node Rule 上下文也没有自动把独立 Plugin/Host 作为受审对象。于是“分析函数还存在”“sources/typecheck facts 还存在”和“正式入口实际执行旧拒绝”是三件不同的事。本轮以正常对照及实际诊断验证后者。

## 结果的判定和边界

`expected.codes` 要求具体 code+severity 子集；一个不相关的异常或 workflow 错误不能代替源码拒绝。已有正式源码位置的案例还要求真实文件和正行号。`should_accept`、真实数值输出和 TS metrics 分别判定；worker 原守卫或 TS 包装诊断没有伪造不存在的位置。基线夹具失败单独报告，不能算 current 回退。

本轮观察不覆盖任意 TS 语法、checker 所有推断、所有 single-esm 资源或每个 dependency graph 形状。表中未逐分支构造的谓词明确保留为盘点项，不把已有全门禁通过等同于这些分支全部完成新旧对照。最终结果以根 runner 的两 kernel 原始 observation / 比较 JSON 和对应临时工程源码为准；发现回退的 current 仍保留拒绝期望，避免把失败变成通过。

本轮 JavaScript 共有 78 个 observation：初始 69 例在基线全部符合；补充 9 例的实际基线拒绝/正常对照也已验证。当前观察到的 26 个缺失拒绝均集中在独立 Plugin/Host：audit 的源码/归属/completion、Plugin build、独立 worker，以及正式 quality-check 的两个代表主题。新增 external/resolve/package_root、BaseLib 依赖和真实相对模块链仍保持旧判断。这个数量是具体案例数量，不代表 26 种独立根因；同一未接入审查范围可影响多个正式入口和多个源码主题。

## 第二轮有限分支变体

新增模块 `sandbox/rule_parity/javascript/variants.py` 单列 114 例，保留原 78 例和原拒绝期望。两版 kernel 已实际执行新增整轮：基线 **114/114 符合**，current **111/114 符合**。新增三个红项是 `completion.plugin-promise-hook`、`completion.plugin-async-factory` 和 `declaration.examples-outputs`；前两项是独立 Plugin 缺失审查的更具体分支，后一项是旧 JS 正式接受的声明被新 parser 拒绝。前两轮合计 192 例、29 个不符合预期的 current observation；数量不能解释为 29 个独立根因。

下表的 case ID 均带完整前缀 `js.variant.`。代码中的小循环只是分别写明这些有限真实源文件，不是新的规则 DSL。

| 前次待覆盖分支 | 新 case ID | 实际观察和边界 |
| --- | --- | --- |
| checker 的 Promise 签名，不只看 async 关键字 | `completion.promise-signature`, `promise-suspend`, `helper-immediate`, `helper-discarded`, `helper-await`, `await-owned`, `new-promise` | immediate Promise 签名/调用被拒绝；suspend 的正常 await / 返回通过；丢弃工作仍拒绝 |
| Plugin 工厂与 hook 完成协议 | `completion.plugin-promise-hook`, `plugin-suspend-hook`, `plugin-async-factory`; Host 对照 `host-async-start` | 基线拒绝 Promise-returning immediate hook 及 async 工厂，current audit 接受；允许 suspend hook 时工厂仍同步，正常 Host async start 两版通过 |
| Node 输入 TS ABI | `completion.abi-input` | 正式 build 的实际参数类型与合同不符，两版均由原生 TS 契约拒绝；不要求本来没有正行号的包装诊断伪造位置 |
| 嵌套函数/别名的 completion 旧边界 | `completion.nested-uncalled`, `nested-escape`, `shadow-promise`, `shadow-on` | 两版一致：嵌套函数内部没有全面递归审查；Promise/on 同名纯局部仍会触发旧语法启发式。标 `baseline_limitation`，通过或拒绝不宣称分析器理解任意代码 |
| module-state 的多级 alias/嵌套 alias/delete/API 变异 | `state.alias`, `alias-chain`, `nested-alias`, `delete`, `object-assign`, `define-property`, `reflect-set`, `reflect-delete` | 模块顶层声明先用不可变 frozen 初始化保持合法，实际 mutation 主题可到达；两版均有 `VF_MODULE_STATE` 与源码行号 |
| 共享 builtin 原型/对象、赋值后 alias、computed member | `state.prototype`, `prototype-alias`, `prototype-assigned-alias`, `builtin-object`, `builtin-alias`, `builtin-computed`; 正常 `local-object.normal`, `local-array.normal` | 真共享对象/原型变异拒绝；真正局部对象可变与 Array 名称遮蔽通过 |
| RegExp sticky/global 与局部、无状态对照 | `state.regexp-y`, `regexp-gy`, `regexp-local.normal`, `regexp-stateless.normal` | 模块 y/gy 拒绝，局部 gy 与模块普通 i 两版通过；原 g 已由第一轮覆盖 |
| globalThis 全局对象写入旧缺口 | `state.global-this-write` | Host 的 globalThis 不在旧 builtinObjects 集合；两版均接受，明确记为旧分析边界，不能把这种接受解释为一份已授予的任意状态权限 |
| BaseLib 各宿主/非确定性子分支 | `base.host-date`, `host-performance`, `host-crypto`, `host-process`, `host-document`, `host-fetch`, `host-math-computed`, `host-math-escape`; `builtin-fs`, `builtin-http`, `builtin-worker_threads` | 原生 TS 符号/导入事实触发宿主拒绝；两版全部保持 |
| 宿主原语的真正局部 shadow / 纯运算 | `base.shadow-date`, `shadow-fetch`, `shadow-math`, `shadow-pure-math`; `plugin.shadow-global.normal` | 两版全部通过，与前述拒绝成正负对照，不靠文字名称判断权限 |
| Node/BaseLib→已选 Plugin，及正常声明的同类依赖 | `imports.node-plugin`, `base_lib-plugin`, `base-declared.normal`, `plugin-declared.normal`, `host-declared.normal` | Node/BaseLib 跨层实际 Plugin 拒绝；真实 BaseLib/Plugin/Host 依赖声明后正常通过。第一轮已保留各未声明关系的拒绝期望 |
| runtime/registry/capability owner 分支的正式可达性 | `imports.runtime-unowned`, `registry-unowned`, `capability-unowned` | 基线 `project_resources.py:671–709` 只生成 node/base_lib/host_extension/plugin。独立目录名不创造新 owner；正式 Node 导入这些文件准确给 `VF_IMPORT_OWNER`，不伪造归属宣称 `VF_IMPORT_LAYER` 的三个字面分支被正式执行 |
| single-esm worker/serviceWorker/worklet/module URL/WASM/本地资源 | `native.worker`, `shared-worker`, `service-worker`, `worklet`, `module-url`, `fetch-local`, `import-scripts`, `wasm`; 正常 `absolute-url.normal`, `fetch-absolute.normal` | 用 Host 的合法职责让原生检查可达，避免 Node 可选 host-I/O 审查先拦截；八项拒绝、两个非本地 URL 构建对照全部保持。只构建，不实际发网络请求 |
| 真实 Node 行/字节 warning 及 max 等值边界 | `numeric.lines-449`, `lines-450`, `lines-500`, `lines-501`; `bytes-53999`, `bytes-54000`, `bytes-60000`, `bytes-60001` | 来源是实际 TS 文件长度，warning/error/severity 与两版正式审查一致；不伪造长度事实 |
| 真实可配置复杂度及等值正负对照 | `numeric.max_functions-1/2`, `max_branches-1/2`, `max_nesting_depth-1/2`, `max_contract_keys-1/2`, `max_params-1/2`; `base-max_functions-1/2`, `base-max_branches-1/2`, `base-max_nesting_depth-1/2` | 基线用合法数字 policy；current 用所选 Ruleset 的 `native/maintainability` 局部 `params.policy` override。相同实际 TS facts 和合同数值，所有低限值拒绝、等值通过；配置机制迁移没有被误报为规则能力回退 |
| BaseLib 真实长度/字节 max 等值 | `numeric.base-lines-500/501`, `base-bytes-60000/60001` | 等值合法，超过才 error；两版保持 |
| Node→BaseLib 链 warning 等值及 max 等值 | `numeric.dependency-4/5/6` | 指标包含起始 Node；4 无 warning，5/6 warning，6 并非 max error；第一轮 `.dependency-chain.7` 的真实指标 8 给 error |
| 合法/非法 TaskPlan、业务消费和 cleanup | `task.result_key.normal`, `detached.normal`, `result_key.sync`, `detached.sync`, `result-missing-contract` | TaskPlan 来自 JSONC 的 async/result_key/detached 声明。合法 result_key 设真实 consumer；detached 设真实无输出 side call，业务正常产物都返回 4。同步 metadata 两版可生成；不存在“看见 async 标记一律非法”的旧要求。不存在的 result_key 由原生合同事实拒绝 |
| helper 内工作逃逸的旧边界 | `task.helper-timer-escape`, `helper-promise-escape` | 真实 Node 调用 void helper，但旧 completion visitor 不沿调用图审核其内部工作，两版 audit 都接受。明确标旧边界，不能声称此处自动得到 TaskPlan 归属 |
| owner=source 隐藏工作分支 | `source-owner.app-timer`, `app-promise`, `app-normal` | 真正 web-app 构建及 post-esbuild closure：两版正常构建。`ownerFor` 在基线 driver:333–349 仅查直接/派生归属，正式生成器没有 source owner，故 `auditUnclassifiedHiddenWork:1698` 的 source 分支不能从这些 Application 输入到达。没有新造 hook 或假 owner 来填覆盖数字 |
| JS 实际声明样例 | `declaration.examples-inputs.normal`, `examples-outputs` | 完整 inputs/params 对照两版 audit 正常；包含 outputs 的完整旧 JS 样例 audit 通过，current `core/descriptors/models.py:271–272` 在 parser 层直接 `DESCRIPTOR.INVALID`。Python 原来已有自己的 outputs 拒绝规则，不能据此扩大成 Python 新回退 |

current Node 可维护性 handler 明确消费 `params.policy`（`targets/javascript/build/rule_session.py:299`）。第二轮夹具因此按已批准的一次迁移改用真实 Rule 参数，旧文件没被读取不能单独证明“参数功能回退”。反之，同一旧源码主题在适配合法的 ABI / 资源形式后仍被正式接受，或者旧合法 JS 合同被新 parser 拒绝，才保留对应红项。

以上把前轮列出的有限剩余主题分别落为案例或不可达证据，并不承诺任意 PromiseLike 结构、全部 TypeScript AST、任意程序效果或全部平台能力都被理解。单 ESM 原生可执行约束和 TS 契约事实仍与可选审查分开；业务 Node 执行依然使用原生计划，未为测试增加新的资格门禁或权限体系。
