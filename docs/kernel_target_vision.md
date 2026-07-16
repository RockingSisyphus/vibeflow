# VibeFlow 目标愿景

## 设计初衷

VibeFlow（包名 `vibeflow`）服务于人机协同开发，尤其是大量依赖 LLM 编写、修改和维护代码的项目。它的目标不是让程序更容易随意扩展，而是把架构纪律变成可执行的硬约束。

LLM 长期参与开发时最容易出现的问题：

- 功能越写越大，形成巨型函数或巨型模块。
- 出错后局部叠补丁，而不是定位根因。
- 多轮修改后出现隐式依赖、隐藏副作用和跨模块耦合。
- 代码还能跑，但整体结构已经不可审计。

VibeFlow 要把这些风险前移到配置、契约、编译、健康检查和运行时中处理。

## 核心目标

VibeFlow 是可迁移、可复用的严格标准流程图内核。业务开发者只写小型 node、纯 `base_lib` helper、必要插件和 JSONC 拓扑配置。

核心原则：

- node 必须足够小。
- 普通 node 默认必须是无业务 IO 的纯函数；需要真实副作用时必须用可审计的 `flow_kind` / `external` 分类取得对应 `effect_scope`。
- node 之间不允许 Python 层面的导入、调用或隐式耦合。
- 程序控制流只能由 config 中显式 `pipeline.edges` 声明。
- `requires` / `provides` 是严格 key/type 数据契约，不是控制流推导来源。
- 每个 node 必须声明标准流程图 `flow_kind`。
- 可执行图必须有 `terminal` start/end。
- 普通 graph 必须无环；循环必须用一等 loop node 表达。
- 健康检查必须能解释违反规则的原因和修复方向。
- 已登记 workflow 默认在真实 config 和 nodeset source 上原位演进；审核视图不能成为平行 source of truth。

## 术语

- `node`：原子业务单元，通过 `run_pure(inputs, params) -> outputs` 执行；普通 node 为纯函数，显式 effect scope 可开放受控外部能力。
- `flow_kind`：标准流程图角色，决定 node 的架构语义和图形形状。
- `effect_scope`：内核从 `flow_kind`、`external` 和实现类别确定的副作用检查档位；不是 config 中可自由声明的字段。
- `nodeset`：由多个 node 或其他 nodeset 组成的复合拓扑单元。
- `pipeline`：最终可运行拓扑，由 JSONC 配置声明 node、nodeset 和显式 flow edge。
- `key`：Context / run result 中的唯一数据地址，用于输出 mapping、trace 和 provenance。
- `type`：可重复的逻辑数据类型，下游按 `type` 消费，运行时通过 envelope 暴露实际来源 key。
- `base_lib`：受控纯函数基础库，可被 node 依赖，但必须接受健康检查。
- `policy`：治理规则集合，决定哪些限制硬失败、哪些限制可降级。
- `plugin`：扩展 policy、compile 或 runtime 的机制，不能隐式绕过绝对规则。

旧 `boundary` 公共模型已移除。外部输入、输出、数据存储请求、文档产物等必须通过标准 `flow_kind` 节点和显式契约表达。

## 标准 flow_kind

合法类型：

| flow_kind | 语义 |
| --- | --- |
| `terminal` | 开始 / 结束 |
| `process` | 普通处理 |
| `decision` | 判断 / 路由 |
| `io` | 输入 / 输出动作 |
| `predefined` | 预定义过程 / nodeset |
| `data_store` | 数据存储请求或引用 |
| `document` | 文档生成或文档结构 |
| `preparation` | 准备 / 初始化 |

`external_dependency` 不是流程图类型。第三方库或外部维护代码用 `NodeInfo.external=True` 标记；它不会改变图形形状、不会让 cycle 合法化，也不会自动成为 decision。

`flow_kind` 同时参与确定实现可用的 `effect_scope`，因此不能再把它描述成“只影响图形、不影响 IO 能力”。内核采用固定映射：

| 实现分类 | effect_scope | 允许的真实副作用 |
| --- | --- | --- |
| 普通 implemented node（`external=False`，包括图形 `flow_kind=terminal/process/decision/predefined/preparation`） | `none` | 无业务 IO |
| `flow_kind=io` | `terminal` | 真实 stdin/stdout/stderr，以及 `print`、`input`、`argparse` |
| `flow_kind=document` 或 `flow_kind=data_store` | `python_io` | 文件、环境、网络、数据库、subprocess 和终端 IO |
| 任意 `flow_kind` 且 `external=True` | `trusted` | 信任边界，优先级最高 |
| plugin | `trusted` | 信任边界 |
| planned `python_stub` | `none` | 无业务 IO |

图形 `flow_kind=terminal` 与权限档位 `effect_scope=terminal` 没有对应关系：start/end 节点仍是 `none`；只有 `flow_kind=io` 取得 `terminal` 档位。`external=True` 不改变图形、decision、cycle、契约或 trace 规则，但会把实现检查切换到最高优先级 `trusted`，因此它确实是显式的 purity/IO 信任绕过，必须只用于真正外部维护或已审计实现。

## Node 元数据目标

所有 node 必须声明：

```python
NodeInfo(
    type_key="demo.add",
    display_name="Add",
    category="demo",
    description="Add a configured delta.",
    version="0.1.0",
    flow_kind="process",
    external=False,
)
```

`external=True` 只表示“该实现包装外部/第三方/非本项目维护代码”。内核仍验证：

- `NODE_INFO`
- `CONTRACT`
- `requires/provides`
- 配置拓扑位置
- decision route / `when` 规则
- runtime trace

但跳过普通 node 的源码质量、复杂度、导入链和副作用限制等对外部实现不合理的检查。其有效 `effect_scope` 是 `trusted`；这不是“安全”的同义词，而是项目明确承担信任责任。

## 显式 Flow Edge

配置中的 `pipeline.edges` 是唯一控制流来源：

```jsonc
{
  "pipeline": {
    "inputs": [{"key": "value.in", "type": "value.in"}],
    "outputs": [{"type": "value.ready", "cardinality": "exactly_one"}],
    "nodes": [
      {"name": "start", "type": "demo.start"},
      {
        "name": "prepare",
        "type": "demo.prepare",
        "requires": [{"type": "value.in", "cardinality": "exactly_one"}],
        "provides": [{"key": "value.ready", "type": "value.ready"}]
      },
      {
        "name": "route",
        "type": "demo.route",
        "requires": [{"type": "value.ready", "cardinality": "exactly_one"}],
        "provides": [{"key": "flow.route", "type": "flow.route"}]
      },
      {"name": "end", "type": "demo.end", "requires": [{"type": "value.ready", "cardinality": "exactly_one"}]}
    ],
    "edges": [
      ["start", "prepare"],
      ["prepare", "route"],
      {"from": "route", "to": "end", "when": "flow.route == 'done'"}
    ],
    "max_steps": 1000
  }
}
```

规则：

- 可执行图必须至少有一个 `terminal` start 和一个 `terminal` end。
- 已实现节点不能孤立。
- 每个已实现节点必须从 start 可达。
- 每个已实现节点必须能到达 end。
- `decision` 的分支 edge 必须写 `when`。
- `decision` 输出 schema 中声明的 enum/boolean 分支必须被覆盖。
- 每个 decision 分支必须能到达 end。
- 显式 edge cycle 会触发 `GRAPH.CYCLE.FORBIDDEN`。
- 运行时用 `max_steps` 作为安全护栏，不作为循环语义。

## 数据契约与 Runtime Inbox

数据契约必须使用结构化对象，不支持旧字符串简写：

```jsonc
"requires": [{"type": "value.in", "cardinality": "exactly_one"}],
"provides": [{"key": "value.ready", "type": "value.ready"}],
"inputs": [{"key": "value.in", "type": "value.in"}],
"outputs": [{"type": "value.ready", "cardinality": "exactly_one"}]
```

运行时不提供跨多跳全局黑板读取。入口输入只进入入口节点 inbox；node 输出会作为 envelope 沿实际激活的直接 outgoing edge 投递给下游。`exactly_one` / `optional_one` / `all` 由下游 require 的 `cardinality` 约束，最终 run result 只保留 `pipeline.outputs` 声明的 envelope 和 runtime 元数据。

## Planned Architecture

现有 workflow pipeline 与导入的独立 nodeset 文件就是架构 source of truth。登记的 `ARCHITECTURE.jsonc` 只是从这些 source、registry metadata/config schema 和有效资源确定性生成的单文件审查视图，不是可手工编辑的第二份契约。AI 可以先提交 planned 设计，再逐步实现：

```jsonc
{
  "type_key": "paperflow.catalog",
  "display_name": "Catalog Papers",
  "description": "Planned paper catalog flow.",
  "status": "planned",
  "requires": [],
  "provides": []
}
```

planned nodeset 也可以包含由 planned nodes/edges 构成的 `pipeline` body，用于逐步细化和展开审查。

规则：

- `status` 默认是 `implemented`。
- planned node 可声明 config `flow_kind`。
- implemented node 不允许在 config 中伪造 `flow_kind`。
- `planned_behavior` 默认是 `blocking`；也可写 `transparent` 让 planned 内容参与 flow 连通性检查。
- `python_stub` planned 内容只用于开发测试，必须写 `project/stubs/*.py` 下的 `run_stub(inputs, params)`，通过显式运行开关才可执行，且始终使用 `effect_scope=none`。
- planned nodeset 可无 body 占位，也可带 body；body 会进入架构 JSONC、展开图及适用的 dependency、recursion、depth、planned-descendant 检查。
- planned body 不按 implemented body 执行；`python_stub` nodeset 只执行一个 stub 调用。implemented nodeset 必须有完整 pipeline。
- implemented nodeset 不能包含 blocking planned child；transparent/python_stub child 会保留 warning。
- health 对 planned 内容给 warning。
- runtime 默认拒绝运行 planned 内容；开启 planned stub 后也只允许 python_stub 运行。

### 新建与修改已有项目

架构工作必须先区分两种模式：

- **修改已有项目**：先读当前 workflow 登记的 `ARCHITECTURE.jsonc`，再沿其中的 source 定位真实 workflow config 和 nodeset。修改前列出复用、修改、删除、新增的 node、edge、hook 和 source path，只改清单中的对象，未列出的 ID、连边和调用层级默认保持。
- **新建空白项目**：可以从粗粒度标准流程和 planned nodeset 开始，再通过审核逐层细化。

已有 workflow 默认原位修改。只有空白项目或人类明确批准整体重构时，才允许新建粗粒度 planned 拓扑。不得为了审核另建平行 config，也不得用手写 Mermaid、概念图或笼统差异图代替从真实 config 生成的审核产物。

当用户要求“审核后再实现”时，机器检查通过不是人类批准。AI 必须在正式审核产物生成后停止实施，等待用户在后续消息中明确确认；同一轮内的 architecture、validate、SVG 或 review 成功都不能越过这道门。

## 副作用和外部系统

真实副作用必须在图中显式归属，不能藏在普通 `process` / `decision` / `terminal` 节点或 `base_lib` 中：

- 交互式 stdin/stdout/stderr、`print`、`input`、`argparse`：使用 `flow_kind=io`，对应 `effect_scope=terminal`。
- 文件、环境、网络、数据库、subprocess 或需要终端能力的文档/存储工作：使用 `flow_kind=document` 或 `flow_kind=data_store`，对应 `effect_scope=python_io`。
- 第三方或外部维护实现：使用真实 `flow_kind` + `external=True`，对应最高优先级 `effect_scope=trusted`。
- plugin：始终属于 `trusted`；启用即表示项目信任其 hook 实现。
- 其他普通 implemented node，以及 planned `python_stub`：`effect_scope=none`。

所有类别仍必须声明并遵守契约、拓扑、decision、输出 key 和 trace 规则。具有副作用或 `external=True` 的 node，其 `CONTRACT.examples` 只做结构检查，不在健康检查中执行，避免验证阶段触发真实外部行为；只有 `none` 范围的普通实现示例可以作为纯函数样例运行。

## CLI 让渡模式 / delegate-cli

`delegate-cli` 是把 VibeFlow workflow 暴露成普通业务命令行程序的受控外部边界：

```bash
python run.py delegate-cli --config project/configs/main.jsonc -- --input data.yaml --verbose
```

首个 `--` 之前由 VibeFlow 消费已知 core 参数，未知 token 保持顺序进入业务参数；首个 `--` 之后全部原样让渡。分隔符可省略。让渡后的 `list[str]` 通过唯一入口类型 `cli.argv` 注入，图必须以 `exactly_one` 输出要求产生唯一 `cli.exit_code`，其最终 provider 的 key/type 都是 `cli.exit_code`，值必须是非 bool 的 `int` 且处于 `0..255`。

业务 stdin/stdout/stderr 是真实进程标准流：内核不捕获、不重写，也不补 JSON 或换行。VibeFlow 自身的启动、兼容提示、失败阶段、artifact 路径和最终退出码写入每个新运行目录的 `vibeflow.log`，不得写入业务标准流，也不得记录 argv 原文。只有运行目录无法创建时，才允许向 stderr 写最小诊断并返回 1。

正常业务退出和获授权代码抛出的 `SystemExit` 可返回 `0..255`。只有 `io`、`document`、`data_store` node 或 runtime plugin 可以授权退出；`SystemExit(None)` 视为 0，合法整数原样返回，其他值、越界值以及未授权 `SystemExit` 都是框架错误并返回 1。argparse 层缺少 `--config` 或已知 core 参数值非法时写 stderr、返回 2 且不创建 run；health、runtime、CLI contract 或非法 `SystemExit` 失败返回 1，详细 VibeFlow 诊断只写 `vibeflow.log`。

`delegate-cli` 不改变 `run` 和 `review` 的职责：`run` 仍是带运行产物和结构化结果的通用执行/诊断入口，`review` 仍是 fail-closed 的正式架构审核入口。

## 插件目标

插件类型：

- `PolicyPlugin`
- `CompilerPlugin`
- `RuntimePlugin`

插件可以增加治理规则、收紧策略、追加健康检查或记录 runtime 事件。插件实现使用 `effect_scope=trusted`，可以执行 Python IO，并由启用它的项目承担信任责任；这不允许 plugin 篡改契约、拓扑或不可降级的治理结论。runtime plugin 还可以在 CLI 让渡模式 / `delegate-cli` 中发出授权 `SystemExit`。

## 图形输出目标

内核应从同一份编译结果输出：

- `architecture.jsonc`：确定性、不可执行的单文件架构审查视图。
- `graph.mmd`：Mermaid flowchart 源码。
- `graph.txt`：无外部依赖的 ASCII flowchart。
- `graph.svg`：通过 VibeFlow 公开命令生成的 SVG 图；bundled Mermaid CLI/mmdc 只是内核渲染实现细节。

图中应显示：

- 标准 flow_kind 形状。
- planned / external 标记。
- decision `when` 条件。
- nodeset 折叠/展开。
- planned nodeset 的已有 body；无 body 时保留明确占位。
- 契约 `key -> type`、cardinality、中文说明、健康警告/错误。

### 正式架构审核

正式审核使用一个固定、fail-closed 的编排入口：

```bash
python run.py review \
  --config project/configs/main.jsonc \
  --output reports/graph.expanded.svg
```

它必须以已登记的真实 workflow 为输入，依次完成不依赖旧架构文档的 graph/schema/health preflight、canonical `ARCHITECTURE.jsonc` 更新及复核、workspace validate、expanded `review-columns` SVG 渲染和 SVG 结构检查。任一步失败都必须返回失败且不发布新的目标 SVG；不得直接调用 Mermaid CLI/mmdc、渲染 expanded MMD、复用旧 SVG 或手写图进行补位。

普通 `architecture`、`validate` 和 `svg` 命令仍可用于单项生成或诊断，但不能分别执行后声称完成了正式架构审核。`review` 的 `PASS` / `CONCERNS` 也只代表机器审核结果，不代表人类批准实现。

## 健康报告目标

健康报告必须稳定输出：

- `rule_id`
- `severity`
- `object_type`
- `object_id`
- `failure_layer`
- `message`
- `details`
- `suggested_fix_type`

主要 object type：`node`、`nodeset`、`pipeline`、`base_lib`、`plugin`、`policy`。

## 运行产物目标

正式运行目录：

```text
runs/<run_id>/
  input_summary.json
  effective_policy.json
  compiled_graph.json
  health_report.json
  graph.mmd
  graph.txt
  graph.svg
  graph.svg.error.txt
  graph.expanded.svg
  graph.expanded.svg.error.txt
  architecture.jsonc
  vibeflow.log                  # delegate-cli 专用内核诊断
  runtime_trace.jsonl
  output_summary.json
```

trace 默认保存结构摘要，不保存原始输入输出。
