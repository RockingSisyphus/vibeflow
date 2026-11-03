# 发行与文档装配

当前本地版本为 1.5.1，Workflow ABI v12、Plugin ABI v5、共享 AOT v6、预览快照 v5；Rule ABI v3、HTTP 通信协议和协作启动清单 v2 保持不变。本次发行层定向验收及最终双包验收完成；最近一次完整功能门禁为 1.5.0，本轮未推送或发布。

1.3.5 修复 JavaScript 核心 SDK 解压到 workspace 内时被误认成业务资源的问题：Target 按既有资源清单识别准确文件，在形成业务引用与插件源码闭包时排除核心内部依赖；原始分析保留，用户贡献声明及共享 Rule 政策不变。1.3.4 统一资源使用 Rule 与 `vibeflow.resource_use.v1` 结果：独立 BaseLib（包括间接依赖）必须显式声明，Plugin 贡献资源整包引入并禁止重复声明，贡献代码实际路径必须位于所属 Plugin 目录。Python、JavaScript 的验证、构建、运行准备和展示共同消费规则结果；旧选择器及重复许可检查已删除。Python AOT 按实际引用收集实现，未引用的可用库不随包加载或复制。预览最新快照覆盖各注册 root 当前仍存在的 workflow，继续隐藏 Plugin 贡献资源。1.3.3 的 global_state 环境变量能力保留。

包含已退役通用宿主接口的旧发行物已在新包验收后清除，历史源码通过 Git 恢复。其他归档不受影响。两个 profile 使用下述工具构建；正式发布需验证解压运行、wheel、sdist 与完整门禁，禁止同名覆盖既有 ZIP。

## 1.5.1 构建内容

`DISTRIBUTION.json` 收窄为只读发行身份记录，格式为 `vibeflow.distribution.v3`，仅保留 schema、发行版本和原始 development_profile。删除 root 列表、协议和自动化开关副本、内核路径与重复哈希；root 注册只使用项目配置，开发协议仍由既有 profile 原稿生成 AGENTS 和手册，完整性仍由原有 MANIFEST 检查。Workflow、Plugin、Rule、AOT、HTTP 和预览格式均未改变。

README、AGENTS 和项目治理指南明确区分目录位置、root ID 与发行身份。改目录名更新注册路径；改 ID 同步引用并通过公开命令刷新业务架构文档，不修改发行记录或重封内核清单。英文首页的 ABI 标识一并纠正。

构建与验收读取方已同步迁移，内核哈希验收读取实际 MANIFEST。相关场景改从构建 CLI 和随包 CLI 出发，移除绑定内核源码布局的旧断言。首批定向检查为 2 passed、2 failed、7 个准备错误，共同原因是新 kernel README 的分发相对链接在源码模板中不存在，导致构建自检拒绝；已改为说明分发根目录路径。修复后的定向复验 11/11 通过，包含公开构建、目录与 ID 改名、架构刷新、Python/JS 执行及发行身份/清单不变。最终双包的改名、Python/JS 执行、身份只读及清单不变验收也已通过，内核与 1.5.0 字节一致。复核后继续移除源 profile 装配配置中失去消费者的协议/自动化副本、专属验证与内部测试助手；清理后的同一批定向检查再次 11/11 通过；重新生成的两个 ZIP 与已验收包逐字节相同。本次未重跑完整功能门禁，运行时代码没有变化。

两个最终 ZIP 分别通过三字段身份识别、自定义 root 目录与 ID、架构刷新、Python 运行、JS 构建/运行、身份只读以及内核清单不变的独立验收。两个 profile 的内核 ZIP 彼此相同，也与归档 1.5.0 内核逐字节相同。原始 1.5.0 ZIP 和校验索引保留于 archive，原校验值核对通过。

| 本地包 | SHA256 |
| --- | --- |
| [vibeflow-distribution-1.5.1.zip](../../dist/vibeflow-distribution-1.5.1.zip) | `9596a1f9ca9a71209acdb2d799def4eeeef6c88b3d7b701b11be73ad5017470a` |
| [vibeflow-distribution-autonomous-1.5.1.zip](../../dist/vibeflow-distribution-autonomous-1.5.1.zip) | `2980f41c60a5dfd4a038ecb76e17bf876f49f85150b4dde223d376752187cc34` |

当前校验索引为 [SHA256SUMS-1.5.1.txt](../../dist/SHA256SUMS-1.5.1.txt)。最终仓库 all 检查为 0 error、0 warning，旧版及新版 ZIP 校验值均通过，本次隔离临时材料已清理。验收仅覆盖本机 Linux 的发行层使用流程；本次未重跑 wheel、其他平台、完整适配采集或完整功能门禁。

## 1.5.0 构建内容

Node 通过固定的 `context.workflow` 方法使用协作会话，运行输入分别为 Python `workflow_session` 和 JavaScript `workflowSession`。`workflow_operations` 只声明流程事实，供启动清单与架构展示读取。应用直接管理 DOM、监听和队列，活实例可通过普通运行输入传递。

Loop 的 `max_iterations: null` 支持持续运行，省略时默认 1000；取消等待与停止清理行为保持有效。旧 ABI 和 AOT 通过既有版本检查拒绝，需重新构建。分发构建、完整门禁及清理结果见 [1.5.0 本地验收记录](release-1.5.0-validation.md)。

## 1.4.5 构建内容

审核出口统一为 Architecture 和离线 HTML，结果 JSON 写到标准输出。保留 Mermaid 文本导出；旧静态附件与字符流程图的生成链、命令、依赖和查看器模式彻底移除。浏览器验收使用独立测试依赖，不随分发包交付。旧 review 输出参数明确拒绝，帮助文案与实际参数同步。

验证范围和首轮失败后的修复记录见[1.4.5 验证记录](release-1.4.5-validation.md)。本机验证不代表远端 CI 或其他平台验收。

## 1.4.4 构建内容

用户文档按主题归位，AGENTS 只保留核心目标、通用开发规范与任务导航。新增项目、root 和 workflow 的统一架构阅读与维护指南，明确 AI 优先阅读项目总览、目标 root 条目及相关 workflow，再定位真实源码；架构登记、字段及更新命令集中维护。

协同审核使用 HTML。两个 profile 均携带新的架构指南和文档路由。ABI、AOT 和预览格式保持不变。

HTML 查看器的互不连通分支改为独立布局后按快照节点的首次出现顺序排列，展开或收起 Nodeset 不再因尺寸变化交换入口位置；嵌套子图沿用同一规则，资源视图继续紧凑排版。真实鼠标回归能在旧布局上复现入口换位，在新布局上通过；相关定向验证为 29 passed。

本地 collaborative / autonomous 两个 1.4.4 ZIP 已重新构建并包含上述查看器修复。构建器的仓库检查通过（0 error、0 warning）；从最终 ZIP 分别解压，通过内核校验、Python 模板验证及 AOT 构建运行、JavaScript 构建、Node 执行探针及执行后的 HTML review 命令检查。两包内核字节一致，包内独立查看器和内核 ZIP 中的布局文件均与当前源码一致。此前仅文档重整的 1.4.4 构建内核与 1.4.3 相同，本次已因查看器修复变化；旧 ZIP 和校验文件保留原始字节归档，当前两个 ZIP 与 SHA256SUMS 位于 dist。未重跑完整仓库功能门禁、wheel/sdist 验证或远端 CI。

## 1.4.3 历史构建内容

修复 JavaScript Target 使用 TypeScript 7 时，构建、审查与源码检查按不同文件集合保留完整编译服务而产生的内存倍增。分析会话只保留当前编译环境，连续相同上下文继续复用；切换上下文或源码变化时先释放旧环境，结束时关闭最后一个环境。函数指标、调用图和已完成的规则结果仍复用，各节点的权限与审查范围保持独立。ABI 与配置格式不变。

JavaScript 最小模板为执行探针生成的 `run_artifacts/` 显式声明目录用途，避免正常执行探针后被根目录布局规则拒绝 review；其他默认治理规则保持有效。

本轮 JavaScript 相关 pytest 为 1188 passed、0 failed、0 skipped；当前锁定图形环境（Mermaid 11.17.2）的补验为 147 passed、0 failed、0 skipped；含 Node 与真实 Chromium 的 JS integration 为 51 passed、0 failed、0 skipped。解压后的连续操作验收暴露上述模板目录问题后，补丁通过发行架构、两个 profile 与确定性相关的 34 项定向回归（0 failed、0 skipped）。补验包含重叠用例，不将各组 pytest 数量相加解释为独立覆盖数。本轮未重跑完整仓库门禁或远端 CI。内存测量与其他行为验证边界见 [JS 检查会话](javascript-check-sessions.md)。

本地 collaborative / autonomous 两个 1.4.3 ZIP 已构建，从最终 ZIP 解压后通过内核检查、Python 模板验证、JS 构建、Node 执行探针及执行后的 review（PASS、预览已发布）。两个 profile 的内核字节一致，确认从包内 ZIP 导入；与现有 1.4.2 相比，内核内容仅两个 JS 分析文件变化，另有上述 JS 模板目录声明修复。包内 8 节点 / 8 文件空图 review 的 `tsc --api` 峰值为 1、RSS 合计峰值 252.9 MiB，退出后未发现编译服务残留。1.4.2 ZIP 和校验文件已保留原始字节归档；当前 ZIP 与 SHA256SUMS 位于 `dist`。这表示本地包验证完成，未上传 GitHub、打标签或部署业务。

## 1.4.2 历史构建内容

修复 Python 嵌套 Nodeset / Loop、并发分支及取消收尾可能掩盖原始业务异常的问题。运行时保留最先确认的失败，后续执行错误、清理错误和失败观察错误作为附加信息保留；真正的外部取消仍按取消处理，等待实际协程、线程及释放完成。Python 与 JavaScript 协作终态按实际执行结果确定，停止请求本身不覆盖已经发生的失败。跨进程错误记录保留异常原因、上下文及附加错误。

关闭详细 trace 时不再累积逐次执行顺序和完整嵌套路径，仍保留静态节点计数。依赖详细路径进行业务统计的宿主需要启用详细 trace 或改用相应观察接口。既有 ABI 和 AOT 格式保持不变；已有 AOT 需重建、重新部署才能包含本次运行时修复。完整功能验收与外部项目验证边界见[决策记录](../goal-decisions.md)。

## 1.4.1 历史构建内容

修复 Python 普通同步节点通过 HTTP 协作宿主执行 Send 时的事件循环转交，并修复嵌套取消可能打断真实异步清理的边界。已中止的接收操作不会消费排队消息。协作实例、同步调用和异步生命周期合同不变。 JS 同进程回归和数学沙箱通过 esbuild 的正式 JavaScript API 打包，避免 Windows 将 Unix 包装脚本当作可执行文件；测试仍执行真实 AOT，不跳过协作断言。 Python 数学沙箱为源码批量审核按父调用分配时间预算，避免慢速 CI 将审核耗时误判为协作挂起；AOT 仍保留执行阶段的原有超时，业务与清理断言不变。


两端三个 workflow 数学沙箱增加与正常计算并发的 Kill 场景，检查真实异步 finally 清理完成、终态及无数值输出；正常公式和错误公式对照继续保留。Node 与真实无头 Chromium 执行同一个浏览器 AOT 产物，协作期间零网络请求。Workflow ABI v11、共享 AOT v5、协作启动清单 v2 及其他 ABI 保持不变。完整代码验收结果见[设计记录](../design/workflow-coordination.md)。

## 1.4.0 历史构建内容

Core workflows 统一入口、引用、完成合同及同步资格事实；Python HTTP 与同进程宿主共用独立 Coordination 组件，Node 与浏览器共用通用 JS 组件，运行时显式绑定实际 AOT 目标。官方 InvokeSync 同步返回普通值；Call、消息、Wait、Kill 维护独立实例及实际终态。Python 增加原生 `async def` 节点、异步入口、生命周期等待、取消与实际清理，并贯通源码和 plan/block/compiled AOT。

启动配置改为显式 `{kind:"process",command,...}` 或 `{kind:"in_process"}`。同步和异步入口严格区分；旧启动格式和旧构建产物明确拒绝，需按[协作迁移说明](../../distribution/docs/user/workflow-coordination.md)修改并重建，不保留旧执行路径。浏览器组件不承担 DOM、酒馆业务或刷新恢复。

Python、JS 正式沙箱增加三个独立 workflow 的联合公式：两轮异步消息嵌入同步调用，覆盖并发身份和数据隔离、终态读取及错误公式对照。JS 使用同一单文件脚本验证 Node 与离线无头 Chromium，协作期间零网络请求。实现及分层说明见[设计与验收记录](../design/workflow-coordination.md)。

保存的架构文档将内核引用统一为 `@kernel/...`，避免带入构建机源码绝对路径，使不同源码目录构建的分发包保持一致；实时诊断继续保留实际路径。

## 1.3.8 历史构建内容

Call、Kill、Receive、Send 共用新的缺角卡片形状，默认分别为金、红、深蓝、浅蓝；操作名在卡片内加粗显示，CallAndWait 保留 Call 样式。作者样式可覆盖默认值，planned 保留原色并使用虚线及 60% 不透明度。重复的相同声明动作只产生一份展示事实，不合并实际运行调用。

`PROJECT_ARCHITECTURE.jsonc` 仅展示项目一级目录；各 root 记录 workflow 文件名、路径、用途、入口、关联和注册架构文档，移除递归目录展示。治理所需源码清单仍完整扫描。详见 [workflow 协同](../../distribution/docs/user/workflow-coordination.md)。

SDK 的声明与实现附属文件共用文件引用解析，正确处理 Windows 盘符、网络共享路径及字面的 `%`、`#` 和空格，避免合法实现被误报为冲突。Windows CI 同步覆盖 SDK 身份与附属文件场景。

## 1.3.7 历史构建内容

自有 JSON、AOT 元数据与绑定、workflow 启动声明、CLI 输入、源码及工具输出明确使用 UTF-8；文本子进程按协议指定编码，Python 子进程同时明确标准流编码。procfs 的数字内容按纯数字文本读取，可能包含任意进程名称字节的 stat 文件按二进制解析。外部业务文件仍可显式选择自身格式的编码，不改变 Python 全局默认值。

仓库自检的 base/all profile 新增 `TEXT_ENCODING_UNSPECIFIED`，检查常见文本文件及子进程调用未明确编码的情况，输出源码位置和修复建议。检查范围、动态调用和字符串内嵌代码等静态分析边界见 [repo checker 说明](../../repo_check/README.md)。回归测试从真实 AOT 包调用 API、CLI 和协同宿主，在移除源项目及非 UTF-8 默认环境下验证中文配置、输入和输出。

1.3.6 的统一架构审核、节点自身 workflow/launch 声明与 planned Call 启动修复继续保留。已有业务配置无需因本次编码修复迁移；要使用修复后的内核，需重新构建和部署 AOT 包。

候选验证在仓库外构建，正式产物由项目构建器生成到 `dist`，保留既有版本 ZIP 的原始字节。版本号与文档同步不代表完整门禁或 GitHub 发布已经完成，验收结论按实际执行范围报告。

## Profile 配置

`distribution/profiles.jsonc` 是 profile 的唯一配置源，schema 为 `vibeflow.distribution-profiles.v2`。路径使用仓库相对形式：prompt 来自 `distribution/prompts/`，发行正文来自 `distribution/docs/overview.md` 与 `distribution/docs/user/`。

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

运行观测接口的业务用法和双语言更新示例集中在 `distribution/docs/user/runtime-observation.md`；开发手册与公共提示词通过文档路由定位。架构阅读、登记及更新集中在 `distribution/docs/user/architecture.md`。审核页面说明集中在 `distribution/docs/user/local-preview.md`。从最终 ZIP 解压包验证随包文档、公开 SDK、业务输出与状态资料，按实际覆盖范围记录结果。

修改 canonical 文档及 prompt fragments 后重新构建两个 profile，发布目录和 ZIP 中的文档、AGENTS 与清单随构建更新。验收报告中的归档哈希对应当次构建；后续文档修订产生新的归档哈希，历史字节保存在版本 ZIP 中，代码和文档变化由 Git 追溯。

目录与证据保留约定见 [目录职责](directory-layout.md)。
