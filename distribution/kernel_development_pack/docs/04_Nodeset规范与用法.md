# 04. Nodeset 规范与用法

nodeset 是独立 JSONC 实现文件，作用类似 Python node 的 `.py` 文件：它声明一个可复用实现类型键 `type_key`，pipeline 调用处用 `type_used` 指向这个实现。

普通 node 的实现键来自 Python `NodeInfo.type_key`；nodeset 的实现键来自 nodeset JSONC 根对象的 `type_key`。两者共享同一个全局命名空间，不能重复。

## 最小 nodeset 文件

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
          {"key": "value.out", "type": "value.out", "display_name": "Value Out"}
        ],
        "config": {"delta": 1}
      },
      {
        "id": "end",
        "type_used": "demo.end",
        "display_name": "End",
        "description": "Consumes the add-one output.",
        "requires": [
          {"type": "value.out", "cardinality": "exactly_one", "display_name": "Value Out"}
        ]
      }
    ],
    "edges": [["start", "add"], ["add", "end"]],
    "outputs": [
      {"type": "value.out", "cardinality": "exactly_one", "display_name": "Value Out"}
    ]
  }
}
```

规则：

- 根对象必须写 `type_key`、`display_name`、`description`、`requires`、`provides` 和 `pipeline`。
- `requires`、`provides`、`pipeline.inputs`、`pipeline.outputs` 都必须使用对象契约，并写非空 `display_name`。
- `name`、`category`、`version`、`purity`、`exports` 已从 nodeset 模型中移除，出现即为 schema/config error。
- nodeset 内部允许 `io`、`data_store`、`document`、`external=True` 等节点；可读性通过展开 SVG 审查，不再要求 nodeset 纯函数属性。
- nodeset 对外输出只看根对象 `provides`。运行时会从内部 pipeline result 中按 `provides[].type` 取值，再写入调用点的 `provides[].key`。

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
- nodeset 内部 pipeline 必须有 terminal start/end。
- nodeset 内部控制流必须显式写 `edges`；`requires/provides` 不会自动生成边。
- nodeset 根 `provides` 必须能由内部 pipeline output 或内部 provider 产生，否则报 `NODESET.PROVIDES.UNKNOWN_KEY`。
- nodeset 内部需要从外层读取的类型必须声明在 nodeset `requires` 中。
- 内部 node 数量超过 10 会给 `NODESET.SMELL.TOO_WIDE` warning，推荐继续拆分小 nodeset。

如果怀疑 config 读取或 nodeset 解析慢，可开启解析 trace：

```bash
VIBEFLOW_CONFIG_TRACE=1 python run.py validate --config project/configs/main.jsonc
```

trace 会输出 import 文件、展开后的 nodeset 数、每个 nodeset 解析耗时、依赖边和总耗时。

## 常见 nodeset 错误

- `CONFIG.NODESETS.INLINE_REMOVED`：主 config 或 nodeset 文件仍写了内联 `nodesets`。
- `CONFIG.NODESET_IMPORT.NAMES_REMOVED`：`nodeset_imports` 仍写了 `names` 选择器。
- `NODESET.RECURSION`：nodeset 调用或 loop body 形成递归。
- `NODESET.PROVIDES.UNKNOWN_KEY`：nodeset 声明的 `provides` 无法由内部结果产生。
- `NODESET.CONFIG.UNKNOWN_NODE`：`node_configs` 覆盖路径指向不存在的内部 node。
- `NODESET.CONFIG.NESTED_PATH_REQUIRED`：覆盖嵌套 nodeset 或 loop 内部节点时没有使用 dotted path。
- `NODESET.CONFIG.INVALID_PATH`：dotted path 穿过了普通 node，而不是 nodeset 或 loop 调用。
