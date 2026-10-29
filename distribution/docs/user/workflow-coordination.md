# 命名入口与独立 Workflow 通信

命名入口选择一次运行的执行范围；独立 workflow 通过显式 Capability 操作调用和通信。

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

`workflow-io` 标记流程分类。授权、目标检查和关联提取处理已声明的 `vibeflow.workflow` 操作；应用直接调用 AOT 入口、自定义 Capability 或注入的调度函数，由应用维护调用关系。`vibeflow.port` 描述宿主端口边界，对端 workflow 可用 `expected_workflows` 补充展示关联。

## 接口约定

Node 通过 `context.capabilities["vibeflow.workflow"]` 使用接口。Python 再以 `api["call"](...)` 调用，JS 使用 `api.call(...)`。请求采用与其他 Capability 一致的对象参数。

| 操作 | 请求 | 结果与等待行为 |
|---|---|---|
| `invoke_sync` | `{workflow, inputs?}` | 同语言同进程同步入口，直接返回输出普通值 |
| `call` | `{workflow, launch, inputs?, timeout?}` | 等待宿主注册确认后返回 `{id}`；不等待业务结束 |
| `wait` | `{id, timeout?}` | 等待真实终态，返回 `state`、`outputs`、`error` 等；可重复读取 |
| `send` | `{id, port?, payload}` | 交给本地发送适配器后继续；不等待对端处理，无业务返回值 |
| `receive` | `{port?, timeout?}` | 默认等待消息，返回 `{sender, port, payload}` |
| `kill` | `{id, workflow, timeout?}` | 请求宿主停止该实例，等待真实终态；不支持时明确失败 |

### 当前实例身份：所有 Node 均可读取

任意 Node 都可以通过 `context.workflow.self()` 取得 `{id}`：Python 读取 `context.workflow.self()["id"]`，JavaScript/TypeScript 读取 `context.workflow.self().id`。不需要声明 Capability、选择授权 Rule 或增加独立 Self 节点。例如普通“准备请求”节点可以把当前 ID 写入请求的回信地址。

ID 属于一次 workflow 根调用，进入 Nodeset/Loop 不变，另一独立调用得到新的 ID；它不是配置文件名或日志目录名。标准连接宿主将此 ID 绑定到通信服务登记的实例 ID。不连接通信服务时也能读取本地实例 ID，但读取身份本身不创建邮箱或启动服务。自定义宿主可通过 Python 的 `workflow_instance_id` 或 JavaScript 的运行选项 `workflowInstanceId` 传入其登记的 ID。

默认端口是 `default`，超时以秒计。取消等待只结束当前等待，不自动停止对端。两端的等待操作均使用原生异步 completion，并接入 Node 取消信号。普通退出先完成本地待发交接，强制退出不保证尚未交接的消息。第一版只支持本机、内存中的普通 JSON；大于跨语言安全整数范围的整数须编码为字符串。

需要一次性子工作时：`call → wait`。需要提前启动长期 workflow 时：`call` 后保存实例 ID，后续使用 `send / receive`，最后由作者安排 `kill` 或正常退出。`call` 没有可直接确认的下游 kill 时产生 warning；普通调用节点可在其参数 schema 中声明 `allow_background`，在 config 设置 `true` 表示作者明确接受长期运行。Wait 或 CallAndWait 内置的等待不免除此检查；该警告只检查直接关联的 Kill 声明，不证明所有分支都会清理。

实例 ID 是框架生成的不透明身份，不等于 PID，也不会随 PID 复用。作者负责保存、交换身份和业务请求 ID；框架不自动匹配请求与响应。

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
  "allow_background": false
}
```

`workflow.path` 相对目标 root，`root` 省略时采用当前 workflow 的 root；`entry` 可选，传到现有命名入口选择接口。未指定时使用目标默认入口或唯一入口，多入口无默认值时必须选择。命令不必重复写入口。`launch.cwd` 相对调用 workflow 所属 root，命令是参数数组，不经过 shell。环境初始化、窗口、浏览器权限仍由作者负责。

Kill 节点也必须在 `config.workflow` 声明目标，并从输入取得实例 ID；同一 workflow 运行多份时只停止所选实例。实例归属不匹配会返回 `VF_WORKFLOW_MISMATCH`。Send/Receive 可在 `config.expected_workflows` 中填写上述 workflow 引用列表；它仅描述预期交互，不限制实际通信。

标准节点的流程分类是 `workflow-io`。Rule action 只描述操作和等待行为，不重复声明目标、入口或启动方式。

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

call 启动的命令会收到 `VIBEFLOW_COORDINATION_URL` 和 `VIBEFLOW_INSTANCE_ID`，标准接入会自动使用它们。独立接入会取得新的身份。Python 自定义宿主可使用 `targets.python.runtime.workflow_host.run_connected(runtime_factory, ...)`；工厂接收 entry、capabilities 和 workflow_instance_id，返回新的 Runtime。

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

## 可复制的普通节点模板

发行包 `kernel/templates/workflow_nodes` 包含 call、call 后等待、wait、send、receive、kill 和普通端口收发的 Python / JS 示例。Node 模板复制到 `nodes/`，协议声明由独立 Plugin 提供；可以更改外观、名称和业务契约。JS 的 `interfaces.mjs` 在打包时从公开 Core 契约生成，不维护另一套协议。详见同目录 README。

## 普通端口节点

端口收发由普通 SDK Node 实现：Node 声明具体输入输出契约，Plugin 提供端口 Capability 和 Schema，调用点选择端口授权规则。`vibeflow.io` Ruleset 用于终端 IO 效果检查。

Python 的核心实现可以直接是：

```python
async def run_pure(self, inputs, params, context):
    received = await context.capabilities["vibeflow.port"]["receive"](
        {"port": params["port"]})
    return {"number": received["value"]}
```

发送节点调用 send 后返回 `{}`，不声明业务输出。JS 使用同样的对象请求；receive 声明 `completion:"suspend"`，send 声明 immediate。接收取得值、发送无业务输出的语义保持一致。

接收—处理—发送流程使用真实 terminal 作为起点和终点，端口 Node 位于二者之间。

源码运行只检查所选入口及其实际引用的定义；其他入口的 planned 内容不会阻止已实现入口运行。review/build 仍检查完整工作流，包括任何入口都无法到达的孤立节点。模块装载、源码绑定或编译错误仍会报告。

## 等待与同步调用

call/wait/receive/kill 等待操作要求 workflow 使用 `entry_mode: "async"`。Python 等待 Node 使用 `async def run_pure` 并 await，JS 等待 Node 声明 `completion: "suspend"`。同步计算可通过 InvokeSync 调用同语言、同进程目标。

通过宿主提供的 `operations()` 绑定执行官方节点时，Python 同进程组件与 HTTP 客户端共用即时操作的线程转交逻辑：普通同步节点中的 Send 在宿主事件循环交接消息，节点仍直接返回；HTTP 发送的实际交付由 `flush()` / `finish()` 等待。直接使用底层 Client 方法的应用应在所属事件循环调用它们。

Python 的调用并等待示例：

```python
async def run_pure(self, inputs, params, context):
    api = context.capabilities["vibeflow.workflow"]
    call, wait = api["call"], api["wait"]
    identity = await call({"workflow": params["workflow"],
                                   "launch": params["launch"]})
    return {"result": await wait({"id": identity["id"]})}
```

`invoke_sync({workflow, inputs?})` 是 immediate 操作，直接返回目标的公开输出。使用发行模板中的 `InvokeSync` 节点并声明对应的 Capability 与 Rule；在 `config.workflow` 中填写目标，**无需 launch**。目标必须显式绑定到同语言、同进程的同步执行方法。不能借它调用 HTTP 或系统进程。

每次同步调用建立独立根上下文、身份与权限；Nodeset/Loop 仍属于该次根调用。同步嵌套保留执行锁的必要重入关系，观察记录与调用方分开。返回或抛错后移除本次临时实例，不保留邮箱和终态。异步错误不会被同步“等待完成”；错误声明的待完成对象会立即被拒绝。原始错误和清理错误保留在异常因果链中。

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

普通应用可直接使用宿主管理入口；workflow 内的官方调用则受到已准备的调用声明、目标绑定和节点权限约束。自定义执行方法必须执行描述所对应的产物，框架不会证明任意应用函数的真实业务行为。

两端跨 workflow 数据都采用普通 JSON 和值复制；同进程不会额外开放共享对象引用。通用 JS 组件只需要语言运行环境，不依赖 Node 进程 API、DOM、网络或酒馆 API。页面刷新恢复、资源装载和业务生命周期由应用管理。

异步实例的终态可以重复读取。宿主确认不再需要后调用 Python `scope.release(id)` 或 JS `scope.release(id)`；运行中实例不可释放。关闭同进程作用域会取消并等待其拥有的运行和真实清理，然后释放记录。普通调用方结束不会自动停止独立子 workflow。关闭 HTTP 服务仍不杀死独立进程。

同进程与 HTTP 宿主使用相同的错误报告合同。终态 `error` 保留 `code`、`message`，并在存在时携带 `cause`、`cleanup_errors`；错误组及其他并发执行错误位于 `errors`。Python 没有显式原因且未抑制的隐式异常上下文位于 `context`。循环原因链以 `recursive:true` 标记重复位置。清理或发送失败会补充到原始运行错误中。同步调用仍抛出原始异常对象；跨实例读取的是普通 JSON 错误数据。Python 的取消会等待所属清理与客户端完成交接，清理本身失败时同时保留取消和清理错误。业务失败引发的内部取消不会把失败改报为取消；曾请求停止也不单独决定实例终态。

正常 CLI 退出后的资源清理如果失败，框架报告清理异常，并以 `business_exit` 保留原退出码和来源；清理成功时仍正常返回退出码。

## 相关文档

- [本地预览](local-preview.md)：入口筛选、操作样式与跨 workflow 跳转。
- [普通图并发](graph-concurrency.md)：分支调度与实际收尾。
- [迁移说明](rule-system-migration.md)：旧 IO、同步/异步接口和启动配置升级。
