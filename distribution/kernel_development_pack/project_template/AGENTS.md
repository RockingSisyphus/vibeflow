# VibeFlow AI 开发指引

本目录是一个可复制的业务项目开发包，内置 `kernel/vibeflow-kernel.zip` 作为运行和校验内核。AI 默认应按本文开发业务程序。

## 任务判定与审核协议

- 先判定任务是新建项目（greenfield）还是修改已有项目（existing）。只有 greenfield 或用户明确批准整体重构时，才先建 `a → b → c` 粗粒度 planned 拓扑。
- existing 任务必须先读所属 root 登记的 `ARCHITECTURE.jsonc`，再按 source 定位同一个真实 workflow config、相关 nodeset 和 registry。
- 修改前先输出`复用 / 修改 / 删除 / 新增`清单，逐项写明 source path、node/edge/hook id、当前职责和计划变化。只修改清单内对象；未列出的 id、edge、hook 和调用层级默认保持。
- existing 任务只能在登记 workflow 及其真实 source 上原位修改。不得为审核新建平行 config，不得用手写 Mermaid/SVG、概念图或笼统差异图替代修改原项目。
- 正式审核统一执行 `python run.py review --config <登记的 workflow> --output <expanded.svg>`。`review` 会做源图 preflight，自动更新登记的架构文档，再做正式 validate、canonical expanded SVG 渲染和结构检查。
- `review` 必须 fail-closed：任何阶段失败立即停止，不得直接调用 Mermaid CLI/mmdc，不得用 expanded `.mmd`、手写 SVG 或旧产物补位。
- 用户要求“审核后再实现”或“等我确认”时，当前轮在生成审核产物后必须停止。只有后续一条明确用户批准消息才算通过；`validate`、`architecture`、`svg` 或 `review` 成功都不等于人类批准。

## CLI 让渡模式 / delegate-cli

- 用户要求普通业务 CLI 时，使用 `python run.py delegate-cli --config project/configs/main.jsonc -- <business argv>`；不另写顶层 launcher 绕过 manifest、workspace、health 和 run artifact。
- 首个 `--` 是可选分界：分界前的已知 core 参数由 VibeFlow 消费，未知 token 原序让渡；分界后全部原样让渡。业务参数与 core 同名时放到 `--` 之后。
- workflow 必须接受 `cli.argv` pipeline input，并通过 `exactly_one` pipeline output 产生唯一 `cli.exit_code`；最终 provider 的 key/type 都必须是 `cli.exit_code`，值是非 bool 整数 `0..255`。
- 业务 stdin/stdout/stderr 是真实进程标准流；不包装成 `cli.response`，不让 VibeFlow 捕获/重放，不添加 JSON 或换行。VibeFlow 诊断只写当次 run 的 `vibeflow.log`，不记录 argv 原文或业务流。
- 只有 `io` / `document` / `data_store` node 或 runtime plugin 可抛授权 `SystemExit`。`None` 返回 0，非 bool 整数 `0..255` 原样返回；其他值、未授权 `SystemExit`、health/runtime/CLI contract 失败返回 1。已知 core 参数的 argparse 错误返回 2 且不创建 run；run 目录无法创建时才可向 stderr 写最小诊断并返回 1。
- `delegate-cli` 不替代 `run` 的通用执行/结构化诊断职责，也不改变 `review` 的正式架构审核职责。

## 硬性边界

- 不要解包、修改或重建 `kernel/vibeflow-kernel.zip`。
- 不要修改 `kernel/`、`run.py` 或 `kernel/MANIFEST.sha256`；这些文件由分发包构建脚本生成和校验。
- 不要为了理解内核而读取或展开 `kernel/vibeflow-kernel.zip`；开发业务程序时只读 `kernel/docs/`、`project/` 和本文件。
- `kernel/docs/`、`kernel/tools/` 和 `kernel/THIRD_PARTY_NOTICES.md` 是随内核分发的只读参考材料；根目录 `README.md`、`AGENTS.md` 和项目自己的说明可由项目维护者定制。
- 分发包不内置 `.gitignore`；如果项目需要 Git 忽略规则，由项目自行添加，常见忽略项包括 `kernel/tools/mermaid-renderer/node_modules/`、`runs/`、`reports/`、`__pycache__/` 和 `*.pyc`。
- 如果内核报错或警告，优先修改 `project/` 下的业务代码、registry 或 JSONC 配置来满足内核要求；不要 patch 内核来绕过检查。
- 如果完整性检查失败，不要通过修改 manifest 或 `run.py` 绕过；应从可信来源重新生成或恢复分发包。
- 业务代码只放在 `project/nodes/`、`project/base_lib/`、`project/plugins/` 和 `project/configs/`。
- `project/nodes/` 放业务 node；`project/base_lib/` 放可复用纯 helper；`project/plugins/` 放 policy/compiler/runtime 插件；`project/configs/` 放可运行 JSONC；`project/configs/nodesets/` 放可复用 nodeset JSONC。
- 不要把业务 `.py` 堆在 root 顶层或单个宽目录；`quality.structure` 默认允许 root 总文件数到 120，但单个代码目录超过 16 个 `.py` 会失败。
- 普通 implemented node 和 planned `python_stub` 使用 `effect_scope=none`，无业务 IO。`flow_kind=io` 使用 `terminal`，只开放真实标准流、`print` / `input` / `argparse`。`flow_kind=document` / `data_store` 使用 `python_io`，开放文件、环境、网络、数据库、subprocess 和终端。
- 图形 `flow_kind=terminal` 仍是 `effect_scope=none`，不要和权限档位 `terminal` 混淆。`effect_scope` 由内核派生，不在 config 中自由声明。
- 任意 node 只要 `external=True` 就以最高优先级使用 `effect_scope=trusted`；plugin 也是 `trusted`。`external=True` 会显式绕过普通 IO/purity 限制，只能用于真正外部维护/受信任实现，不能用来给项目内部代码逃避检查。契约、`flow_kind`、拓扑、输出和 trace 仍检查。
- effectful 或 `external=True` node 的 `CONTRACT.examples` 只做结构检查、不执行；只有 `none` 范围的普通实现样例可执行。
- 控制流只写在 JSONC 的 `pipeline.edges` 中；不要用 Python 调用关系隐式表达流程。
- `requires` / `provides` 只表达数据契约，不会自动生成控制流或图上的理论数据边；没有显式 edge，就没有图边。
- 每个 `pipeline.nodes[]` 调用点必须写 `id` 和 `type_used`。旧 `name`、调用处旧 `type`、旧 `registry_key`、旧 `nodeset.xxx` 前缀都不再接受。
- Python node 的实现键来自 `NodeInfo.type_key`；nodeset 的实现键来自独立 nodeset JSONC 根对象的 `type_key`。调用处 `type_used` 可以指向二者之一或系统类型。
- Health 会推断同步主线、data bypass 和 async 相关边。主线 edge 负责调度并在 SVG/Mermaid 加粗；data bypass edge 只投递数据不触发目标并显示虚线；async edge 连接显式 async node/nodeset，不进入同步主线。
- terminal start/end 只定义起止，不读取、不提供、不转发业务 envelope。mainline edge 负责调度与投递；data bypass 只投递不触发，且必须从真正提供 target 所需 type 的 node 发出。
- 每个 `pipeline.nodes[]` 调用点都必须写 `display_name` 和 `description`，让 Mermaid/SVG 能直接区分节点名、易读名和说明。
- `requires`、`provides`、`pipeline.inputs`、`pipeline.outputs` 的每个对象都必须写非空 `display_name`。图上 contract label 先显示 `display_name`，再显示 id/key/type。
- `project/registry.py` 同时声明可用 node、base_lib 和 plugin；base_lib/plugin 的 `register(...)` 必须写 `display_name` 和 `description`。workflow config 只用 `base_lib.modules[].id` 和 `plugins[].id` 引用本流程实际使用的资源，不要把未使用资源写进 config。
- `vibeflow_project.jsonc` 只保留 `registry`、`quality_enabled`、`quality`、可选 `runtime`，以及用于登记生成文档的 `architecture.documents`；不要把 base_lib/plugin 当成 root 级全局启用项写在这里。`runtime.async_max_workers` 控制每个 Runtime 自有线程池并发数（默认 4），`runtime.async_flush_timeout` 控制 detached task 收尾等待（默认 `null`，可设非负秒数），`runtime.nodeset_max_depth` 控制普通 nodeset 与 `loop.body` 的最大静态嵌套深度（默认 4）。
- `project/ARCHITECTURE.jsonc` 是由真实 workflow、nodeset、registry 和资源配置确定性生成的单文件审查视图。在判断、解释或修改项目架构前，必须优先阅读它来了解入口流程、调用层级、节点职责、数据契约和配置来源。不要手工编辑它，也不要把它当成可执行 config；要改变项目架构，必须修改 `project/configs/*.jsonc` 中的真实 workflow config 或其导入的相关 nodeset JSONC，必要时再修改 registry metadata/config schema。单独的 `python run.py architecture ...` 只用于缺失文档的预读修复或单项诊断；正式审核必须使用会自动更新文档的 `python run.py review ...`。
- 节点自定义颜色只能写在 `style.fill`、`style.stroke`、`style.text` 中，颜色必须是 `#RRGGBB`，且不得使用 VibeFlow 系统保留色。合法自定义色会覆盖节点默认/系统 class 的 fill/stroke/text 颜色。
- `display_name`、`description`、`style`、`similar_to` 是调用点元数据，不进入运行时 `params`；运行时同名参数必须写进 `config`。
- 只有确认两个 node 是有意变体或副本时才写 `similar_to`，并且必须指向同作用域已存在 node、使用 `variant` 或 `copy`、写清 `reason`；不要用它掩盖应该拆分或抽 base_lib 的重复实现。
- 普通 `pipeline.edges` 和 nodeset 内部 `pipeline.edges` 不允许形成环；所有循环都必须使用唯一一等 loop 类型 `vibeflow.loop.while` 调用 nodeset body。
- nodeset 必须是独立 JSONC 文件，根对象声明 `type_key`、`display_name`、`description`、`requires` 和 `provides`。implemented nodeset 还必须包含完整 `pipeline`；planned nodeset 可省略 `pipeline` 作为粗粒度占位，也可带 planned body 逐步细化。主 config 不允许内联 `nodesets`，nodeset 文件也不允许 `exports`、`purity`、`category`、`version`。
- planned nodeset 的 body 会进入 `ARCHITECTURE.jsonc` 和展开 Mermaid/SVG，并参与适用的 dependency、recursion、depth 与 planned-descendant 检查；它不会因此按 implemented body 执行。`python_stub` planned nodeset 始终作为单个 stub 执行，不展开 body。
- nodeset 文件可以写 `nodeset_imports` 调用其他独立 nodeset 文件；调用处直接用 nodeset `type_key` 作为 `type_used`，不要写旧 `nodeset.xxx` 前缀。
- nodeset 调用和 `loop.body` 都是 nodeset dependency，不能直接或间接递归；出现 `NODESET.RECURSION` 时要拆开结构或改成真正的 `vibeflow.loop.while` 循环语义。
- nodeset dependency 默认最多 4 层：顶层 pipeline 为 0，普通 nodeset 或 `loop.body` 首次进入为 1，循环迭代不累计。所有已加载和 planned 定义都检查；需要更深结构时在所属 root 的 `runtime.nodeset_max_depth` 中显式提高。
- `node_configs` 可以穿透 nodeset 调用和 `vibeflow.loop.while` 调用；dotted path 的每一段都写调用点 `id`，loop 段会进入该调用点的 `loop.body`，不要把 body `type_key` 当成路径段。
- `decision` 只用于分支选择，不要用 decision cycle 模拟 retry、训练循环、多 batch、多 epoch、carry state 或 metrics collect。
- loop 的退出条件只能在 `loop.stop_after` 和 `loop.stop_when` 中二选一；不要再写 `vibeflow.loop.for_each`、`loop.items`、`loop.epochs` 或 `loop.until`。
- `execution="block"` 是严格 block 模式，loop/body 不能 block 化时会启动前报错；`execution="compiled"` 会优先生成 graph/nodeset/loop block，不适合的区域回退 plan。
- `requires` 是数据需求，不是控制分支数。join 默认是 safe OR；只有确认任一 active incoming 都足够时才写 `any_active`，只有至少两条每轮都会激活的真实并行 schedule incoming 才写 `all`。transfer-only bypass 不参与 `all` 计数。
- `join_policy: "all"` 只用于每轮都会激活的真实并行 schedule 分支；顺序链、互斥分支和 transfer-only edge 都不能冒充这种并行。
- 按 `GRAPH.DATA.RUNTIME_REQUIREMENT_UNREACHABLE`、`GRAPH.DATA.NO_PAYLOAD_BYPASS`、`GRAPH.JOIN.ALL_DEPENDS_ON_TRANSFER_ONLY`、`GRAPH.JOIN.ALL_BRANCHES_MUTUALLY_EXCLUSIVE` 和 `GRAPH.JOIN.REDUNDANT_ALL` 的 schedule/transfer/provider/decision-branch details 修图，不要用 start shortcut 或多写 `all` 掩盖数据不可达；同一 decision 的互斥分支不能用 `all` 汇合。
- 非 decision 同步 fan-out 必须有明确语义：分支通过 `join_policy: "all"` 汇合、被识别为 data bypass，或分支目标显式写 `async`。遇到 `GRAPH.MAINLINE.*`，按 details 里的 `source`、`target`、`branch_nodes`、`branch_edges` 和 `suggested_fixes` 改配置。
- node 间可以按引用传递普通 Python 对象；不要依赖 trace 或报告保存对象内容，报告只审计流程和 key。
- 自定义 adapter/启动器读取真实业务输出时，必须从成功运行返回的 `CheckedRunResult.context` 取 envelope，例如 `result.context.get("response.value")["value"]`。不要从 `output_summary.json` 返推业务值；摘要中的 `"scalar": true` 只表示原值是标量，不是业务布尔值 `True`。
- 需要后台指标、日志或诊断任务时，只能显式使用 config 的 `async: "detached"` 或 `async: "result_key"`；复杂后台任务可把调用点写成 nodeset `type_used` 并设置 `async`。不要在 node 内私自启动线程。
- 运行或交付前必须让内核健康检查通过；不要跳过 `python run.py validate ...`。

## 业务语义边界与完成契约

- `io` 边界可以从真实标准流读写、用 `argparse` 解析 `cli.argv`，并做格式/词法适配；业务规则、分类、语义合并、领域校验与错误语义应由明确的 process/decision node 负责。不要在边界、guard、聚合器和输出节点中各复制一份业务逻辑。
- 在进入共享业务判断之前，`io` 边界必须无损保留未知字段/值、字段缺失状态和异常身份；不能提前把不同输入压成同一个默认错误。
- 多个入口承诺相同语义时，它们必须在图上汇入同一套实际执行的共享语义节点或 nodeset。仅仅复用一个 Python helper、使用相似名字，或分别复制等价代码，不等于共享语义链。
- guard 可以识别入口特有的词法或封装错误，但必须把规范化后的错误身份原样传递给后续错误处理；不要把不同错误统一改写成一个默认错误。错误构造节点只负责形成输出表示，不应重新判断或覆盖错误类别。
- guard/error 分支不能形成从原始输入直达业务输出的捷径，从而绕过字段解析、类型转换、合并、校验或其他声明的共享职责。`data bypass` 只用于不触发目标的辅助数据投递，不能冒充业务主线或规避结构约束。
- 外部交互必须由显式 `io` / `data_store` / `document` node 及其 contract 建模。`io` 可做真实终端交互；`data_store` / `document` 可做真实 Python IO。业务结果应由拥有该语义的 node 提供；不要仅为获得更宽权限而伪造 `flow_kind`，也不要让输出 node 扫描原始输入重新计算结果。
- 优先建立 `terminal → input I/O → process/nodeset → output I/O → terminal` 控制脊柱。内部语义结果与外部输出用不同的明确 key/type，由 output I/O 无损适配，不要重复声明 provider key。
- tagged value 的 tag 必须使用业务规范中的精确字面量，value 必须转换为匹配的 Python 原生类型；不缩写 tag，不把整数留作字符串。
- 测试门禁的顶层 `OVERALL`/退出状态是完成判据；局部维度 PASS、若干 case 通过或生成了报告都不能替代顶层 PASS。任何代码修改都会使此前的通过结果失效，必须重新运行 required gate；只有最新结果与当前代码一致且顶层 PASS 时才能声明完成。
- required gate 失败后，如果代码没有变化，不要重复运行同一失败门禁。先读取它给出的失败项和完整报告位置，修改根因后再运行。无法获得新鲜的顶层 PASS 时，应明确报告未完成；若实验协议要求结构化完成声明，必须按协议输出字面量 `INCOMPLETE`，不能用自然语言成功宣称替代它。

## 先读文档

- 开始理解、设计或修改架构前，优先读 root 中登记的 `project/ARCHITECTURE.jsonc`；若文件缺失，先用 architecture 命令生成。改变架构时修改真实 workflow config 或相关 nodeset，不修改生成文档。
- 开始设计或修改业务程序前，先读 `kernel/docs/00_内核目的与项目结构.md`。
- 编写 node 前，读 `kernel/docs/01_Node开发规范.md`。
- 注册 node 和配置默认值前，读 `kernel/docs/02_注册与配置默认值.md`。
- 修改 pipeline/config 前，读 `kernel/docs/03_Config与Pipeline规范.md`。
- 设计或细化 nodeset 前，读 `kernel/docs/04_Nodeset规范与用法.md`。
- 编写纯 helper 或处理外部依赖前，读 `kernel/docs/05_BaseLib与外部依赖规范.md`。
- 编写 plugin 前，读 `kernel/docs/06_Plugin开发规范.md`。
- 运行、导出报告或定位产物前，读 `kernel/docs/07_启动命令与报告.md`。
- 不确定约束时，读 `kernel/docs/08_给AI开发者的约束清单.md`。

如果需要内核公开 API，只通过 `from vibeflow import ...` 使用，例如 `NodeInfo`、`NodeContract`、`NodeRegistry`、`HealthFinding`、`RuntimeOptions`、`CheckedRunResult`、`run_checked`、`run_workspace_checked`。不要依赖未在文档中说明的内部模块或私有函数。

## 推荐开发流程

1. 按本文顶部协议判定 greenfield 或 existing，不得把 existing 任务默认转成新的 planned config。
2. greenfield 先用粗粒度 planned node/nodeset 表达待审核架构；existing 先读登记架构文档、建立四类变更清单，然后在同一个 workflow 及其导入 nodeset 上原位修改。
3. planned node 必须声明 `id`、`display_name`、`description` 和 `flow_kind`；planned nodeset 必须声明 `type_key`、`display_name`、`description`、`requires` 和 `provides`。它可以无 body 占位，也可以用 planned nodes/edges 细化；默认 `planned_behavior` 是 `blocking`。
4. 执行 `python run.py review --config project/configs/main.jsonc --output reports/graph.expanded.svg` 生成正式审核产物。该命令会更新登记架构文档，无需先用多条命令手工拼接审核流程。
5. 告知人类审核员查看 `project/ARCHITECTURE.jsonc` 和 `reports/graph.expanded.svg`。用户要求审核门时，等待后续明确批准，不在当前轮实现待审部分。
6. 获得明确批准后才逐层实现 planned 内容。真正实现 node 时创建 Python node，声明 `NODE_INFO`、`CONTRACT` 和 `run_pure(inputs, params)`，并在 `project/registry.py` 注册。
7. 真正实现 nodeset 时补齐 `requires`、`provides`、`pipeline.nodes` 和 `pipeline.edges`，移除该 nodeset 的 `status: "planned"`。只有所有子 node/nodeset 都 implemented 时，父 nodeset 才能变成 implemented；保留 planned child 时按其 behavior 接受 warning/error。
8. 细化可以继续嵌套，但默认不得超过 4 层 nodeset/loop body；确有需要时在所属 root 的 `runtime.nodeset_max_depth` 中明确提高上限。
9. 训练或批处理循环先把单轮 body 抽成 nodeset，再用 `vibeflow.loop.while` 调用；跨轮状态用 `loop.carry`，指标列表用 `loop.collect`，固定轮数用 `loop.stop_after`，条件退出用 bool `loop.stop_when`。
10. 每次再次修改架构都重复“四类清单 → 真实 source 原位修改 → `run.py review` → 后续明确批准”，不得以新建审核 config 简化旧架构。
11. `validate` 和 `quality` 只是静态门禁。每个 runnable config 还必须用最小代表输入做 runtime probe，检查业务结果 key、envelope `value` 的 Python 原生类型、`runtime.stop_reason == "completed"` 和 `runtime.qualified_exec_order`。

## 常用命令

- 校验配置和健康检查：`python run.py validate --config project/configs/main.jsonc`
- 正式架构审核：`python run.py review --config project/configs/main.jsonc --output reports/graph.expanded.svg`
- 生成登记的单文件架构文档：`python run.py architecture --config project/configs/main.jsonc --output project/ARCHITECTURE.jsonc`
- 只检查架构文档是否是当前确定性输出：`python run.py architecture --config project/configs/main.jsonc --output project/ARCHITECTURE.jsonc --check`
- 校验 kernel 完整性：`python run.py verify-kernel`
- 运行程序：`python run.py run --config project/configs/main.jsonc --run-root runs`
- 作为普通业务 CLI 运行：`python run.py delegate-cli --config project/configs/main.jsonc -- --input data.yaml --verbose`
- 导出 Mermaid：`python run.py mermaid --config project/configs/main.jsonc --output reports/graph.mmd`
- 导出展开 nodeset 的 Mermaid 源码：`python run.py mermaid --config project/configs/main.jsonc --expand-nodesets --output reports/graph.expanded.mmd`。这个文件只用于调试源码，不要直接用 Mermaid CLI/mmdc 转成 SVG。
- 导出 SVG：`python run.py svg --config project/configs/main.jsonc --output reports/graph.svg`
- 导出展开 nodeset 的详细审查 SVG：`python run.py svg --config project/configs/main.jsonc --expand-nodesets --output reports/graph.expanded.svg`
- 质量检查业务代码：`python run.py quality --path project`

## 判断标准

- 内核报错代表架构、配置、契约或实现不满足约束；修业务项目，不修内核。
- planned 内容用于设计审查；默认不可运行，只有 `python_stub` 在显式开发开关下可执行。
- planned nodeset 可以没有 body，也可以带 body 逐步细化；带 body 会出现在单文件架构文档和展开图中，但不会因此获得 implemented 执行语义。
- `planned_behavior: "transparent"` 只用于 flow health 连通性，不可运行。
- `planned_behavior: {"kind": "python_stub", "stub_module": "project/stubs/xxx.py"}` 只用于开发测试；必须配合 `--allow-planned-stub` 才能运行，不能视为 production ready。
- implemented 内容必须完整、可达、可校验、可运行。
- `ARCHITECTURE.jsonc` 是 AI/开发者先读的完整结构索引，canonical expanded SVG 用于视觉审核；正式交付两类产物时必须运行 `python run.py review`。SVG 节点和资源列内应能读清易读标题、`id`、`type_used`、状态和说明，contract 应显示在已有连边上并优先显示 `display_name`；信息挤在一起时应先改善 config 的描述长度、拆节点或调整 style，不得绕过 `review`。
- 为消除 `NODESET.SMELL.TOO_WIDE` 拆成更多小 nodeset 是推荐方向；如果怀疑 config 读取或解析慢，用 `VIBEFLOW_CONFIG_TRACE=1 python run.py validate --config ...` 查看 import、nodeset 数、单个 nodeset 解析耗时和总耗时。
- 一等 loop 的展开图应能看到 loop body nodeset；调试训练循环时优先看 `runtime.qualified_exec_order`、`runtime.total_step_count` 和事件 `path`，不要只看顶层 `runtime.exec_order`。
- `GRAPH.JOIN.AMBIGUOUS_UNCONDITIONAL` 表示某个 join 可能被 unconditional provider 提前触发或和 conditional provider 争抢同一个 `exactly_one` 输入；修配置，不要靠旧 context 或节点内部判断绕过。
- 系统保留色不能作为自定义色：普通 node 默认 `#ECECFF/#9370DB/#333333`，planned `#fef08a/#ca8a04/#713f12`，plugin resource `#eff6ff/#2563eb/#1e3a8a`，base_lib resource `#ecfdf5/#059669/#064e3b`，以及 health、external、document、nodeset 等语义色。
- 健康检查的 warning/error 要先看 `object_id`、`source_location` 和 `details`。`details.owner` 区分顶层 `pipeline` 与 `nodeset:<name>`；flow/data 问题会列出相关 edge、direct source、provider type 或 downstream requirement 摘要；mainline 问题会列出 `source` / `target`、`branch_nodes`、`branch_edges`、`mainline_path` 和 `suggested_fixes`。`GRAPH.SMELL.DUPLICATE_LOGIC` 会列出具体 nodes、node_types、fingerprint 和 duplicate_group；只有确认为有意关系时才补 `similar_to`。
- 如果 `details.aggregated == true`，先修代表 finding 指向的 `owner` / `node` / `required_type` / `direct_sources`；`occurrences` 是 nested nodeset / loop body 静态展开后被压缩的重复次数，不是独立 bug 数。
- `python run.py quality --path ...` 的文本报告也会打印 `object_id` 和紧凑 `details:`；重复函数、依赖环、双向依赖和内部模块 import warning 按 details 中的函数和 import site 修改。
- 调试嵌套 nodeset 或 loop 时，顶层运行顺序看 `runtime.exec_order`，完整嵌套顺序看 `runtime.qualified_exec_order` 和事件的 `path` 数组；`qualified_node` 是给人看的 dotted 展示名。
