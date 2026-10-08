# Rule、Node 与组件迁移修复独立复核

日期：2026-10-08。基线为[原审计 R01–R19](system-migration-audit-20261007.md)，开发者说明为[迁移修复结果](system-migration-results-20261007.md)。复核对象是当前未提交工作区，HEAD 仍为 `9c443f3`，开发版本为 0.16.0。

本轮仅增加审计文档、复现程序和证据，不修改产品代码、测试定义或开发者已有改动。

## 结论

**主要迁移是真实完成的，但“所有这类问题已经清零”尚不成立。** 旧公开模型、自动发现/Registry 适配、JS 第二套解析和校验、quality→固定内置小图→quality 循环及活动测试转换桥已实质退役。原来已声明资源因目录名或导入位置而出现不同结果的14项对照已全部通过。

独立复核另确认4项剩余：未归属源码仍按目录名称赋予资源角色；已删除 Host 配置在不同入口的接受规则不一致；普通项目源码的效果 Rule 保留固定判定且不消费自身效果参数；旧 metadata 诊断映射仍有无生产者项。前3项有可观察行为或接口差异，最后一项是清理遗漏。这些不等于两个完整旧、新系统仍并行运行。

默认主题内部复用 AST/图算法、保留原生 ABI/runtime、内置插件使用原生 callable 绑定仍存在。这些是当前明确保留的职责或组合边界，不能与迁移缺陷混算。

## 实际验证与限制

| 验证面 | 本轮实际结果 |
| --- | --- |
| 原审计正式 CLI 目录对照 | 14/14 PASS；[观察](system-migration-recheck-20261008/python-cli-directory-comparison.json) |
| 迁移、贡献、身份、AOT、规则预览等定向回归 | 205 passed、1 skipped；[日志](system-migration-recheck-20261008/targeted-tests.log) |
| 源码与 wheel 退役审计 | PASS；31个退役文件、5个迁移内置路径、3个测试桥及退役符号清单；[结果](system-migration-recheck-20261008/retirement-audit.json) |
| 开发者全量验收与当前输入匹配 | 2360/2360文件 SHA-256 相同；[逐文件核对结果](system-migration-recheck-20261008/recorded-input-comparison.json) |
| 实际 wheel 与源码匹配 | 333个产品文件逐字节相同，无缺失；SHA与开发者记录相同；[结果](system-migration-recheck-20261008/wheel-comparison.json) |
| 补充发现 | 正式 CLI、公共配置加载器和效果 Rule 直接探针，见下面 S01–S04 |

开发者的[全量记录](system-migration-results-20261007/final-full-verification.json)为17/17步骤通过，其中pytest 2127 passed。该记录对应的输入确实与当前工作区一致；**本轮没有重新执行这17步全量验收**，独立重跑的是上表定向范围。定向中的1项跳过不能计为通过，测试存在工具链/渲染器前置条件，本轮没有宣称所有展示与业务运行均重新验收。

补充行为可用[复现程序](system-migration-recheck-20261008/reproduce_residuals.py)独立重跑：`PYTHONPATH=src python docs/maintainers/system-migration-recheck-20261008/reproduce_residuals.py`。它只创建新的/tmp项目，不修改产品源码；本轮已实际运行，[完整重放观察](system-migration-recheck-20261008/residual-replay.json)与下面各项一致。

第一次直接调用pytest漏掉仓库规定的 `VIBEFLOW_TEST_TOOLCHAIN_ROOT`，得到50 passed、19 failed，失败均为JS测试环境缺项；[原始日志](system-migration-recheck-20261008/initial-tests-missing-toolchain.log)保留。另一次调用误选不存在的测试路径，未执行测试；随后使用 `tools/run_tests.py`、实际存在的文件及独立临时工具链完成上述205项。它们没有被当作产品失败或成功验收证据。

## R01–R19 逐项判定

| 原编号 | 本轮判定 | 当前实现与核对依据 |
| --- | --- | --- |
| R01 | 原已声明资源冲突已修复；范围外仍有S01 | `source_membership.source_ownership`消费Descriptor及真实源文件；正式CLI顶层/方法导入10项一致，未声明库反例仍拒绝 |
| R02 | 已修复 | BaseLib支撑文件来自implementation_files及ownership；四项旧失败目录现均PASS |
| R03 | 已修复 | 名称触发的base_lib整模块扫描及is_base_lib已删除；调用者效果Rule依实际helper闭包检查，unchecked library含print反例与空Rule选择对照通过 |
| R04 | 已修复 | 旧BaseLibRegistry adapter连同模块和导出删除；`PythonResourceBinding`直接持有canonical descriptor，不重新抄写rulesets |
| R05 | 已修复 | `parse_javascript_plugin_descriptor`退出源码/导出；SDK经统一decoder装配，活跃lifecycle binding保留 |
| R06 | 已修复 | JS独立quality models/validation删除；当前只执行所选Rule路径 |
| R07 | 已修复 | Node Schema加入examples.outputs；Python默认interface Rule的限制仍由Rule承担，不再由声明模型否定 |
| R08 | 原Core参数问题已修复；另有S03 | builtin implementation消费有效policy；1/1000结果及Application参数/preview一致性回归通过 |
| R09 | 已修复 | Core implementation模块只留事实模型/调用图算法；判定移至builtin，不再创建固定小图回导quality；Core不隐式选择标准Rule |
| R10 | 有意保留的主题粒度 | 综合workflow/effects直接调用普通判定算法，仍不是所有topic的Ruleset子调用；文档明确，替换独立topic不等于替换综合主题 |
| R11 | 实现绑定统一；原生内置插件边界保留 | builtin与外部共同贡献/冻结/冲突处理；`native_binding`按origin.plugin_id解析，无内置resource ID优先分支。builtin仍通过Target的callable表配对，不是全部外置为普通JS/Python SDK源码插件 |
| R12 | 已修复 | JS build与emitter强制WorkflowPlan + JavascriptBindingPlan；旧WorkflowSpec/model/parser/validation实际删除；AOT定向回归通过 |
| R13 | 已修复 | BaseLib scan/analyze、旧metadata normalizer、NodeInfo/NodeContract、Context/RegistryBase及导出退役；当前没有发现它们藏在改名后的第二套模型中 |
| R14 | 已修复 | 新canonical binding/resource selection替代ConfigResources与旧resource registry转换；PluginRegistry继续负责原生实例和lifecycle，已不充当资源声明权威 |
| R15 | 执行fallback已删除；配置契约部分修复 | build/audit只用workflow Host；但workspace配置加载器仍接受项目级host_extensions，见S02 |
| R16 | 大部分清理完成，仍有S04 | 静态info.rule_catalog、未用policy registry参数和旧路径豁免已删除；无生产者诊断码仍残留。Context/boundary通用词汇本身不能作为旧API仍存在的证明 |
| R17 | 原清单已退役 | 31个文件及旧内置命名空间不存在，wheel也不含它们；混合职责模块保留活跃binding等功能 |
| R18 | 原清单已清理 | 列出的死函数/属性、is_base_lib和无正式生产者的JS source owner分支已删除；扩展静态候选逐一核对动态加载与回调，没有确认新的整文件死代码 |
| R19 | 活动转换链已退役 | code_plugins/source_membership/contributions测试桥删除；活动夹具直接生成SDK/Descriptor/canonical plan；冻结resource_migration与历史发行仍作证据保留 |

R10、R11此前就包含设计边界，不能为了得到“19项全部修复”的计数而把它们改判为缺陷。R01、R08原来具体复现已关闭，S01、S03是扩展检查发现的邻近残余，不能反过来说旧14项或Core探针仍失败。

## S01：未归属源码仍走旧目录角色推断（优先处理）

位置：`src/vibeflow/core/quality/models.py:98–104`，`root_structure.py:194–245,303–340`；`tooling/application/python/project/quality.py:138–154`。

新ownership分支只处理声明拥有的source；若source不在任何资源的ownership中，`resource_import_violations`返回None，主链就回退到 `_role_for_file/_role_for_path/_is_node_role`。默认 `infer_roles_from_path=True`，`base_lib_paths=("base_lib",)`；`nodes/task_nodes/*_nodes`被赋予Node角色，`plugins`被赋予Plugin角色。

此外，`structure_roles_for_root`会把声明库的入口**父目录**加入base_lib_paths；同目录的未归属邻居也会获得库角色。该行为不是implementation_files中的显式归属。

本轮创建只含两个普通函数文件的项目：`<目录>/worker.py`导入`utility/math.py`。没有Node/BaseLib/Plugin声明，函数代码与导入相同，仅改目录名。实际运行 `python -m vibeflow quality-check --workspace ... --json`：

| worker目录 | 正式workspace结果 | 原因 |
| --- | --- | --- |
| ordinary | PASS | 没有角色导入限制 |
| nodes、task_nodes、custom_nodes | FAIL | QUALITY.STRUCTURE.NODE_UNDECLARED_PROJECT_IMPORT |
| base_lib | FAIL | QUALITY.STRUCTURE.BASE_LIB_UPWARD_IMPORT |
| plugins | PASS | 当前目标utility不是Node角色，未触发Plugin→Node限制 |

[六项实际观察](system-migration-recheck-20261008/unclaimed-layout-workspace-cli.json)。同样文件使用 `quality-check --path`时默认未开启结构限制，六项均PASS，[路径入口观察](system-migration-recheck-20261008/unclaimed-layout-cli.json)。差异不能解释成一个入口少加载了Node声明，因为这些项目根本没有任何Node声明。

修复代码注释有意保留“普通、未归属源码”的layout hints。**这是仍在正式Rule内部运行的旧语义，不是第二套Rule引擎，也不恢复旧注册。** 但当目录词直接产生error并把普通函数称为Node时，已不只是展示提示。它与“身份只来自声明”的迁移目标存在边界冲突。原审计曾明确未承诺孤立源码自动登记；这里要求的是不从名字伪造身份，并不要求自动登记或扩大扫描范围。

建议以声明关系判断资源间导入；普通未归属代码保留数量、复杂度、距离等通用结构检查。若确实保留目录规范，应明确成为另一个可选布局规则，不混称资源身份。

## S02：退役Host字段仍被公共加载器及预览接受

位置：`tooling/project/project_config_options.py:24–28,55–66,84–86`；`targets/javascript/build/project_paths.py:29–33`；`tooling/application/rule_review.py:145–158`。

公共project options仍把javascript.host_extensions列为合法字段并解析/返回，workspace_loader正常保存它。Target options则在字段存在时直接报“was removed”。同一份带此字段的原生I/O workflow，本轮正式 `review-rules --config ... --json`退出0，正式 `validate --workspace ... --config ... --json`退出1，报 `VF_AOT_JAVASCRIPT_CONFIG`迁移错误。

证据：[公共加载器与Target对照](system-migration-recheck-20261008/host-config-contract.json)、[预览CLI](system-migration-recheck-20261008/host-preview-cli.json)、[validate CLI](system-migration-recheck-20261008/host-validate-cli.json)。预览无需执行业务，但应使用同一退役配置契约；现在保留了互相矛盾的两份字段接受逻辑。

**旧Host fallback本身已删除。** 剩余的是loader契约和相关旧解析代码。应在共享project配置层统一拒绝，并让预览/检查沿用该契约。

## S03：普通源码效果Rule记录新参数，仍使用固定旧判定

位置：`targets/python/quality/rules/effects.py:12–22`，`quality/rules/project_effects.py:10–90`；接入为 `tooling/application/python/project/quality_scan.py:65–84,104–113`。

同一个 `vibeflow.no_side_effects`声明提供effect_scope与policy参数。Node/BaseLib分支消费这些参数；python_source分支只把effect_scope写入effect_policy记录，随后调用不接收params的 `source_effect_findings(source, tree)`。它保留独立SIDE_EFFECT_IMPORT_ROOTS/CALLS/ATTR_CALLS判定表。

本轮直接执行公开Rule实现，对普通源码 `def read(): return open("data.txt").read()`分别提供none/python_io/terminal/trusted：四次都产生 `QUALITY.SIDE_EFFECT.CALL`，但输出effect_policy分别声称使用各个scope。[实际结果](system-migration-recheck-20261008/project-effects-parameters.json)。源码分支同样没有将policy传给判定器。

**这是公开Rule实现的参数与结果契约不一致；没有证明当前CLI某个scope选项失效。** 当前普通项目扫描固定选择该Rule且默认scope=none，默认禁止open的目的仍能实现。不能据此要求项目扫描自动支持用户所有Catalog——那是原审计排除的额外目标。

但将旧固定扫描包进具有参数的新Rule，却仅更新记录、不更新判定，仍属于用户担心的“新接口内部继续带旧机制”。建议让这个分支消费相同有效policy/scope，或将固定普通源码效果审查声明为独立且不承诺这些参数的Rule。更改前应明确普通源码审查的契约，不能简单放宽默认判定。

## S04：退役metadata诊断映射仍有无生产者项

位置：`targets/python/quality/source_analysis/types.py:194–210`。

`node_info_flow_kind`、`node_flow_kind_invalid`、`missing_node_info`、`missing_contract`仍在 `_rule_id_for_violation`映射/分组中。对当前src/tests检索，这四个旧code只出现于此函数，没有生产者。NodeInfo和旧contract类元数据已删除，默认接口判定消费NodeDescriptor.contract。

这是低优先级闲置分支，不是旧metadata重新取得声明权威。可删除映射中的退役code；公共诊断code若确有外部兼容承诺，应显式说明，不能保留成无人知晓的内部兼容。

## 排除的候选与仍保留的边界

- 扩展AST引用清单只有4个无静态入边模块候选：`__main__.py`是命令入口，两个Application plugin_definitions及JS builtin_plugin由import_module装配，均活跃。[原始候选](system-migration-recheck-20261008/static-candidates.json)不是删除清单。
- `_close_definitions`由atexit.register执行；`__getattr__/__dir__`是模块协议，不能按没有普通调用判死。
- Core `descriptors/source_bundle.py`名称虽带bundle，实际保存canonical源归属与plugin declaration；当前没有旧JSONC bundle发现功能，不能因文件名判残留。
- `tests/targets/javascript/aot_fixtures.py`仍有测试数据到plan dataclass的小构造器，未调用退役parser/validator，也不恢复产品旧模型。fixture authoring helper与旧格式自动发现转换桥应分开。
- 原生PluginRegistry维护已绑定实例、hook优先级和dispose；新PythonResourceBinding保存Descriptor及选择/位置。这是语言运行绑定，不是旧的第二份声明数据模型。
- 默认综合workflow/effects主题和builtin Target callable配对仍存在。若目标升级为“每个细检查均可单独覆盖、全部默认规则都外置成普通SDK插件”，还需新工作；本轮没有把这项新目标当作开发者已经承诺却失败。
- 历史发行zip、冻结夹具、旧审计和失败批次记录属于证据资产，未发现当前产品从中加载退役系统。

## 后续范围

优先处理S01身份推断和S03参数契约，然后统一S02配置接受逻辑、清理S04映射。继续沿用声明ownership、唯一配置契约和真实Rule参数，不以给旧目录加allowlist、改目录名或只改报告文字来验收。

本轮结论是**主要迁移已完成，尚有4项明确残余**，不是项目任意语法、第三方公开API用法及业务结果均已证明正确。复核只读，没有在发现问题后顺手修改实现。
