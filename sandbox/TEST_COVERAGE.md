# 沙盒与代码测试覆盖

沙盒检查公开接入和真实执行；tests 检查功能、实现与历史回归。两者由完整门禁一起运行，不因目录迁移缩减验收范围。

| 使用情境 | 实际验证入口 |
| --- | --- |
| Python 工作流、Nodeset、Loop、异步、规则入口、CLI 与资源释放 | sandbox/python/integration/run_all.py |
| JS/TS 最小 AOT、Node/browser、Capability 与 Host Extension | sandbox/javascript/minimal/run_e2e.py、sandbox/javascript/integration/run_all.py |
| Python/JS 外部规则、typed records、局部替换与领域工作流 | 两 Target 的 rule_graph、domain_rules；tests/integration/test_rule_plugin_graph.py 与两个 Target 的领域测试 |
| 多文件 Node、BaseLib、Plugin 与 JS Host | 两 Target 的 multifile_resources；tests/fixtures/rule_gaps/run_all.py --group resources |
| Python 业务日志、状态、成功、运行失败与启动失败 | sandbox/python/runtime_observation/probe.py；tests/targets/python/test_run_observation.py |
| JS/TS 状态回调、Node/browser 运行、日志与生命周期 | sandbox/javascript/runtime_observation/probe.py；Target 回归与完整门禁的浏览器步骤 |
| 内部上下文身份、只读共享、默认参数和词法身份回归 | tests/core、tests/targets/python，复用 tests/fixtures/python |
| 历史规则对照与接口组合回归 | tests/fixtures/rule_parity/run_all.py、tests/fixtures/rule_gaps/run_all.py |
| SVG 实际浏览器、布局、资源区和内部性能断言 | tests/fixtures/python/review_layout、review_performance、两个 Target 的 resource_sections |
| SDK、编译与装配、发布包来源隔离 | tests/fixtures/adaptation_regressions、wheel 和双 profile 发行验收 |

```bash
python tools/verify_project.py --full
python quality/test.py
```

完整验证按锁文件在临时工作区安装 TypeScript/esbuild 和 Mermaid/Puppeteer，实际执行图形与浏览器检查。未准备渲染器的普通 pytest 中出现的跳过，不能代替完整图形验收。

用户沙盒继续加载当前工作区源码。完整门禁另有从当前源码构建的 wheel 和两个开发包的隔离验收；这两类证据分别说明源码场景与实际交付物的行为。

历史案例矩阵与当时成绩见 [设计演进](../docs/design/history/rule-system-repair-results.md) 和 [原始证据索引](../docs/maintainers/evidence/index.md)。当前成绩以本次实际验证记录为准。
