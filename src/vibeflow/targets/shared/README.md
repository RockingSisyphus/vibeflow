<!-- vibeflow-directory-purpose -->
# src/vibeflow/targets/shared

## 目录用途与边界

仅用于：跨 Target 的事实/绑定服务、纯检查算法和装配支持；不定义具体 Target 的资源，不依赖 Python 或 JavaScript Target。

- 运行日志、缓存、依赖安装和候选构建放在仓库外临时工作区。
- 新文件按职责归置；过时内容由 Git 历史追溯，不保留旧路径兼容层。

完整归位规则见[仓库目录职责](../../../../docs/maintainers/directory-layout.md)。
