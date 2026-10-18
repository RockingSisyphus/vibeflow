# VibeFlow 1.0.2

## 中文更新日志

本版以正式版本 v1.0.1 为基线，修复并发节点图形回退为普通矩形的问题。

- 普通 process 节点按实际调度边识别分发，以及多前驱 `join_policy: all` 回收，恢复双圆默认图形。它们仍是普通图节点，不恢复旧任务管理类型或特殊边界。
- Python 与 JavaScript 的 Architecture、Mermaid 和 SVG 共用展示级联；保留 Node 声明及调用级形状覆盖、外部节点颜色，以及终端、判断和复合节点原有图形。纯数据边与 safe_any 汇合不会误用并发图形。
- 调度器、默认 8 的局部并发容量、排队补位和断路／回收兼分发检查保持不变。开发者与用户文档同步更新。

### 升级与资产

Workflow ABI 仍为 `vibeflow.workflow.v8`，AOT manifest 仍为 `vibeflow.aot-build.v3`。从 1.0.1 升级无需新增配置迁移，重新生成 Architecture 和 SVG 即可。1.0.0 及更早版本仍须完成[普通图并发迁移](../../../distribution/docs/user/graph-concurrency.md#从旧任务接口迁移)并重建计划及 AOT 产物。

资产为 `vibeflow-distribution-1.0.2.zip`（collaborative）、`vibeflow-distribution-autonomous-1.0.2.zip` 和 `SHA256SUMS-1.0.2.txt`。两个 profile 共用内核与最小项目，历史 Release 资产保持原样。

### 验证范围

SVG 修复此前通过 21 项专项与 91 项相关回归，覆盖两端真实 SVG 中分发与回收各有两个圆、正常展示覆盖及其他节点图形。本次发行验证独立记录，不表述为重新执行原 18 阶段全量。

2026-10-18 发行专项 52 项全部通过。两个正式 ZIP 与隔离部署验证使用的 ZIP 逐字节一致，15 份 canonical 文档的集合及内容均匹配；两包内核一致。双 profile 验证内核、Python AOT API／无源码 CLI 及 Node 构建运行，1.0.2 wheel 隔离安装与运行通过。实际解压的两包均从包内 kernel ZIP 加载生产模块，验证 Python 和 JavaScript 真实 SVG 中分发与回收各有两个圆，并验证展示覆盖和排除情形。验证日志位于仓库外 `vibeflow-release-1.0.2-20261018`，不写入发行包或用户桌面。

## English release notes

Changes since v1.0.1. This release fixes ordinary parallel nodes falling back to rectangles.

- Restore default double-circle shapes for process dispatch nodes and multi-predecessor all-join collectors, inferred from normal scheduling edges. These remain ordinary graph nodes.
- Python and JavaScript Architecture, Mermaid and SVG outputs share the presentation cascade. Explicit shape overrides, external-node colours and other native node shapes remain supported. Transfer-only edges and safe-any merges do not receive these defaults.
- Scheduling, per-dispatch capacity (default 8), incremental refill and graph rejection rules are unchanged. Developer and user documentation describe the rendering fix.

Workflow ABI remains v8 and the AOT manifest remains v3. Upgrading from 1.0.1 requires regenerating Architecture and SVG outputs, with no additional configuration migration. Earlier releases still require the graph concurrency migration and rebuilt plans/AOT artifacts. Assets include collaborative and autonomous ZIPs plus SHA256SUMS; historical assets remain unchanged.

The fix previously passed 21 focused and 91 related regressions, including real SVG checks for both renderers. Release verification is separate from the original 18-stage acceptance batch.

Release verification on 2026-10-18 passed all 52 selected tests. Both formal archives are byte-identical to those used by isolated dual-profile deployment, Python AOT API/source-free CLI and Node checks. All 15 selected canonical documents match exactly. The 1.0.2 wheel passed isolated installation and execution. Both extracted packages loaded production modules from their kernel ZIP and passed real Python/JavaScript SVG checks for both double-circle nodes, overrides and exclusions.

[完整比较 / Full comparison: v1.0.1 → v1.0.2](https://github.com/RockingSisyphus/vibeflow/compare/v1.0.1...v1.0.2)
