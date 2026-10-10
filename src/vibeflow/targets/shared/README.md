<!-- vibeflow-directory-purpose -->
# src/vibeflow/targets/shared

## 目录用途与边界

仅用于：确实由多个 Target 复用的绑定和事实辅助逻辑；不作为语言实现的转发层。

- 新文件按上述用途归属；新增子目录同时写明职责，不能作为临时收纳箱。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](../../../../docs/maintainers/directory-layout.md)。
