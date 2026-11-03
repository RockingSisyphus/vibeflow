<!-- vibeflow-directory-purpose -->
# tools

## 目录用途与边界

用于仓库开发、验证、清理、渲染、辅助脚本，以及随发行物交付的独立 workflow-viewer；产品 CLI 归 src/vibeflow/tooling，构建发行包的入口归 distribution。

- 新文件按上述用途归属；新增子目录同时写明职责，不能作为临时收纳箱。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](../docs/maintainers/directory-layout.md)。

测试通过 run_tests.py 统一调度 tests/e2e；verify_project.py 在同一批次中加上仓库检查、语法编译、交付物安装和清理预览。两者共用隔离环境与按文件调度。详细命令见[开发与验证](../docs/maintainers/development.md)。不在 tools 或 sandbox 中新增独立重复总包。
