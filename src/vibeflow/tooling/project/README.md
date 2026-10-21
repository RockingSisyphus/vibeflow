<!-- vibeflow-directory-purpose -->
# src/vibeflow/tooling/project

## 目录用途与边界

统一项目准备层：inventory 负责目录和 workflow 清单及发现错误；resources 负责所有权、可见性、Plugin 包和声明绑定准备；governance 负责编排 project/root 规则。preparation 在一次操作内复用这些结果。Python/JavaScript 的声明加载、实现绑定和源码分析仍归各 Target。architecture_registration 只处理已有 workflow 架构文档登记；完整项目架构序列化归 presentation/project_architecture。

- 新文件按上述用途归属；新增子目录同时写明职责，不能作为临时收纳箱。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](../../../../docs/maintainers/directory-layout.md)。
