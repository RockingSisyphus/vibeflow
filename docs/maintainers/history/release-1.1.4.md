# VibeFlow 1.1.4

## 中文更新日志

本版以 v1.1.2 为基线，修复 HTML 浏览器中 Nodeset / Loop 展开后仍显示原调用卡片、看起来像断路的问题。

- 展开后隐藏原卡片，调用名称和完整说明作为分组标题、副标题显示在外框顶部，自动换行并预留高度。
- 内部子图直接展示在标题下方，外部连边继续连接分组边界，保留调用的有效填充色、边框色和文字色。
- 标题、边界及内部节点均可拖动画布、选中或右键操作；收起后恢复原节点卡片。重复调用仍按完整调用路径独立展开。
- 同步维护文档与真实浏览器回归，覆盖嵌套 Nodeset、Loop、标题拖拽、原地收起及锚点保持。

两个 profile 继续预装可直接离线打开的 HTML 入口，不携带开发历史。Workflow ABI v8、AOT manifest v3、快照 v2 保持不变，无业务配置迁移；SVG 仍为可选对照，AOT 执行不生成报告。

## English release notes

Fix expanded Nodeset / Loop groups retaining a disconnected-looking invocation card.

- Replace the expanded card with the call name and full description in the group header, wrapping text and reserving its layout height.
- Keep the inner graph below the header and external edges attached to the group boundary. Preserve effective fill, border and text colors.
- Keep panning, selection, context-menu collapse, anchor stability and independent repeated-call expansion. Collapsing restores the original card.
- Update maintenance guidance and real browser regressions for nested calls, loops and header interactions.

Both distribution profiles retain their ready-to-open offline HTML entry and ship without development history. Workflow ABI v8, AOT manifest v3 and snapshot v2 remain unchanged. SVG is optional; AOT execution remains report-free.

[完整比较 / Full comparison: v1.1.2 → v1.1.4](https://github.com/RockingSisyphus/vibeflow/compare/v1.1.2...v1.1.4)

## 发行验证 / Release verification（2026-10-20）

- 预览、planned、发行构建、两个 profile、包内提示词与文档等相关回归 **66／66 通过**，项目质检通过。
- 两个正式 ZIP 解压到中文及空格路径，在运行命令前直接离线打开空历史页面；随后向包内原有页面提供两端编译后的嵌套工作流事实，完整浏览器验收通过，覆盖 14 种形状、重复与深层调用、Loop、标题和内部拖拽、原地收起、锚点稳定、历史、关联与视图切换。无页面错误、缺失初始资源或联网请求，用户配置保持原样。
- 首次构建因前一轮验证遗留的两处 Python 字节码缓存被拒绝；清理生成缓存后构建与质检通过，未改变源码或测试判定，原失败日志保留。
- 本次为定向与发行专项验证，没有重复本地完整门禁；推送后由 GitHub CI 运行 Node 22 / 24 完整检查，状态单独报告。日志位于仓库旁 `VibeFlow-evidence/release-1.1.4-20261020`。

All 66 selected preview/planned/distribution regressions and repository quality checks passed. Both formal archives were extracted under paths containing spaces and Chinese characters. Their bundled pages passed offline empty-history checks and full interactions with Python/JavaScript compiled nested workflow facts, without replacing the packaged viewer assets. Both passed all 14 shapes, nested/loop expansion, header panning, collapse, anchor stability, history and view checks, with no page errors or network requests. An initial build stopped on generated Python bytecode caches; removing those caches resolved it without source changes. These are targeted and release-specific checks; the Node 22/24 full CI result is reported separately.
