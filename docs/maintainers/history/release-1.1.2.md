# VibeFlow 1.1.2

## 中文更新日志

本版以 v1.1.1 为基线，补齐分发包解压后的 HTML 入口交付。

- collaborative、autonomous 两个 ZIP 均直接包含根目录 `vibeflow-preview.html`、`vibeflow-preview.config.js`、`vibeflow-preview/assets/` 和空的 `vibeflow-preview/index.js`。解压后可立即双击打开，无需先运行 Python、review 或安装 Node 依赖。
- 初始历史为空，页面显示生成与刷新提示；不携带开发仓库的历史，也不为打包创建虚构的审核／构建／运行记录。使用者运行 review 后，在页面刷新历史或打开当次快照定位链接查看 workflow。
- 打包程序复用包内已有的 preview 安装命令，不另写一套 HTML 生成器；浏览器资源仍从 `tools/workflow-viewer` 的唯一维护源装配。内层资源继续支持命令安装与 wheel 使用。
- 更新包内 README、快速开始和预览手册，增加两个 profile 的“解压后、不运行任何命令就直接离线打开”浏览器检查，覆盖中文及空格路径、空索引、缺失资源和联网请求。

Workflow ABI v8、AOT manifest v3、快照 v2 保持不变，无业务配置迁移。1.1.0 / 1.1.1 旧包可运行 `python run.py preview` 安装入口；已有历史与配置仍按原有规则保留。SVG 继续作为可选对照，AOT 执行不新增报告。

资产为 `vibeflow-distribution-1.1.2.zip`（collaborative）、`vibeflow-distribution-autonomous-1.1.2.zip` 和 `SHA256SUMS-1.1.2.txt`。此前正式 Release 的资产保持原样。

使用说明见[本地预览与历史](../../../distribution/docs/user/local-preview.md)。

### 发行验证（2026-10-20）

1.1.2 相关回归 **64／64 通过**。两个正式 ZIP 解压到中文及空格路径后，在未运行任何命令前直接使用真实浏览器打开 HTML，验证空历史、全部本地资源加载、无页面异常及无联网请求；随后在两包内分别执行 Python 与 JavaScript review，并通过对应快照链接显示实际工作流，数据配置保持原样。

上一版 v1.1.1 的 Node 22 / 24 完整 CI 已通过；本次为版本及发行专项，不表述为重新执行本地 18 阶段完整门禁。构建与验证日志保存在仓库旁 `VibeFlow-evidence/release-1.1.2-20261020`。

## English release notes

Changes since v1.1.1:

- Both collaborative and autonomous archives include the root HTML entry, viewer configuration, offline assets and an empty history index. Open the page directly after extraction without first running Python/review or installing Node dependencies.
- Show a clear empty-history message initially. Do not ship development history or create synthetic review/build/run records during packaging. Run review to create real workflow snapshots, then refresh history or follow the snapshot deep link.
- Reuse the bundled preview installation command and the viewer's single maintained source. Keep embedded resources available for command installation and wheels.
- Update package guidance and test both extracted profiles in a real offline browser before any command, including paths containing spaces and Chinese characters, missing resources and network requests.

Workflow ABI v8, AOT manifest v3 and snapshot v2 remain unchanged. No business configuration migration is required. Older 1.1.0 / 1.1.1 packages can install the entry with `python run.py preview`. Existing history/configuration behavior, optional SVG comparison and report-free AOT execution remain unchanged.

Assets include both profile ZIPs and SHA256SUMS. Earlier release assets remain unchanged.

[完整比较 / Full comparison: v1.1.1 → v1.1.2](https://github.com/RockingSisyphus/vibeflow/compare/v1.1.1...v1.1.2)

Release verification passed all 64 selected regressions. Both formal ZIPs opened directly in a real offline browser from paths containing spaces and Chinese characters, with an empty history, no missing resources, no page errors and no network requests. Python and JavaScript review then generated real snapshots that opened through their deep links, preserving viewer configuration. The v1.1.1 Node 22/24 full CI baseline passed; these are release-specific checks rather than another local full 18-stage run.
