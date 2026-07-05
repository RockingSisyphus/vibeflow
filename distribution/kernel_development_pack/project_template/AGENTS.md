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
- node 默认必须是纯函数：不要读写文件、网络、数据库、浏览器、环境变量或启动外部进程。
- 外部输入输出必须建模为 `io`、`data_store`、`document` 类型节点，或明确的 `external=True` 节点。
- 控制流只写在 JSONC 的 `pipeline.edges` 中；不要用 Python 调用关系隐式表达流程。
- `requires` / `provides` 只表达数据契约，不会自动生成控制流。
- 每个 `pipeline.nodes[]` 调用点都必须写 `display_name` 和 `description`，让 Mermaid/SVG 能直接区分节点名、易读名和说明。
- 节点自定义颜色只能写在 `style.fill`、`style.stroke`、`style.text` 中，颜色必须是 `#RRGGBB`，且不得使用 VibeFlow 系统保留色。合法自定义色会覆盖节点默认/系统 class 的 fill/stroke/text 颜色。
- `display_name`、`category`、`version`、`description`、`style`、`similar_to` 是调用点元数据，不进入运行时 `params`；运行时同名参数必须写进 `config`。
- 只有确认两个 node 是有意变体或副本时才写 `similar_to`，并且必须指向同作用域已存在 node、使用 `variant` 或 `copy`、写清 `reason`；不要用它掩盖应该拆分或抽 base_lib 的重复实现。
- 普通 `pipeline.edges` 和 nodeset 内部 `pipeline.edges` 不允许形成环；所有循环都必须使用唯一一等 loop 类型 `vibeflow.loop.while` 调用 nodeset body。
- nodeset 通过符号表解析；`nodeset.xxx` 和 `loop.body` 可以引用同一 config 中后面才声明的 nodeset，不要为了可见性调整声明顺序。
- `nodeset.xxx` 调用和 `loop.body` 都是 nodeset dependency，不能直接或间接递归；出现 `NODESET.RECURSION` 时要拆开结构或改成真正的 `vibeflow.loop.while` 循环语义。
- `decision` 只用于分支选择，不要用 decision cycle 模拟 retry、训练循环、多 batch、多 epoch、carry state 或 metrics collect。
- loop 的退出条件只能在 `loop.stop_after` 和 `loop.stop_when` 中二选一；不要再写 `vibeflow.loop.for_each`、`loop.items`、`loop.epochs` 或 `loop.until`。
- `execution="block"` / `execution="compiled"` 会执行结构化 `LoopBlock`，loop body 不能 block 化时会报错，不会静默降级。
- join 默认是 safe OR；只有确认任一 active incoming 都足够触发目标时才写 `join_policy: "any_active"`，需要等待所有 incoming 时写 `join_policy: "all"`。复杂分支汇合优先写显式 merge/select node。
- node 间可以按引用传递普通 Python 对象；不要依赖 trace 或报告保存对象内容，报告只审计流程和 key。
- 需要后台指标、日志或诊断任务时，只能显式使用 config 的 `async: "detached"` 或 `async: "result_key"`，不要在 node 内私自启动线程。
- 运行或交付前必须让内核健康检查通过；不要跳过 `python run.py validate ...`。

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

如果需要内核公开 API，只通过 `from vibeflow import ...` 使用，例如 `NodeInfo`、`NodeContract`、`NodeRegistry`、`HealthFinding`、`RuntimeOptions`、`run_checked`。不要依赖未在文档中说明的内部模块或私有函数。

## 推荐开发流程

1. 先把用户希望开发的程序抽象成一个粗粒度标准流程图，只保留几大块。
2. 用 planned nodeset 表达这些大块。例如初始流程是 `a -> b -> c`，就在顶层 config 中定义 `a`、`b`、`c` 三个 `status: "planned"` 的 nodeset，并在顶层 `pipeline.edges` 中连接 `a -> b -> c`。
3. planned node 必须声明 `flow_kind`，并像 implemented node 一样写 `display_name` 和 `description`；planned nodeset 可暂时不补齐内部 pipeline、契约和 exports。默认 `planned_behavior` 是 `blocking`，只用于架构图审查。
4. 生成流程图给人类审核：快速源码图用 `python run.py mermaid --config project/configs/main.jsonc --output reports/graph.mmd`，快速图片用 `python run.py svg --config project/configs/main.jsonc --output reports/graph.svg`。
5. 需要展开 nodeset 给人类审查时，必须用 `python run.py svg --config project/configs/main.jsonc --expand-nodesets --output reports/graph.expanded.svg` 生成详细审查 SVG。不要把 `graph.expanded.mmd` 直接交给 Mermaid CLI/mmdc 渲染成 SVG；那会绕过 VibeFlow 的 review-columns/detail-panel composer，导致排版退回旧的全局展开图。
6. 告知人类审核员查看 `reports/graph.mmd`、`reports/graph.svg` 或 `reports/graph.expanded.svg`。不要在粗粒度架构未经确认时直接实现大量 node。
7. 人类审核通过后，再逐个细化 nodeset。比如把 planned nodeset `a` 细化为 `d -> e -> f`，可以先把 `d`、`e`、`f` 也标为 planned，再生成展开图继续审核。
8. 细化可以继续嵌套；任何尚未确定的节点或节点集都应保持 `status: "planned"`，用流程图先暴露结构。
9. 真正实现某个 node 时，必须创建对应 Python node，声明 `NODE_INFO`、`CONTRACT` 和 `run_pure(inputs, params)`，并在 `project/registry.py` 注册。
10. 真正实现某个 nodeset 时，必须补齐 metadata、`requires`、`provides`、`exports`、内部 `pipeline.nodes` 和 `pipeline.edges`，且移除该 nodeset 的 `status: "planned"`。
11. 只有当 nodeset 内部所有子 node / 子 nodeset 都已经 implemented，父 nodeset 才能变成 implemented。例外是设计期可用 `planned_behavior: "transparent"` 或 `python_stub` 子节点保持连通性，此时父 nodeset 会得到 warning；blocking planned child 仍会报错。
12. 按同样方式实现后续 nodeset，直到顶层 `a`、`b`、`c` 全部 implemented，最终程序才能运行。
13. 如果需要训练或批处理循环，先把循环 body 抽成 nodeset，再用 `vibeflow.loop.while` 调用；body 内只表达单轮逻辑，跨轮状态用 `loop.carry`，指标列表用 `loop.collect`，固定轮数用 `loop.stop_after`，条件退出用 body/state 输出的 bool `loop.stop_when`。
14. 后续修改架构也使用同一模式：先放 planned 占位并导出流程图给人类审核，再逐步实现。

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
- 流程图是人类审核程序结构的主要产物；重大架构变更先出图再实现。SVG 节点内应能读清易读标题、`id`、`type`、状态和说明，contract 应显示在已有连边上；信息挤在一起时应先改善 config 的描述长度、拆节点或调整 style，而不是绕过 `python run.py svg`。
- 为消除 `NODESET.SMELL.TOO_WIDE` 拆成更多小 nodeset 是推荐方向；如果怀疑 config 读取或解析慢，用 `VIBEFLOW_CONFIG_TRACE=1 python run.py validate --config ...` 查看 import、nodeset 数、单个 nodeset 解析耗时和总耗时。
- 一等 loop 的展开图应能看到 loop body nodeset；调试训练循环时优先看 `runtime.qualified_exec_order`、`runtime.total_step_count` 和事件 `path`，不要只看顶层 `runtime.exec_order`。
- `GRAPH.JOIN.AMBIGUOUS_UNCONDITIONAL` 表示某个 join 可能被 unconditional provider 提前触发或和 conditional provider 争抢同一个 `exactly_one` 输入；修配置，不要靠旧 context 或节点内部判断绕过。
- 系统保留色不能作为自定义色：普通 node 默认 `#ECECFF/#9370DB/#333333`，planned `#fef08a/#ca8a04/#713f12`，plugin resource `#eff6ff/#2563eb/#1e3a8a`，base_lib resource `#ecfdf5/#059669/#064e3b`，以及 health、external、document、nodeset 等语义色。
- 健康检查的 warning/error 要先看 `object_id`、`source_location` 和 `details`。`details.owner` 区分顶层 `pipeline` 与 `nodeset:<name>`；flow/data 问题会列出相关 edge、direct source、provider type 或 downstream requirement 摘要。`GRAPH.SMELL.DUPLICATE_LOGIC` 会列出具体 nodes、node_types、fingerprint 和 duplicate_group；只有确认为有意关系时才补 `similar_to`。
- 如果 `details.aggregated == true`，先修代表 finding 指向的 `owner` / `node` / `required_type` / `direct_sources`；`occurrences` 是 nested nodeset / loop body 静态展开后被压缩的重复次数，不是独立 bug 数。
- `python run.py quality --path ...` 的文本报告也会打印 `object_id` 和紧凑 `details:`；重复函数、依赖环、双向依赖和内部模块 import warning 按 details 中的函数和 import site 修改。
- 调试嵌套 nodeset 或 loop 时，顶层运行顺序看 `runtime.exec_order`，完整嵌套顺序看 `runtime.qualified_exec_order` 和事件的 `path` 数组；`qualified_node` 是给人看的 dotted 展示名。
