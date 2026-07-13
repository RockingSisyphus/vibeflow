# VibeFlow AI 开发指引

本目录是一个可复制的业务项目开发包，内置 `kernel/vibeflow-kernel.zip` 作为运行和校验内核。AI 默认应按本文开发业务程序。

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
- node 默认必须是纯函数：不要读写文件、网络、数据库、浏览器、环境变量或启动外部进程。
- 外部输入输出必须建模为 `io`、`data_store`、`document` 类型节点，或明确的 `external=True` 节点。
- 控制流只写在 JSONC 的 `pipeline.edges` 中；不要用 Python 调用关系隐式表达流程。
- `requires` / `provides` 只表达数据契约，不会自动生成控制流或图上的理论数据边；没有显式 edge，就没有图边。
- 每个 `pipeline.nodes[]` 调用点必须写 `id` 和 `type_used`。旧 `name`、调用处旧 `type`、旧 `registry_key`、旧 `nodeset.xxx` 前缀都不再接受。
- Python node 的实现键来自 `NodeInfo.type_key`；nodeset 的实现键来自独立 nodeset JSONC 根对象的 `type_key`。调用处 `type_used` 可以指向二者之一或系统类型。
- Health 会推断同步主线、data bypass 和 async 相关边。主线 edge 负责调度并在 SVG/Mermaid 加粗；data bypass edge 只投递数据不触发目标并显示虚线；async edge 连接显式 async node/nodeset，不进入同步主线。
- terminal start/end 只定义起止，不读取、不提供、不转发业务 envelope。mainline edge 负责调度与投递；data bypass 只投递不触发，且必须从真正提供 target 所需 type 的 node 发出。
- 每个 `pipeline.nodes[]` 调用点都必须写 `display_name` 和 `description`，让 Mermaid/SVG 能直接区分节点名、易读名和说明。
- `requires`、`provides`、`pipeline.inputs`、`pipeline.outputs` 的每个对象都必须写非空 `display_name`。图上 contract label 先显示 `display_name`，再显示 id/key/type。
- `project/registry.py` 同时声明可用 node、base_lib 和 plugin；base_lib/plugin 的 `register(...)` 必须写 `display_name` 和 `description`。workflow config 只用 `base_lib.modules[].id` 和 `plugins[].id` 引用本流程实际使用的资源，不要把未使用资源写进 config。
- `vibeflow_project.jsonc` 只保留 `registry`、`quality_enabled`、`quality` 和可选的 `runtime.async_max_workers` / `runtime.async_flush_timeout`；不要把 base_lib/plugin 当成 root 级全局启用项写在这里。
- 节点自定义颜色只能写在 `style.fill`、`style.stroke`、`style.text` 中，颜色必须是 `#RRGGBB`，且不得使用 VibeFlow 系统保留色。合法自定义色会覆盖节点默认/系统 class 的 fill/stroke/text 颜色。
- `display_name`、`description`、`style`、`similar_to` 是调用点元数据，不进入运行时 `params`；运行时同名参数必须写进 `config`。
- 只有确认两个 node 是有意变体或副本时才写 `similar_to`，并且必须指向同作用域已存在 node、使用 `variant` 或 `copy`、写清 `reason`；不要用它掩盖应该拆分或抽 base_lib 的重复实现。
- 普通 `pipeline.edges` 和 nodeset 内部 `pipeline.edges` 不允许形成环；所有循环都必须使用唯一一等 loop 类型 `vibeflow.loop.while` 调用 nodeset body。
- nodeset 必须是独立 JSONC 文件，根对象声明 `type_key`、`display_name`、`description`、`requires`、`provides` 和 `pipeline`；主 config 不允许内联 `nodesets`，nodeset 文件也不允许 `exports`、`purity`、`category`、`version`。
- nodeset 文件可以写 `nodeset_imports` 调用其他独立 nodeset 文件；调用处直接用 nodeset `type_key` 作为 `type_used`，不要写旧 `nodeset.xxx` 前缀。
- nodeset 调用和 `loop.body` 都是 nodeset dependency，不能直接或间接递归；出现 `NODESET.RECURSION` 时要拆开结构或改成真正的 `vibeflow.loop.while` 循环语义。
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

- 输入/输出边界节点只负责读取、写入、格式解码、字段规范化和外部表示转换；业务规则、分类、合并、校验与错误语义应由明确的 process/decision 节点负责。不要在边界、guard、聚合器和输出节点中各复制一份业务逻辑。
- 在进入共享业务判断之前，边界必须无损保留未知字段/值、字段缺失状态和异常身份；它只能做表示/词法适配并产生显式 malformed 标记，不能提前把不同输入压成同一个默认错误。
- 多个入口承诺相同语义时，它们必须在图上汇入同一套实际执行的共享语义节点或 nodeset。仅仅复用一个 Python helper、使用相似名字，或分别复制等价代码，不等于共享语义链。
- guard 可以识别入口特有的词法或封装错误，但必须把规范化后的错误身份原样传递给后续错误处理；不要把不同错误统一改写成一个默认错误。错误构造节点只负责形成输出表示，不应重新判断或覆盖错误类别。
- guard/error 分支不能形成从原始输入直达业务输出的捷径，从而绕过字段解析、类型转换、合并、校验或其他声明的共享职责。`data bypass` 只用于不触发目标的辅助数据投递，不能冒充业务主线或规避结构约束。
- 外部读写必须由显式 `io` / `data_store` / `document` / `external=True` 节点及其 contract 建模。业务结果应由拥有该语义的节点提供，再由 output I/O 节点序列化或写出；不要让输出节点扫描原始输入重新计算结果。
- 优先建立 `terminal → input I/O → process/nodeset → output I/O → terminal` 控制脊柱。内部语义结果与外部输出用不同的明确 key/type，由 output I/O 无损适配，不要重复声明 provider key。
- tagged value 的 tag 必须使用业务规范中的精确字面量，value 必须转换为匹配的 Python 原生类型；不缩写 tag，不把整数留作字符串。
- 测试门禁的顶层 `OVERALL`/退出状态是完成判据；局部维度 PASS、若干 case 通过或生成了报告都不能替代顶层 PASS。任何代码修改都会使此前的通过结果失效，必须重新运行 required gate；只有最新结果与当前代码一致且顶层 PASS 时才能声明完成。
- required gate 失败后，如果代码没有变化，不要重复运行同一失败门禁。先读取它给出的失败项和完整报告位置，修改根因后再运行。无法获得新鲜的顶层 PASS 时，应明确报告未完成；若实验协议要求结构化完成声明，必须按协议输出字面量 `INCOMPLETE`，不能用自然语言成功宣称替代它。

## 先读文档

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

1. 先把用户希望开发的程序抽象成一个粗粒度标准流程图，只保留几大块。
2. 用 planned nodeset 表达这些大块。例如初始流程是 `a -> b -> c`，就为 `a`、`b`、`c` 各写一个独立 planned nodeset JSONC 文件，根对象声明 `type_key`，再在顶层 config 用 `type_used` 调用它们并连接 `pipeline.edges`。
3. planned node 必须声明 `id`、`display_name`、`description` 和 `flow_kind`；planned nodeset 必须声明 `type_key`、`display_name`、`description`、`requires` 和 `provides`，但可暂时不写内部 `pipeline`。默认 `planned_behavior` 是 `blocking`，只用于架构图审查。
4. 生成流程图给人类审核：快速源码图用 `python run.py mermaid --config project/configs/main.jsonc --output reports/graph.mmd`，快速图片用 `python run.py svg --config project/configs/main.jsonc --output reports/graph.svg`。
5. 需要展开 nodeset 给人类审查时，必须用 `python run.py svg --config project/configs/main.jsonc --expand-nodesets --output reports/graph.expanded.svg` 生成详细审查 SVG。不要把 `graph.expanded.mmd` 直接交给 Mermaid CLI/mmdc 渲染成 SVG；那会绕过 VibeFlow 的 review-columns/detail-panel composer，导致排版退回旧的全局展开图。
6. 告知人类审核员查看 `reports/graph.mmd`、`reports/graph.svg` 或 `reports/graph.expanded.svg`。不要在粗粒度架构未经确认时直接实现大量 node。
7. 人类审核通过后，再逐个细化 nodeset。比如把 planned nodeset `a` 细化为 `d -> e -> f`，可以先把 `d`、`e`、`f` 也标为 planned，再生成展开图继续审核。
8. 细化可以继续嵌套；任何尚未确定的节点或节点集都应保持 `status: "planned"`，用流程图先暴露结构。
9. 真正实现某个 node 时，必须创建对应 Python node，声明 `NODE_INFO`、`CONTRACT` 和 `run_pure(inputs, params)`，并在 `project/registry.py` 注册。真正实现某个 base_lib/plugin 时，也在同一个 `project/registry.py` 的 `build_base_lib_registry()` / `build_plugin_registry()` 注册为可用资源；实际 workflow 需要时再在 config 中按 id 引用。
10. 真正实现某个 nodeset 时，必须补齐 `requires`、`provides`、内部 `pipeline.nodes` 和 `pipeline.edges`，且移除该 nodeset 的 `status: "planned"`；不要写已移除的 `exports` 或 `purity`。
11. 只有当 nodeset 内部所有子 node / 子 nodeset 都已经 implemented，父 nodeset 才能变成 implemented。例外是设计期可用 `planned_behavior: "transparent"` 或 `python_stub` 子节点保持连通性，此时父 nodeset 会得到 warning；blocking planned child 仍会报错。
12. 按同样方式实现后续 nodeset，直到顶层 `a`、`b`、`c` 全部 implemented，最终程序才能运行。
13. 如果需要训练或批处理循环，先把循环 body 抽成 nodeset，再用 `vibeflow.loop.while` 调用；body 内只表达单轮逻辑，跨轮状态用 `loop.carry`，指标列表用 `loop.collect`，固定轮数用 `loop.stop_after`，条件退出用 body/state 输出的 bool `loop.stop_when`。
14. 后续修改架构也使用同一模式：先放 planned 占位并导出流程图给人类审核，再逐步实现。
15. `validate` 和 `quality` 只是静态门禁。每个 runnable config 还必须用最小代表输入做一次 runtime probe（运行时探针），检查业务结果 key、envelope `value` 的 Python 原生类型、`runtime.stop_reason == "completed"` 和 `runtime.qualified_exec_order`。

## 常用命令

- 校验配置和健康检查：`python run.py validate --config project/configs/main.jsonc`
- 校验 kernel 完整性：`python run.py verify-kernel`
- 运行程序：`python run.py run --config project/configs/main.jsonc --run-root runs`
- 导出 Mermaid：`python run.py mermaid --config project/configs/main.jsonc --output reports/graph.mmd`
- 导出展开 nodeset 的 Mermaid 源码：`python run.py mermaid --config project/configs/main.jsonc --expand-nodesets --output reports/graph.expanded.mmd`。这个文件只用于调试源码，不要直接用 Mermaid CLI/mmdc 转成 SVG。
- 导出 SVG：`python run.py svg --config project/configs/main.jsonc --output reports/graph.svg`
- 导出展开 nodeset 的详细审查 SVG：`python run.py svg --config project/configs/main.jsonc --expand-nodesets --output reports/graph.expanded.svg`
- 质量检查业务代码：`python run.py quality --path project`

## 判断标准

- 内核报错代表架构、配置、契约或实现不满足约束；修业务项目，不修内核。
- planned 内容用于设计审查；默认不可运行，只有 `python_stub` 在显式开发开关下可执行。
- `planned_behavior: "transparent"` 只用于 flow health 连通性，不可运行。
- `planned_behavior: {"kind": "python_stub", "stub_module": "project/stubs/xxx.py"}` 只用于开发测试；必须配合 `--allow-planned-stub` 才能运行，不能视为 production ready。
- implemented 内容必须完整、可达、可校验、可运行。
- 流程图是人类审核程序结构的主要产物；重大架构变更先出图再实现。SVG 节点和资源列内应能读清易读标题、`id`、`type_used`、状态和说明，contract 应显示在已有连边上并优先显示 `display_name`；信息挤在一起时应先改善 config 的描述长度、拆节点或调整 style，而不是绕过 `python run.py svg`。SVG 默认保持 `htmlLabels=false`，并由内核对原生 SVG 文本做标题加粗、字段名前缀加粗、字段行左对齐等增强。
- 为消除 `NODESET.SMELL.TOO_WIDE` 拆成更多小 nodeset 是推荐方向；如果怀疑 config 读取或解析慢，用 `VIBEFLOW_CONFIG_TRACE=1 python run.py validate --config ...` 查看 import、nodeset 数、单个 nodeset 解析耗时和总耗时。
- 一等 loop 的展开图应能看到 loop body nodeset；调试训练循环时优先看 `runtime.qualified_exec_order`、`runtime.total_step_count` 和事件 `path`，不要只看顶层 `runtime.exec_order`。
- `GRAPH.JOIN.AMBIGUOUS_UNCONDITIONAL` 表示某个 join 可能被 unconditional provider 提前触发或和 conditional provider 争抢同一个 `exactly_one` 输入；修配置，不要靠旧 context 或节点内部判断绕过。
- 系统保留色不能作为自定义色：普通 node 默认 `#ECECFF/#9370DB/#333333`，planned `#fef08a/#ca8a04/#713f12`，plugin resource `#eff6ff/#2563eb/#1e3a8a`，base_lib resource `#ecfdf5/#059669/#064e3b`，以及 health、external、document、nodeset 等语义色。
- 健康检查的 warning/error 要先看 `object_id`、`source_location` 和 `details`。`details.owner` 区分顶层 `pipeline` 与 `nodeset:<name>`；flow/data 问题会列出相关 edge、direct source、provider type 或 downstream requirement 摘要；mainline 问题会列出 `source` / `target`、`branch_nodes`、`branch_edges`、`mainline_path` 和 `suggested_fixes`。`GRAPH.SMELL.DUPLICATE_LOGIC` 会列出具体 nodes、node_types、fingerprint 和 duplicate_group；只有确认为有意关系时才补 `similar_to`。
- 如果 `details.aggregated == true`，先修代表 finding 指向的 `owner` / `node` / `required_type` / `direct_sources`；`occurrences` 是 nested nodeset / loop body 静态展开后被压缩的重复次数，不是独立 bug 数。
- `python run.py quality --path ...` 的文本报告也会打印 `object_id` 和紧凑 `details:`；重复函数、依赖环、双向依赖和内部模块 import warning 按 details 中的函数和 import site 修改。
- 调试嵌套 nodeset 或 loop 时，顶层运行顺序看 `runtime.exec_order`，完整嵌套顺序看 `runtime.qualified_exec_order` 和事件的 `path` 数组；`qualified_node` 是给人看的 dotted 展示名。
