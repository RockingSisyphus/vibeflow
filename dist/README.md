<!-- vibeflow-directory-purpose -->
# dist

## 目录用途与边界

仅用于：最新正式 collaborative / autonomous 发行目录、对应 ZIP 和校验清单；候选构建、测试结果与依赖安装归仓库外工作区。

- 发行目录由构建器生成，不手工增删其内容；目录职责由本说明统一约束。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](../docs/maintainers/directory-layout.md)。
