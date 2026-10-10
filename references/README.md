# Local references

This canonical directory is reserved for local reference repositories and
research material. Its contents are intentionally excluded from Git and must
not become implicit build, test, or runtime dependencies.

This file is tracked so a clean checkout preserves the directory required by
the repository quality profile.

## 目录用途与边界

仅用于：外来的参考项目及来源说明；下层第三方源码保留其自身布局，不能混入 VibeFlow 自有代码、生成物或测试报告。

- 第三方项目保持上游目录布局；来源说明维护在本目录，不改写外来项目的 README。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](../docs/maintainers/directory-layout.md)。
