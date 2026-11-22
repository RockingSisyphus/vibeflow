<!-- vibeflow-directory-purpose -->
# javascript / Workflow 协作数学

真实 A/B/C 数学 Node 项目；tests/e2e/cooperation.py 只编写正常 workflow 输入并复用正式协作模板。正常构建所得产物通过应用 Coordinator、HTTP、Node 和浏览器按钮运行，覆盖独立实例、消息、取消、错误及清理。

本目录保存真实使用工程、配置与独立预期；驱动和断言按功能统一在 tests/e2e，不保留单独总包或探针。测试复制输入至仓库外工作区后进行修改、构建和运行。

功能域回归入口：

```bash
python tools/run_tests.py -- tests/e2e/test_cooperation.py tests/e2e/test_cooperation_javascript.py tests/e2e/test_cooperation_http.py
```

完整验收及其他平台场景见[测试覆盖](../../TEST_COVERAGE.md)和[开发与验证](../../../docs/maintainers/development.md)。新增目录同步说明职责；运行日志、依赖和构建产物不写入本目录。
