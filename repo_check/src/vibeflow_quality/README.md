<!-- vibeflow-directory-purpose -->
# repo_check/src/vibeflow_quality

## 目录用途与边界

仅用于：仓库目录、文档和架构边界检查实现；不放业务质量规则、产品 runtime 或测试输出。

- 新文件按上述用途归属；新增子目录同时写明职责，不能作为临时收纳箱。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](../../../docs/maintainers/directory-layout.md)。
