# 发行与文档装配

VibeFlow 当前发行版本为 0.20.0，准备 collaborative 与 autonomous 两个开发包。两者共享 Core、机器 policy、最小 Python/JavaScript 项目和 Workflow ABI。迁移入口与删除接口见 [统一资源迁移](../../distribution/docs/user/rule-system-migration.md)。完整仓库验收的双 profile smoke 在隔离目录构建，不自动覆盖归档发行包。

0.20.0 将任务等待改为一次结果交付：接收后任务卡自动回收，结果由父流程保存和转交；旧重复等待和停止已消费引用的代码须迁移。Workflow ABI 仍为 v6，配置形状不变。接口与示例见[原生任务管理](../../distribution/docs/user/task-management.md)，开发、全量验收与构建见[本轮记录](history/task-result-delivery-20261014.md)。

0.19.1 修复跨 root 独立 Nodeset 源码审查遗漏 BaseLib 归属的问题，保持 planned 调用与真正未登记导入的检查行为。修复与验证见[复现及修复记录](history/task-ownership-reproduction-20261014.md)。

0.19.0 引入原生任务管理与 Workflow ABI v6：管理 Node 使用声明目标启动任务，普通 TaskRef 数组可沿数据连边传递，停止请求与实际退出分开，workflow 在所属执行与清理完成后才退出。JS 使用事件循环，Python 使用线程与完成通知。旧 `async/result_key/detached` 入口须显式迁移，没有自动转换层；迁移后重新生成 Architecture、计划与构建产物。接口与内存边界见[原生任务管理](../../distribution/docs/user/task-management.md)，开发和全量验收见[实施记录](history/task-management-implementation-20261014.md)。

0.19.0 两种本地发布包及实际 ZIP 解压验证见[构建记录](history/release-0.19.0.md)。

0.18.3 汇总条件边保留、嵌套插件配置导出及相关规则修复，并加入永久沙箱与运行回归。只读 JSON 的冻结与副本转换统一由独立公共模块提供；配置语法与 Workflow ABI 保持不变。具体修复见下文。

GitHub 发布说明按上一正式 Release v0.13.2 的 Git 历史整理，见 [0.18.3 中英文更新说明](history/release-0.18.3.md)。

0.18.2 将内置 Rule、Ruleset 与 Node 声明按语言归入 `targets/<language>/rules/`、`rulesets/` 和 `nodetypes/`；图检查与节点源码检查分开保存。Core 保留通用规则机制，共享检查算法归入 Target 共享支持层，现有规则标识、默认选择和公共 SDK 行为保持不变。仓库独立自检工具迁至 `repo_check/`，与产品质量检查入口区分；同步更新构建器对独立 JavaScript SDK 的 Node 声明资源装配。

0.18.2 修复包按节点首次引用顺序构造规则检查的 Nodeset 边界，消除跨进程哈希随机化造成的 planned 诊断与 events 排列变化，避免未修改的 Architecture 被误报过期。两种 profile 的 ZIP 回归覆盖不同 `PYTHONHASHSEED` 下立即检查通过、完整文档逐字节一致，以及真实 workflow 改动仍能检出。

同版本修复 JavaScript `python_io` 动态宿主槽读取的误报，并统一数据规则对初始输入的资格判断：按调度边识别空起点，不再遗漏纯控制边。多来源数据与混合 `safe_any` 汇合共用完整调度路径的互斥判断；中间节点不再丢失祖先条件，存在旁路、重叠条件或无法证明的跨字段关系时仍保留冲突诊断。拓扑、汇合、运行输入和路径条件算法按职责拆分，公开 Rule 标识与选择方式不变，未修改 Core 调度语义。

后续条件边修复将 Core 去重收窄为完整 `EdgeSpec` 相等：不合成条件、不合并角色、不推断条件等价。同端点的不同声明完整进入计划，各自保留调度与传输权限；Python 数据投递直接遍历传输路线，不再借用同端点调度路线的条件或权限。供数与汇合按前驱节点统计，重复声明诊断与 Core 精确去重保持一致，不再把不同条件诊断为 `GRAPH.EDGE.CONFLICTING_DUPLICATE`，不同角色也不再触发旧的合并冲突。公开配置语法和 ABI 不变。

嵌套插件配置修复将只读 JSON 与普通 JSON 副本的双向转换归入独立公共模块 `vibeflow.core.descriptors.json_values`，所有声明与插件配置调用统一入口。Python 资源导出递归转换配置、选择和展示字段，避免内层 mappingproxy 泄漏到 `compiled_graph.json`，导致公开运行入口在业务 Node 执行前失败。转换保留配置结构和值，运行时仍保持只读，原 `DescriptorModelError` 公开入口及校验规则保留。回归覆盖 plan/compiled/block、默认与覆盖值、空对象、对象数组及副本隔离。

0.18.1 将 Python 与 JavaScript 的事实视图身份管理抽为共享模块，拆分语言事实适配、分析服务和检查会话职责，移除规则调用中的重复身份计算。Python 固定输入验证显示耗时改善；JavaScript 已消除重复摘要，但尚未证明稳定的端到端提速。同步完善仓库目录说明与文档导航；构建时排除带维护者标记的目录 README，保留发行用户指南。

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
