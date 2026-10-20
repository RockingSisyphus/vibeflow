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
    "actions":[{"operation":"call","target":"worker","entry":"main","wait":true},
               {"operation":"wait"}]
  }
}]
```

SDK 声明也可直接选择这些 Rule，调用配置可以覆盖其规则选择。有效权限按完整调用路径保存；同类型的另一处调用不能借用授权。图级限制覆盖其负责的有效子图，节点选择空 Ruleset 不能取消图级限制。`restrict` 默认限制 `vibeflow.workflow` 和 `vibeflow.port`，也可通过 `capabilities` 参数指定其他接口。

`actions` 是作者对操作、目标和等待方式的显式声明，用于图审查和展示；框架不分析任意业务代码来证明声明。调整实现、目标或等待配置时应同步更新它。动态目标可以省略，页面会保留操作说明而不虚构目标图。未提供 actions 时，规则根据明确声明的 operations 输出基本操作说明。

## 接口约定

Node 通过 `context.capabilities["vibeflow.workflow"]` 使用接口。Python 再以 `api["call"](...)` 调用，JS 使用 `api.call(...)`。请求采用与其他 Capability 一致的对象参数。

| 操作 | 请求 | 结果与等待行为 |
|---|---|---|
| `self` | `{}`，也可省略参数 | `{id}`；属于当前 workflow 实例，进入 Nodeset / Loop 不变 |
| `call` | `{target, entry?, inputs?, timeout?}` | 等待宿主注册确认后返回 `{id}`；不等待业务结束 |
| `wait` | `{id, timeout?}` | 等待真实终态，返回 `state`、`outputs`、`error` 等；可重复读取 |
| `send` | `{id, port?, payload}` | 交给本地发送适配器后继续；不等待对端处理，无业务返回值 |
| `receive` | `{port?, timeout?}` | 默认等待消息，返回 `{sender, port, payload}` |
| `kill` | `{id, timeout?}` | 请求宿主停止该实例，等待真实终态；不支持时明确失败 |

默认端口是 `default`，超时以秒计。取消等待只结束当前等待，不自动停止对端。JS 的等待操作使用异步 completion；Python 接入 Node 的取消信号。普通退出先完成本地待发交接，强制退出不保证尚未交接的消息。第一版只支持本机、内存中的普通 JSON；大于跨语言安全整数范围的整数须编码为字符串。

需要一次性子工作时：`call → wait`。需要提前启动长期 workflow 时：`call` 后保存实例 ID，后续使用 `send / receive`，最后由作者安排 `kill` 或正常退出。`call` 没有可直接确认的下游 wait/kill 时产生 warning；普通调用节点可在其参数 schema 中声明 `allow_background`，在 config 设置 `true` 表示作者明确接受长期运行。该警告不证明所有分支都会清理。

实例 ID 是框架生成的不透明身份，不等于 PID，也不会随 PID 复用。作者负责保存、交换身份和业务请求 ID；框架不自动匹配请求与响应。

## 目标和宿主

工作流配置可声明稳定目标别名。workflow 路径相对所属 root，`root` 缺省为当前 root：

```jsonc
"workflow_targets": {
  "worker": {
    "root":"worker_root",
    "workflow":"configs/worker.jsonc",
    "entry":"main",
    "command":["python","-m","vibeflow.coordination","run-python","--bundle","build/worker"],
    "cwd":"../worker",
    "env":{}
  }
}
```

命令是参数数组，不经过 shell；工作目录相对服务配置文件。Windows 路径仍作为单个参数传入，JSON 中反斜杠需要转义。环境初始化、应用窗口、浏览器插件及其权限由作者负责。

使用已安装的 wheel 时，可以通过下面的模块命令启动；解压开发包时改用 `python run.py coordination …`，启动目标的 command 也使用其实际 `run.py` 路径。作者提供的命令必须能在自己的环境找到内核，不依赖父进程临时修改的 Python 导入路径。

先明确启动本机服务：

```bash
python -m vibeflow coordination serve --config communications.jsonc --port 8765
```

`communications.jsonc` 使用相同的 `workflow_targets` 声明；也可直接使用包含它的 workflow 配置。目标别名属于这份服务配置的命名空间；多个 workflow 共用服务时，作者将它们需要的启动目标统一登记，避免同名别名指向不同程序。服务不会自动读取被启动程序的目标配置。服务监听 `127.0.0.1`，不会自动启动或托管已经接入的程序。作者选择本机可信宿主；这不是运行不可信业务代码的隔离沙箱。

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
| `register`：`{id?,workflow?,pid?,stop_supported}` | call 启动的宿主使用环境中的 id；独立宿主省略 id。返回 `{id,inputs,entry}`。每个运行只登记一次，旧终态 ID 不能复用。 |
| `control`：`{id}` | 支持停止的宿主轮询。返回 `{pending:true}`，或 `{stop:true,ended:false}`；宿主收到后取消该次运行，完成实际清理再报告终态。 |
| `complete`：`{id,state,outputs,error}` | `state` 为 succeeded、failed 或 cancelled。输出和错误须为 JSON。宿主必须在真实执行与清理结束后报告。 |
| `send`：`{id,sender,port,payload}` | 将消息交给指定实例邮箱；服务确认入队，不等于业务处理完成。 |
| `receive`：`{id,port}` | 返回 `{sender,port,payload}`，无消息时返回 `{pending:true}` 后继续轮询。 |
| `call`：`{target,entry?,inputs?}` | 返回预留 `{id}`；随后请求 `ready`，直到宿主登记。包装脚本退出不会替代登记。 |
| `ready` / `wait`：`{id}` | 未就绪时返回 `{pending:true}`；ready 返回身份，wait 返回真实终态及输出，可重复读取。 |
| `kill`：`{id}` | 发出停止请求或报告不支持；继续 wait 确认真实结束。 |
| `instances`：`{}` | 返回实例状态列表，供作者诊断和自行清理。 |

轮询由服务短暂等待后响应，宿主可结束当前 HTTP 等待来实现本地取消。取消等待不等于 kill。普通退出前完成本地发送队列的交接；各宿主使用相同的实例与消息地址，不共享线程或进程生命周期。

启动脚本退出不代表 workflow 结束。宿主注册、消息交接和终态报告决定 call/wait 的结果；kill 使用宿主提供的实例停止实现。框架不会因为调用方退出而清理后台实例，不自动建立运行组、进程池或重试。停止整个浏览器、桌面应用或系统服务需要作者明确提供相应宿主实现。

新进程仍有冷启动成本。高频请求适合由作者启动长期 workflow 并通过消息复用；Python AOT 仍复用 Bundle 的固定资料，不增加启动时图检查。

## 可复制的普通节点模板

发行包 `kernel/templates/workflow_nodes` 包含 self、call、call 后等待、wait、send、receive、kill 和普通端口收发的 Python / JS 示例。它们是固定 SDK 声明，需由项目 Plugin 显式贡献；可以更改外观、名称和业务契约。JS 的 `interfaces.mjs` 在打包时从公开 Core 契约生成，不维护另一套协议。详见同目录 README。

## 普通端口节点与迁移

原生 `type_used:"vibeflow.io"` 和 `io` 字段已移除，旧配置收到 `GRAPH.IO.MIGRATION`。把 receive/send 实现写成普通 SDK Node，在 Plugin 中声明具体输入输出契约、端口 Capability 和 Schema，并显式选择端口授权规则。`vibeflow.io` Ruleset 仍保留终端 IO 检查用途。

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

页面支持全部入口或指定入口查看，卡片和侧栏显示操作、目标及是否等待。双击、右键或侧栏按钮可原地展开目标 workflow；多目标通过侧栏选择。循环关系按用户选择逐步展开，保留真实调用边界。

快照只携带本次准备的目标架构事实。缺失目标、入口或资源时局部显示原因，不拿历史快照冒充目标。原 SVG 仍仅作可选对照附件。
