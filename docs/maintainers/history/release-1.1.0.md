# VibeFlow 1.1.0

## 中文更新日志

本版以正式版本 v1.0.2 为基线，加入独立离线工作流浏览器，并收拢架构事实与展示导出职责。

- **离线 HTML 预览。** 工作区生成 `vibeflow-preview.html`，双击即可浏览。网页唯一源码在 `tools/workflow-viewer`，通过配置指定数据目录；无需服务、网络或前端安装。页面采用紧凑的构成主义布局。
- **自主绘图与完整信息。** v2 快照携带 Architecture 事实；浏览器使用原生 SVG 卡片和离线 ELK 自主排版，不提取 Mermaid 图元。14 种形状、有效颜色、图标、调用级覆盖、计划与外部节点得到表达。节点详情包含职责、类型、参数、契约和来源；连边显示条件、数据契约及角色，区分正常流程、并发和仅传递数据的虚线。
- **交互、历史与多视图。** Nodeset / Loop 按完整调用路径独立原地展开，内部和标题均可拖动画布；缩放无固定上限，支持比例输入、搜索定位和状态恢复。审查、构建与运行历史支持筛选和手动刷新。流程、BaseLib、Plugin、Host Extension 与 workflow 关联均由事实或显式声明展示；跨 workflow 跳转选择不晚于当前记录的目标历史。
- **默认只导出数据。** 两端 `review`、`build` 及 Python 源码 `run` / `delegate-cli` 发布结构化快照；默认不启动 Mermaid。`review --with-svg` 或 `review --output FILE.svg` 显式生成独立 SVG 对照附件。`preview --reindex` 重建新版历史索引；`--preview-root` 可重定向预览产物。
- **职责与发行整理。** 共享事实、快照存储与网页安装分离；JavaScript 审查和构建共用正式事实入口。删除旧图元链路、过时转接和死代码，统一形状、样式、节点及连边事实，同步使用文档和 AI 协作协议。wheel、源码与两个发行 profile 从工具唯一维护源装配资源。
- **当前仓库质检。** GitHub CI 继续以 `tools/verify_project.py --full` 为唯一完整验证入口，覆盖 Node 22 / 24，并保留日志与分阶段结果。提交原先保留的同步图 parity 测试修正，使远端测试输入与本地完整验证一致；补齐源码规则夹具实际导入的 requests 测试依赖，修复干净 CI 环境中两项误报。

### 升级与边界

Workflow ABI 仍为 `vibeflow.workflow.v8`，AOT manifest 仍为 `vibeflow.aot-build.v3`。从 1.0.1 / 1.0.2 升级无需新增业务配置迁移。预览快照一次切换到 v2，旧预览不迁移、不兼容，请重新生成；运行日志、trace、业务输出、已登记 Architecture 文档和显式构建路径保持原有语义。更早版本仍须完成[普通图并发迁移](../../../distribution/docs/user/graph-concurrency.md#从旧任务接口迁移)。

AOT **执行**不采集架构、不运行源码检查或生成报告；开发期构建可生成一次快照。第一版运行历史只覆盖 Python 源码运行与 delegate-cli，不覆盖 JavaScript 或 AOT 运行。HTML 与 Mermaid 以语义完整和声明样式合理表达为准，不要求像素一致。

资产为 `vibeflow-distribution-1.1.0.zip`（collaborative）、`vibeflow-distribution-autonomous-1.1.0.zip` 和 `SHA256SUMS-1.1.0.txt`。两个 profile 共用内核和项目模板；历史 GitHub Release 资产保持原样。使用方式见[本地预览手册](../../../distribution/docs/user/local-preview.md)。

### 验证范围

发布准备前的最终完整批次已通过 18／18 步：pytest 4,609 项，Python / JavaScript 集成 103／103 与 50／50，规则一致性 1,219／1,219，补充场景 680／680，适配回归 207／207，布局 4／4，两端资源区分别 14／14；包括真实浏览器、性能、隔离 wheel 和双 profile 解压运行。首轮失败及修复后的完整批次分别保留，详见[清理与验收记录](../presentation-cleanup-20261019.md)。版本及发布验证单独记录，不表述为重复执行该完整批次。

## English release notes

Changes since v1.0.2. This release adds an independent offline workflow viewer and consolidates architecture facts and presentation exports.

- Open the generated `vibeflow-preview.html` directly, without a server, network or frontend installation. The configurable viewer has one maintained source under `tools/workflow-viewer` and a compact constructivist design.
- Snapshot v2 contains Architecture facts. Native SVG cards and bundled ELK draw the graph independently of Mermaid, supporting 14 shapes, effective colours, icons and call overrides. Node details include responsibilities, parameters, contracts and sources. Edges expose conditions, contracts and roles, with distinct flow, parallel and transfer-only styles.
- Expand nested/repeated Nodesets and Loops independently in place. Drag inside expanded containers, zoom without a fixed ceiling, enter a scale, search hidden calls and restore browsing state. Filter review/build/run history and switch among flow, BaseLib, Plugin, Host Extension and declared workflow relationships. Historical links never select a future snapshot.
- Default review/build and Python source run/delegate-cli export structured data without starting Mermaid. Request an optional SVG comparison with `review --with-svg` or `review --output FILE.svg`. Use `--preview-root` for another output location and `preview --reindex` to rebuild the v2 index.
- Shared facts, storage, viewer installation and target adapters have separate owners. Remove obsolete fragment extraction, forwarding layers and dead code; update user/AI documentation and package the viewer from its single source in wheels and both distribution profiles.
- GitHub CI runs the current full verification entrypoint on Node 22 and 24 and preserves logs and stage reports. The previously retained synchronous graph parity correction is now committed with the tested source. Declare the requests test dependency used by source-rule fixtures so clean CI environments reach the intended diagnostics.

Workflow ABI remains v8 and AOT manifest remains v3. No new business configuration migration is required from 1.0.1 / 1.0.2. Old preview data is incompatible with v2 and must be regenerated. Logs, trace, business outputs, registered Architecture documents and explicit build paths keep their existing meaning. AOT execution does not inspect source or generate reports. Runtime history currently covers Python source run/delegate-cli only. HTML and Mermaid preserve semantics and declared style intent rather than pixel identity.

Assets include collaborative and autonomous ZIPs plus SHA256SUMS. Historical releases remain unchanged. Before release preparation, the final full batch passed all 18 stages, including 4,609 pytest cases, both target integrations, rule regressions, real browsers, performance, isolated wheel and extracted dual-profile execution. This baseline and release-specific checks are recorded separately.

[完整比较 / Full comparison: v1.0.2 → v1.1.0](https://github.com/RockingSisyphus/vibeflow/compare/v1.0.2...v1.1.0)
