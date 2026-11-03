<!-- vibeflow-directory-purpose -->
# javascript / 应用功能项目

真实 SDK 项目与配置，提供配置覆盖、条件控制、嵌套循环、活对象、存储、资源、计划状态和应用端口等输入。执行、会话生命周期、错误和真实页面交互分别由对应功能域测试负责。

本目录保存真实使用工程、配置与独立预期；驱动和断言按功能统一在 tests/e2e，不保留单独总包或探针。测试复制输入至仓库外工作区后进行修改、构建和运行。

功能域回归入口：

```bash
python tools/run_tests.py -- tests/e2e/test_execution.py tests/e2e/test_javascript.py tests/e2e/test_session_behaviors.py tests/e2e/test_preview.py
```

完整验收及其他平台场景见[测试覆盖](../../TEST_COVERAGE.md)和[开发与验证](../../../docs/maintainers/development.md)。新增目录同步说明职责；运行日志、依赖和构建产物不写入本目录。
