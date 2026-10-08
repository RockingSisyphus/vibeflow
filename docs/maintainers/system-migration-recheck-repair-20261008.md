# 系统迁移独立复核补充修复

本次继续已授权的统一资源接入与旧架构退役，依据[独立复核 S01–S04](system-migration-recheck-20261008.md)，在现有未提交工作上推进。原审计、独立复核及之前各轮验收记录保留。

状态：S01–S04 已修复，本次最终完整验收 17/17 通过，源码及新 wheel 的退役项核对通过。此前 17/17 完整验收及声明资源 14/14 对照确实通过，但未覆盖这四项残余；原完成说明已据此校正。

## 复现与处理范围

再次运行独立复核的只读复现程序，得到同样观察，见[修复前观察](system-migration-recheck-repair-20261008/before-observations.json)。程序只创建独立临时项目。修改前工作树差异另保存于 `/tmp/vibeflow-recheck-repair-baseline-k8htalyb`，不重置已有修改。

| 项目 | 已确认问题 | 修复与验收要求 |
| --- | --- | --- |
| S01 / R01 | 未声明普通源码按目录词赋予资源身份；库入口邻居被父目录归属覆盖 | 删除目录身份及降级路径；普通代码换目录结果一致，真实声明依赖违规继续拒绝，保留通用指标 |
| S02 / R15 | 共享项目加载器接受退役 Host 字段，预览成功而验证拒绝 | 共享配置契约按字段存在统一迁移错误；空列表同样拒绝，workflow Host 保持有效 |
| S03 / R08 | 普通源码效果 Rule 记录 scope/policy，固定表却不消费参数 | 统一有效效果策略与判定；默认 none 保持严格，scope/policy 覆盖改变实际判定且记录准确 |
| S04 / R16 | 旧 NodeInfo/contract 诊断映射无生产者 | 删除死映射，并核对源码与新 wheel 不包含退役项 |

不扩大扫描范围、不增加业务启动门禁、不增加目录 allowlist，也不改变已确认的综合主题粒度或原生 callable 绑定边界。

## 实际修复

S01 删除 `QualityStructureRoles` 的四个旧字段、目录身份函数及降级调用。库入口父目录不再扩张归属；未归属源码直接返回空资源违规列表。`_resource_scopes` 继续携带真实声明，`enforce_role_imports` 继续控制声明依赖检查。数量、目录深度、复杂度与距离等通用指标保留。活动 Core 沙箱使用 canonical 归属；冻结旧 kernel 的观察及输入仅在 baseline 分支保留，三个旧目录推断反例明确记录为已授权语义改变。

S02 将 `javascript.host_extensions` 的存在检查集中在共享 `project_javascript_options`，移除旧列表解析、返回值及 Target 重复判断。正式入口共用已验证项目配置。底层 Target 接受调用者构造的 plan/bindings，不新增跨层加载依赖。合法的 workflow Host 及 runtime options 保留。

S03 删除三个 `SIDE_EFFECT_*` 表；普通源码复用 `ModulePurityVisitor` 的效果分类、真实 helper、别名和 ExitStack 检查，仅适配普通文件的 warning 输出，不施加 Node 接口、输入或顶层约束。Rule 的有效 scope/policy 传入共同判定。默认 `none` 下原表的 15 类导入、24 类调用均继续被拒绝，见[覆盖核对](system-migration-recheck-repair-20261008/s03-classifier-coverage.json)。普通源码现在也报告共享默认规则已检查的 print、动态导入、线程/FFI 等效果，见[实际新增诊断](system-migration-recheck-repair-20261008/s03-new-diagnostics.json)；没有放宽默认政策。`trusted` 沿用当前 Python 严格判定，不恢复旧身份豁免。

S04 删除四个复核旧码，并核实清理五个邻近无生产者映射：`node_external_invalid`、`node_decision_missing_route_output`、`type_mismatch`、`signature_unavailable`、`example_shape`。当前 Node interface 的 Decision、examples 及 ABI 检查直接产生的实际诊断保持有效。开发退役工具增加这些精确旧码及角色/重复表符号，并直接检查 wheel 中的 Python 源码。

## 验收记录

| 定向验证 | 实际结果 |
| --- | --- |
| S01 身份、真实依赖、通用指标及正式 workspace CLI | [52 passed](system-migration-recheck-repair-20261008/s01-focused-tests.log) |
| 实际双版本 Core 对照 | [324/324 matched](system-migration-recheck-repair-20261008/s01-core-parity-summary.json) |
| S02 公共加载、预览、验证与合法 workflow Host | [108 passed、1 skipped](system-migration-recheck-repair-20261008/s02-focused-tests.log)；定向环境缺少渲染器，本次完整环境 pytest 无跳过，JS/browser 67/67 通过 |
| S03 scope/policy、真实 Catalog 执行与相关 Python 行为 | [226 passed](system-migration-recheck-repair-20261008/s03-focused-tests.log) |
| S04 扩展清理后再验实际 ABI 与源码效果 | [73 passed](system-migration-recheck-repair-20261008/s04-abi-tests.log) |
| 原审计正式 CLI | [14/14 PASS](system-migration-recheck-repair-20261008/python-cli-directory-comparison.json) |
| 原复核程序重放 | [六目录 workspace/path 均成功；两个 Host 入口同码拒绝；python_io 允许 open，其余三 scope 拒绝](system-migration-recheck-repair-20261008/after-observations.json) |
| 仓库质量 | [零错误、零警告](system-migration-recheck-repair-20261008/quality-before-full.log) |

首轮 S03 定向的五项失败和次轮一项失败原样保留。三个 scope 矩阵失败来自探针直接返回非 Mapping，违反现 Node ABI；修改探针为执行操作后返回合法 Mapping，效果断言未放宽。实际 read_text 诊断被同位置 Path 构造覆盖，已修复为保留第一个具体操作，并保留旧行为断言。另两项是新增测试对执行记录结构的读取错误。日志见[首轮](system-migration-recheck-repair-20261008/s03-initial-failures.log)、[次轮](system-migration-recheck-repair-20261008/s03-second-failures.log)。

第一轮补充完整验收跑完全部 17 步，[16 项通过、1 项失败](system-migration-recheck-repair-20261008/initial-full-verification.json)。pytest 为 2191 passed、1 failed：文档索引未登记独立复核及本文，见[完整日志](system-migration-recheck-repair-20261008/initial-full-tests.log)。Python 138/138、JS 67/67、规则 1219/1219、补充 680/680、适配 207/207、browser、性能、wheel 隔离及双发行 smoke 均通过。本批结束后才补齐两个索引条目，没有修改测试预期或产品代码。

本批指纹也校正了旧脚本的采集范围：它按目录词排除 `build`，误漏 JS Target 的 17 个产品源码文件。补采时原 2362 项哈希未变，17 个文件的修改时间均早于批次日志创建；批末 2379 项逐文件哈希与补齐后相同，见[输入证据](system-migration-recheck-repair-20261008/initial-full-inputs.json)。[修正的只读采集程序](system-migration-recheck-repair-20261008/snapshot_inputs.py)不再排除产品 build 目录，不参与业务启动。

索引定向通过后，重新执行 `python tools/verify_project.py --full`，隔离目录为 `/tmp/vibeflow-recheck-repair-final-20261008`。最终退出码为 0，[17/17 项全部通过](system-migration-recheck-repair-20261008/final-full-verification.json)，[完整日志](system-migration-recheck-repair-20261008/final-full-tests.log)保留各正式命令及结果。

| 最终完整验收 | 结果与证据 |
| --- | --- |
| pytest | 2192 passed，无失败、无跳过 |
| 原生 Python / JS 集成 | Python 138/138；JS/browser 67/67，无跳过 |
| 规则对照 | [1219/1219 matched](system-migration-recheck-repair-20261008/rule-parity-cases.json)，进程错误 0 |
| 补充规则沙箱 | [680/680 matched](system-migration-recheck-repair-20261008/rule-gaps-cases.json)，进程错误 0 |
| 适配回归 | [207/207 matched](system-migration-recheck-repair-20261008/adaptation-regressions-cases.json)，进程错误 0 |
| 真实 browser 运行观察 | [状态、结果及指标均符合预期](system-migration-recheck-repair-20261008/runtime-observation-browser.json) |
| 布局及资源展示 | [布局 4/4](system-migration-recheck-repair-20261008/review-layout.json)，资源案例 [Python 14/14](system-migration-recheck-repair-20261008/python-resource-sections-cases.json)、[JS 14/14](system-migration-recheck-repair-20261008/javascript-resource-sections-cases.json) |
| 性能 | [57 个调用观察通过](system-migration-recheck-repair-20261008/review-performance.json) |
| wheel 与双发行 | wheel 隔离运行、两个 profile 构建及压缩包解包 smoke 均通过，命令见完整日志 |
| 仓库收尾 | 最终质量零错误、零警告；临时生成物清理目标 0 |

完整批次的启动前、运行中及结束后共 2379 个输入文件逐项相同，聚合 SHA-256 为 `f693c168d396232969de178cd140ca4f24ac66aeaa64816f2caa0051c190c654`，见[完整输入与原复核证据保护记录](system-migration-recheck-repair-20261008/final-full-inputs.json)。独立复核的原 16 个文件哈希未变。本文最终结果和这些开发证据在批次结束后补齐；产品源码、活动测试、沙箱、发行输入及用户文档均未在批次运行中修改。

[扩展退役核对](system-migration-recheck-repair-20261008/final-wheel-retirement-audit.json)同时检查源码及本次 wheel，31 个退役文件、66 个指定符号、9 个旧诊断码及相关搬迁/测试桥检查全部通过，失败项为空。另一次[独立安装包核对](system-migration-recheck-repair-20261008/final-wheel-independent.json)不执行该工具，直接比较 ZIP 成员与源码，并分别解析 AST、检查精确字符串：333 个产品文件（含 314 个 Python 文件）逐字节一致，无缺少、额外、重复或差异项；S01–S04 指定退役项在两端均零命中，AST 均可解析。新 wheel 的 SHA-256 为 `d6bdd43effaa739c6d7f06f7808fa201e69ff49505ecf944fae4020da602ec21`。

上述结果完成本次四项复核修复，并补上前次验收的覆盖缺口。

## 第二次独立核实（2026-10-08）

用户要求再次核实“已经修复”的说法后，本聊天重新读取当前实现、运行上一轮原始复现程序和正式测试入口，并独立检查源码与实际 wheel。结论：**上次 S01–S04 四项均已修复，本轮未发现它们仍残留或通过兼容分支回退。** 当前仍是未提交工作区，HEAD 为 `9c443f3`；核实对象为实际文件而非仅Git提交说明。

| 项目 | 本轮独立观察 | 判定 |
| --- | --- | --- |
| S01 | ordinary/nodes/task_nodes/custom_nodes/base_lib/plugins六种布局，workspace与path共12次CLI退出0；目录角色字段、推断函数和库父目录扩张已删除；实际声明依赖及显式支撑文件反例回归通过 | 已修复，未通过关闭全部结构检查来掩盖 |
| S02 | 原带退役Host字段的项目，review-rules与validate均退出1，同报WORKSPACE.PROJECT_CONFIG.JAVASCRIPT；共享加载器按字段存在拒绝，旧列表解析及Target重复判断已删除；空列表/None对照回归通过 | 已修复，配置契约统一 |
| S03 | 原open探针none/terminal/trusted仍报效果诊断，python_io无诊断；effect_policy记录与判定一致；普通源码传入有效scope/policy，复用共同visitor；policy覆盖、Catalog真实执行及Node/BaseLib/普通源码矩阵回归通过 | 已修复，不再只改记录而使用旧固定表 |
| S04 | 对当前Python源码和wheel逐一解析AST，9个旧精确诊断字符串与目录/重复效果表相关符号均零命中；扩展退役审计通过 | 已修复，代码及包内均清除 |

本轮实际使用 `tools/run_tests.py`运行6份相关测试文件，**198 passed，零失败、零跳过**；[完整日志](system-migration-recheck-repair-20261008/independent-recheck/targeted-tests.log)。重新执行最初目录复现，仍为**14/14 PASS**；[结果](system-migration-recheck-repair-20261008/independent-recheck/python-cli-directory-comparison.json)。[原始S01–S03程序重放](system-migration-recheck-repair-20261008/independent-recheck/residual-replay.json)保留每个CLI命令、退出码与完整输出。

最终全量记录的**2379个输入文件与当前文件全部SHA-256一致**，见[独立输入核对](system-migration-recheck-repair-20261008/independent-recheck/input-comparison.json)。读取实际新wheel，333个产品文件与当前源码逐字节一致，无缺失；包SHA-256仍为 `d6bdd43effaa739c6d7f06f7808fa201e69ff49505ecf944fae4020da602ec21`，见[包与源码核对](system-migration-recheck-repair-20261008/independent-recheck/wheel-comparison.json)。另分别保留[源码及包退役审计](system-migration-recheck-repair-20261008/independent-recheck/retirement-audit.json)与[不依赖该工具的AST核对](system-migration-recheck-repair-20261008/independent-recheck/independent-ast-retirement.json)。

开发者17/17完整验收及2192项pytest通过记录与本轮核对的输入匹配；**本轮独立重跑的是上述定向范围，没有再次执行17步全量**。结论只关闭上次具体四项，不把它扩大为任意业务行为或所有潜在问题已证明正确。本轮只补充文档与证据，没有改产品代码或测试预期；原先修复前观察继续保留。
