# 基线规则对照结果

本文冻结修复前的历史事实。当前修复与验收见 [完整修复结果](../../../docs/design/history/rule-system-repair-results.md)，当前期待及实际观察见 [机器报告](../../../docs/maintainers/evidence/index.md#artifact-d561a82679d8256e)。

2026年10月03日实跑。基线为 `f169429a8d41`，当前生产代码为 `15adf51d0676`。本轮只修改测试和盘点文档，不修改生产规则实现。

本轮在原 456 个当前场景上追加 **763 个有限变体**，总计 **1,219 个场景**。基线 1,204 个观察全部符合校准预期，**0 个基线夹具失败、0 个观察进程失败**；15 个仅当前版本具备的 Rule 入口/选择场景单列。

当前 **1,168 符合预期、51 不符合预期**，对照退出码仍为 **1**。原 456 个 ID 和原 38 个失败全部保留，新增 13 个失败场景。51 是具体场景数量，其中包含待核定的声明契约变化；多个场景也可能属于同一遗漏，不能解释成 51 个独立根因或副作用安全问题。

| 分组 | 基线观察 | 当前场景 | 当前符合 | 当前不符合 | 本轮新增 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Core 与正式工作流消费 | 311 | 324 | 319 | 5 | 116 |
| 配置及中立声明模型 | 410 | 412 | 411 | 1 | 343 |
| Python | 291 | 291 | 275 | 16 | 190 |
| JavaScript | 192 | 192 | 163 | 29 | 114 |
| 合计 | 1,204 | 1,219 | 1,168 | 51 | 763 |

分类为 1,146 preserved、24 approved_change、20 new_feature、29 baseline_limitation。分类描述场景的依据，不表示该场景已经通过。已批准迁移仍使用版本专属夹具：Python 类元信息迁为资源声明、JS ABI v1 迁为 v2、旧数值 policy 迁为所选 Ruleset 参数。不会要求重新引入旧 policy 审查通道。

## 本轮新增的覆盖

| 分组 | 新变体覆盖 |
| --- | --- |
| Core | 默认/自定义/关闭的结构与数值边界；路径角色、public entry、依赖多路径与限制；嵌套执行锁、result 消费；Decision 互斥、cardinality、payload bypass、导出；planned 父子；重复 Nodeset/Loop、显式空规则、真实 import/static/run 资料 |
| Tooling | Loop、异步结果、契约列表、相似性、展示、锁、Nodeset 导入、资源选择和 policy 参数分支；六类中立声明的身份、契约、实现、Target、source locator、依赖、JSON 值和工厂默认值 |
| Python | 声明/契约形状、签名、语义、字节/宽度/配置键；副作用别名、namespace、inputs 修改及 helper 参数；BaseLib 准入/扫描/闭包；defaults、bases、decorators、metaclass 和模块控制结构 |
| JavaScript | Promise 签名和完成协议、模块状态 alias/原型/RegExp/shadow、BaseLib 宿主与非确定性、跨层/同类依赖、single-esm 资源、真实 TS 阈值及 Ruleset 参数覆盖、TaskPlan 构建和真实数值执行 |

每个上一轮剩余主题已对应到具体 ID、已有案例或正式不可达/非活跃的源码证据，见 [Core](../../../docs/design/history/baseline-rule-inventory-core.md)、[Tooling](../../../docs/design/history/baseline-rule-inventory-tooling.md)、[Python](../../../docs/design/history/baseline-rule-inventory-python.md)、[JavaScript](../../../docs/design/history/baseline-rule-inventory-javascript.md)。未伪造 JS `source/runtime/registry/capability` owner 来填充正式入口覆盖。

## 原来的失败全部保留

| 能力 | 原失败场景 / 差异 |
| --- | --- |
| Python Decision 和契约重叠 | `python.contract.decision_missing_route / overlap`：旧错误，当前接受 |
| Python examples 结构 | 三条 `example_missing_params / example_missing_inputs / example_bad_params`：旧 warning 消失 |
| Python 相对 BaseLib 链 | `chain_relative_2 / chain_relative_4`：原长度 3/5，当前均 2，长链拒绝也漏报 |
| Python 自定义允许目录 | `reachable_functions_support`：旧函数数量上限拒绝消失 |
| 子 Nodeset 空规则 | `core.workflow.unconstrained_child_identity`：关闭审查时原生身份丢失，默认父审查误拒 |
| 已加载未调用的默认 Nodeset | `core.formal.nodeset.{flow,mainline,metadata}.unused`：孤点/终点/未消费、fanout/mainline、说明 warning 丢失 |
| 独立 JS Plugin/Host | 原 26 条 audit/build/worker/quality 场景继续漏报导入执行、状态、宿主、Promise/listener/timer、完成协议或依赖声明错误 |

自定义 support 目录的依赖链在旧版也没有正确长度，仍记为 baseline_limitation；它与旧版能检查该目录函数复杂度、当前却漏报的回退不同。

## 新增 13 个失败场景的性质

| 主题 | 新失败场景 | 实际差异 |
| --- | --- | --- |
| 重复 Nodeset 的子 [] 身份 | `core.variant.formal.repeat.child_empty_identity` | 同一已知遗漏的重复调用实证；Loop body [] 对照正常 |
| 旧 JS 合法 examples.outputs | `tooling.descriptor.contract.examples.outputs_baseline_valid`、`js.variant.declaration.examples-outputs` | 基线 parser 和真实 JS audit 接受，新模型拒绝；Python 原 Node 审查已拒绝 outputs，不能扩大为 Python 新回退 |
| category 是否必填 | `python.variant.metadata.category_empty` | 旧 Python 拒绝，新声明允许可选 category；属于待核定的公开声明契约差异，未擅自当作已批准变化 |
| semantics 数字值 | `python.variant.semantics.value_number / input_value_number` | 旧拒绝，新中立模型把数字字符串化后接受；合法字符串/空字符串对照分别验证 |
| 公开 callable | `python.variant.signature.public_lambda` | 旧 PUBLIC_CALLABLE 拒绝；新 AST 接口检查只遍历函数声明，遗漏 lambda 赋值；公开普通值对照正常 |
| 合法内置 decorator | `python.variant.import.decorator_qualified_static / decorator_property` | 原本安全的声明现在在 import Rule 被误拒，exit 0 变为 1 |
| 空模块控制结构 | `python.variant.import.try / match` | 空语句块的旧模块语法拒绝消失；这些场景本身没有 IO，不能据此称实际副作用已执行 |
| Plugin 完成协议 | `js.variant.completion.plugin-promise-hook / plugin-async-factory` | 独立 Plugin 审查遗漏的更具体分支：旧 audit 拒绝，当前接受；真正 suspend hook 的正常对照保留 |

真实副作用另外用 `python.variant.import.try_marker / match_marker` 验证。两版均经正式 `run` 在绑定前拒绝 open/write，四次 marker 都为空、exit 1。当前只让目标 Node 选 import-only Ruleset，static/run 为空，相邻 Node 明确 []，每次只产生一条目标 `NODE.IMPORT.SIDE_EFFECT`；不靠其他 Node 或后续 static finding 遮掩导入阻断。因此，本轮证明这两个具体写入反例仍被阻断。

JS 的五项 Node 与三项 BaseLib 可配置数值限制最初用旧 policy 文件时未生效；将夹具按已批准迁移改为真实 Ruleset 局部 `params.policy` 覆盖后，超限拒绝、等值通过全部成立。没有把旧配置被移除误记为规则能力丢失。两种合法 JS TaskPlan 产物都实际输出 4；single-esm 的八项本地资源拒绝和两个合法 URL 构建对照均保持原判断。

## 运行证据与验证

统一运行：

```bash
python tests/fixtures/rule_parity/run_all.py \
  --work /tmp/vibeflow-rule-parity-variants-complete \
  --report /tmp/vibeflow-rule-parity-variants-complete.json
```

末次导入控制变量校准只修改 Python 的两个 run marker 夹具，最终冻结后另重跑完整 Python 组：

```bash
python tests/fixtures/rule_parity/run_all.py --target python \
  --work /tmp/vibeflow-rule-parity-python-controlled-final \
  --report /tmp/vibeflow-rule-parity-python-controlled-final.json
```

最终汇总 `/tmp/vibeflow-rule-parity-variants-verified.json` 使用统一运行的 Core/Tooling/JS 与冻结后的完整 Python 观察，重新执行同一比较器；保留每组报告来源。原始源码、日志和 observations 在上述两个 work 目录内。

- 比较器隔离 pytest：21 passed，含警告漏报、无关失败、误拒、缺失案例、原因/位置/指标、异常状态与明确旧 CLI 崩溃运输；所需 Rule 诊断不会被崩溃代替。
- 仓库独立质量：`python repo_check/run.py --profile all` PASS。
- 独立质量工具：`python repo_check/test.py`，45 tests OK。
- 新 Python 文件语法、空白及 `git diff --check` 通过；生产树 `src/` 和 `pyproject.toml` 无改动。

六条旧非法契约使正式 CLI 在 `contract_payload` 序列化时崩溃，单列为基线局限；对应审查判断另用真实公开 validator 验证。错误不被包装成成功资料，也不混入新回退数量。

没有降低已知回退的期待，没有使用 xfail。尚未运行发行构建和完整项目发布门禁；当前审查仍有不符合预期的行为，局部检查通过不意味着重构已经无回退。这里完成的是清单中有限分支的测试与证据，不承诺穷举任意语言代码、图、参数值或第三方规则。
