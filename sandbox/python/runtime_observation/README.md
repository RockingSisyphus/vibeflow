<!-- vibeflow-directory-purpose -->
# Python 运行观测输入

project.py 只编写正常 SDK 工程及配置，供运行观测和 SDK 配置场景复用。进程驱动与断言统一在 tests/e2e；运行数据写入仓库外的隔离工作区。

```bash
python tools/run_tests.py -- tests/e2e/test_observation.py tests/e2e/test_sdk_configuration.py
```

当前回归通过真实 CLI 验证成功、业务异常及启动失败，观察自然状态、业务控制台与内核日志，并验证新运行的状态重置。SDK 场景另行验证原生默认值、覆盖和实例隔离；Node 与浏览器的状态交互也使用各自真实应用入口。

逐域判据与实际运行边界见[测试覆盖](../../TEST_COVERAGE.md)，统一执行规则见[开发与验证](../../../docs/maintainers/development.md)。这里不维护独立 probe、报告聚合或内部状态采集器。
