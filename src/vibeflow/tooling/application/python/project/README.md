<!-- vibeflow-directory-purpose -->
# src/vibeflow/tooling/application/python/project

## 目录用途与边界

仅用于：Python 应用层项目准备与导出协调；共用路径模型归 tooling/project。

- 新文件按上述用途归属；新增子目录同时写明职责，不能作为临时收纳箱。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](../../../../../../docs/maintainers/directory-layout.md)。

声明加载与运行统一使用 Python SDK 的 `source_paths` 管理导入路径作用域；`lifecycle.py` 只负责创建所选插件，实例释放由 Target 的 `plugin_lifetime` 负责。工作区数据模型和诊断分别以 `tooling.project.workspace_model`、`tooling.project.diagnostic_sink` 为权威来源。`core.py` 保留现有公开便捷入口，注册表与配置加载直接指向权威实现。
