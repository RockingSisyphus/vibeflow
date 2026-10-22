<!-- vibeflow-directory-purpose -->
# tools/mermaid-renderer

## 目录用途与边界

仅用于：仓库使用的 Mermaid 渲染器依赖声明与配置；安装依赖、浏览器下载和 SVG 输出使用仓库外工作区。

- 新文件按上述用途归属；新增子目录同时写明职责，不能作为临时收纳箱。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](../../docs/maintainers/directory-layout.md)。

直接依赖固定版本，传递依赖由 package-lock.json 固定。更新渲染链后复用现有 SVG 布局、资源视图与真实浏览器回归核对输出。

KaTeX 仍受 Mermaid / CLI 的 `^0.16` 依赖范围约束；上游 [GHSA-238p-pmpm-9mq7](https://github.com/KaTeX/KaTeX/security/advisories/GHSA-238p-pmpm-9mq7) 的修补版本为 0.18.2。该低等级告警要求已有原型污染或攻击者可影响渲染选项原型等前提，不代表已证明本项目存在可利用路径。后续渲染链支持修补版本时同步更新并复验。
