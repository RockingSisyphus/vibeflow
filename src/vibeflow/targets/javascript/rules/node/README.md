<!-- vibeflow-directory-purpose -->
# src/vibeflow/targets/javascript/rules/node

## 目录用途与边界

仅用于：JavaScript 节点源码 Rule 声明和实现绑定；宿主进程与源码事实服务归 build。

- 运行日志、缓存、依赖安装和候选构建放在仓库外临时工作区。
- 新文件按职责归置；过时内容由 Git 历史追溯，不保留旧路径兼容层。

完整归位规则见[仓库目录职责](../../../../../../docs/maintainers/directory-layout.md)。
