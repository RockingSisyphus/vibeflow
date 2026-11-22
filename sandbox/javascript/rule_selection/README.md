<!-- vibeflow-directory-purpose -->
# javascript / 规则选择

真实 SDK Rule/Ruleset 声明和配置，检查默认选择、显式覆盖、空选择、嵌套与有效作用域；诊断必须属于目标规则。

本目录保存真实使用工程、配置与独立预期；驱动和断言按功能统一在 tests/e2e，不保留单独总包或探针。测试复制输入至仓库外工作区后进行修改、构建和运行。

功能域回归入口：

```bash
python tools/run_tests.py -- tests/e2e/test_selection.py
```

完整验收及其他平台场景见[测试覆盖](../../TEST_COVERAGE.md)和[开发与验证](../../../docs/maintainers/development.md)。新增目录同步说明职责；运行日志、依赖和构建产物不写入本目录。
