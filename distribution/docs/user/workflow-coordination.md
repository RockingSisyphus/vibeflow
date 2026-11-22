# 命名入口与独立 Workflow 通信

命名入口选择一次运行的执行范围；独立 workflow 通过专用的 `context.workflow` 接口调用和通信。

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

## 多入口与业务语义

若 CLI、浏览器事件或其他入口承诺相同业务判断，让它们的实际调用路径汇入同一套 Node/Nodeset。入口边界负责读取和格式适配，业务分类、合并和领域校验由拥有该职责的节点处理；输出边界适配节点产生的结果。

边界适配保留未知字段、字段缺失与错误类别，交给负责判断的节点处理。入口可以识别自身的词法错误，并保留该错误身份。辅助数据通过 `data bypass` 到达需要它的调用，业务主线仍经过共享处理节点；这些关系由实际 edge 和调用点表达。

## Workflow 专用接口

普通 Node 通过 `context.workflow` 使用固定的协作操作。Python 和 JS 均直接调用方法；Python 等待方法使用 `await`，JS 等待 Node 声明 `completion: "suspend"`。等待流程使用 `pipeline.entry_mode: "async"`。

| 方法 | 请求 | 行为 |
|---|---|---|
| `self()` | 无 | 返回当前实例的 `{id}`，不需要连接通信服务 |
| `invoke_sync` | `{workflow, inputs?}` | 同语言、同进程同步调用，直接返回公开输出 |
| `call` | `{workflow, launch, inputs?, timeout?}` | 等待宿主登记后返回 `{id}`，不等待业务结束 |
| `wait` | `{id, timeout?}` | 等待真实终态，返回状态、输出和错误，可重复读取 |
| `send` | `{id, port?, payload}` | 交给本地发送适配器后继续，不等待业务处理 |
| `receive` | `{port?, timeout?}` | 等待消息，返回 `{sender, port, payload}` |
| `kill` | `{id, workflow, timeout?}` | 停止指定实例，等待实际执行与清理结束 |

未连接宿主时，`self()` 仍可使用；实际调用其他操作时报告未连接或操作不支持。HTTP 宿主不提供同进程同步调用。Node 的取消信号自动传入协作等待；取消等待不停止对端。默认端口为 `default`，超时单位为秒。

Call 在启动前检查调用方是否已取消；已经取消时不再创建新实例。已经发出的启动仍遵守独立实例生命周期。`wait / receive` 的 `timeout: 0` 查询当前结果：已有终态或消息立即返回，否则报告 `VF_WAIT_TIMEOUT`；HTTP 仍需要一次实际请求，超时不是网络传输的硬截止。

实例 ID 属于一次根调用，进入 Nodeset／Loop 不变；新 workflow 使用新 ID。身份不是文件名或 PID。作者负责保存目标实例 ID、交换回信地址和匹配业务请求。通信使用本机、内存中的普通 JSON；跨语言安全整数范围之外的整数编码为字符串。

一次子工作可使用 `call → wait`。长期服务可先 `call`，保存 ID 后多次 `send / receive`，最后正常退出或显式 `kill`。调用方结束不会自动停止独立子 workflow。

```python
async def run_pure(self, inputs, params, context):
    child = await context.workflow.call({
        "workflow": params["workflow"], "launch": params["launch"]})
    return {"result": await context.workflow.wait({"id": child["id"]})}
```

## 操作声明与架构展示

Node 定义使用 `workflow_operations` 保存流程事实，例如：

```jsonc
"workflow_operations": [
  {"operation": "call", "wait": true},
  {"operation": "wait"}
]
```

只接受 `invoke_sync / call / wait / send / receive / kill`；`wait` 布尔属性只用于 Call，默认 `false`。声明用于构建调用描述、启动清单和预览，不能证明任意业务代码的真实行为。已实现调用读取 Node 定义；尚无定义的 planned 调用可以在调用处保存同名声明，planned 调用不进入实际启动清单。

目标及启动方式只放在调用的 `config.workflow`、`config.launch`。Send／Receive 可用 `config.expected_workflows` 描述预期交互对象，它用于展示，不限制消息实际对端。普通副作用检查仍由所选 Rule 负责。

## 目标和宿主

目标和启动方式在具体 Call 节点的 `config` 中声明，不维护顶层目标表：

```jsonc
"config": {
  "workflow": {"root":"worker_root", "path":"configs/worker.jsonc", "entry":"main"},
  "launch": {
    "kind":"process",
    "command":["python","-m","vibeflow.coordination","run-python","--bundle","../worker/build"],
    "cwd":".",
    "env":{}
  },
}
```

`workflow.path` 相对目标 root，`root` 省略时采用当前 workflow 的 root；`entry` 可选，传到现有命名入口选择接口。未指定时使用目标默认入口或唯一入口，多入口无默认值时必须选择。命令不必重复写入口。`launch.cwd` 相对调用 workflow 所属 root，命令是参数数组，不经过 shell。环境初始化、窗口、浏览器权限仍由作者负责。

Kill 节点也必须在 `config.workflow` 声明目标，并从输入取得实例 ID；同一 workflow 运行多份时只停止所选实例。实例归属不匹配会返回 `VF_WORKFLOW_MISMATCH`。Send/Receive 可在 `config.expected_workflows` 中填写上述 workflow 引用列表；它仅描述预期交互，不限制实际通信。

标准节点的流程分类是 `workflow-io`。workflow_operations 只描述操作和等待行为，不重复声明目标、入口或启动方式。

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

call 启动的命令会收到 `VIBEFLOW_COORDINATION_URL` 和 `VIBEFLOW_INSTANCE_ID`，标准接入会自动使用它们。独立接入会取得新的身份。Python 自定义宿主可使用 `targets.python.runtime.workflow_host.run_connected(runtime_factory, ...)`；工厂接收 entry、workflow_session 和 workflow_instance_id，返回新的 Runtime。

直接调用 Runtime／Bundle 时，Python 使用 `workflow_session=client.session()` 并设置 `workflow_instance_id=client.id`；JS 使用 `{workflowSession: client.session(), workflowInstanceId: client.id}`。标准宿主已处理这两个参数。会话的公开合同是上述六种协作操作；应用 API 通过普通运行输入或项目模块使用。

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
| `release`：`{id}` | 显式释放已结束实例的记录；运行中的实例不可释放。 |

轮询由服务短暂等待后响应，宿主可结束当前 HTTP 等待来实现本地取消。取消等待不等于 kill。普通退出前完成本地发送队列的交接；各宿主使用相同的实例与消息地址，不共享线程或进程生命周期。

启动脚本退出不代表 workflow 结束。宿主注册、消息交接和终态报告决定 call/wait 的结果；kill 使用宿主提供的实例停止实现。框架不会因为调用方退出而清理后台实例，不自动建立运行组、进程池或重试。停止整个浏览器、桌面应用或系统服务需要作者明确提供相应宿主实现。

新进程仍有冷启动成本。高频请求适合由作者启动长期 workflow 并通过消息复用；Python AOT 仍复用 Bundle 的固定资料，不增加启动时图检查。

## 普通节点模板

`kernel/templates/workflow_nodes` 提供 Python／JS 的 InvokeSync、Call、CallAndWait、Wait、Send、Receive、Kill。节点是普通 SDK 业务代码；配套 Plugin 只声明示例业务数据类型。修改名称、数据契约和参数即可用于项目，不需要额外的接口资源包。

Python Runtime／Bundle 的运行入口使用 `workflow_session`，JS 的运行选项使用 `workflowSession`。标准宿主和同进程绑定自动提供会话；自定义应用传入对应的固定会话对象。会话只负责 workflow 协作，不承载应用自己的队列或浏览器对象。

## 浏览器与桌面分工

浏览器负责页面交互、桌面 Python 程序负责计算时，分别建立两个 workflow，使用各自 Target 构建。在本机显式启动通信服务，两端通过标准连接宿主接入：

- 浏览器：等待按钮事件 → 准备请求及当前实例回信地址 → Send → Receive → 更新页面。
- 桌面：Loop〔Receive → 计算 → Send〕，使用 `max_iterations: null` 持续处理请求。

例如桌面处理节点收到 `{sender, payload}` 后，将结果发给该 sender：

```python
context.workflow.send({"id": message["sender"],
                       "port": "reply", "payload": result})
```

浏览器直接调用页面 API，例如在异步 Node 执行时建立监听，事件到达后移除监听并返回数据；取消时也移除监听。业务队列和监听由项目普通模块或运行输入中的应用实例管理。不要在声明模块导入时建立监听；同进程应用对象不能通过跨 workflow 的 JSON 消息传递。

页面通过 `runConnected(runWorkflowAsync, {url, workflow, initial})` 接入本机服务；Python 使用下文标准接入命令。两个 workflow 处理相同业务请求，但拥有独立执行生命周期；关闭页面、重连和停止桌面程序由应用显式管理。命名入口只选择一个图的执行范围，不会把浏览器与桌面运行环境合并成一个实例。

## 同进程宿主：Python、Node 与浏览器

Call 的同进程配置为 `"launch":{"kind":"in_process"}`。宿主显式绑定构建描述和执行方法；框架不在运行时扫描工程、审查图或自动注入宿主。Python bundle 的 `workflow_descriptor` 与 JS 生成模块的 `workflowDescriptor` 包含目标引用、模式、命名入口、公开输入输出和已准备的调用声明。

Python 接入现有应用事件循环：

```python
from pathlib import Path
from vibeflow.coordination import Coordinator
from vibeflow.tooling.application.python.bundle import load_bundle
from vibeflow.targets.python.runtime.workflow_host import bind_workflow

scope = Coordinator()
bundle = load_bundle("build/expressions")
def factory(**options):
    return bundle.create_runtime(
        run_dir=Path("runs") / options["workflow_instance_id"], **options)
bind_workflow(scope, bundle.workflow_descriptor, factory)

result = scope.invoke_sync({
    "workflow": bundle.workflow_descriptor["workflow"], "inputs": {}})
# 在应用自己的 async 函数中：
# await scope.run(async_bundle.workflow_descriptor["workflow"], inputs)
# await scope.aclose()
```

Node 与浏览器使用同一个通用组件，以下接线可随应用一起打包：

```javascript
import {Coordinator} from "./kernel/javascript/coordinator.mjs";
import * as expressions from "./build/expressions/workflow.js";
import * as application from "./build/application/workflow.js";

const scope = new Coordinator();
scope.bind(expressions.workflowDescriptor, expressions.runWorkflow);
scope.bind(application.workflowDescriptor, application.runWorkflowAsync);
const value = scope.invoke_sync({
  workflow: expressions.workflowDescriptor.workflow, inputs: {}});
const ended = await scope.run(application.workflowDescriptor.workflow, {});
await scope.close();
```

普通应用可直接使用宿主管理入口；workflow 内的官方调用则受到已准备的调用声明和目标绑定约束。自定义执行方法必须执行描述所对应的产物，框架不会证明任意应用函数的真实业务行为。

两端跨 workflow 数据都采用普通 JSON 和值复制；同进程不会额外开放共享对象引用。通用 JS 组件只需要语言运行环境，不依赖 Node 进程 API、DOM、网络或酒馆 API。页面刷新恢复、资源装载和业务生命周期由应用管理。

异步实例的终态可以重复读取。宿主确认不再需要后调用 Python `scope.release(id)` 或 JS `scope.release(id)`；运行中实例不可释放。关闭同进程作用域会取消并等待其拥有的运行和真实清理，然后释放记录。普通调用方结束不会自动停止独立子 workflow。关闭 HTTP 服务仍不杀死独立进程。

同进程与 HTTP 宿主使用相同的错误报告合同。终态 `error` 保留 `code`、`message`，并在存在时携带 `cause`、`cleanup_errors`；错误组及其他并发执行错误位于 `errors`。Python 没有显式原因且未抑制的隐式异常上下文位于 `context`。循环原因链以 `recursive:true` 标记重复位置。清理或发送失败会补充到原始运行错误中。同步调用仍抛出原始异常对象；跨实例读取的是普通 JSON 错误数据。Python 的取消会等待所属清理与客户端完成交接，清理本身失败时同时保留取消和清理错误。业务失败引发的内部取消不会把失败改报为取消；曾请求停止也不单独决定实例终态。

正常 CLI 退出后的资源清理如果失败，框架报告清理异常，并以 `business_exit` 保留原退出码和来源；清理成功时仍正常返回退出码。

## 相关文档

- [本地预览](local-preview.md)：入口筛选、操作样式与跨 workflow 跳转。
- [普通图并发](graph-concurrency.md)：分支调度与实际收尾。
- [迁移说明](rule-system-migration.md)：旧 IO、同步/异步接口和启动配置升级。
