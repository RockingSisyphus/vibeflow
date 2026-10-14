# 原生任务管理

需要同时执行几个任务，并按结束结果决定后续行为时，使用任务管理 Node。例如启动 A、B、C，等待任一任务结束并接收结果；B 失败后保存 B 的结果、从名单移除 B，再请求 A、C 停止，接收它们清理完成后的结果。

开发者声明 `flow_kind="task_manager"` 的 Node，并选择 `vibeflow.task_manager` Ruleset。管理 Node 使用 `context.tasks` 启动、停止和等待任务；普通 Node 取得自身取消信号、执行等待和 `finally` 清理，也可以通过普通数据连边传递任务引用。关闭源码规则不会向普通 Node 授予控制接口。管理身份不豁免其他副作用或质量规则。

## 配置启动目标

调用配置使用 `task_targets` 声明有限的启动槽，槽中的 Node／Nodeset 调用复用正常的输入输出合同、配置和实现绑定。例如：

```jsonc
{
  "id": "launch", "type_used": "example.manager",
  "display_name": "启动并发任务", "description": "启动并监督工作任务",
  "task_targets": {
    "work": {"type_used": "example.worker", "config": {"mode": "service"}}
  }
}
```

只有已编译的槽可启动，不接受函数回调或任意类型名。Architecture 保存管理调用及目标，图中显示启动关系。默认管理节点是浅玫红双圆形，标注“任务管理”；错误和警告保留形状与标识。颜色不会授予控制权限。

## 任务引用与控制接口

任务引用是普通数据 `{run_id: string, task_id: string}`。名单是普通数组，可复制、筛选、合并或传给另一个管理 Node，框架不修改名单、不因数据连边隐式等待。引用属于本次 workflow；跨运行、未知引用及未知启动槽会报明确合同错误。

| JS 接口 | Python 接口 | 行为 |
| --- | --- | --- |
| `start(key, inputs)` | `start(key, inputs)` | 立即返回独立 TaskRef |
| `await waitAny(refs)` | `wait_any(refs)` | 任一任务实际退出后交付并消费 TaskOutcome；空名单返回 null／None |
| `requestStop(refs, reason?)` | `request_stop(refs, reason=None)` | 返回 StopAck，分别表示 stop_requested 或 already_exited，不等待退出 |
| `await waitAllExited(refs)` | `wait_all_exited(refs)` | 等名单中全部任务实际退出，按名单顺序交付并消费结果；空名单返回空数组 |

这些方法位于 `context.tasks`。Python 管理 Node 必须使用 `run_pure(self, inputs, params, context)`；普通 Node 可继续使用二参形式，或接收可选第三参 context。Python 方法同步调用，不使用 `await`。JS 的等待方法必须 `await`，并用 `runWorkflowAsync` 执行异步 workflow。

TaskOutcome 包含 `task` 引用与 `status`（succeeded、failed、cancelled）。成功时有 `outputs`；失败时有带来源位置的结构化 `error`，不传原始异常对象。StopAck 包含 `task` 与 `state`。同一次等待内的重复引用按首次出现顺序去重。任务先结束、父流程后等待，仍能取得结果；结果交付时框架立即删除任务卡，不支持重复查询。父流程保存返回的普通结果数据，并从待处理名单移除对应引用。复制件也会失效，再等待或停止已消费引用报 VF_TASK_REF_INVALID。

```ts
const refs = ['main', 'io', 'control'].map(key => context.tasks.start(key, {}));
const first = await context.tasks.waitAny(refs);
const pending = refs.filter(ref => ref.task_id !== first?.task.task_id);
if (first?.status === 'failed') context.tasks.requestStop(pending);
const results = [...(first ? [first] : []), ...await context.tasks.waitAllExited(pending)];
```

管理 Node 可在自身 `if`、循环中决策，或把结果传给现有 Decision。失败不会自动停止兄弟任务。显式等待的失败可作为业务数据处理；未消费失败在 workflow 最终收尾时报错。

## 停止与清理完成的区别

请求停止与实际退出是两个状态。管理 Node 可请求停止后直接返回，但 workflow 正常结束、异常或外部取消都必须停止并等待所属实际执行、Node 的异步 `finally`、SDK 操作及受管后代收尾。不能取消的操作仍属于 workflow，并保持 stopping，直到真实完成；超时不能冒充退出。收尾等待不会被同一取消信号提前截断；收尾期间禁止新启动。

普通 Node 应等待自身工作，在 `finally` 释放计时器、监听器或其他资源。不能丢弃尚未完成的 Promise 或遗留后台工作。`task_manager` 身份不意味着框架自动清理任意业务资源；释放逻辑仍由持有资源的 Node 编写。

任务退出后释放活跃执行和控制资源；结果只暂存到接收它的 waitAny/waitAllExited 完成交付。交付后任务卡自动回收，无需 release 接口。父流程把结果作为普通数据传给其他节点，后者不再通过旧任务引用查询。常驻 workflow 持续创建并接收短任务时，已交付任务卡不会累积；一直不接收的结果仍会占用空间。业务保存的结果和 trace 历史由各自的用途决定保留期限。

Workflow ABI 为 v6。旧 `async`、`result_key`、`detached` 调用入口与停止等待超时选项必须迁移，没有自动转换层。将旧启动点改为管理 Node 的声明目标，把引用通过数据连边传到显式等待点；独立后台任务也须归属于本次 workflow。迁移后重新生成 Architecture，再执行 validate、quality 和实际运行／构建。

## 输入与输出如何对应

`start` 的第一个参数是 task_targets 的槽名，不是 Node 类型名。第二个参数以目标 `requires[].type` 为键，传入原始业务值。例如 worker 要求 `example.request`，启动写成：

```ts
const ref = context.tasks.start('work', {'example.request': {label: 'A'}});
```

worker 内部仍通过 `inputs['example.request'].value` 读取值；Python 对应 `inputs['example.request']['value']`。不要在 start 时手工添加 `value` 包装。目标的 exactly_one 输入必须提供；all 输入传入数组，保留全部值，空数组可表示没有该类型输入。

成功结果的 `outputs` 以目标 `provides[].key` 为键。如果 worker 声明输出 key 为 `value`，读取 `outcome.outputs.value`，Python 对应 `outcome['outputs']['value']`。失败或取消结果检查 `status` 与 `error`，不按成功输出读取。不要用具体错误码推断所有语言都返回同一种异常；业务判断优先使用 status，错误细节用于报告。

## Python 管理 Node 示例

以下管理 Node 没有外部输入，启动三个已注册的 `example.worker`，按先结束的结果逐个处理；任一失败后停止其余任务，最后返回完整结果名单。worker 要求 example.request 对象，提供自己的业务输出。将 Manage、worker 与所需 DataSchema 一起加入 Plugin.resources，并在 workflow 选择该插件，插件写法见[Python SDK](python-development.md#node-与固定插件)。

```python
from vibeflow.targets.python.sdk import node

@node(
    type_key="example.manager",
    display_name="管理并发任务",
    description="启动工作任务，处理失败并等待退出。",
    flow_kind="task_manager",
    rulesets=["vibeflow.task_manager"],
    contract={
        "requires": [],
        "provides": [{"key": "report", "type": "example.report",
                      "display_name": "任务结果"}],
        "input_semantics": {},
        "output_semantics": {"report": ["所有任务的最终结果。"]},
    },
)
class Manage:
    def run_pure(self, inputs, params, context):
        refs = [context.tasks.start("work", {"example.request": {"label": label}})
                for label in ("A", "B", "C")]
        pending = list(refs)
        received = []
        while pending:
            outcome = context.tasks.wait_any(pending)
            received.append(outcome)
            pending = [ref for ref in pending if ref != outcome["task"]]
            if outcome["status"] == "failed":
                context.tasks.request_stop(pending, "另一个工作任务失败")
                break
        return {"report": [*received, *context.tasks.wait_all_exited(pending)]}
```

## JavaScript/TypeScript 管理 Node 示例

`nodes/manage.ts` 实现同样的策略。这里只展示管理 Node；worker、example.request 对象 schema 和 example.report 数组 schema 由项目插件提供。

```ts
import type {TaskManagerContext} from '@vibeflow/plugin';

export async function run(inputs: any, params: any, context: TaskManagerContext) {
  const refs = ['A', 'B', 'C'].map(label =>
    context.tasks.start('work', {'example.request': {label}}));
  let pending = [...refs];
  const received = [];
  while (pending.length) {
    const outcome = await context.tasks.waitAny(pending);
    if (!outcome) break;
    received.push(outcome);
    pending = pending.filter(ref => ref.task_id !== outcome.task.task_id);
    if (outcome.status === 'failed') {
      context.tasks.requestStop(pending, '另一个工作任务失败');
      break;
    }
  }
  return {report: [...received, ...await context.tasks.waitAllExited(pending)]};
}
```

项目插件中的声明：

```ts
import {defineNode} from '@vibeflow/plugin';

export const manager = defineNode({
  type_key: 'example.manager',
  display_name: '管理并发任务', description: '处理工作任务的结果并等待退出。',
  flow_kind: 'task_manager', rulesets: ['vibeflow.task_manager'],
  contract: {
    requires: [],
    provides: [{key: 'report', type: 'example.report', display_name: '任务结果'}],
    input_semantics: {}, output_semantics: {report: ['所有任务的最终结果。']},
  },
  implementations: [{
    language: 'typescript', targets: ['node', 'browser'], completion: 'suspend',
    source: {kind: 'file', ref: 'nodes/manage.ts', export: 'run'},
  }],
});
```

将 manager 放入固定 plugin 的 resources，并选择该插件。实现路径相对声明模块；若插件文件放在 plugins 子目录，需要相应调整 ref。实现返回 Promise，所以所属 workflow 的 `pipeline.entry_mode` 必须是 `async`。该字段选择异步运行入口，不是已经移除的调用级 async 启动配置。

上述两种声明都可使用：

```jsonc
{
  "id": "manage", "type_used": "example.manager",
  "display_name": "管理任务", "description": "启动三个任务并等待最终结果。",
  "task_targets": {"work": {"type_used": "example.worker"}}
}
```

若使用 Nodeset 作为目标，先通过 `nodeset_imports` 导入定义，然后在 task_targets 的 type_used 引用其 type_key。目标复用 Nodeset 的对外输入输出与配置。

## 普通 Node 如何响应停止

Python 普通 Node 接收可选 context，在工作步骤之间调用 `context.signal.throw_if_aborted()`；等待停止可以调用 `context.signal.wait()`，它返回后仍须执行 finally。JS context.signal 是 AbortSignal，等待操作应接入该信号；手工登记 abort 监听时，在 finally 中移除，若登记时已经 aborted，应立即处理，避免漏掉停止请求。没有响应信号的操作会继续运行，workflow 等待它实际结束，不强制杀线程。

两种语言都将业务资源释放放在 finally 中。清理动作本身应等到完成，不因“已请求停止”而跳过。JS 清理需要异步操作时继续 await；Python 线程需要 join，线程池需要等待 shutdown。业务超时可以触发 requestStop，但不能把超时结果当作 waitAllExited 已完成。

## 跨节点传递与一次接收

启动 Node 可以把 refs 按普通 provides 返回；普通 Node 复制或筛选名单，再交给另一个 task_manager。后者读取 requires 的业务值并调用 context.tasks，目标与结果仍属于同一次 workflow。不要把 context 或控制接口存入数据，也不要在 Node 返回后从后台回调调用该 context。

每次处理 waitAny 结果后排除对应引用，否则下次等待会遇到已消费引用错误。把已接收结果和剩余引用分开传递：前者是普通业务数据，后者只供管理节点接收尚未交付的任务。waitAllExited 返回顺序是名单首次出现顺序，不能据此推断实际完成顺序。不要让多个管理者并发接收同一任务；重叠等待最多交付一次，失败的批量等待不会偷偷消费其余结果。复制名单不复制任务；再次 start 才创建新任务。引用不能跨 workflow 复用。

## 从旧并发配置迁移

1. 把旧并发调用移动到某个管理 Node 的 task_targets；保留原目标 type_used、config、Node/Nodeset 合同与实现。
2. 用 start 创建引用。原 result_key 消费点改为等待 TaskOutcome，再从成功 outputs 读取原业务值；按需要显式转交给后续 Node。
3. 原 detached 工作同样登记为任务；workflow 结束会请求停止并等待它退出。需要持续服务时，应明确本次 workflow 的运行边界。
4. 在 worker 中接入取消并补齐 finally。业务管理逻辑明确哪些失败触发停止，不依赖自动停止兄弟任务。
5. 删除旧 async/result_key/detached 与停止等待超时选项；JS 等待实现声明 suspend，pipeline 使用 async 入口。
6. 重新生成 Architecture，执行 validate、quality 与实际运行/构建。Node/插件与配置命令见[Workflow 与 Config](workflow-and-config.md)和两侧开发手册。

Python 的 `runtime.async_max_workers` 仍可配置工作并发数，名称不表示支持旧调用级 async。管理 Node 的颜色与双圆形只用于识别；修改样式或关闭某个局部规则都不会授予普通 Node 控制权限。

## 从 0.19.x 的重复查询方式迁移

等待接口现为一次交付：waitAny 后删除该引用，将取得的结果保存在父流程；waitAllExited 只接收剩余名单。先等待结束、再 requestStop 的旧写法应改为接收前请求停止，或直接使用已取得结果。需要交给别的节点时，通过 requires/provides 传结果，不传已消费引用。旧重复等待示例须同步修改。底层清理、失败收尾和跨 Node 的未消费引用传递方式保持不变。
