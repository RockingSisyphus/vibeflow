# 发行与文档装配

当前分发版本为 1.4.1，Workflow ABI 为 v11、共享 AOT 为 v5、协作启动清单为 v2；Plugin ABI v4、Rule ABI v3、预览快照 v4 保持不变。

1.3.5 修复 JavaScript 核心 SDK 解压到 workspace 内时被误认成业务资源的问题：Target 按既有资源清单识别准确文件，在形成业务引用与插件源码闭包时排除核心内部依赖；原始分析保留，用户贡献声明及共享 Rule 政策不变。1.3.4 统一资源使用 Rule 与 `vibeflow.resource_use.v1` 结果：独立 BaseLib（包括间接依赖）必须显式声明，Plugin 贡献资源整包引入并禁止重复声明，贡献代码实际路径必须位于所属 Plugin 目录。Python、JavaScript 的验证、构建、运行准备和展示共同消费规则结果；旧选择器及重复许可检查已删除。Python AOT 按实际引用收集实现，未引用的可用库不随包加载或复制。预览最新快照覆盖各注册 root 当前仍存在的 workflow，继续隐藏 Plugin 贡献资源。1.3.3 的 global_state 环境变量能力保留。

既有版本 ZIP 保留原始字节。两个 profile 使用下述工具构建；正式发布需验证解压运行、wheel、sdist 与完整门禁，禁止同名覆盖既有 ZIP。

## 1.4.1 构建内容

修复 Python 普通同步节点通过 HTTP 协作宿主执行 Send 时的事件循环转交，并修复嵌套取消可能打断真实异步清理的边界。已中止的接收操作不会消费排队消息。协作实例、同步调用和异步生命周期合同不变。 JS 同进程回归和数学沙箱通过 esbuild 的正式 JavaScript API 打包，避免 Windows 将 Unix 包装脚本当作可执行文件；测试仍执行真实 AOT，不跳过协作断言。

预览中的跨 workflow 跳转与左侧列表切换使用一致的独立记录，各 workflow 保留各自的阅读位置和展开状态。Wait 默认统一为其他协作操作的缺口矩形。`WORKFLOW.CALL.UNOBSERVED` 不再把 Wait 或 CallAndWait 当作缺少 Kill 的豁免，仍为警告并保留显式 `allow_background: true`；不增加自动停止行为。

两端三个 workflow 数学沙箱增加与正常计算并发的 Kill 场景，检查真实异步 finally 清理完成、终态及无数值输出；正常公式和错误公式对照继续保留。Node 与真实无头 Chromium 执行同一个浏览器 AOT 产物，协作期间零网络请求。Workflow ABI v11、共享 AOT v5、协作启动清单 v2 及其他 ABI 保持不变。完整代码验收结果见[设计记录](../design/workflow-coordination.md)。

## 1.4.0 历史构建内容

Core workflows 统一入口、引用、完成合同及同步资格事实；Python HTTP 与同进程宿主共用独立 Coordination 组件，Node 与浏览器共用通用 JS 组件，运行时显式绑定实际 AOT 目标。官方 InvokeSync 同步返回普通值；Call、消息、Wait、Kill 维护独立实例及实际终态。Python 增加原生 `async def` 节点、异步入口、生命周期等待、取消与实际清理，并贯通源码和 plan/block/compiled AOT。

启动配置改为显式 `{kind:"process",command,...}` 或 `{kind:"in_process"}`。同步和异步入口严格区分；旧启动格式和旧构建产物明确拒绝，需按[协作迁移说明](../../distribution/docs/user/workflow-coordination.md)修改并重建，不保留旧执行路径。浏览器组件不承担 DOM、酒馆业务或刷新恢复。

Python、JS 正式沙箱增加三个独立 workflow 的联合公式：两轮异步消息嵌入同步调用，覆盖并发身份和数据隔离、终态读取及错误公式对照。JS 使用同一单文件脚本验证 Node 与离线无头 Chromium，协作期间零网络请求。实现及分层说明见[设计与验收记录](../design/workflow-coordination.md)。

保存的架构文档将内核引用统一为 `@kernel/...`，避免带入构建机源码绝对路径，使不同源码目录构建的分发包保持一致；实时诊断继续保留实际路径。

## 1.3.8 历史构建内容

任意 Python、JavaScript/TypeScript Node 都可通过 `context.workflow.self()` 读取本次实例的 `{id}`，无需 Capability 声明或授权。Nodeset、Loop 与父 workflow 共享身份；协同宿主使用服务注册的实例 ID。独立 Self 模板、Capability self 操作及其数据契约已删除，旧节点应迁移到上下文接口并重新构建 AOT。

Call、Kill、Receive、Send 共用新的缺角卡片形状，默认分别为金、红、深蓝、浅蓝；操作名在卡片内加粗显示，CallAndWait 保留 Call 样式。作者样式可覆盖默认值，planned 保留原色并使用虚线及 60% 不透明度。重复的相同声明动作只产生一份展示事实，不合并实际运行调用。

`PROJECT_ARCHITECTURE.jsonc` 仅展示项目一级目录；各 root 记录 workflow 文件名、路径、用途、入口、关联和注册架构文档，移除递归目录展示。治理所需源码清单仍完整扫描。详见 [workflow 协同](../../distribution/docs/user/workflow-coordination.md)。

SDK 的声明与实现附属文件共用文件引用解析，正确处理 Windows 盘符、网络共享路径及字面的 `%`、`#` 和空格，避免合法实现被误报为冲突。Windows CI 同步覆盖 SDK 身份与附属文件场景。

## 1.3.7 历史构建内容

自有 JSON、AOT 元数据与绑定、workflow 启动声明、CLI 输入、源码及工具输出明确使用 UTF-8；文本子进程按协议指定编码，Python 子进程同时明确标准流编码。procfs 的数字内容按 ASCII 读取，可能包含任意进程名称字节的 stat 文件按二进制解析。外部业务文件仍可显式选择自身格式的编码，不改变 Python 全局默认值。

仓库自检的 base/all profile 新增 `TEXT_ENCODING_UNSPECIFIED`，检查常见文本文件及子进程调用未明确编码的情况，输出源码位置和修复建议。检查范围、动态调用和字符串内嵌代码等静态分析边界见 [repo checker 说明](../../repo_check/README.md)。回归测试从真实 AOT 包调用 API、CLI 和协同宿主，在移除源项目及非 UTF-8 默认环境下验证中文配置、输入和输出。

1.3.6 的统一架构审核、节点自身 workflow/launch 声明与 planned Call 启动修复继续保留。已有业务配置无需因本次编码修复迁移；要使用修复后的内核，需重新构建和部署 AOT 包。

候选验证在仓库外构建，正式产物由项目构建器生成到 `dist`，保留既有版本 ZIP 的原始字节。版本号与文档同步不代表完整门禁或 GitHub 发布已经完成，验收结论按实际执行范围报告。

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
