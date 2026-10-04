# Rule、Ruleset、Node 声明与插件沙箱验收

沙箱分为可直接运行的项目和基于临时副本的自动测试。正常项目不会混入故意无效的声明；自动测试在副本中制造失败，检查正式命令的诊断、退出码、导入边界和发布行为。

验收覆盖公开契约及已确定场景。Rule 按受信代码执行，只读上下文用例验证公共查询保持共享分析资料一致。

原矩阵侧重新 API 的功能验收。[f169429 基线能力盘点](../docs/design/baseline-rule-inventory.md) 和 [两版本对照沙箱](rule_parity/README.md) 补充了旧源码审查保留能力，既检测漏报，也检测误拒。修复前的 51 项不匹配保留在 [历史对照结果](rule_parity/RESULTS.md)；当前 1219 项均通过，完整门禁直接运行这组检测。

[第二轮覆盖审计](../docs/design/baseline-rule-coverage-second-audit.md) 发现了规则选择范围、JS records 运输/动态导入资料、公开规则与正式入口等缺口。[持久补测](rule_gaps/README.md) 保留合法对照、真实数值、状态与来源；修复前 68 项不匹配保留在 [历史补测记录](rule_gaps/RESULTS.md)。当前新增 205 项均通过。两组共 1424 项的实际观察、27 个主题与修复或批准迁移的对应见 [机器报告](rule_repair_report.json) 和 [修复验收](../docs/design/rule-system-repair-results.md)。

## 可运行项目

| 项目 | 业务与接入方式 |
| --- | --- |
| `python/domain_rules`、`javascript/domain_rules` | 固定代码插件贡献模型功能块、数据变换 Node 及领域 Rule/Ruleset；原生工作流计算 `3 × 2 + 1 = 7` |
| `python/rule_graph`、`javascript/rule_graph` | 两个普通语言 Rule 通过 SDK Ruleset 的 `requires` 传递具名 typed records；共享、嵌套与替换资源可单独检查 |
| `resources/python`、`resources/javascript` | 多文件 Node、BaseLib、Plugin 与 JS/TS Host；正式 SVG/Architecture 的资源、源码依赖和样式来源；真实数值结果为 6 |
| `python/integration` | Python 原生执行、路由、Nodeset、Loop、副作用授权及完整 CLI 回归 |
| `javascript/integration` | TypeScript AOT、分支、Nodeset、Loop、插件生命周期、Capability、Host Extension、Node/browser 真实执行 |
| 两个 Target 的 `minimal` | 最小公开项目和发行入口 smoke |

## 自动覆盖矩阵

| 能力 | 实际检查 | 测试入口 |
| --- | --- | --- |
| 规则图与数据传递 | Python/TS 外部 handler；自动绑定 records；有效空列表；有 finding 但资料可用；failed/unavailable、缺失输出、类型错误阻止依赖消费者 | `tests/integration/test_rule_plugin_graph.py` |
| 局部组合与覆盖 | 嵌套、多路径共享、调用参数隔离；消费中的 provider 替换及接口保持；覆盖优先、合并和无序冲突；三类循环及输入绑定错误的正式资源诊断 | 同上；`tests/core/test_rule_graph.py` 补充内核边界 |
| 阶段职责 | 未声明 import/run 的规则图默认只选静态入口；显式 import/run 入口；真实 Node 数值与 handler 阶段记录分别断言 | 同上；两个 Target 的 `test_workflow_import_rules.py` |
| Node 与插件贡献 | 固定插件启用、共享与传递引用、重复 ID、悬空资源、未知 Ruleset、缺少实现文件/导出；保留资源来源和真实导入边界 | `tests/integration/test_bundle_registration_sandbox.py`，保留历史案例文件名 |
| Python 跨 root 与延迟绑定 | Rule/Ruleset 冲突保留双方声明来源并形成正式诊断；调用级 import Rule 在 validate 和实际绑定中取得真实 workflow 调用及参数 | `tests/integration/test_python_rule_entrypoints.py` |
| Python 源码上下文 | AST/符号快照、导入别名/相对导入、引用与 helper 归属、重复 Nodeset 调用；资料复用和后续规则不受 AST 修改影响 | `tests/targets/python/test_rule_sessions.py`、`test_domain_rules.py` |
| JS 公开源码 API | 真实 TS Rule 调用 `text/ast/nodes/symbols/imports/reachable/ownership`；精确位置与 helper 归属；两个 Rule 尝试修改上下文、AST、查询结果及依赖输入，后续资料保持正确 | `tests/targets/javascript/test_rule_source_api.py` |
| 领域错误进入正式流程 | 模型允许位置、普通变换和 helper 的非法定义、共享源码归属；JSON/text 诊断、规则 ID、文件/行号、退出码；review 失败保留已有正式文件 | 两个 Target 的 `test_domain_rules.py` |
| 权限由规则选择决定 | 默认 Process 拒绝终端输出；相同 `flow_kind` 通过 Ruleset/覆盖允许输出；显式 `[]` 如实报告未约束；真实 stdout 和业务结果 | 两个 Target 的 `test_domain_rules.py`；Python `test_delegate_rule_permissions.py` 补充委托场景 |
| 正式业务 SVG | 两个 Target 实际 Mermaid/浏览器渲染；原生/Node/状态/调用样式顺序；浅蓝模型、绿色变换、形状、图标、原生身份与规则选择；Architecture 保存展示来源和 Node tags/metadata | `tests/integration/test_domain_svg_sandbox.py` |
| 正式规则 SVG | `review-rules` 生成真实 SVG；依赖/覆盖边、参数来源、实例来源；实现文件主动抛异常仍能展示声明图，证明未执行业务或 Rule 实现 | 同上 |
| 完整交付 | 仓库独立质量、全部 pytest、两 Target 集成、浏览器、wheel 隔离、两个发行 profile 及真实发行入口 | `tools/verify_project.py --full` |
| 基线审查保留 | 通用阈值/依赖/结构、原生事实、配置/声明模型、Python Node/helper/BaseLib 与真实源码指标、JS Node/BaseLib/Plugin/Host 的正式入口和 worker；包含数值边界、语法变体、遮蔽、所有权与嵌套调用；批准迁移及正式不可达分支单独说明 | `sandbox/rule_parity/run_all.py`，独立执行并报告失败；比较器的 pytest 只验证报告机制 |
| 第二轮接口与组合补齐 | Node 规则范围、records 真实性、导入边/位置、跨 Target/跨 root、非法声明运输、替换来源、公开 leaf、平台入口、原生 bundle 组、缓存及 findings；领域分支/Nodeset/Loop 的真实业务与 SVG | `sandbox/rule_gaps/run_all.py`，独立执行并报告不匹配；`tests/integration/test_rule_gaps_reporting.py` 只验证报告可靠性 |
| 多文件资源专项 | 正式 CLI 验证四类资源的启用、归属、传递依赖、规则、登记后修改、全部形状和最终 SVG 颜色；Node/browser 宿主 FIFO、取消、计时器、回执及实例隔离 | `sandbox/rule_gaps/run_all.py --group resources`；案例与结果见[资源矩阵](../docs/design/multifile-resource-cases.md) |

Python 的模型定义约定是声明类中的 `model_forward`；TS 示例允许实现文件的 `modelForward`。领域判断由各自插件实现，测试不会把这两种语言约定强行混成一种。

Python 正式 `run` 执行运行入口。JS 当前的正式 `build` 执行静态审查，产物 `runWorkflow` 执行业务；JS 运行入口通过公开 Target API `run_javascript_rules(..., phase="run")` 验证。测试保持这些职责，不向离线产物注入外部 Rule worker。

插件受信入口及直接导入先初始化，延迟实现保持所选 import 检查后绑定的顺序。用例分别断言源码加载 marker、检查函数及业务调用次数、失败诊断和正式产物发布，区分声明取得与实际执行。

## 重复运行

在仓库根目录运行完整门禁：

```bash
npm_config_cache=/tmp/vibeflow-npm-cache python tools/verify_project.py --full
python quality/test.py
```

完整门禁在 pytest 前根据锁文件准备 Mermaid/Puppeteer，并传入 `VIBEFLOW_MERMAID_RENDERER_ROOT`，真实 SVG 用例实际执行。普通 pytest 未准备渲染器时，SVG 用例会明确跳过；该结果不能代替完整图形验收。

仅运行新增规则和注册场景：

```bash
python tools/run_tests.py -- \
  tests/integration/test_rule_plugin_graph.py \
  tests/integration/test_bundle_registration_sandbox.py \
  tests/integration/test_python_rule_entrypoints.py \
  tests/targets/python/test_domain_rules.py \
  tests/targets/javascript/test_domain_rules.py \
  tests/targets/javascript/test_rule_source_api.py
```

单独执行真实图形测试时，指向已经按 `tools/mermaid-renderer/package-lock.json` 安装的渲染器目录：

```bash
VIBEFLOW_MERMAID_RENDERER_ROOT=/path/to/renderer \
  python tools/run_tests.py -- tests/integration/test_domain_svg_sandbox.py
```

测试默认使用临时工作区，检查当前配置、已使用实现及源码闭包。新增资源组与既有接口组的独立命令和 475 项资源验收记录见[资源沙箱](resources/README.md)；两组均接入完整验证。

基线 current-only 对照和新接口沙箱已接入完整门禁；独立重跑如下。历史观察冻结，不匹配及观察错误均返回非零：

```bash
python sandbox/rule_parity/run_all.py \
  --current-only \
  --work /tmp/vibeflow-rule-parity-run \
  --report /tmp/vibeflow-rule-parity-run.json
```

第二轮接口与组合补测单独执行，按锁文件准备工具链和实际 SVG 渲染器；存在当前实现问题时返回非零：

```bash
npm_config_cache=/tmp/vibeflow-npm-cache python sandbox/rule_gaps/run_all.py \
  --work /tmp/vibeflow-rule-gaps-run \
  --report /tmp/vibeflow-rule-gaps-run.json
```
