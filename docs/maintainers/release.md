# 发行与文档装配

当前分发版本为 1.3.2，Workflow/AOT/Plugin ABI 为 10/4/4。此版修复跨 root 复用 Node 时继承方法的源码解析，以及 Python AOT 的项目目录关系与插件导出类加载来源；包含此前 project/root 治理政策统一迁移。既有 1.3.0、1.3.1 ZIP 保留原始字节，ABI 不变。两个 profile 使用下述工具构建；正式发布需验证解压运行、wheel、sdist 与完整门禁，禁止同名覆盖既有 ZIP。

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
