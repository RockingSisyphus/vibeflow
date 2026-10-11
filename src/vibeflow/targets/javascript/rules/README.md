<!-- vibeflow-directory-purpose -->
# src/vibeflow/targets/javascript/rules

## 目录用途与边界

仅用于：JavaScript 内置 Rule 声明、检查实现和内置 Plugin 装配；图检查归 graph，节点源码检查归 node，Ruleset 归同级 rulesets。

- 运行日志、缓存、依赖安装和候选构建放在仓库外临时工作区。
- 新文件按职责归置；过时内容由 Git 历史追溯，不保留旧路径兼容层。

完整归位规则见[仓库目录职责](../../../../../docs/maintainers/directory-layout.md)。
