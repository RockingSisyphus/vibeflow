<!-- vibeflow-directory-purpose -->
# python / 最小 SDK 项目

正式声明、配置及纯 helper 构成的最小接入示例，供正常构建、应用宿主与隔离交付验证；修改 helper 的效果由端到端输出确认。

本目录保存真实使用工程、配置与独立预期；驱动和断言按功能统一在 tests/e2e，不保留单独总包或探针。测试复制输入至仓库外工作区后进行修改、构建和运行。

功能域回归入口：

```bash
python tools/run_tests.py -- tests/e2e/test_deployment.py tests/e2e/test_javascript.py
```

完整验收及其他平台场景见[测试覆盖](../../TEST_COVERAGE.md)和[开发与验证](../../../docs/maintainers/development.md)。新增目录同步说明职责；运行日志、依赖和构建产物不写入本目录。
