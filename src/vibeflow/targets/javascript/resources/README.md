<!-- vibeflow-directory-purpose -->
# src/vibeflow/targets/javascript/resources

## 目录用途与边界

仅用于：随内核分发的 JavaScript SDK、ABI、类型声明、运行辅助及分析驱动源文件；独立通信适配放在 coordination 子目录；identity.py 提供本次核心文件身份及业务事实投影，复用现有资源清单，不引入使用政策；不放 npm 安装结果。

- 新文件按上述用途归属；新增子目录同时写明职责，不能作为临时收纳箱。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](../../../../../docs/maintainers/directory-layout.md)。
