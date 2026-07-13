# 04. Nodeset 规范与用法

nodeset 是独立 JSONC 实现文件，作用类似 Python node 的 `.py` 文件：它声明一个可复用实现类型键 `type_key`，pipeline 调用处用 `type_used` 指向这个实现。

普通 node 的实现键来自 Python `NodeInfo.type_key`；nodeset 的实现键来自 nodeset JSONC 根对象的 `type_key`。两者共享同一个全局命名空间，不能重复。

## 最小 implemented nodeset 文件

`project/configs/nodesets/demo_add_one.jsonc`：

```jsonc
{
  "type_key": "demo.add_one",
  "display_name": "Add One Flow",
  "description": "Composite flow that adds one to value.in.",
  "requires": [
    {"type": "value.in", "cardinality": "exactly_one", "display_name": "Value In"}
  ],
  "provides": [
    {"key": "value.out", "type": "value.out", "display_name": "Value Out"}
  ],
  "pipeline": {
    "inputs": [
      {"key": "value.in", "type": "value.in", "display_name": "Value In"}
    ],
    "nodes": [
      {
        "id": "start",
        "type_used": "demo.start",
        "display_name": "Start",
        "description": "Starts the add-one nodeset."
      },
      {
        "id": "add",
        "type_used": "demo.add",
        "display_name": "Add One",
        "description": "Adds one to the incoming value.",
        "requires": [
          {"type": "value.in", "cardinality": "exactly_one", "display_name": "Value In"}
        ],
        "provides": [
          {"key": "semantic.value", "type": "semantic.value", "display_name": "Semantic Value"}
        ],
        "config": {"delta": 1}
      },
      {
        "id": "output",
        "type_used": "demo.output",
        "display_name": "Output I/O",
        "description": "Adapts the internal semantic value to the external nodeset contract.",
        "requires": [
          {"type": "semantic.value", "cardinality": "exactly_one", "display_name": "Semantic Value"}
        ],
        "provides": [
          {"key": "value.out", "type": "value.out", "display_name": "Value Out"}
        ]
      },
      {
        "id": "end",
        "type_used": "demo.end",
        "display_name": "End",
        "description": "Ends after the add-one output is produced.",
        "similar_to": {
          "node": "start",
          "relationship": "copy",
          "reason": "Both terminal calls intentionally use the same empty lifecycle implementation."
        }
      }
    ],
    "edges": [["start", "add"], ["add", "output"], ["output", "end"]],
    "outputs": [
      {"type": "value.out", "cardinality": "exactly_one", "display_name": "Value Out"}
    ]
  }
}
```

规则：

- 所有 nodeset 根对象都必须写 `type_key`、`display_name`、`description`、`requires` 和 `provides`；implemented nodeset 还必须写完整 `pipeline`。
- `requires`、`provides`、`pipeline.inputs`、`pipeline.outputs` 都必须使用对象契约，并写非空 `display_name`。
- `name`、`category`、`version`、`purity`、`exports` 已从 nodeset 模型中移除，出现即为 schema/config error。
- nodeset 内部允许 `io`、`data_store`、`document`、`external=True` 等节点；可读性通过展开 SVG 审查，不再要求 nodeset 纯函数属性。
- nodeset 对外输出只看根对象 `provides`。运行时会从内部 pipeline result 中按 `provides[].type` 取值，再写入调用点的 `provides[].key`。

## Nodeset 内部的数据与运行时门禁

- terminal start/end 只负责生命周期，不读取、不提供、不转发业务数据；nodeset 也使用 `terminal → input I/O → process → output I/O → terminal` 的控制脊柱。
- `requires` 是数据需求，不是控制分支数。顺序语义链保持默认 join；只有至少两条每轮都会激活的真实并行 schedule 分支才能使用 `join_policy="all"`。data-bypass 只传输 payload，必须从真正拥有所需 envelope 的 provider 发出，不会激活目标。
- 修改图后必须消除 `GRAPH.DATA.RUNTIME_REQUIREMENT_UNREACHABLE`、`GRAPH.DATA.NO_PAYLOAD_BYPASS`、`GRAPH.JOIN.ALL_DEPENDS_ON_TRANSFER_ONLY`、`GRAPH.JOIN.ALL_BRANCHES_MUTUALLY_EXCLUSIVE` 和 `GRAPH.JOIN.REDUNDANT_ALL`；按 finding 中的 schedule/transfer incoming、候选 provider、decision 分支条件和修复建议改真实数据流。
- 如果使用 tagged value，tag 必须是规范的精确字面量，value 必须是匹配的 Python 原生类型，不得缩写 tag 或把整数保留为字符串。
- `validate` 和 `quality` 只是静态门禁。每个入口还要执行最小 runtime probe，检查结果 key 和原生类型、`runtime.stop_reason` 等于 `completed`，以及 `runtime.qualified_exec_order` 真实经过预期的内部路径。

## 在主 config 中导入和调用

```jsonc
{
  "nodeset_imports": [
    {"path": "nodesets/demo_add_one.jsonc"}
  ],
  "pipeline": {
    "nodes": [
      {
        "id": "flow_add_one",
        "type_used": "demo.add_one",
        "display_name": "Add One Flow",
        "description": "Runs the imported add-one nodeset.",
        "requires": [
          {"type": "value.in", "cardinality": "exactly_one", "display_name": "Value In"}
        ],
        "provides": [
          {"key": "value.out", "type": "value.out", "display_name": "Value Out"}
        ]
      }
    ]
  }
}
```

调用规则：

- 调用点必须写 `id` 和 `type_used`。旧 `name`、旧调用处 `type`、旧 `nodeset.<name>` 前缀都不再接受。
- `type_used` 可以指向 Python node `NodeInfo.type_key`、nodeset `type_key`，或系统类型如 `vibeflow.loop.while`。
- 调用点 `display_name` / `description` 描述本次调用用途；展开子图标题优先使用调用点 `display_name`，其次使用 nodeset 定义的 `display_name`。
- 调用点 `requires` / `provides` 必须与 nodeset 定义的 `requires` / `provides` 匹配。

## nodeset_imports

主 config 和 nodeset 文件都可以写 `nodeset_imports`，用于调用更深层 nodeset：

```jsonc
{
  "nodeset_imports": [
    {"path": "math/demo_add_one.jsonc"},
    {"path": "reporting/summary.jsonc"},
    {"root": "vibetrain", "path": "configs/nodesets/train_step.jsonc"}
  ],
  "type_key": "demo.pipeline_part",
  "display_name": "Pipeline Part",
  "description": "Calls imported nested nodesets.",
  "requires": [],
  "provides": [],
  "pipeline": {"nodes": [], "edges": []}
}
```

规则：

- 字符串形式和 `{"path": ...}` 都相对当前 JSONC 文件解析，用于导入同 root 或同目录树内的 nodeset。
- workspace 模式下可以写 `{"root": "<root_id>", "path": "<path>"}` 导入其他 source root 下的 nodeset；`root` 必须匹配根目录 `vibeflow_config.jsonc` 中的 `roots[].id`，`path` 相对该 root 目录解析。
- 每个导入文件根对象就是一个 nodeset definition；不再支持一个文件里内联 `nodesets: [...]`。
- `names` 选择器已移除；需要拆分时把每个 nodeset 放到独立文件。
- 导入链会去重并检测循环；递归导入或递归 nodeset 调用会报 `NODESET.RECURSION`。
- `vibeflow.loop.while.loop.body` 也引用 nodeset `type_key`，同样参与依赖和递归检查。
- 普通 nodeset 调用和 `loop.body` 共用最大嵌套深度。顶层 pipeline 为 0，第一次进入 body 为 1，循环迭代次数不增加深度；默认上限为 4，可在所属 root 的 `vibeflow_project.jsonc` 中用 `runtime.nodeset_max_depth` 提高。
- 深度检查覆盖所有已加载定义，包括未使用和 planned nodeset。超过上限会报 `NODESET.NESTING.DEPTH_EXCEEDED`，`details` 会列出 `limit`、`actual_depth`、`chain` 和逐跳调用点。
- 健康检查、Mermaid 和 SVG 会标注 nodeset 来自哪个 root/source，方便区分框架层 nodeset 和项目层 nodeset。

## planned nodeset

设计期可以用独立 nodeset 文件声明 planned nodeset：

```jsonc
{
  "type_key": "demo.future_module",
  "display_name": "Future Module",
  "description": "Architecture placeholder for a future composite flow.",
  "status": "planned",
  "planned_behavior": "blocking",
  "requires": [],
  "provides": []
}
```

planned nodeset 不要求 `pipeline`，但仍必须写 `type_key`、`display_name`、`description`、`requires` 和 `provides`。默认 `planned_behavior` 是 `blocking`，只能用于架构审查；需要运行时 stub 时按 planned node 的 `python_stub` 规则处理。

planned nodeset 也可以包含待逐步细化的 body，例如：

```jsonc
{
  "type_key": "demo.future_module",
  "display_name": "Future Module",
  "description": "Planned internal flow for review.",
  "status": "planned",
  "requires": [],
  "provides": [],
  "pipeline": {
    "nodes": [
      {"id": "start", "status": "planned", "flow_kind": "terminal", "display_name": "Start", "description": "Starts the planned module."},
      {"id": "design_step", "status": "planned", "flow_kind": "process", "display_name": "Design Step", "description": "Represents the next implementation step."},
      {"id": "end", "status": "planned", "flow_kind": "terminal", "display_name": "End", "description": "Ends the planned module."}
    ],
    "edges": [["start", "design_step"], ["design_step", "end"]]
  }
}
```

这类 body 不是可执行实现，但不是被忽略的注释：它会完整进入登记的架构 JSONC 和展开 Mermaid/SVG，并参与 nodeset dependency、recursion、最大深度和 planned-descendant 等适用检查。即使 planned nodeset 使用 `python_stub`，运行时也只把整个调用当作一个 stub 执行，不展开 body。只有补齐可执行 pipeline、满足内部健康检查并切换为 implemented 后，body 才具有 implemented 执行语义。

## 配置覆盖

调用 nodeset 时，可以给内部 node 覆盖配置：

```jsonc
{
  "id": "flow_add_five",
  "type_used": "demo.add_one",
  "display_name": "Add Five Flow",
  "description": "Reuses the add-one nodeset shape with a different delta.",
  "requires": [
    {"type": "value.in", "cardinality": "exactly_one", "display_name": "Value In"}
  ],
  "provides": [
    {"key": "value.out", "type": "value.out", "display_name": "Value Out"}
  ],
  "node_configs": {
    "add": {"delta": 5}
  }
}
```

这里 `add` 是 nodeset 内部 node 的 `id`。嵌套 nodeset 或 `vibeflow.loop.while` 使用 dotted path，例如 `first.add`、`outer.inner.add`、`train_loop.batch_step`。loop 路径段指向调用点 `id`，并进入该调用点的 `loop.body`，不是直接写 body nodeset 的 `type_key`。

nodeset 也可以声明内部 `global_config`；调用点 `config` 会覆盖 nodeset 内部 `global_config`，再覆盖内部 node 局部 `config`。当 `allow_config_override` 为 `false` 且出现同名覆盖时，健康检查会 warning，但实际覆盖仍会发生。

## 关键限制

- nodeset 不能直接或间接递归调用自己。
- nodeset 内部普通 `pipeline.edges` 不允许形成环；循环必须用 `vibeflow.loop.while` 调用 nodeset body。
- implemented nodeset 的内部 pipeline 必须有 terminal start/end；planned body 仍应写出 start/end，便于架构审查并接受适用的 flow 检查。
- nodeset 内部控制流必须显式写 `edges`；`requires/provides` 不会自动生成边。
- implemented nodeset（以及声明了 body 的 planned nodeset）根 `provides` 必须能由内部 pipeline output 或内部 provider 产生，否则报 `NODESET.PROVIDES.UNKNOWN_KEY`；无 body 的 planned 占位只保留对外契约。
- nodeset 内部需要从外层读取的类型必须声明在 nodeset `requires` 中。
- 内部 node 数量超过 10 会给 `NODESET.SMELL.TOO_WIDE` warning，推荐继续拆分小 nodeset。

## Nodeset 内部的调度与数据边

- nodeset 内部的 terminal start/end 同样不携带业务数据。外部输入只会注入真正的初始输入 node：没有 schedule incoming，或直接由空 start 调度的有 `requires` node。
- `requires` 不会自动生成控制分支，也不会让较后的 node 再次获得 nodeset input。需要保留上游 envelope 时，从真实 provider 写显式 data-bypass，不要从空 start 画“数据线”。
- 顺序语义 nodeset 不要因为 node 有多个 requirement 就写 `join_policy: "all"`。只有 fan-out 后两条真实 schedule 分支都会在本轮激活时，汇合 node 才使用 `all`。
- 优先在 nodeset 内保持 `terminal → input I/O → semantic process → output I/O → terminal` 脊柱。nodeset 根 `provides` 导出 output I/O 的边界 contract，不要让 terminal 或外部 caller 代替输出适配。
- Health 会在每个 nested nodeset owner 内单独检查 runtime requirement、bypass payload 和 join edge class；修复时先看 `details.owner=nodeset:<type_key>`。

完整且由 pytest 实际执行的三种中性图形见 `03_Config与Pipeline规范.md` 的“可执行的中性拓扑示例”：顺序数据 bypass、真实并行 `all` 汇合、typed I/O 边界。这些规则在顶层 pipeline 和 nodeset 内部完全一致。

如果怀疑 config 读取或 nodeset 解析慢，可开启解析 trace：

```bash
VIBEFLOW_CONFIG_TRACE=1 python run.py validate --config project/configs/main.jsonc
```

trace 会输出 import 文件、展开后的 nodeset 数、每个 nodeset 解析耗时、依赖边和总耗时。

## 常见 nodeset 错误

- `CONFIG.NODESETS.INLINE_REMOVED`：主 config 或 nodeset 文件仍写了内联 `nodesets`。
- `CONFIG.NODESET_IMPORT.NAMES_REMOVED`：`nodeset_imports` 仍写了 `names` 选择器。
- `NODESET.RECURSION`：nodeset 调用或 loop body 形成递归。
- `NODESET.NESTING.DEPTH_EXCEEDED`：普通 nodeset/loop body 的最长调用链超过 root 配置的最大深度。
- `NODESET.PROVIDES.UNKNOWN_KEY`：nodeset 声明的 `provides` 无法由内部结果产生。
- `NODESET.CONFIG.UNKNOWN_NODE`：`node_configs` 覆盖路径指向不存在的内部 node。
- `NODESET.CONFIG.NESTED_PATH_REQUIRED`：覆盖嵌套 nodeset 或 loop 内部节点时没有使用 dotted path。
- `NODESET.CONFIG.INVALID_PATH`：dotted path 穿过了普通 node，而不是 nodeset 或 loop 调用。
