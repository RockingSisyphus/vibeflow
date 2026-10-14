# 沙盒与代码测试覆盖

沙盒检查公开接入和真实执行；tests 检查功能、实现与历史回归。两者由完整门禁一起运行，不因目录迁移缩减验收范围。

| 使用情境 | 实际验证入口 |
| --- | --- |
| 原生任务引用数组、任务管理 Node、失败作为结果、协作停止与实际退出、名单中转、Node／Chromium 两种 AOT profile | 两 Target 的 task_management/run_all.py，integration 与根目录 `--full`；机制屏障回归见两个 Target 的 test_task_management.py |
| 跨 root Nodeset 任务目标源码归属，planned/implemented 对照及真实未登记导入 | JavaScript task_management/run_ownership.py 独立静态复现；当前保留待修复失败，未纳入既有全量通过分母 |
| 综合数学应用：自定义源码 Rule、typed records、warning 对照、配置覆盖、分支/汇合、Nodeset/Loop、Port 与复用并发 | 两 Target 的 comprehensive_math/run_all.py；各 integration runner 自动执行；[公式与通过判定](../docs/maintainers/comprehensive-math-sandbox.md) |
| 简单数学使用场景：CLI、对象、插件修改、异步/Port | 五个 addition 独立入口；各 integration runner 自动执行；[替代与通过判定](../docs/maintainers/history/audits/addition-sandboxes-20261009.md) |
| 嵌套数学工作流：条件/固定的内外层循环、carry/collect、编译源码、hooks、trace、TaskPlan、调度/数据边和超限诊断 | 两 Target 的 workflow_math/run_all.py；integration 自动执行；[19 项替代与通过判定](../docs/maintainers/history/audits/workflow-math-20261010.md) |
| 同一起终点的不同条件边：成功/失败均收尾，顺序无关，完全重复与重叠条件不重复执行 | JavaScript workflow_math/conditional_routes.py；八次真实 AOT 构建、二十四次 Node.js 调用；integration 与根目录 `--full` 自动执行；[场景与判定](javascript/workflow_math/README.md) |
| 分段数学工作流：直线、互斥分支、多终点、按类型汇合、数据旁路、编译源码和 trace | Python piecewise_math/run_all.py；integration 自动执行；[11 项替代与通过判定](../docs/maintainers/history/audits/piecewise-math-20261010.md) |
| Python 工作流、Nodeset、Loop、异步、规则入口、CLI 与资源释放 | sandbox/python/integration/run_all.py |
| JS/TS 最小 AOT、Node/browser、Capability 与 Host Extension | sandbox/javascript/minimal/run_e2e.py、sandbox/javascript/integration/run_all.py |
| Python/JS 外部规则、typed records、局部替换与领域工作流 | 两 Target 的 rule_graph、domain_rules；tests/integration/test_rule_plugin_graph.py 与两个 Target 的领域测试 |
| Workflow 静态默认与动态替代、Nodeset 接管、Node 调用选择、空选择、本层与整体范围 | 两 Target 的 rule_selection/run_all.py；integration 自动执行；三份配置逐项断言规则标识、负责路径、Records 绑定、执行次数及局部资料边界 |
| 多文件 Node、BaseLib、Plugin 与 JS Host | 两 Target 的 multifile_resources；tests/fixtures/rule_gaps/run_all.py --group resources |
| Python 业务日志、状态、成功、运行失败与启动失败 | sandbox/python/runtime_observation/probe.py；tests/targets/python/test_run_observation.py |
| JS/TS 状态回调、Node/browser 运行、日志与生命周期 | sandbox/javascript/runtime_observation/probe.py；Target 回归与完整门禁的浏览器步骤 |
| 内部上下文身份、只读共享、默认参数和词法身份回归 | tests/core、tests/targets/python，复用 tests/fixtures/python |
| 历史规则对照与接口组合回归 | tests/fixtures/rule_parity/run_all.py、tests/fixtures/rule_gaps/run_all.py |
| SVG 实际浏览器、布局、资源区和内部性能断言 | tests/fixtures/python/review_layout、review_performance、两个 Target 的 resource_sections |
| SDK、编译与装配、发布包来源隔离 | tests/fixtures/adaptation_regressions、wheel 和双 profile 发行验收 |

```bash
python tools/verify_project.py --full
python repo_check/test.py
```

完整验证按锁文件在临时工作区安装 TypeScript/esbuild 和 Mermaid/Puppeteer，实际执行图形与浏览器检查。未准备渲染器的普通 pytest 中出现的跳过，不能代替完整图形验收。

用户沙盒继续加载当前工作区源码。完整门禁另有从当前源码构建的 wheel 和两个开发包的隔离验收；这两类证据分别说明源码场景与实际交付物的行为。

历史案例矩阵与当时成绩见 [设计演进](../docs/design/history/rule-system-repair-results.md) 和 [原始证据索引](../docs/maintainers/evidence/index.md)。当前成绩以本次实际验证记录为准。
