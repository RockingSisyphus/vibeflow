<!-- vibeflow-directory-purpose -->
# 多 root SDK 工程

桌面与后端 root 分别声明同名私有资源；共享 Node 和 Library 使用自身目录的相对引用。两端正常构建的独立期望为 18 和 22。

本目录保存真实工程输入，没有顶层 project/：desktop/ 与 backend/ 本身就是在 vibeflow_config.jsonc 注册的业务 root。构建与检查均在工作副本执行。

功能域回归入口：

```bash
python tools/run_tests.py -- tests/e2e/test_governance.py
```

正常输出、局部与完整治理范围、规则覆盖及非法引用的判据见[测试覆盖](../../TEST_COVERAGE.md)。生成报告、预览与 AOT 产物放在仓库外工作区。
