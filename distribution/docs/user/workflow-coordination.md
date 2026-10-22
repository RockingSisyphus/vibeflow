# 命名入口与独立 Workflow 通信

入口、接口和 Rule 分别负责选择执行范围、提供功能和授予调用权限。Node 的名称、形状、颜色及 `flow_kind` 不授予通信功能。

## 一个图的多个入口

在 `pipeline` 中声明入口，每个入口指向一个没有入边的 terminal：

```jsonc
"entries": {
  "cli": {"start": "cli_start"},
  "gui": {"start": "gui_start"}
},
"default_entry": "cli"
```

入口可声明自己的 `inputs` 和 `outputs`，格式与 pipeline 公共契约一致；省略时继承 pipeline 契约。每个输入仍须显式写 `required`。只执行所选入口可达的路径，汇合不等待其他入口。互斥入口的预处理节点可提供相同业务 key；同一入口内仍不能出现重复 provider。

单入口自动选择；多个入口没有默认值时必须指定名称。未声明命名入口的配置保持原行为。

```bash
python -m vibeflow run --config configs/main.jsonc --entry gui --input input.json
python -m vibeflow delegate-cli --workspace vibeflow_config.jsonc --config configs/main.jsonc --entry cli -- --help
python build/main/run.py run --entry gui --input input.json
```

Python SDK 使用 `PipelineRuntime(..., entry="gui")`、`bundle.create_runtime(entry="gui")` 或 `bundle.run(..., entry="gui")`。JavaScript 使用 `runWorkflow(inputs, {entry:"gui"})` 或异步版本 `runWorkflowAsync`；生成的类型声明包含各入口的契约。AOT 在构建时保存入口范围，运行时不重新编译或检查图。

## Capability 与显式规则

普通 SDK Node 声明所需 Capability，例如：

```jsonc
"capabilities": [{"id":"vibeflow.workflow", "operations":["call","wait"]}]
```

项目 Plugin 同时显式贡献 Capability 及其数据 Schema。公开的纯声明辅助位于 `vibeflow.core.workflows.interfaces`：`workflow_capability_descriptor()`、`WORKFLOW_SCHEMA_TYPES`、`port_capability_descriptor(...)`、`PORT_SCHEMA_TYPES`。Python 用 SDK `capability` / `data_schema` 贡献这些声明；JS 用 `defineCapability` / `defineDataSchema`。它们不会自动注册任何资源。

图级选择限制规则：

```jsonc
"rulesets": ["vibeflow.workflow", {"rule_id":"vibeflow.capability.restrict"}]
```

需要功能的调用点显式授权：

```jsonc
"rulesets": ["vibeflow.process", {
  "rule_id":"vibeflow.capability.allow",
  "params": {
    "capability":"vibeflow.workflow",
    "operations":["call","wait"],
    "actions":[{"operation":"call","wait":true},
               {"operation":"wait"}]
  }
}]
```

SDK 声明也可直接选择这些 Rule，调用配置可以覆盖其规则选择。有效权限按完整调用路径保存；同类型的另一处调用不能借用授权。图级限制覆盖其负责的有效子图，节点选择空 Ruleset 不能取消图级限制。`restrict` 默认限制 `vibeflow.workflow` 和 `vibeflow.port`，也可通过 `capabilities` 参数指定其他接口。

`actions` 是作者对操作和等待方式的显式声明，用于图审查和展示；框架不分析任意业务代码来证明声明。目标、入口和启动方式统一在节点 `config` 中维护。调整实现或等待方式时同步更新 actions，调整目标时更新 config。Send/Receive 未声明 `expected_workflows` 时，页面保留操作说明而不虚构对端。未提供 actions 时，规则根据明确声明的 operations 输出基本操作说明。

`workflow-io` 是流程分类，不是限制任意函数调用的执行沙箱。本节的授权、目标检查和关联提取作用于已声明的 `vibeflow.workflow` 操作。应用直接调用 AOT 导出的 `runWorkflow`/`runWorkflowAsync`、把另一个 workflow 接成自定义 Capability，或者通过输入对象注入调度函数，都不会自动成为该协议的 Call。现有规则检查声明的 Capability 权限、数据契约和源码依赖等，不证明所有间接调用均已登记为 workflow 关联。普通 `vibeflow.port` 也只声明宿主端口边界，不说明端口背后接的是哪个 workflow。

## 接口约定

Node 通过 `context.capabilities["vibeflow.workflow"]` 使用接口。Python 再以 `api["call"](...)` 调用，JS 使用 `api.call(...)`。请求采用与其他 Capability 一致的对象参数。

| 操作 | 请求 | 结果与等待行为 |
|---|---|---|
| `call` | `{workflow, launch, inputs?, timeout?}` | 等待宿主注册确认后返回 `{id}`；不等待业务结束 |
| `wait` | `{id, timeout?}` | 等待真实终态，返回 `state`、`outputs`、`error` 等；可重复读取 |
| `send` | `{id, port?, payload}` | 交给本地发送适配器后继续；不等待对端处理，无业务返回值 |
| `receive` | `{port?, timeout?}` | 默认等待消息，返回 `{sender, port, payload}` |
| `kill` | `{id, workflow, timeout?}` | 请求宿主停止该实例，等待真实终态；不支持时明确失败 |

主要的跨实例动作是 Call、Send、Receive、Kill；`wait` 等待指定实例的真实终态，CallAndWait 是 Call 后接 Wait 的组合。四类主要操作默认共用缺角卡片形状 `notch-rect`，分别使用金色、浅蓝、深蓝、红色；节点卡片直接突出显示操作名。附带 `wait` 不改变主要操作配色；真正同时执行多个主要操作时显示各操作名，采用组合操作样式。作者显式声明的外观仍可覆盖默认值。

### 当前实例身份：所有 Node 均可读取

任意 Node 都可以通过 `context.workflow.self()` 取得 `{id}`：Python 读取 `context.workflow.self()["id"]`，JavaScript/TypeScript 读取 `context.workflow.self().id`。不需要声明 Capability、选择授权 Rule 或增加独立 Self 节点。例如普通“准备请求”节点可以把当前 ID 写入请求的回信地址。

ID 属于一次 workflow 根调用，进入 Nodeset/Loop 不变，另一独立调用得到新的 ID；它不是配置文件名或日志目录名。标准连接宿主将此 ID 绑定到通信服务登记的实例 ID。不连接通信服务时也能读取本地实例 ID，但读取身份本身不创建邮箱或启动服务。自定义宿主可通过 Python 的 `workflow_instance_id` 或 JavaScript 的运行选项 `workflowInstanceId` 传入其登记的 ID。

旧模板中的独立 Self 节点和 `vibeflow.workflow` Capability 的 `self` 操作已移除；读取身份统一使用上述上下文接口。

默认端口是 `default`，超时以秒计。取消等待只结束当前等待，不自动停止对端。JS 的等待操作使用异步 completion；Python 接入 Node 的取消信号。普通退出先完成本地待发交接，强制退出不保证尚未交接的消息。第一版只支持本机、内存中的普通 JSON；大于跨语言安全整数范围的整数须编码为字符串。

需要一次性子工作时：`call → wait`。需要提前启动长期 workflow 时：`call` 后保存实例 ID，后续使用 `send / receive`，最后由作者安排 `kill` 或正常退出。`call` 没有可直接确认的下游 wait/kill 时产生 warning；普通调用节点可在其参数 schema 中声明 `allow_background`，在 config 设置 `true` 表示作者明确接受长期运行。该警告不证明所有分支都会清理。

实例 ID 是框架生成的不透明身份，不等于 PID，也不会随 PID 复用。作者负责保存、交换身份和业务请求 ID；框架不自动匹配请求与响应。

## 目标和宿主

目标和启动方式在具体 Call 节点的 `config` 中声明，不维护顶层目标表：

```jsonc
"config": {
  "workflow": {"root":"worker_root", "path":"configs/worker.jsonc", "entry":"main"},
  "launch": {
    "command":["python","-m","vibeflow.coordination","run-python","--bundle","../worker/build"],
    "cwd":".",
    "env":{}
  },
  "allow_background": false
}
```

`workflow.path` 相对目标 root，`root` 省略时采用当前 workflow 的 root；`entry` 可选，传到现有命名入口选择接口。未指定时使用目标默认入口或唯一入口，多入口无默认值时必须选择。命令不必重复写入口。`launch.cwd` 相对调用 workflow 所属 root，命令是参数数组，不经过 shell。环境初始化、窗口、浏览器权限仍由作者负责。

Kill 节点也必须在 `config.workflow` 声明目标，并从输入取得实例 ID；同一 workflow 运行多份时只停止所选实例。实例归属不匹配会返回 `VF_WORKFLOW_MISMATCH`。Send/Receive 可在 `config.expected_workflows` 中填写上述 workflow 引用列表；它仅描述预期交互，不限制实际通信。

标准节点的流程分类是 `workflow-io`。操作及配置共同生成 Architecture 关联和右键跳转；Rule action 只描述操作和等待行为，不重复声明目标、入口或启动方式。

planned Call 保留设计意图供审查，启动清单只收集已实现调用。未来节点的启动配置尚未补齐时，也不会阻止收集已实现调用；其目标不会因此获得启动资格。

显式启动本机通信服务：

```bash
python -m vibeflow coordination serve --workspace vibeflow_config.jsonc --port 8765
# 可用 --config 限定当前 workspace 中的一份 workflow
python -m vibeflow coordination serve --bundle build/main --port 8765
```

源码服务从注册 workflow 的有效节点配置准备启动声明。构建保存 `workflow-launches.json`，部署服务读取它，无需扫描源工程；Call 请求必须与已准备的 workflow/launch 声明匹配，不允许请求直接引入其他命令。Python 部署包的启动工作目录基于保存的 root，JavaScript 部署包基于产物目录；作者需随部署提供命令引用的外部产物和显式资源。服务监听 `127.0.0.1`，没有自动运行组或子进程清理。

启动声明同时保存调用 workflow 的身份，服务据此区分不同 root 中相同的命令，并解析各自的工作目录。标准宿主自动登记该身份；自定义宿主创建客户端时，应通过 `workflow: {root, path}` 登记自身 workflow。
宿主提供明确身份时，它必须与 Call 配置的目标一致；不一致会报告实际与预期路径，避免把其他 workflow 的执行结果记到该目标下。

使用已安装 wheel 时采用上述模块命令，解压开发包使用 `python run.py coordination …`，启动命令也使用其实际内核路径。

标准 Python 接入命令支持源码和 AOT：

```bash
python -m vibeflow coordination run-python --url http://127.0.0.1:8765 --bundle build/worker
python -m vibeflow coordination run-python --url http://127.0.0.1:8765 --workspace vibeflow_config.jsonc --config configs/worker.jsonc
```

call 启动的命令会收到 `VIBEFLOW_COORDINATION_URL` 和 `VIBEFLOW_INSTANCE_ID`，标准接入会自动使用它们。独立接入会取得新的身份。Python 自定义宿主可使用 `targets.python.runtime.workflow_host.run_connected(runtime_factory, ...)`；工厂接收 entry 和 Capability，返回新的 Runtime。

Node 标准接入文件随发行物置于 `kernel/javascript/workflow_node.mjs`：

```bash
node kernel/javascript/workflow_node.mjs build/worker/workflow.js
```

自定义 Node 或浏览器宿主导入同目录的 `workflow_host.mjs`，以 `runConnected(runWorkflowAsync, {url, id, workflow, ...})` 包装一次调用。`workflow_client.mjs` 公开底层客户端，使用同一 JSON 协议；浏览器自身的启动、权限和资源服务由宿主提供。HTML 预览器保持离线只读，不连接通信服务。

### 外部宿主的 HTTP 接入

所有请求都是 `POST /操作名`，正文为 JSON，响应是 `{"value": ...}` 或 `{"error":{"code":...,"message":...}}`。本机服务支持浏览器 CORS。服务中的身份、消息及终态均在内存中；退出服务后不会恢复。

| 请求 | 宿主职责和响应 |
|---|---|
| `register`：`{id?,workflow?,pid?,stop_supported}` | call 启动的宿主使用环境中的 id；独立宿主省略 id。返回 `{id,inputs,entry,workflow}`。每个运行只登记一次，旧终态 ID 不能复用。 |
| `control`：`{id}` | 支持停止的宿主轮询。返回 `{pending:true}`，或 `{stop:true,ended:false}`；宿主收到后取消该次运行，完成实际清理再报告终态。 |
| `complete`：`{id,state,outputs,error}` | `state` 为 succeeded、failed 或 cancelled。输出和错误须为 JSON。宿主必须在真实执行与清理结束后报告。 |
| `send`：`{id,sender,port,payload}` | 将消息交给指定实例邮箱；服务确认入队，不等于业务处理完成。 |
| `receive`：`{id,port}` | 返回 `{sender,port,payload}`，无消息时返回 `{pending:true}` 后继续轮询。 |
| `call`：`{sender,workflow,launch,inputs?}` | 客户端自动带上调用实例 `sender`。返回预留 `{id}`；随后请求 `ready`，直到宿主登记。包装脚本退出不会替代登记。 |
| `ready` / `wait`：`{id}` | 未就绪时返回 `{pending:true}`；ready 返回身份，wait 返回真实终态及输出，可重复读取。 |
| `kill`：`{id,workflow?}` | 发出停止请求或报告不支持；指定 workflow 时校验实例归属，继续 wait 确认真实结束。 |
| `instances`：`{}` | 返回实例状态列表，供作者诊断和自行清理。 |

轮询由服务短暂等待后响应，宿主可结束当前 HTTP 等待来实现本地取消。取消等待不等于 kill。普通退出前完成本地发送队列的交接；各宿主使用相同的实例与消息地址，不共享线程或进程生命周期。

启动脚本退出不代表 workflow 结束。宿主注册、消息交接和终态报告决定 call/wait 的结果；kill 使用宿主提供的实例停止实现。框架不会因为调用方退出而清理后台实例，不自动建立运行组、进程池或重试。停止整个浏览器、桌面应用或系统服务需要作者明确提供相应宿主实现。

新进程仍有冷启动成本。高频请求适合由作者启动长期 workflow 并通过消息复用；Python AOT 仍复用 Bundle 的固定资料，不增加启动时图检查。

## 可复制的普通节点模板

发行包 `kernel/templates/workflow_nodes` 包含 call、call 后等待、wait、send、receive、kill 和普通端口收发的 Python / JS 示例。它们是固定 SDK 声明，需由项目 Plugin 显式贡献；可以更改外观、名称和业务契约。JS 的 `interfaces.mjs` 在打包时从公开 Core 契约生成，不维护另一套协议。详见同目录 README。

## 普通端口节点与迁移

原生 `definition_id:"vibeflow.io"` 和 `io` 字段已移除，旧配置收到 `GRAPH.IO.MIGRATION`。把 receive/send 实现写成普通 SDK Node，在 Plugin 中声明具体输入输出契约、端口 Capability 和 Schema，并显式选择端口授权规则。`vibeflow.io` Ruleset 仍保留终端 IO 检查用途。

Python 的核心实现可以直接是：

```python
def run_pure(self, inputs, params, context):
    received = context.capabilities["vibeflow.port"]["receive"](
        {"port": params["port"]})
    return {"number": received["value"]}
```

发送节点调用 send 后返回 `{}`，不声明业务输出。JS 使用同样的对象请求；receive 声明 `completion:"suspend"`，send 声明 immediate。接收取得值、发送无业务输出的语义保持一致。

旧 IO 隐式充当起点或终点的位置需要增加真实 terminal；一次接收—处理—发送流程因此通常增加两步。普通 IO 不自动取得图边界身份，也不按名称补入资源。Workflow ABI 现为 v9，旧 AOT 必须重建；旧预览 v2 历史继续可读，业务日志、trace 和输出不迁移。

## HTML 审查

页面支持全部入口或指定入口查看，卡片和侧栏显示操作、目标及是否等待。Call/Kill 通过右键菜单跳转至目标 workflow；Send/Receive 按预期交互列表提供多个跳转按钮，跳转后可返回。Call 的目标入口会被选中。只有 Nodeset 提供原地展开/收起；workflow 之间不原地展开。历史快照优先使用当次准备的目标事实，不静默换用最新快照。

快照只携带本次准备的目标架构事实。缺失目标、入口或资源时局部显示原因，不拿历史快照冒充目标。原 SVG 仍仅作可选对照附件。

源码运行只检查所选入口及其实际引用的定义；其他入口的 planned 内容不会阻止已实现入口运行。review/build 仍检查完整工作流，包括任何入口都无法到达的孤立节点。模块装载、源码绑定或编译错误仍会报告。运行历史保存实际入口，首次打开该记录时默认选择此入口。
