# 迁移整改代码独立复核

复核日期：2026-10-08。对象为当前 0.16.0 未提交工作树，HEAD 为 `9c443f3111e65e6f99842d86d983416a745d391b`，开始时有 545 项既有 Git 状态记录。依据[原全范围审计](system-migration-wide-audit-20261008.md)与[开发者整改说明](system-migration-remediation-20261008.md)，逐项检查 M01–M11，并检查本轮同时退役的 `required=None` 输入行为。

**原 M01–M11 的具体残余和原复现症状已清理；仍有一个 P2 级共享效果判定缺陷，因而不能无保留接受“相关行为已全部修正”的结论。** F01 位于整改后的 Python 共享遍历器：函数体局部绑定被提前用于默认参数检查，终端与进程参数引用可被误放行。它不是旧 scanner 仍存续的证据，但直接影响统一后的判定正确性。

本次只增加审核报告、独立复现脚本与证据、文档索引。没有修复或改写产品及活动测试，没有提交、推送或发布。

## F01：默认参数被错误地当作函数体局部表达式检查（P2）

位置：[共享 visitor](../../../src/vibeflow/targets/python/quality/source_analysis/visitors.py#L212) 的 `visit_FunctionDef`，特别是 215–218 行；`visit_AsyncFunctionDef`、NodePurityVisitor 与 ModulePurityVisitor 也走这段实现。

当前实现在 `generic_visit(node)` 之前把参数和函数体的局部名称全部写入 `_current_local_names`，并删除同名导入别名。随后 `_is_local_reference` 把默认参数里的同名宿主引用当成局部对象，跳过效果检查。

Python 在定义函数时求默认参数，使用外层作用域。函数参数还没有绑定，函数体里的 `import sys` 也尚未执行。下面两段代码的默认值都会读取模块 `sys.stdout`，参数改名不应改变审查结果：

```python
import sys

def helper(sys=sys.stdout):
    return sys

def control(stream=sys.stdout):
    return stream
```

| 对照 | scope | 预期 | 普通源码 / Node / BaseLib / Plugin 实测 |
| --- | --- | --- | --- |
| `helper(sys=sys.stdout)` | none | 检出终端引用 | 四类均无诊断 |
| `control(stream=sys.stdout)` | none | 检出终端引用 | 四类均检出 |
| `helper(sys=sys.argv)` | 五种 scope 分别测试 | 均检出进程 argv 访问 | 四类、五种 scope 均无诊断 |
| `helper(stream=sys.stdout)`，函数体再 `import sys` | none | 检出定义时终端引用 | 四类均无诊断 |
| `helper(sys)`，只在函数体读取传入对象的 `sys.stdout` | none | 应允许局部对象访问 | 四类均允许，属于有效控制项 |

这里包括参数名称和函数体导入引起的遮蔽，不需要动态反射、路径关联或循环推断。安全的[实际 Python 求值对照](../evidence/index.md#artifact-3ae717ff6de7c69b)确认默认值对象就是外层 `sys.stdout` / `sys.argv`，未输出 argv 内容。

独立静态矩阵共 40 项，当前源码与最终 kernel 均为 **28 项漏检、12 项符合预期**。这是同一个作用域错误的多个变体，不能计为 28 个独立缺陷。探针只把代码解析为 AST，不导入或执行被检查代码：

- [可重放脚本](../evidence/index.md#artifact-17749670d1d65421)
- [源码逐案结果](../evidence/index.md#artifact-abd3ae43cefe1381)
- [kernel 逐案结果与真实产品来源](../evidence/index.md#artifact-a8cc6d367c5ade9f)

另外，通过与原审计相同的资源项目和正式 `validate --workspace --config --json` 入口重放四项对照：BaseLib、Plugin 的 shadowed 默认参数均 **PASS**；改名控制项均 **FAIL**，诊断来自 `vibeflow.no_side_effects`。见[正式 CLI 证据](../evidence/index.md#artifact-911d074a13c58893)。

修正应按实际求值作用域分别遍历签名表达式和函数体：默认参数及装饰器使用外层绑定，函数体使用本地绑定。保留局部对象免于宿主误认的正确行为，不能通过禁止 `sys` 参数名或取消全部局部对象识别修补。还应覆盖嵌套与 async 函数；Node 和 Module 的输入跟踪状态也应遵守同一求值边界。修复后先重放上述控制项，再跑现有效果和正式资源回归。

## M01–M11 逐项结论

| 项目 | 当前源码证据与独立复核结果 | 判定 |
| --- | --- | --- |
| M01 | `_BaseLibAstScanner` 已删除；`_BaseLibEffectVisitor` 继承 `_EffectVisitor`，只保留结构及诊断适配。原五种效果在两类资源中均被拒绝 | 旧双遍历残余已清理；共享判定仍受 F01 影响 |
| M02 | Plugin 分支把 `resolved_function_calls(source.path)` 传入 ModulePurityVisitor，并继续遍历 helper 函数体。原 `write` / `identity` 两者均通过，真实 helper I/O 回归通过 | 原名称误判已修复 |
| M03 | Python handler 按实际消费字段补默认与验证；JS builtin 验证 params，再由 `_source_check` 发送 `ruleParams`；driver 消费 scope 和 imports 四字段，缓存键包括整个请求 | 参数丢失已修复；正式计划、native 和缓存重放通过 |
| M04 | `_default_rule_id` 的不可达 COUPLING 分支已删除，实际 METADATA 映射保留 | 已清理 |
| M05 | `_inputs_to_initial` / `_copy_input_item` 及专用导出已删除，活动 Nodeset 转换保留 | 已清理 |
| M06 | `_resolve_paths` / `_module_search_path` 已删除，模块仅保留仍使用的 `_finding` | 已清理 |
| M07 | `_publish_review_pair` 已删除；测试调用 `handle_review`，通过故障注入验证正式发布路径 | 已清理 |
| M08 | `_find_chromium` 已删除；测试现行候选选择与 renderer 回退，不再给旧 helper 保活 | 已清理；本次相关浏览器用例有跳过，未独立重跑全量浏览器验收 |
| M09 | builtin 不再发送 ownership topic；normalizeImportPolicy 不再保存 owner.effectScope，实际 ownership/completion 检查仍存在 | 协议残片已清理 |
| M10 | 原两处以及扩大回归发现的 CLI 本地 parser wrapper 已删除；共享 `_node_call` 保留 implemented 输入中的非法字段，由正式 parser 拒绝；planned/system 显式契约仍保留 | 原静默转换桥已清理 |
| M11 | 版本黑名单已删除；明确当前开发版本声明读取 pyproject.toml，历史叙述允许存在；quality 工具 49 项测试通过 | 过期政策已修复 |

[全部产品 AST 符号核对](../evidence/index.md#artifact-676ae6b5144d1a07)中七个原旧 scanner/helper 名称均无定义或引用。M03 原正式 SDK 复现的三组结果为：none 拒绝 console；未知 `audit_marker` 明确报 RULE.EXECUTION；terminal 放行 console。有效请求均含 ruleParams，未知参数未进入 native 判定。见[正式 JS 重放](../evidence/index.md#artifact-447c9610e5655562)。

## 输入迁移与生成产物

Core PipelineInputSpec.required 是无默认值的必填 bool；parser、schema 与 portable 模型拒绝缺失及非 bool。Python RuntimeContractMixin 与 JS validatePublicInputs 均先拒未知键再查必填；无输入声明只接受空对象。optional 可缺失，null 仍算存在。portable supplied inputs 的 key/type/required/顺序必须与 canonical 输入一致，旧整组免检分支已退出生产代码。

独立重跑最终 wheel 输入探针：**8 项解析、12 项 Python/实际 Node 运行全部通过**。拒绝案例在业务节点执行前失败；报告中的 136 个产品模块均来自安装 wheel。该探针由开发者提供，本次重新执行，不能等同于新增独立设计的反例。

同时重新执行最终 kernel 的开发者包级探针：Python 效果 **873/873**、JS SDK→Ruleset→RulePlan→native **33/33**，产品模块分别为 114 / 118，均无源码工作树混入。JS A→B→A→C→B 的实际 RuleResult、参数记录、缓存条目和请求增量通过；回返 A/B 没有新增 native 请求。这些既有矩阵通过，但没有覆盖 F01。

独立逐字节比较当前 **334 个产品文件**与最终 wheel、协作及自主 profile 的两个 kernel：无缺失、多余或差异文件。五个最终 archive/kernel 的尺寸及 SHA256 均与开发者记录相符，两个 kernel 本身相同。F01 因此确实进入本次构建产物。[核对结果](../evidence/index.md#artifact-676ae6b5144d1a07)保存完整当前文件哈希。

## 本次独立运行与边界

| 实际运行 | 结果 |
| --- | --- |
| effects、参数、旧 helper 退役、正式 review 与活动 authoring 14 文件 | 682 passed，3 skipped |
| portable、跨 Target conformance、Python 输入 guardrail、正式 AOT 输入 5 文件 | 92 passed，1 skipped |
| quality 工具自身测试 | 49 passed |
| 原审计 Python 正式 CLI 13 项 | 10 项效果拒绝，3 项纯 helper 通过 |
| 原审计 JS 正式参数 3 组 | 结果与新契约一致 |
| 新默认参数作用域矩阵：源码 / kernel | 各 40 项，均有 28 项漏检 |
| 新默认参数正式 CLI 4 项 | 两项误放行、两项改名控制正确拒绝 |

两组 pytest 文件互不重叠，共 **774 passed、4 skipped**。首次运行受 /tmp 用户配额错误 EDQUOT 影响，603 passed、79 failed、3 skipped；失败的 native driver 报 `Unknown system error -122 ... write`。将 scratch 和 TMPDIR 指向工作区隔离目录，同一组选项全部通过。环境故障不作为产品缺陷，也未清理用户既有文件。

开发者第三批全量 17/17、pytest 2561、完整工作流/浏览器/规则对照结果属于本次核对过的既有记录；本次没有重新执行全量 17 阶段，四项 skip 不计为独立验收通过。复核期间 334 个产品文件哈希没有变化。最终仓库 [all profile 检查](../evidence/index.md#artifact-9e3eede82e03889f)通过，0 error / warning / info。

历史夹具独立以 HEAD 核对：445 个历史输入文件相同，README 有既有未提交说明变化，目录仍为 446 文件。此 HEAD 对照与开发者“整改起点到终点 446 文件不变”的基线不同，不能据此认定其冻结承诺违反；本次未重建该起点快照。见[独立夹具核对](../evidence/index.md#artifact-8b68f510d46ccea9)。

[独立汇总](../evidence/index.md#artifact-042753c198be842f)、[效果测试日志](../evidence/index.md#artifact-73c633023c988c71)、[输入测试日志](../evidence/index.md#artifact-3a4881360ff50bac)、[quality 日志](../evidence/index.md#artifact-7df727f8f99ac684)随本报告保留。完整生成包探针 JSON 与隔离运行目录位于本地 `dist/remediation-independent-review-20261008/`。
