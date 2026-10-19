<!-- vibeflow-directory-purpose -->
# docs/assets

## 目录用途与边界

仅用于：被开发文档引用的图片、图表、工作簿等正文附件；不放独立代码或一次运行的输出。

- 新文件按上述用途归属；新增子目录同时写明职责，不能作为临时收纳箱。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](../maintainers/directory-layout.md)。

## 首页流程图

`comprehensive_flowchart.mmd` 和 `.svg` 来自 `sandbox/python/integration/project/configs/pass_comprehensive_flowchart.jsonc`。更新时将该 integration 项目复制到仓库外工作区，使用当前 src 的 `export-mermaid --workspace <副本>/vibeflow_config.jsonc --config <副本>/project/configs/pass_comprehensive_flowchart.jsonc --hide-contract --output <mmd>`，再用 `tooling.presentation.mermaid.render_mermaid_svg` 渲染同份文本。仅把最终两个正文附件复制回本目录；临时副本和渲染中间文件用完删除。图片是当前配置的静态概览，交互与历史以 HTML 预览为准。
