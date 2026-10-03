# 第二轮：基线规则与新接口的沙箱缺口审计

2026年10月03日。基线 `f169429a8d41`，当前生产代码 `15adf51d0676`。本轮复查实际调用链、版本差异、已有测试的入口和断言，并在临时项目中做有限探针；产出是审计记录，生产实现和既有测试期待未调整。

结论：仍有缺口。上一轮的 1,219 个场景覆盖了大量旧规则的判断分支，但不能替代新规则选择边界、资料运输、实际组合和正式入口一致性的验收。下列发现不计入上一轮的 51 个不匹配场景；多个反例也不等于多个独立根因。

后续补测已经落入 [持久沙箱](../../sandbox/rule_gaps/README.md)，本报告保留发现问题时的探针事实。新增验收及实际结果见 [补测结果](../../sandbox/rule_gaps/RESULTS.md)；文中“缺少沙箱”描述的是审计当时的状态，具体补齐情况按下方对应表及结果页判断，生产问题不会因增加测试而自动修复。

## 本轮如何判断覆盖

- 同时检查 [旧能力清单](baseline-rule-inventory.md)、[两版本结果](../../sandbox/rule_parity/RESULTS.md) 和普通功能沙箱。复制沙箱到临时目录、调用真实 CLI/worker/build/run 的 pytest，同样属于正式沙箱证据。
- 有人工 facts 的内核测试，只证明图或算法在该输入上的行为；不能证明 Target 能提供同样的真实资料。
- 负例须有同入口的合法对照，断言目标诊断、状态、退出码、consumer/业务是否执行和实际文件标记，防止其他错误提前挡住目标分支。
- 源码解析、符号绑定和原生计划是执行事实；不能用审查覆盖制造这些事实。旧 policy 移除、隐式 effect 授权移除等已批准变化，不要求恢复旧通道。
- 保持已有命令范围，不将孤立源码扫描、包自动发现、热加载或其他语言加入本次验收。

## 已确认的新接口问题

### 1. Python 的 Node 导入规则会误查其他独立 Node

正式 `run` 项目使用三个不同实现文件 `start.py/node.py/end.py`，没有任何导入关系，公开源码快照的 `imports=[]`，符号归属分别对应各 Node。

| 唯一规则选择差异 | 实际结果 |
| --- | --- |
| 三个 Node 都选择 `[]` | `CONCERNS`、exit 0；start/demo/end 都完成；demo 产出整数；`node.py` 顶层 marker 写入 |
| 仅 start 选择 `vibeflow.process`；demo/end 保持 `[]` | `FAIL`、exit 1；marker 未写入；报告 `node.py:1` 的 `NODE.IMPORT.SIDE_EFFECT`，对象和调用却归为 start |

`targets/python/quality/rules/import_side_effects.py:12` 遍历整份 `sources.files`；`quality/rule_adapter.py:142–158` 将同一工作流快照交给每个 Node，并按当前 Node 关联诊断。默认规则因而越过了该 Node 的实际导入闭包。公共上下文可以保留完整资料，但内置 Node 规则需要正确选择自己的被检查对象。

现有明确空选择和导入 marker 测试没有把“独立文件的宽松 Node”和“启用默认导入规则的邻居”放在一起。最小补测是上述两个项目，再加真正共享模块/实际导入 helper 的正常归属对照；不能简单禁止规则读取完整上下文。

这是新增规则选择语义的缺陷。旧版没有 `[]` 选择能力，两个旧夹具都被旧 registry 导入预检拒绝，不能直接算作旧规则漏报。

### 2. JS typed records 被 worker 静默改写

真实 TS provider → requires consumer → 正式 `validate` 的观察：

| provider 的 value | consumer 实际取得 | 状态 / exit |
| --- | --- | --- |
| `[3]` | `[3]` | PASS / 0 |
| `null` | `null` | PASS / 0 |
| `Map` | `{}` | PASS / 0 |
| `Date` | `{}` | PASS / 0 |
| `undefined` | `null` | PASS / 0 |
| `NaN` / `bigint` / 循环对象 | consumer 未执行 | ERROR / 1 |

`targets/javascript/resources/plugin_worker.mjs:26–36` 将 undefined 改为 null，并用 `Object.entries` 转换任意对象。公开文档要求可移植 JSON，Rule ABI 的 `JsonValue` 不包含这些对象。该路径已具有部分拒绝能力，问题是某些不合法资料被伪装成合法成功资料。

`tests/core/test_rule_graph.py:353–371` 的纯内存 opaque/NaN 负例无法触达 worker；`tests/integration/test_rule_plugin_graph.py:81–105` 检查缺失端口、错误 type_id 和失败状态，没有覆盖这些值。补测应保留上表所有正反对照，并核对 provider 状态、诊断资源来源、consumer 未执行，而不只看 CLI 非零。

旧 worker 有类似对象转换，但旧版没有 typed Rule records。这属于新增接口缺陷，不计作旧审查回退，也不表示 Rule 代码被操作系统隔离。

### 3. JS 公共 Source API 漏掉真实动态导入边

真实项目使用 `await import("./helper.js")`。正式检查取得的 `facts.sources` 已包含 `helper.ts`，但外部 Rule 调用得到：

- `sources.imports(nodeFile)=[]`；
- `sources.reachable(nodeFile)` 只含 Node 自身；
- `sources.ownership(helperFile).node_types=[]`。

正式 validate 为 PASS。问题是检查范围内的资料查询不一致，而非 helper 没有被扫描。原有及当前 `toolchain_driver.mjs:345–366` 都识别字面量 dynamic import/require；新 worker 的 `plugin_worker.mjs:95–126` 只查顶层 `moduleSpecifier`，其 reachability 和 usage ownership 随之漏边。

现有真实 `test_rule_source_api.py` 使用静态相对 import。应加入同一 helper 的静态 import 与字面量 dynamic import 对照，核对 facts、精确导入位置、reachable 和 usage ownership 一致；声明归属和引用归属仍需分开。未验证的动态路径表达式不因此承诺可静态解析。

### 4. review-rules 错误合并不同语言 Target 的资源

将现有 Python/JS `domain_rules` 放入一个合法混合 workspace，两个 Target 各自注册同名领域资源。Python validate 为 CONCERNS/exit 0，JS validate 为 PASS/exit 0；两者 review-rules 都返回 ERROR/exit 1：`conflicting Rule declaration 'example.model_definition'`。

`tooling/application/rule_review.py:34–50` 无 Target 区分地合并所有 root。实际 Python 声明装配只合并 Python roots；JS audit 使用其所属项目的 catalog。保留完整 workspace 用于路径解析，不等于把所有 Target 的 catalog 合并为同一个命名空间。

现有 mixed workspace 测试覆盖命令分派和 quality 隔离，但 review-rules 正常例是单 Target。最小补测应同时包含：合法混合 Target 同名资源、Python 同 Target 兄弟 root 的合法引用，以及同一实际作用域的真实冲突；比较预览和正式检查的有效选择，不能只检查图文件存在。

### 5. 新声明的错误类型没有一致进入正式资源诊断

两个 Target 的正式项目探针均证明：

- `category.presentation.shape={}` 使 `review-rules --json` 抛 TypeError，输出不是 JSON；合法 shape 对照通过。普通 validate 仍非零，但错误运输不完整。
- Rule 的 `outputs={"evidence":42}` 被转换为字符串类型 ID，review-rules 通过；真实 handler 后续失败。声明 schema 明确要求端口 type_id 是字符串，应该在资源读取时报告错误。
- `shape=[]` 和 `params_schema` 中的 list 则已有正常拒绝行为；不能将所有错误资源笼统记成未验证。

原因分别是 `core/descriptors/categories.py:25` 对冻结后的字典做集合成员判断，以及 `core/rules/models.py:92–120` 对端口类型使用 `str()`。现有展示测试侧重合法级联，新资源测试没有覆盖这两个错误类型。

最小补测应通过 bundle 和正式 CLI 加载非法 Node/category presentation 及 Rule 端口类型，断言稳定资源诊断、声明位置、单个 JSON 输出和退出码；另有合法字符串/形状对照，且业务实现尚未导入。

### 6. 实现替换后的默认参数来源记录错误

内核探针把 original（limit 默认 10）替换为 replacement（limit 默认 20，另有 mode 默认值）。有效 params 为 replacement 的 20/new，但 `parameter_sources.limit` 仍是 `default:original`，mode 没有来源。

`core/rules/graph.py:225–240` 在选中 replacement 前生成原规则的来源表，随后使用替代规则 defaults 合并真实值。参数执行值正确，报告与规则图的解释错误。现有两个 Target 的 replacement fixture 恰好使用相同默认值，未揭示此差异。

应使用默认值不同且新增一个参数的替代规则，经正式 validate/review-rules 验证：参数值、原调用实例身份、替代实现和每个默认/显式/覆盖参数的来源一致。这是新增图报告缺陷，不是旧数值限制消失。

### 7. 已公开的 implementation 规则尚不能直接用于真实 Node Ruleset

`builtin_rule_resources()` 明确公开 `vibeflow.implementation.node/base_lib/dependency_chain`。实际 Python 项目将 node leaf 直接选入 Ruleset 后，validate 因缺 `metrics` 返回 FAIL/exit 1；JS handler 集合未接入这些 leaf。内存调用 `evaluate_implementation_rule(..., metrics=..., limits=...)` 则可以运行。

位置：`core/rules/builtin/implementation.py:18–40`、`targets/python/quality/rule_adapter.py` 的事实装配、`targets/javascript/build/rule_session.py` 的 builtin handlers。现有 Core parity 给了人工 metrics，真实 Target 用的是较大主题 maintainability，所以两类测试都不会暴露直接组合边界。

应补“公开 leaf 通过声明直接选中”的合法/超限正式项目，验证两个 Target 提供真正的指标，或明确界定这些 leaf 的公开使用范围及所需事实契约。这里证明的是公开组合和 Target 接入缺口，不能推断默认 maintainability 全部失效。

### 8. JS 平台专属 Rule 的正式入口结果不一致

一个 JS root 中，同一 Rule 提供互不重叠的 node/browser 实现：两个正式 build 都 PASS，未选平台的 validate 却 ERROR，提示 `requires exactly one compatible JavaScript/TypeScript implementation`。

`targets/javascript/build/rule_session.py:348–350` 在 neutral target `javascript` 下同时选入两个实现，再要求数量为一。现有 Rule 测试用一个实现同时支持两平台，不覆盖这类声明。

需要一个双实现正常例，明确 target-neutral 审查对平台专属 Rule 的调用语义并检查 validate/quality/review 与两种 build。当前资料只证明入口不一致；具体是对两平台分别检查，还是要求提供 neutral 审查实现，需要形成清晰的公开契约。它不是旧源码规则回退，也不同于第 4 项跨语言 root 合并问题。

## 旧新共有的局限

Python planned stub 的主文件 `work.py` 导入 `helper.py`，helper 顶层写 marker。原生 planned 声明字段校准后，两版真实 `run --allow-planned-stub` 均为 CONCERNS/exit 0，三步完成并产出整数，helper marker 已写。

两版 `targets/python/project/planned_files.py:51–65` 只读取主 stub 文件，`runtime/support/planned.py:47–52` 随后真实执行模块。现有 `strict_planned_behavior.py:117/255/274` 的安全负例都在主文件，integration 的正例也如此，未检查真实 helper 导入闭包。

这不是迁移新增回退。应补安全 helper 正常例与 helper 顶层执行反例，记录实际导入边界；再依据 planned stub 既有契约处理，而不能把 Node 的显式规则选择替换成全项目强制预检。

## 明确缺少沙箱证据，但尚未证明功能错误

| 场景 | 已有覆盖及不足 | 最小新增验收 |
| --- | --- | --- |
| 领域 bundle Node 的原生组合 | 领域项目实际运行只有串行 `3×2+1=7`；原生 integration 有分支/Nodeset/Loop；源码快照和规则预览也有重复 Nodeset，但未叠加领域资源做真实数值执行 | 同一 bundle 模型 Node 分别进入择一分支、一次 Nodeset 调用、一次 Loop body；检查真实结果、调用路径、规则归属与分类展示 |
| bundle 的其他原生资源组 | 支持 base_lib/data_schemas/capabilities/host_extensions/plugins；现有 bundle 沙箱仅测 categories/nodes/rules/rulesets；JS integration 其他资源直接用 descriptors 登记 | 将已有正常 Host+Capability+Runtime Plugin 项目改由 bundle 接入后真实 build/run，保留一个悬空引用或冲突反例 |
| source consumer 的缓存边界 | Core 内存测试、JS 真实同源码两调用及 Python 真实源码快照已经覆盖去重和关联；缺真实 Target 中 typed inputs/参数变化的 requires consumer 组合 | 同源码不同 inputs/有效 params 必须分别执行；同值可复用；新检查 session 必须重新执行，核对 records 与全部调用关联 |
| 显式 includes 和部分图错误运输 | 嵌套成员的隐式 includes、依赖/覆盖及三类循环已有正式沙箱；显式 includes 的正向筛选主要是 Core 内存测试；部分输入冲突、未绑定和参数 schema 错误没有持久 CLI 图案例 | 显式只 include 好规则时坏规则/marker 不执行，加入坏规则后按目标原因失败；分别制造 INPUT.CONFLICT、INPUT.UNBOUND、PARAMS.SCHEMA，并保持其他图条件合法 |
| 非法 finding 的契约和汇聚 | 非 Finding 的 123 在内核正确形成 RULE.EXECUTION；内核接受非法 severity `fatal`/None 后却给 PASS/completed；Python 聚合会把未知值放入 error 桶 | 真实 Python/TS handler 的合法 error/warning/info 与非法 severity/对象对照，比较内核状态、正式诊断、退出码和依赖消费；目前不声称两个正式 Target 都漏报 |

真实 builder、emitter、native parser 和执行器已有 profile、Capability 取消/隔离、Host 生命周期、Plugin+Host 协同和浏览器测试。本轮没有证据将这些既有原生能力称为新回退，也没有必要仅因为它们未加入 parity 就复制所有测试。

## 建议的补测顺序

1. 先加入 Node 规则作用范围、records 真实性和 Source API 导入关系的正式正反例；它们影响审查对象和可用资料。
2. 再加入公开 leaf、混合 Target/平台入口、非法声明和替换来源；它们影响资源是否可组合，以及报告能否解释真实执行。
3. 最后补领域 Node 的有限原生组合、bundle 其他资源组、缓存边界及 planned helper 的既有局限。

补测保持真实失败，不降低上一轮 51 项的期待，不用无关前置错误或 xfail 隐藏问题。无需扩展命令范围，也无需新增第二套诊断、启用或权限体系。

## 本轮证据和验证边界

- Root Tooling 探针：`/tmp/vibeflow-second-tooling-probe.py` 与对应目录的 `observations.json`；两 Target 合法对照和非法资源均走正式 CLI，JS 使用既有锁定工具链。
- mixed Target 探针：`/tmp/vibeflow-second-mixed-probe.py` 与对应目录 `observations.json`。
- Python 两版本：`/tmp/test_python_second_audit.py`、`/tmp/vibeflow-second-audit-python-v3-{baseline,current}.json`、`/tmp/vibeflow-second-audit-python-v3.log`；隔离执行 2 passed，指的是观察断言通过，包含当前误拒与旧新局限。
- JS worker/Source API：`/tmp/vibeflow-js-new-api-audit-lw7o2u5e/observations.json` 和 `/tmp/vibeflow-js-new-api-audit-x_u90va3/observations.json`；平台项目为 `/tmp/vibeflow-js-source-platform-audit-1n1gyysj/observations.json`。
- 公开 leaf 的真实 Python CLI：`/tmp/vibeflow-core-builtin-leaf-audit.json`；参数来源和非法 severity 为纯内核探针，正式补测仍缺。
- 本轮复跑现有 `test_rule_review.py`、`test_rule_resources.py`、`test_presentation_cascade.py`、`test_rule_parity_reporting.py`：39 passed。这证明现有断言通过，也实证它们未覆盖上述新增反例。

本轮未重跑 1,219 全组、完整发行门禁或修改生产代码；上一轮 51 项仍以原报告为准。临时探针不是已经纳入仓库的持久回归测试，表中的新增案例需要后续落入正式沙箱。

## 持久补测对应

| 本报告发现 | 已新增的组与场景 |
| --- | --- |
| Python Node 导入规则越界 | `python` 独立空选择/选中邻居/选中自身；真实共享与非共享 helper、选择与归属对照 |
| JS records 静默改写 | `javascript` 合法数组/对象/空值/async 与 Map、Date、undefined、非有限数、bigint、循环值；真实 provider 状态与 consumer 可用性 |
| JS 导入资料不一致 | `javascript` 静态、dynamic、require 的真实 snapshot、导入边、精确行号、可达性和声明/使用归属；不存在源码的正式错误 |
| 不同 Target 资源错误合并 | `tooling` 两语言同 ID、同 Target 兄弟 root 合法引用与真实资源冲突；validate 与 review-rules 的有效选择 |
| 非法声明类型 | `tooling` 两语言 category/Node shape 与 Rule 输入/输出的正常类型、对象/列表/数字；正式 JSON、来源、退出码、handler 尚未执行 |
| 替换参数来源 | `graph` 不同默认值和新参数、显式覆盖、正式实际值/计划与 review-rules 来源；预览不调用 handler |
| 公开 implementation leaf 接入 | `graph` 两 Target 的 Node、BaseLib、dependency_chain 正常和超限实际源码；已接入 maintainability 的同源码对照 |
| JS 平台入口不一致 | `javascript` shared 与 node/browser 分离实现；validate、quality、review 和两个平台 build 的正式对照与实际业务 |
| planned helper 的旧新局限 | `python` 主文件/实际导入 helper 的正常与初始化执行反例，真实 run 和文件 marker |
| 领域 Node 原生组合 | `composition` 领域 bundle 的分支、Nodeset 和一次 Loop 数值执行；领域反例的完整调用路径；Architecture/Mermaid/真实 SVG |
| bundle 其他资源组 | `javascript` 五个原生资源组只经 bundle 装配；真实 build/run、Host/Capability/Plugin 生命周期、悬空引用及冲突 |
| 源码 consumer 缓存 | `graph` 同值/不同 typed inputs/不同有效参数、新 session；实际次数、proof 值和正式 findings 的 first/second 双调用关联 |
| 显式 includes 与图错误 | `graph` 好/坏 handler 的显式选择和实际 marker；INPUT.CONFLICT、INPUT.UNBOUND、PARAMS.SCHEMA 的资源诊断与无 handler 执行 |
| finding 契约及汇聚 | `graph` Core raw/typed 与真实 Python/TS 的 error/warning/info、fatal/None、数字/字符串；规则定义 ID、位置、状态和 requires 消费 |

以上补测保持失败可见，不扩展命令范围、不修生产实现，也不要求恢复已经批准移除的旧 policy 或隐式权限机制。完整交付门禁与基线对照不由新增沙箱的报告机制测试替代。
