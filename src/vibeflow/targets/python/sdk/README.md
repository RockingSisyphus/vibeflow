<!-- vibeflow-directory-purpose -->
# src/vibeflow/targets/python/sdk

## 目录用途与边界

Python Node / BaseLib / Plugin / Rule 声明与接口。loading 负责可信声明装载；source_namespace 为同次准备中的声明、实现和延迟导入提供共享的所有者模块身份。命名空间随资源准备或AOT bundle复用，业务执行不持有装载锁，不扫描或清除其他项目模块。

- 新文件按上述用途归属；新增子目录同时写明职责，不能作为临时收纳箱。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](../../../../../docs/maintainers/directory-layout.md)。
