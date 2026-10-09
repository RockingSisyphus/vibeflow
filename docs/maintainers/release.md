# 发行与文档装配

VibeFlow 当前开发版本为 0.17.0，按旧 API 直接退役的破坏性升级准备 collaborative 与 autonomous 两个开发包。两者共享 Core、机器 policy、最小 Python/JavaScript 项目和 Workflow ABI。迁移入口与删除接口见 [统一资源迁移](../../distribution/docs/user/rule-system-migration.md)。完整仓库验收的双 profile smoke 在隔离目录构建，不自动覆盖归档发行包。

0.15.2 包含用户项目 SVG 展示边界修正：资源目录只展示当前 workflow 使用的 Plugin、BaseLib、Host 等条目，恢复旧版横竖布局，移除内部定义、源码文件和 reference 的 SVG 投影。变更与源码回归见 [展示边界记录](history/user-svg-boundary-20261006.md)，本版归档与隔离验收见 [0.15.2 构建记录](evidence/index.md#artifact-89ba4710b187715e)。

[0.15.1 修复构建记录](evidence/index.md#artifact-31e3261df1859ff8)与[首次构建验收](evidence/index.md#artifact-4a550cca6daaf3aa)保留历史哈希，初始包位于 `archive/history/0.15.1-initial-20261006/`。

## Profile 配置

`distribution/profiles.jsonc` 是 profile 的唯一配置源，schema 为 `vibeflow.distribution-profiles.v1`。路径使用仓库相对形式：prompt 来自 `distribution/prompts/`，发行正文来自 `distribution/docs/overview.md` 与 `distribution/docs/user/`。

公共文档集进入两个包，每个包选择自己的 profile 协议。发行正文面向业务项目开发者和 AI；内核设计、仓库验证及历史证据保留在开发目录。

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

## 文档装配

构建器按 profile 复制 canonical 用户文档并保留其相对路径，生成 `kernel/docs/README.md` 导航，再从 prompt fragments 确定性合成根 `AGENTS.md`。根 README 只提供 profile、最小项目和文档入口。

完整性检查验证文档集合、字节内容、AGENTS、metadata、manifest 和 kernel hash。两个 profile 的 kernel ZIP、项目模板和机器 policy 必须字节一致。

更新公共接口时，同时核对使用手册、AI 阅读路由、最小项目 README 和当前设计说明。详细 API 放在主题手册，提示词保留导航与执行协议。多文件资源和 Rule/Ruleset 均有公共文档入口。

运行观测接口的业务用法集中在 `distribution/docs/user/runtime-observation.md`，Python 与 JS/TS 开发手册在完整 Node 示例中展示更新调用。公共提示词交代调用位置、完整数组替换和发布时机，两个 profile 共用该片段。修订后从生成 ZIP 解压包运行这些示例，确认公开 SDK、业务输出与最终状态资料一致；结果保留在对应开发验收记录。

修改 canonical 文档及 prompt fragments 后重新构建两个 profile，发布目录和 ZIP 中的文档、AGENTS 与清单随构建更新。验收报告中的归档哈希对应当次构建；后续文档修订产生新的归档哈希，历史报告保留原构建记录。

目录与证据保留约定见 [目录职责](directory-layout.md)。
