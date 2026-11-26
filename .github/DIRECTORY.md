<!-- vibeflow-directory-purpose -->
# .github

本文件使用 DIRECTORY.md，避免被 GitHub 优先选为仓库首页 README。

## 目录用途与边界

用于 GitHub 的 CI、Issue 与 Pull Request 配置，以及根 README 引用的项目展示图。本地执行输出和产品实现各归所属目录。

- 新文件按上述用途归属；新增子目录同时写明职责，不能作为临时收纳箱。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](../docs/maintainers/directory-layout.md)。
