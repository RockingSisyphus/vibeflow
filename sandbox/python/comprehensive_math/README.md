<!-- vibeflow-directory-purpose -->
# python / 综合数学应用

独立 SDK 项目，包含 Plugin、typed-record Rule、多文件 BaseLib、两层 Nodeset、分支、汇合及 while 循环。完整公式、六组独立预期和规则修正对照见[共用说明](../../../docs/maintainers/comprehensive-math-sandbox.md)。

本目录保存真实使用工程、配置与独立预期；驱动和断言按功能统一在 tests/e2e，不保留单独总包或探针。测试复制输入至仓库外工作区后进行修改、构建和运行。

功能域回归入口：

```bash
python tools/run_tests.py -- tests/e2e/test_comprehensive.py
```

完整验收及其他平台场景见[测试覆盖](../../TEST_COVERAGE.md)和[开发与验证](../../../docs/maintainers/development.md)。新增目录同步说明职责；运行日志、依赖和构建产物不写入本目录。
