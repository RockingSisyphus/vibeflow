# 迁移残余整改与契约统一

本轮依据[全范围审计](system-migration-wide-audit-20261008.md)实施 M01–M11，并按用户选择退役 Python `required=None` 的整组输入免检行为。旧审计、复现证据与历史基线夹具保持原样；本记录描述整改后的行为。

## 信息权威与执行边界

资源身份来自 canonical Descriptor，源码判断来自实际导入、符号、调用与归属；Rule 行为来自有效参数，输入执行合同来自 Core 模型。Python 原生 ExecutionPlan、portable WorkflowPlan 与语言 BindingPlan 各自保留职责。仍有生产消费者的薄 facade、公开别名、默认 Rule 组合粒度保持不变。

## 修改与结果

| 项目 | 修改及行为 | 保留边界 |
| --- | --- | --- |
| M01 | BaseLib 删除独立 AST scanner，复用共享效果 visitor；具名导入、终端引用、状态、别名、分支与初始化表达式进入同一效果遍历 | BaseLib 自身结构、接口、显式支撑文件及所选规则仍独立检查 |
| M02 | Plugin 消费当前闭包的 resolved calls，并继续检查 helper 函数体；纯 write/read/close 不因名字失败，真实 I/O 改名仍可检出 | 无法解析的调用保留语言分析器的保守分类 |
| M03 | JS 有效 params 经 ruleParams 进入 driver；两种 Target 按实际 handler 补默认和验证参数；效果类别、导入政策与资源依赖分别判定 | scope 名称保留；JS 既有时间/随机数检查保留，未新增 Python 对应禁令 |
| M04 | 删除不可达 NODE.COUPLING 映射 | 保留实际生效的 NODE.METADATA 诊断码 |
| M05 | 删除 `_inputs_to_initial`、`_copy_input_item` 及专用导出 | 活跃 Nodeset/Loop 转换保留 |
| M06 | 删除 `_resolve_paths`、`_module_search_path` 及专用依赖和导出 | 活跃资源装配、模块和 `_finding` 保留 |
| M07 | 删除旧 Architecture/SVG 成对发布事务；测试通过正式 review 观察渲染及发布失败 | Architecture 先更新，SVG 失败保留旧 SVG |
| M08 | 删除旧单浏览器 helper；测试现行 bundled 优先、候选顺序、去重，并通过正式 renderer 的故障注入验证回退；真实浏览器行为由全量渲染验收确认 | 活跃 Puppeteer renderer 及可用性 API 保留 |
| M09 | 删除无消费者 ownership topic 和 owner.effectScope | 实际 ownership、依赖及 completion 检查保留 |
| M10 | 迁移共享测试 helper 的活动调用者；删除原审计两处及扩大回归发现的最后一处 CLI parser wrapper、字段删除及静默转换 | implemented 契约来自 Descriptor；planned/system 继续显式声明；刻意负例保留 |
| M11 | 删除全文版本号黑名单；中英文明确当前开发版本声明读取 pyproject.toml，历史叙述允许共存；正式发行验收将生成包 README 版本与自身 DISTRIBUTION 元数据比较 | quality 保持标准库独立实现，不扫描历史 dist；本轮新生成发行说明按自身 DISTRIBUTION 元数据验收 |
| 输入合同 | Core/portable required 必填 bool；parser/schema/序列化统一；两 Target 先拒未知键再查必填，空声明只接受 {} | null 值仍算键存在；optional 可缺失；outer requires/provides 继续用 cardinality |

效果权限不来自 owner、资源角色或目录名。terminal 只放行终端效果，python_io 放行一般 I/O，global_state 放行资源或模块状态但不能修改 builtin、原型及宿主关键状态，trusted 不增加权限。显式导入禁止不被 scope 覆盖，允许导入不解除效果或资源依赖限制。完整有效参数进入检查缓存及 effect_policy 记录。

effects/imports 在 policy 中仅消费 imports 四字段，指标规则只消费相应指标。Python effects 自身默认只保留 importlib 根禁止及已有模块允许；imports-only 默认四数组为空。显式空数组生效，未知或不相关参数失败。沙箱 kernel_policy 的旧一般 I/O 禁用表已移除，math 的项目显式允许保留。对象参数整体替换及来源记录不变。

活动 Config、Nodeset、Loop、SDK、沙箱、发行最小项目与文档示例已补显式 required，并把 implemented Node 契约放回 Descriptor。低层 supplied 输入仍开放，但其 key/type/required/顺序必须与 canonical 声明一致。Loop 不通过丢弃未知输入修补错误。

## 验收记录

定向阶段发现的问题均集中修复并复测：输入合同/portable/conformance/JS 构造 197 passed、1 skipped；Python 扩展效果与参数 232 passed；JS 正式 SDK 与会话参数 100 passed、1 skipped；JS 原生效果与状态 76 passed；M10/正式文档拓扑/最小项目 72 passed、2 skipped。各组有重叠，不相加。定向渲染 skip 留待配置浏览器的全量验证。

原审计 13 项 Python 正式 CLI 对照已重放：10 项真实效果均被拒绝，3 项纯 helper 通过；来源与诊断码记录在本次本地验收证据中。定向检查不能替代工作流与生成包验收。

首批完整 17 阶段均运行结束，pytest 为 2313 passed、8 failed；失败包括遗漏的 CLI 输入 authoring、驱动资源 hash 更新、宿主静态状态槽范围、参数跨资源套用，以及 Chromium 临时 socket 路径过长。Python Loop 两例失败来自输入工厂多传了未声明且未使用的 train.batches，已改为该工作流真实声明的三项输入，未过滤运行时未知键。compiler 写标记文件的活动 fixture 改为自身显式选择 python_io，编译角色不自动授予权限。其余 browser 几何/样式失败保留为实际浏览器复测事项，未用静态 SVG 代替。首批 wheel 与两个发行 profile 的隔离构建通过。

最终复核另补宿主关键状态的完整名称匹配、分支别名合并、局部替换、Node 类初始化及可静态解析的 literal 反射引用。共享 visitor 复用同一效果分类；不推断任意反射、跨别名路径关联或完整循环抽象语义。

第二批完整 17 阶段全部运行结束，15 阶段通过；pytest 为 2477 passed、8 failed，规则对照为 1218/1219 matched，规则缺口为 678/680 matched。Python 失败来自新增的局部 receiver 提前免检：词法局部事实只足以排除同名宿主模块误认，不能证明文件、连接、argparse 调用纯；修复恢复已有函数体、ExitStack 清理证明与保守效果分类。JS 两项失败来自公开纯声明入口 defineResource 未识别，以及 compiler 实现与 Node/Host 注册混在同一导入模块；分别补声明识别和拆分实现文件，保留参数构造检查及完整 import layer。真实 display/编辑 150 项、浏览器运行观察、布局、两 Target 资源展示、性能与适配 207 项全部通过；wheel 和两个发行 profile 隔离构建通过。

第二批失败集中修复后，Python 五文件定向批次 465 passed，保留原 8 条失败断言并补局部对象、宿主遮蔽及 argv 回归；JS 效果参数 71 passed，compiler 正式运行四项 4/4 matched，检查代码未进入 Node/browser 产物，活动 driver hash 单测通过。源码再次冻结后开始最终完整批次。独立 quality 测试为 49 passed。

最终使用 `tools/run_tests.py`、独立 `python -B quality/test.py` 与 `python -B tools/verify_project.py --full`。完整批次记录所有阶段失败，修复后先跑对应项再重跑最终全量。[第三批完整验收](system-migration-remediation-20261008/full-03-verification.json) **17/17 阶段通过**，pytest **2561 passed**；Python 工作流 **138/138**、JS 集成 **67/67**，[规则对照](system-migration-remediation-20261008/rule-parity-summary03.json) **1219/1219**、[规则缺口](system-migration-remediation-20261008/rule-gaps-summary03.json) **680/680**、[适配回归](system-migration-remediation-20261008/adaptation-summary03.json) **207/207**。真实浏览器运行观察、布局、资源展示、性能、隔离 wheel 与两个发行 profile 构建均通过。

生成包在仓库外隔离构建，再分别从 wheel、协作 profile 的唯一 kernel ZIP、自主 profile 的唯一 kernel ZIP 执行独立探针：

| 每个产品 | 案例及结果 | 来源证明 |
| --- | --- | --- |
| [输入合同](system-migration-remediation-20261008/packaged-inputs-summary03.json) | 8 项解析负例及 12 项 native/真实 JS 运行案例全部通过；拒绝时业务 Node 执行数与 native trace 步数为 0 | 136 个产品模块全部来自所选包 |
| [Python 效果](system-migration-remediation-20261008/packaged-python-effects-package-verification03.json) | 873/873；同 Rule/scope 对照普通源码、Node、BaseLib、Plugin，含真实 helper、初始化、别名、终端、状态、未知 receiver、Path、ExitStack 重绑定与 argv | 114 个产品模块全部来自所选包，wheel 安装元数据及 ZIP SHA 均核对 |
| [JS 参数与效果](system-migration-remediation-20261008/packaged-js-summary03.json) | 33/33 SDK→Ruleset/override→RulePlan→driver 场景，另 A→B→A→C→B 判断全部匹配；回返 A/B 命中缓存、无新 native 请求 | 118 个产品模块全部来自所选包；driver hash 与最终源码一致 |

包级 JS 探针的首轮额外缓存断言误用了已去重的顶层 findings；既有 Core 合同保留诊断于 RuleResult，并保持 FAIL 状态。探针改为观察实际 RuleResult、alias、effect_policy 与请求增量后，在相同冻结产品上重放通过；首轮失败证据保留，未为探针修改 Core。三包的详细逐案 JSON 与 stdout 保存在本轮本地 `dist/unification-validation-20261008/`；可长期核对的汇总、[构建哈希](system-migration-remediation-20261008/final-artifacts03.json)及[历史夹具对照](system-migration-remediation-20261008/frozen-fixture-check.json)保存在本记录的同名证据目录。历史基线 446 个文件逐一比较，无变化。

本轮不正式发布，不覆盖默认发行目录，不推送。旧 0.15.2 发行资产继续保留其历史语义；本次构建只验证当前开发树。

独立复核随后发现共享函数默认参数作用域缺陷 F01，原第三批及包级矩阵没有覆盖该反例。旧结果保留为当时的验收观察；修正及重新验收见[函数定义作用域跟进记录](python-function-definition-scope-fix-20261008.md)。

后续独立复核发现推导式 target 泄漏至 lambda 的 F02，以及相关纯 close helper 误报。修正同步共享效果遍历、源码引用与真实业务输入传播，并补齐 nonlocal/global 声明归属；最终 17/17、pytest 3589、三个新产品行为案例 4023/4023 通过。原审计与前轮观察保持原样；修改、保留边界及新产物证明见[推导式作用域跟进记录](python-comprehension-scope-fix-20261008.md)。
