# VibeFlow 1.1.1

## 中文更新日志

本版以 v1.1.0 为基线，修复 planned 审核展示并完善 HTML 快照交付说明。

- 卡片与侧栏综合调用和目标定义的状态：指向 planned Nodeset 的普通调用，以及使用 planned body 的 Loop，均明确显示计划状态；同时保留调用声明与目标定义的原始状态，不把规划当作运行成功。
- JavaScript 架构事实补齐 Nodeset 定义的 `planned_behavior`，调用处使用与 Python、Core 相同的有效行为解析规则，保留继承及调用级覆盖。侧栏展示有效计划行为。
- 有内部结构时可按具体调用右键展开；没有内部定义时，卡片与详情明确显示“暂无内部定义”，展开菜单禁用，不再错误提示“可展开”。重复调用的展开状态保持独立。
- 修复展开／收起或定位尚在排版时切换快照的竞态，旧操作不再更新新记录的选择状态。浏览器回归显式暂停一次布局并切换快照验证。
- 发布提示词和用户手册明确：运行 `review` 后交付 HTML 完整路径、当次 `preview_id` 及快照定位链接，说明对应 Config 与变更位置，让用户查看该 workflow；collaborative 仍在获得明确批准后实施。修正多文件资源、Nodeset 和命令手册中的默认 SVG 审核示例，SVG 只作显式请求的可选对照。

Workflow ABI 仍为 v8，AOT manifest 仍为 v3，快照仍为 v2；无业务配置迁移。1.1.0 中 JavaScript 已保存的快照缺失的计划行为不能凭空补写，重新执行 `review` 生成完整事实即可，旧历史保留。AOT 执行不生成报告；本版不改变调度、计划行为执行语义或运行历史范围。

资产为 `vibeflow-distribution-1.1.1.zip`（collaborative）、`vibeflow-distribution-autonomous-1.1.1.zip` 和 `SHA256SUMS-1.1.1.txt`。两个 profile 共用内核和项目模板；1.1.0 与更早的 GitHub Release 资产保持原样。

使用方式见[本地预览与历史](../../../distribution/docs/user/local-preview.md)及[人机协同协议](../../../distribution/docs/user/profiles/collaborative.md)。

### 发行验证（2026-10-20）

相关定向回归 **147／147 通过**，覆盖架构事实、审核命令、既有浏览交互、两个 profile 的文档与发布适配；此前的 27 项专项复验通过。真实浏览器验证两端 planned Node、有／无 body 的 Nodeset、重复实例独立展开、Loop、计划行为覆盖，以及暂停布局后切换快照。首次有效批次为 146 通过／1 失败，暴露并修复异步选择竞态；随后专项中的一次测试前置等待问题也修正，原始失败日志独立保留。

使用仓库 `distribution/build.py` 构建两个正式 ZIP。实际解压后，两包均通过内核加载、Python 审查／源码运行／AOT 构建执行、JavaScript 审查／构建／运行，以及使用包内模块生成的 Python / JavaScript planned 快照页面验证。确认包内提示词交付快照链接、SVG 仅为可选，AOT 执行不新增预览记录。1.1.1 wheel 隔离安装执行通过，仓库质检通过。

本次验收为修复与发行专项，不表述为重新执行此前 18 阶段完整门禁。日志保存在仓库旁 `VibeFlow-evidence/release-1.1.1-20261020`；GitHub CI 对推送后的提交独立执行完整门禁，其状态以 Actions 实际结果为准。

## English release notes

Changes since v1.1.0:

- Show planned status for calls targeting planned Nodesets and Loops using planned bodies. Preserve the original call and definition statuses separately; implementation and execution evidence remain distinct.
- Export JavaScript Nodeset planned behavior and resolve effective call behavior with the existing shared Core rule, matching Python inheritance and call overrides. Display it in the inspector.
- Expand available internals in place, independently for repeated calls. Definitions without a body show an explicit message and a disabled expansion action rather than a misleading expandable label.
- Ignore stale expansion/location completions after switching snapshots, preventing errors and changes to the new record selection.
- Prompts and user documentation deliver the actual HTML review entry, snapshot ID and deep link, identify the relevant workflow and changes, and ask the user to inspect that snapshot. Collaborative approval remains explicit. SVG is an optional comparison; remove default SVG-centric review examples.

Workflow ABI v8, AOT manifest v3 and snapshot v2 remain unchanged. No business configuration migration is needed. Regenerate 1.1.0 JavaScript snapshots with review to obtain previously missing planned behavior facts; retain existing history. AOT execution does not generate reports. Scheduling and planned execution behavior are unchanged.

Assets include collaborative and autonomous ZIPs plus SHA256SUMS. Earlier release assets remain unchanged.

[完整比较 / Full comparison: v1.1.0 → v1.1.1](https://github.com/RockingSisyphus/vibeflow/compare/v1.1.0...v1.1.1)

Release verification passed all 147 selected regressions, the focused 27-case browser/data checks, isolated 1.1.1 wheel installation, and extracted execution of both formal profiles. Each extracted package generated and displayed planned snapshots for both Targets offline, including repeated/Loop expansion and interrupted layout. AOT execution added no preview records. Earlier failed attempts remain recorded separately; this is release-specific validation, not a repeat of the earlier full 18-stage batch.
