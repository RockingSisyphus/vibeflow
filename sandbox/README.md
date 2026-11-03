<!-- vibeflow-directory-purpose -->
# 真实使用项目

python/、javascript/ 保存公开 SDK 声明、业务源码、配置和独立预期，供正常 CLI、应用宿主及端到端测试使用。这里不再维护独立总包、内部探针或转发测试壳。

功能域的驱动与断言统一在 tests/e2e，具体回归输入以测试入口为准。测试先复制项目到隔离工作区，再进行构建、修改及运行；不改写原始示例。

```bash
python tools/run_tests.py -- tests/e2e/test_comprehensive.py
python tools/verify_project.py --full --workers 4
```

目录职责见[仓库目录职责](../docs/maintainers/directory-layout.md)，逐域入口与验收边界见[测试覆盖](TEST_COVERAGE.md)。
