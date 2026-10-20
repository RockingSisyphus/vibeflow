# 双语言 AOT 与维护整理实施记录

基线：`5cb5ecc00ec4ac5d340c39f7098f20097b25a0fe`，开始时工作树干净。

目标：共用执行计划驱动两种 Target；Python 目录 bundle 随附框架，使用目标环境原生依赖；源码与 bundle 共用 runtime。完成 AOT 阶段后继续全项目技术债整理。不得修改 vibeTrain 安装、启动远程任务、提交或发布。

## 阶段

1. 共同计划 ABI v7、读取、执行信息与旧并发字段清理。
2. Python 共同计划装配、预生成块代码与可迁移 bundle。
3. JS 接入共用构建、manifest v3 与两侧定向验收。
4. AOT 阶段完整验收及部署、性能观察。
5. 全项目技术债调用审计、逐模块整改、最终完整验收与候选包。

## 实践复核

共同计划首个双端原型、迁移后取消与释放验证、性能和定向结果形成、技术债首批整改及最终验收前，复核剩余工作、验证成本和维护负担。若需要改变语义、覆盖或部署承诺，使用 critical-fork 解释证据及路线，再请用户决定；仅暂停相关工作。

## 当前证据

实施完成；最终冻结源码的完整批次 3 为 18/18 通过，隔离候选包及独立 Python bundle 已生成并实跑。下文按实施顺序保留各批失败、修复和复验；此前的“尚待”描述为对应阶段状态，不代表当前仍未完成，也不覆盖历史失败。

### 定向批次 1

Python runtime、任务管理与共同计划：124 通过，1 失败。失败是计划 ABI 已升 v7、测试仍断言 v6；保留此观察，随后按新 ABI 更新断言再复验。原生执行与任务测试均通过。

### 迁移原型及定向批次 2

最小 Python bundle 搬到新目录、删除原源码后，plan/block/compiled 均得到 5；清空 PYTHONPATH 的新进程 CLI 通过。首次图快照遇到 Nodeset 定义表回指导致递归溢出，已改为有限记录引用，未引入对象 pickle。

第二批：134 通过、10 失败。9 项来自新增测试夹具缺少 end 却要求 completed，1 项来自新增夹具在 implemented 调用处重复声明 requires。修正夹具以符合原生声明机制，不修改产品语义或放宽健康检查。此批尚未复验。

### 定向批次 3 与扩大回归批次 4

任务沙箱、全局对象、编译阶段、JS 模型及发布：65 通过。扩大 Python、共同编译器、JS golden 和 conformance 后：2773 通过，16 失败，2 跳过（103.09 秒）。失败包含 planned stub 三项、planned 执行锁标记一项、绑定 sidecar 一项、Python 生成源码 golden 一项及 JS 十项 golden。先修复行为回归，再核对预期的 ABI/源码快照变化；本批失败记录保留。

### 行为修复定向批次 5

106 通过，3 跳过，1 失败。前批五项行为回归全部通过；剩余失败是新增迁移测试导入了不存在的函数名称，现改用纯 Core 配置解析入口。删除 NodeSpec/NodeFrame 中旧 async/result_key 字段，保留公开 JSON 输入的明确迁移错误；移除对应死分支和过期并发建议。

### 双端与部署定向批次 6、7

双端构建、golden、共同计划及 Core：193 通过，2 失败（Core 测试还在直接构造已删除的旧字段）。已迁移到当前公开 JSON 入口，仍断言明确迁移错误。

共同作用域接入后，Python 搬迁、Loop/Nodeset、JS 项目构建与 Core：89 通过，2 失败。新增多文件沙箱验证暴露其当前架构文档已过期；需要重生成当前受维护文档。新增 delegated CLI 用例错误地把打印业务输出声明为无副作用 process，改为其真正所属的 io 声明，保持静态规则不变。

### 部署细项批次 8

17 通过，2 失败：多文件用例传入了工作流未声明的输入；CLI 用例用了与现有 delegated CLI 协议不一致的输出别名。修正新增用例，继续保留原协议检查及输入检查。两次失败均未改动产品检查门槛。五组 Loop/Nodeset × 三种执行模式全部通过源码删除后的迁移执行。

### 生命周期与 CLI 批次 9

150 通过，1 失败。真实外部取消、任务退出和锁释放在三种执行模式下通过；搬迁后的 delegated CLI 业务标准流与退出码通过。剩余为新增多文件用例读取了未声明的公开输出别名，应按其现有输出类型 number 读取。

### 扩大批次 10 与 CPU 训练探针

3789 通过，2 失败，7 跳过（492.50 秒）。失败一项是我批量修改新增用例时改错另一处输出别名；另一项 planned stub 用例关闭了整个 Workflow Ruleset，却断言该规则应产生 CONCERNS。恢复该用例所需的真实工作流规则和完整 terminal 流，不改变检查标准。

CPU 实测 PyTorch 2.12.1+cu130（device=cpu），三步损失 0.5098423362、0.0051370566、0.0000826676；源码和搬离源码的 bundle 权重逐元素相等，模型与 Tensor 引用保持同一对象。未执行 GPU 训练，未据此声明 GPU 吞吐。

已核实共同计划首个完整原型确实取代 Python/JS 各自的调用与作用域递归；现有 runtime 继续承担生命周期。尚需完整验收、发行 ZIP 内构建、性能观察及后续正式技术债清理。

### AOT 阶段全量批次 1（保留失败）

18 步完整执行，16 步通过；pytest 4509 通过、4 失败；Python 沙箱因旧 ABI v6 断言失败，并连带缺少该失败 case 的成功图形资料。pytest 的失败为旧 Python build 拒绝预期、两项未显式提供 JS 任务 executor 的测试及新实施记录漏加文档总索引。其他步骤均通过，包含 JS 真实 Browser 50/50、规则 1223/1223、规则补充沙箱、布局、资源展示、审查性能、迁移回归、wheel、双 profile 包及清洁目录。

原始阶段状态见 /home/rockingsisyphus/projects/VibeFlow-evidence/aot-unification-20261016/aot-stage-20261016-verification.json，失败摘要见同目录 results.txt。未将定向复验替代该批失败记录。总耗时约 37 分钟，主要为规则补充沙箱与 Python 图形场景；接下来集中修复并复验受影响模块，再完成全仓整理后的新全量，避免每个小改动触发整批重跑。

### 迁移遗漏复验与元数据核对

106 项定向通过，覆盖首轮全量的四项 pytest 失败，以及搬迁、共同计划和子计划投影。Python 沙箱旧 ABI 断言已按 v7 修正；其原全量失败仍保留。

追加一致性修复：共同计划、声明定位和注册来源在 bundle 内重定位；planned stub 的 advisory source_hash 直接使用构建清单已有值，不在装配时重新读取文件。语言专属 metadata 归入 target_metadata，共同头只保存 workflow/ABI/entry/files 等共用信息。删除无消费者的 async_executor 与按类型保存的空 native facts，改由 Target 按实际调用路径提供执行事实，Python 端口使用同步完成、JS receive 使用 suspend/event_loop。

### AOT 阶段补充验收与性能

双端/共同计划/conformance 扩展复验 3504 通过、2 失败、4 跳过（130.83 秒）；两项为 Python 同步端口事实的旧断言及 JS manifest 插件字段位置的旧断言。修正后连同真实 CPU 训练，3 项通过。Python 完整沙箱 104/104，见 /home/rockingsisyphus/projects/VibeFlow-evidence/aot-unification-20261016/aot-python-sandbox-retest-20261016.txt。首轮完整批次失败记录保持不变；阶段结论来自完整批次加受影响范围复验，不能称为新全量通过。

同输入、compiled/trace=off，三次冷进程、每次重复执行 30 次，原始计时见 /home/rockingsisyphus/projects/VibeFlow-evidence/aot-unification-20261016/aot-performance-20261016.json。源码启动包含工作区载入、checked-run 静态审查、计划生成与绑定，双方均排除图形/前置资料写出。中位启动到首次结果约 383 ms / 216 ms；静态审查约 146 ms，bundle 加载约 1.45 ms；绑定约 43.7 / 20.4 ms；重复执行约 0.63 / 0.69 ms。构建约 218 ms。这是小型 CPU 工作流观察，重复执行未呈现收益，不代表真实训练或 GPU 吞吐。

共同计划与原生 runtime 的路线成立：无需额外执行器，Python/JS 特有事实由各 Target 提供。后续维护成本主要在资源收集、生命周期及部署测试；不通过缩小支持范围降低成本。

### 全项目技术债整改清单

按真实 CLI/API、注册、Rule、构建和分发调用链核对，再用引用检索及 Git 历史（含 5b9f976、3ee7396、1b0aa73、28ebb58）确认迁移来源。对第三方、历史验收与发行资料仅核对引用，不删除。

| 范围/旧用途 | 当前消费者及判断 | 实际处理 |
| --- | --- | --- |
| Python renderer/style/review_layout/review_types 四个跨层迁移转发 | 自有 CLI/图形/测试使用；无文档承诺独立 renderer | 改用中立展示模块，删除四个转发模块及私有 SvgFragment 旧别名 |
| Python diagnostics 纯转发 | delegated CLI 与其测试 | 直接用公共诊断 sink，删除转发模块 |
| 工作区模型与加载的 Python 重复出口/包装 | workspace service、报告、质量与测试 | 数据模型从中立所属模块导入；保留现有公开便捷 API，直接引用同一加载/注册实现 |
| contributions 混合资源选择与插件创建 | workspace service 与测试 | 删除无参资源包装，插件创建集中 lifecycle.py，资源选择用唯一实现 |
| 三套临时 sys.path 插入/移除及发行启动器全局预载 | 声明加载、delegated CLI、普通源码执行 | 统一 SDK 的作用域；普通 API 执行覆盖延迟导入，删除启动器全局补偿与重复 workspace 参数解析 |
| source 插件 finally 可能覆盖业务异常 | compiler 与 runtime 两个边界；AOT 曾单独处理 | Target plugin_lifetime 同时服务源码/AOT，反序释放全部实例并保留主异常 |
| planned 的双重、不完整遍历 | runtime/build 的拒绝与 stub 策略 | 一份声明库存支持深层同名定义、任务目标与循环引用；保留未调用定义也审查/拒绝的既有策略 |
| JS 两份 import-policy 转换 | Rule driver 与 AOT driver | 一份字段映射；AOT 只追加 generated owner 和外部依赖；保留现有低层 policy 拼写 |
| Core config 两份 config/inline 合并与 scope 重复分支 | 公开 helper 与图解析 | 统一合并，保留图入口原诊断位置；scope 合并去除重复逻辑 |
| CLI 两份选项提取，选择首项与 argparse 选择末项不一致 | target dispatch / mixed quality | 共用一份，末项优先且尊重 delegated `--` 边界 |
| SDK / Tooling / AOT 各自的物理文件加载 | 延迟 Node、Rule 与 bundle | 统一 SDK 的同源文件缓存与失败清理；正确处理 namespace 的 None 文件定位 |
| 沙箱已迁移原生 task 却沿用旧异步名称 | 五组当前正例与三个 runtime 测试 | 按实际 task 机制重命名，更新 Nodeset 引用与用途说明；旧输入拒绝与历史记录保留 |
| Core Rule scope 未用变量 | scope 推导内部 | 删除，保留声明审查与实际调用范围的区别 |

保留理由：Mermaid CLI 的 esm 文件适配仍由锁定依赖的真实文件缺失触发；Browser 候选与 snap 排除承担平台支持；Finding/HealthFinding 名称是公开契约；配置作用域别名及 distribution --output 仍是有效公开输入；发行目录构建与归档构建边界不同；retired architecture 清单防止旧机制回流；历史 parity/失败记录与正式发行资料承担可复现证据。它们不因名称含 fallback/compat 而删除。

执行中的成本、目标与路线复核：首批整理减少转发模块、全局状态补偿及重复转换，不更改 DSL/资源所有权。新的真实场景断言覆盖延迟导入、主异常与全部释放、深层 planned 及 CLI 选项一致性。剩余成本为模块回归、隔离候选包与最终新全量；约 37 分钟的完整批次应在代码冻结后执行，不按微小改动反复重跑。


### 整理扩大批次 1

4295 通过、20 失败、11 跳过（113.83 秒），失败清单保留于工作区外 maintenance-batch-1.txt。16 项 delegated CLI 单元测试把 workspace 替换成无任何字段的 object；现令替身提供真实接口的 roots。4 项真实源码绑定暴露旧加载器对缓存模块 `__file__=None` 的处理错误；修复所在的共同 SDK 加载入口，源码 Node/Rule 与 AOT 改用同一文件加载机制，保持原有命名与缓存粒度。未放宽业务或 Rule 断言。

追加部署用例：所选 runtime 的 SourceLocator 可以指向独立安装包，依赖收集必须覆盖这个实现包，不能只收集声明入口。追加修复不调用运行时 factory。案例中已迁移为原生 task 的五组旧 async/result_key 名称同步改为 task 名称；旧失败入口和历史记录保留，现有输出/调度/收尾断言不变。


### 整理后的定向与部署结果

第二批 280 通过，覆盖上一批全部失败及新生命周期/导入边界；第三批 293 通过、2 跳过，覆盖共同计划、两端 golden/manifest、Rule 调用级事实、展示模块迁移及工作区/发行文档。跳过的图形依赖项由随后带真实 renderer 的全量验证覆盖。

部署检查新增并通过：独立 runtime 实现包、跨两个安装目录的 namespace package（含两侧资源）、wheel 构建 Python AOT、两种实际解压发行包构建与 API 运行、删除原解压包后的独立 run.py 执行。外部 Python 实现统一落在一个普通导入目录 `_dependencies`，没有为 namespace 增加独立加载器。

实现及清理已完成，尚待冻结源码后的最终 `python tools/verify_project.py --full`。最终完整结果不能沿用 AOT 阶段失败批次或上述定向批次；正式候选包应取最终冻结代码重建的产物，先前候选仅用于本阶段部署复验，不发布。


### 整理后完整批次 1（保留失败）

18 步完整执行，15 步通过、3 步失败，约 35 分钟。pytest 4525 通过、1 失败：此前 namespace 缓存挡住当前项目的同名 nodes.py。JS 集成 43/50，7 个用例读取已移入 target_metadata 的旧顶层字段；迁移回归 202/207，5 项 compiler annotation 断言同样读取旧字段。记录见工作区外 final-full-20261016-verification.json / results.txt / failures.txt。

其余通过：Python 104/104、规则对照 1223/1223、规则补充、真实 Browser 运行观测、布局/资源展示、两端审查性能、wheel、双 profile 解压后构建与独立运行、最终质量与清洁目录。它们不能抵消本批失败。

集中处理：按 Python 的 package/module/namespace 优先级统一本地模块身份，替换父包时一并清除其旧子模块；显式迁移所有沙箱和迁移回归的 manifest 读取，未加入兼容解码。只读 Mapping 选项的手工对照显示此前 bundle 丢失已保存默认值，现与源码共用选项合并。插件 factory 失败对照曾为源码 CheckedRunError/ERROR、bundle RuntimeError，现共用 checked factory 编排，保留部分创建后的释放及主异常。低层 AOT 的插件整个生命周期纳入运行观测，释放失败也能形成 failed 状态。

Python build 结果保留实际 HealthReport，CLI 不将 CONCERNS 写成 PASS；两种 CLI 共用执行报告与 checked 错误呈现，结果携带已有的输出声明事实，源码 CLI 不再为报告重读一次配置。后续先复验所有已暴露范围，再冻结版本重跑完整批次。

操作记录：一次仓库工具自测未设置 TMPDIR，测试自身上下文已清理；后续自测纳入显式 AI 临时区环境，不据此扩大清理系统临时目录。


### 完整批次 1 后的集中复验

600 通过、1 失败、4 跳过；唯一失败是 dispatch 的 SimpleNamespace 构建替身未提供 health，现改为真实 PythonBuildResult。仓库工具 53/53；迁移回归 207/207，原 5 项 compiler annotations 均通过。真实 JS 集成 45/50，原 7 项元数据失败均已消失，5 个 Browser 启动失败（Code null）单列为环境问题，不能记成通过。

同一个 Chrome 148 和 Puppeteer 启动对照：64 字符 TMPDIR 下 Code null，39 字符 AI 临时目录下启动成功。后续验证使用更短的本次 AI 目录，仍运行真实 Browser，不调整测试条件或超时。原记录见 final-repair-validation-20261016.json 及失败文件；下一批先修完替身并复验 Browser，然后重新完整验收。


### 生命周期装配的最后对照

真实 Browser 短路径复验 50/50；Python 113/113。随后首个构造顺序原型确认：源码插件先于 Node 构造，原 AOT 反序会使依赖插件初始化的 Node 失败。现首次 run 在插件生命周期内调用同一 bind_python_workflow；创建 runtime 只装配结构，Node 仍按 runtime 共享，插件仍按每次执行创建/释放。静态装配不调用 NodeRegistry.get，代码生成依赖结构而非活类；延迟实现的绑定定位直接来自声明，包收集读取 import spec/resources，不导入延迟实现体。绑定错误由源码与 bundle 共用入口形成原有 CheckedRunError 和定位。

扩大复验 2787 通过、4 失败、2 跳过：一项新增用例在 run 前读取了尚未绑定的私有 node 字段，已将原身份断言移到执行后；三项新构造顺序夹具在 Node 中写文件日志，被既有 Rule 正确拒绝。随后 269 通过、3 失败，残留仍是这个夹具的构造期 IO。改为直接比较 Node 对象身份，同时保留原生源码和构造顺序断言，不放宽 Rule，也不修改历史失败记录。


构造顺序及延迟装配复验 102/102，质量检查通过。三种执行模式验证“插件初始化 → Node 构造 → 执行 → 插件释放”；同一 runtime 的 Node 身份保持，另一 runtime 拥有独立实例；搬离并删除源码后延迟 Node 实现仍可加载。运行阶段使用保存的结构和生成代码，未重做 GraphCompiler、计划推导或块生成。最终完整批次必须在这些修复之后重新执行。


最终装配的 wheel / 双 profile 隔离复验通过，包括各解压包构建 bundle、API 执行、删除原项目后的独立 run.py。接下来冻结源码执行完整批次 2；候选交付仅采用该批次重建且通过的产物。


### 完整批次 2（通过，后续修复另行复验）

18/18；pytest 4536/4536，无跳过；Python 104/104，JS 真实 Browser 集成 50/50，规则对照 1223/1223，补充规则 680/680，迁移回归 207/207，wheel 与双 profile 部署均通过。证据为工作区外 final-full-2-20261016-*。本批生成候选暂不作为最终交付，因为只读复核另已复现“部分插件构造失败后 dispose 延迟导入缺少 source_paths”的清理缺口。

最后整改将部分失败释放放入 factory 所用的受管理导入路径，同时保留所属 Root 的现有加载次序；AOT 的部分释放使用已实际创建的顺序逆序，和源码一致，不借用按 Hook priority 排序的列表。正常 Hook 顺序和正常释放行为不变。需以混合优先级、延迟导入的真实失败用例复验 compiler/runtime，并在这之后重新完整验收。


### 部分构造失败的最终清理复验

compiler/runtime 混合优先级、延迟导入、源码及已搬迁 bundle 的原始场景通过；相关定向共 131/131。保留 factory failure 为主错误，全部已创建实例按实际创建顺序逆序释放，项目路径随后退出且不泄漏。正常 Hook/释放顺序继续沿用既有实现。一次定向命令误写测试文件名而未收集测试，已单列 not-collected，未计为验收。最终源码自此冻结，完整批次 3 覆盖这个最后修复，交付候选取该批产物。

### 最终完整批次 3 与交付

`python tools/verify_project.py --full --workers 8`：18/18 通过；pytest 4538/4538、无跳过；Python 沙箱 104/104、JS 真实 Browser 集成 50/50、规则对照 1223/1223、补充规则 680/680、迁移回归 207/207。布局、两端资源展示及审查性能、wheel 隔离、双 profile 发行构建、最终仓库质量与清洁目录均通过。完整状态、汇总及场景详情分别保存于工作区外 `final-full-3-20261016-verification.json`、`final-full-3-20261016-results.txt`、`final-full-3-20261016-details.json`。

正式本地候选目录为 `/home/rockingsisyphus/projects/VibeFlow-evidence/aot-unification-20261016/candidates-ready`，包含 wheel、标准与 autonomous 两种 ZIP、SHA256SUMS，以及带输入示例的 `python-aot-example`。wheel 和两种实际解压包均完成构建 AOT、API 执行、删除原项目后的独立入口运行；交付目录中的示例复制完成后再实跑通过，结果保存为 `final-example-check.txt`。候选文件与 bundle 清单已核对；删除本任务先前两组过时候选，仅保留最终可交付版本及各批历史验收证据。既有发行资产未覆盖。

最终性能见同目录 `final-aot-performance-20261016.json`：三次独立进程、热文件系统、同一三节点 CPU 图与空输入，compiled/trace=off，每进程重复 30 次。双方均排除图形及前置资料输出；源码包含工作区加载和 checked-run 静态审查，启动计时包含 API 导入但不含解释器启动。中位启动至首次结果为源码 384.7 ms、AOT 236.0 ms；静态审查/加载为 87.8/4.8 ms；创建 runtime 为 30.4/88.5 ms，首次执行为 1.5/10.7 ms（AOT 包含延迟 Node 绑定）。重复执行为 0.621/0.632 ms，构建为 285.7 ms。不同入口把模块导入和绑定分摊在不同阶段，不能单独比较 create_runtime；总启动减少约 39%，重复执行无明显收益。本观察不代表 GPU 吞吐，先前阶段数据另行保留。

执行中的成本、目标与路线复核：最终共同计划、静态装配及原生 runtime 路线已在三种模式、对象引用、任务/取消/锁、插件及迁移部署场景下验证；未缩小公开覆盖或添加第二套执行器。维护路径通过上述实际整改减少，仍有效的公开契约、平台支持与历史证据按列明理由保留，不宣称所有技术债清零。本次未修改 vibeTrain 安装，未启动远程训练，未 commit、push 或发布 Release；完整批次后仅补记结果、执行性能观察，并删除展示类型文件末尾的多余空行（AST 含位置逐项相同），未再修改产品逻辑或测试。候选包保留完整验收时冻结的版本。临时构建、测试与性能材料均已清理。

### 文档复核补充

后续用户询问文档同步情况时，再次核对当前开发文档与发行使用文档：修正产品边界文档把当前 ABI 错归于 0.17.0 的表述，并明确 Python AOT 的 run 阶段静态审查和目录源码收集与 JS AOT 的区别。仅调整文档，未修改产品或测试；候选包仍是上轮冻结版本，不将这次文档复核称为新一轮完整验收。
