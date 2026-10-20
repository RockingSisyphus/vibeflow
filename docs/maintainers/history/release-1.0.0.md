# VibeFlow 1.0.0

## 中文更新日志

本版以此前正式版本 v0.20.0 为基线，包含统一编译计划、Python AOT 与跨模块维护整理。

- Python 新增 `python-package` 目录 AOT，随附匹配框架、项目实现与资源，支持搬离原 workspace 运行；提供 `build_python_aot()`、`load_bundle()`、`create_runtime()`、`run()` 和独立 `run.py`，包括 delegated CLI。Python、PyTorch/CUDA、外部数据和 checkpoint 由目标环境提供；动态资源通过重复 `--include` 收集。
- Python 源码与 bundle 共用计划装配及现有 runtime，保留 plan/block/compiled、原生任务、取消与收尾、锁、对象引用、插件和运行观测。静态审查与编译插件在构建时运行，bundle 不再执行源码检查、图编译、计划推导、块代码生成或架构图生成。Node 在运行时插件初始化后绑定。
- Python 与 JS 共用调用身份、配置作用域、WorkflowPlan/BlockPlan 和构建暂存/发布/失败清理。Rule 的声明审查范围与实际执行范围保持区别。JS 保留原生 emitter、esbuild 和 Node/Browser profile。
- 清理重复计划推导、配置合并、导入政策转换、模块加载、路径管理和跨层转发；统一插件失败收尾、CLI 选项及执行报告。修复 namespace 缓存污染、只读 Mapping 默认值合并和部分插件创建失败后的释放问题。有效公开契约、必要平台适配及历史验收资料保留。
- 同步开发和用户文档、最小项目、模板、发行验证及迁移说明。

### 迁移

Workflow ABI 从 v6 升为 `vibeflow.workflow.v7`，AOT manifest 从 v2 升为 `vibeflow.aot-build.v3`；语言专属信息位于 `target_metadata`。旧计划与构建目录须用当前源码重新构建，不提供旧格式兼容解码。已有独立 JS 产物可继续使用其随附 runtime。旧调用级 async/result_key 入口仍明确报告迁移错误，使用原生任务管理接口。

### 验证与资产

功能实现冻结后的完整验收 18/18 通过：pytest 4538、Python 沙箱 104/104、JS 真实 Browser 集成 50/50、规则对照 1223/1223、补充规则 680/680、迁移回归 207/207，并覆盖 wheel 和双 profile 隔离部署。历史失败和后续复验分别保留，见[实施记录](aot-unification-implementation.md)。本次 1.0.0 的版本、文档及正式 ZIP 部署另行复验，不把前一批次改称新全量。

发布资产为 collaborative、autonomous 两种 ZIP 及 `SHA256SUMS-1.0.0.txt`。小型 CPU 探针的启动中位数约 385 → 236 ms，重复执行约 0.63 ms，未观察到重复执行收益；不是 GPU 吞吐结论。

2026-10-16 发行复验：仓库质量检查通过；版本、分发配置、文档、历史归档及 CLI dispatch 共 61 项测试通过；1.0.0 wheel 安装隔离、两种 profile 的真实 ZIP 解压、Python AOT 的 API/独立 CLI 与 JS 构建执行通过。正式构建的两个 ZIP 与隔离验证的 ZIP 逐字节一致。证据保存于工作区外 `VibeFlow-evidence/release-1.0.0-20261016/`。首轮依赖准备受代理影响而中止，未运行测试；其日志单独保留。后续发行命令仅在自身进程中采用直连，未修改系统代理设置。

## English release notes

Changes since v0.20.0:

- Relocatable Python AOT directory packages include the matching framework, project implementations, resources, prepared plans and generated blocks. Public build/load/runtime APIs and standalone run/delegated CLI entry points are included. The destination supplies Python and external dependencies such as PyTorch/CUDA, datasets and checkpoints.
- Source and AOT share the existing Python runtime and plan assembly, including all three execution modes, native tasks, cancellation, teardown, locks, object references, plugins and observation. Bundle execution does not repeat source review or compilation. Runtime plugins initialize before Node binding.
- Shared workflow call identities, configuration scopes, portable plans and build orchestration replace duplicated paths. JS retains its native emitter, esbuild and Node/Browser profiles. Declaration review remains distinct from actual execution.
- Removed obsolete forwarding layers and duplicated configuration, import, path and result handling. Fixed module-cache isolation, read-only option overlays and partial plugin-construction teardown. Necessary public APIs and platform support remain.

Workflow ABI is now v7 and the AOT manifest is v3, with language-specific fields under `target_metadata`. Rebuild old plans and output directories; no legacy format decoder is added. Existing standalone JS artifacts can retain their bundled runtime.

The implementation's frozen full batch passed 18/18 steps and 4538 pytest tests, plus Python/JS integration, rule, browser, wheel and dual-profile deployment checks. Version/documentation and actual 1.0.0 archives are checked separately. Earlier failures remain recorded. The attached assets are both distribution ZIPs and their SHA256 list.

Release-specific verification on 2026-10-16 passed 61 tests, repository checks, an installed 1.0.0 wheel, both extracted distribution profiles, relocated Python AOT API/CLI runs and JS build/execution. The formal ZIPs are byte-identical to the archives exercised by those isolated checks.

[完整比较 / Full comparison: v0.20.0 → v1.0.0](https://github.com/RockingSisyphus/vibeflow/compare/v0.20.0...v1.0.0)
