<!-- vibeflow-directory-purpose -->
# javascript / 多文件资源

Library、Plugin、Node 的声明与实现分别位于真实文件。测试修改 helper 后正常重新构建，再恢复输入，检查输出 6→8→6；字面路径按实际语言构建。

本目录保存真实使用工程、配置与独立预期；驱动和断言按功能统一在 tests/e2e，不保留单独总包或探针。测试复制输入至仓库外工作区后进行修改、构建和运行。

功能域回归入口：

```bash
python tools/run_tests.py -- tests/e2e/test_resources.py
```

完整验收及其他平台场景见[测试覆盖](../../TEST_COVERAGE.md)和[开发与验证](../../../docs/maintainers/development.md)。新增目录同步说明职责；运行日志、依赖和构建产物不写入本目录。
