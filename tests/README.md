<!-- vibeflow-directory-purpose -->
# tests

所有维护的测试统一放在 `e2e/`，按用户功能组织。真实 SDK 示例归 sandbox，案例输入、薄驱动和普通宿主应用归 e2e 对应目录。一次运行的输出与依赖放在仓库外工作区。

通过 `python tools/run_tests.py` 运行；完整交付验收使用 `python tools/verify_project.py --full`。测试边界、环境及批次规则见[开发与验证](../docs/maintainers/development.md)，逐域判据见[测试覆盖](../sandbox/TEST_COVERAGE.md)。
