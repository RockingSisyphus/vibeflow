# 发行与文档装配

当前分发版本为 1.3.6，Workflow/AOT/Plugin ABI 维持 10/4/4。1.3.6 统一架构审核资料及节点自身的 workflow/launch 声明，修复 planned Call 被加入服务启动清单的问题；planned 结构与调用意图仍保留在 HTML 审核材料中。渲染依赖与使用文档同步更新。

1.3.5 修复 JavaScript 核心 SDK 解压到 workspace 内时被误认成业务资源的问题：Target 按既有资源清单识别准确文件，在形成业务引用与插件源码闭包时排除核心内部依赖；原始分析保留，用户贡献声明及共享 Rule 政策不变。1.3.4 统一资源使用 Rule 与 `vibeflow.resource_use.v1` 结果：独立 BaseLib（包括间接依赖）必须显式声明，Plugin 贡献资源整包引入并禁止重复声明，贡献代码实际路径必须位于所属 Plugin 目录。Python、JavaScript 的验证、构建、运行准备和展示共同消费规则结果；旧选择器及重复许可检查已删除。Python AOT 按实际引用收集实现，未引用的可用库不随包加载或复制。预览最新快照覆盖各注册 root 当前仍存在的 workflow，继续隐藏 Plugin 贡献资源。1.3.3 的 global_state 环境变量能力保留。

既有版本 ZIP 保留原始字节，ABI 不变。两个 profile 使用下述工具构建；正式发布需验证解压运行、wheel、sdist 与完整门禁，禁止同名覆盖既有 ZIP。

## 1.3.6 构建内容

1.3.6 包含统一的 `tooling/architecture`、项目架构索引 v2 和预览快照 v4，并将原顶层 `workflow_targets` 替换为节点自身的 `workflow` / `launch` 声明。planned Call 仅保留审查意图，启动清单只包含已实现调用；未补齐的 planned 启动配置不影响已实现调用。通用原子写入由 `tooling/file_io` 包负责，架构、预览和部署声明共用该实现。

候选验证在仓库外构建，正式产物由项目构建器生成到 `dist`，保留既有 1.3.5 ZIP 的原始字节。版本号与文档同步不代表完整门禁或 GitHub 发布已经完成，验收结论按实际执行范围报告。

## Profile 配置

`distribution/profiles.jsonc` 是 profile 的唯一配置源，schema 为 `vibeflow.distribution-profiles.v1`。路径使用仓库相对形式：prompt 来自 `distribution/prompts/`，发行正文来自 `distribution/docs/overview.md` 与 `distribution/docs/user/`。

公共文档集进入两个包，每个包选择自己的 profile 协议。发行正文面向业务项目开发者和 AI；内核设计、仓库验证及当前维护规范保留在开发目录。

## 构建

```bash
python distribution/build.py
```

默认以一个事务发布两个目录和两个确定性 ZIP。构建先在临时目录生成、验证全部 profile；最新 ZIP 留在 dist，被替换的正式 ZIP 才进入 archive；任一阶段失败时不替换旧发行物。

单 profile 构建保留给测试和局部验证：

```bash
python distribution/build.py --profile collaborative --output-dir /tmp/vf-collaborative --archive-dir /tmp/vf-candidate-zips
python distribution/build.py --profile autonomous --output-dir /tmp/vf-autonomous --archive-dir /tmp/vf-candidate-zips
```

## GitHub 发布

先完成文档、版本、正式 ZIP、解压部署与哈希验证，再提交并推送不可变标签。Release 使用已有空草稿和审核后的发布说明，附件为两个 ZIP 与对应的 SHA256SUMS 文件；上传完成后下载核对字节，再发布为正式版本。

本地上传端点不可用时，可手动运行 `.github/workflows/release.yml`，通过 Git Database API 将已验证的 ZIP 写为临时传输 blob，不提交到源码历史；传入标签、已验证的完整 commit、两个 blob ID 和 ZIP 的 SHA256。workflow 检出标签核对版本及提交，取回原始 ZIP，哈希不匹配即停止；只有原始字节一致才使用 GitHub 的标准 job token 上传并发布。这样不会因另一主机重新压缩而换成未经验证的归档。不得为重试移动标签、覆盖既有资产或降低哈希检查。构建与上传失败时草稿保持未发布。

## 文档装配

构建器按 profile 复制 canonical 用户文档并保留其相对路径，生成 `kernel/docs/README.md` 导航，再从 prompt fragments 确定性合成根 `AGENTS.md`。根 README 只提供 profile、最小项目和文档入口。

完整性检查验证文档集合、字节内容、AGENTS、metadata、manifest 和 kernel hash。两个 profile 的 kernel ZIP、项目模板和机器 policy 必须字节一致。

更新公共接口时，同时核对使用手册、AI 阅读路由、最小项目 README 和当前设计说明。详细 API 放在主题手册，提示词保留导航与执行协议。多文件资源和 Rule/Ruleset 均有公共文档入口。

运行观测接口的业务用法集中在 `distribution/docs/user/runtime-observation.md`，Python 与 JS/TS 开发手册在完整 Node 示例中展示更新调用。公共提示词交代调用位置、完整数组替换和发布时机，两个 profile 共用该片段。修订后从生成 ZIP 解压包运行这些示例，确认公开 SDK、业务输出与最终状态资料一致；结果保留在对应开发验收记录。

修改 canonical 文档及 prompt fragments 后重新构建两个 profile，发布目录和 ZIP 中的文档、AGENTS 与清单随构建更新。验收报告中的归档哈希对应当次构建；后续文档修订产生新的归档哈希，历史字节保存在版本 ZIP 中，代码和文档变化由 Git 追溯。

目录与证据保留约定见 [目录职责](directory-layout.md)。
