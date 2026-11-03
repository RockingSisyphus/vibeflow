<!-- vibeflow-directory-purpose -->
# python / 并发、补位与清理

真实 12 个工作项分别以容量 12、4 和默认 8 执行。业务节点的开始及清理日志验证峰值和清理后的增量补位，输出收据验证工作完整性；回收兼分发及断图配置由正式检查命令拒绝。

本目录保存真实使用工程、配置与独立预期；驱动和断言按功能统一在 tests/e2e，不保留单独总包或探针。测试复制输入至仓库外工作区后进行修改、构建和运行。

功能域回归入口：

```bash
python tools/run_tests.py -- tests/e2e/test_concurrency.py
```

完整验收及其他平台场景见[测试覆盖](../../TEST_COVERAGE.md)和[开发与验证](../../../docs/maintainers/development.md)。新增目录同步说明职责；运行日志、依赖和构建产物不写入本目录。
