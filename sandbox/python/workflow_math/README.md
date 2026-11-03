<!-- vibeflow-directory-purpose -->
# python / 嵌套与循环数学

真实小整数 Node、BaseLib、Nodeset 与循环配置。retry 从 1 连加三次 2 得到 7；nested 的独立期望为 (4+6)×2+5=25。停止条件、carry、输出及正常运行日志由功能测试检查。

本目录保存真实使用工程、配置与独立预期；驱动和断言按功能统一在 tests/e2e，不保留单独总包或探针。测试复制输入至仓库外工作区后进行修改、构建和运行。

功能域回归入口：

```bash
python tools/run_tests.py -- tests/e2e/test_execution.py
```

完整验收及其他平台场景见[测试覆盖](../../TEST_COVERAGE.md)和[开发与验证](../../../docs/maintainers/development.md)。新增目录同步说明职责；运行日志、依赖和构建产物不写入本目录。
