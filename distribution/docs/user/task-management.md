# 原生任务管理

每次 workflow 运行拥有自己的任务记录。开发者声明 `flow_kind="task_manager"` 的 Node，并选择 `vibeflow.task_manager` Ruleset。管理 Node 使用 `context.tasks` 启动、停止和等待任务；普通 Node 取得自身取消信号、执行等待和 `finally` 清理，也可以通过普通数据连边传递任务引用。关闭源码规则不会向普通 Node 授予控制接口。管理身份不豁免其他副作用或质量规则。

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

任务引用是普通数据 `{run_id: string, task_id: string}`。名单是普通数组，可复制、筛选、合并或传给另一个管理 Node，框架不修改名单、不因数据连边隐式等待。引用属于本次 workflow；跨运行、未知引用及未知启动槽会报明确合同错误。

| JS 接口 | Python 接口 | 行为 |
| --- | --- | --- |
| `start(key, inputs)` | `start(key, inputs)` | 立即返回独立 TaskRef |
| `await waitAny(refs)` | `wait_any(refs)` | 任一任务实际退出后返回 TaskOutcome；空名单返回 null／None |
| `requestStop(refs, reason?)` | `request_stop(refs, reason=None)` | 返回 StopAck，分别表示 stop_requested 或 already_exited，不等待退出 |
| `await waitAllExited(refs)` | `wait_all_exited(refs)` | 等全部任务实际退出，按名单顺序返回结果；空名单返回空数组 |

这些方法位于 `context.tasks`。Python 管理 Node 必须使用 `run_pure(self, inputs, params, context)`；普通 Node 可继续使用二参形式，或接收可选第三参 context。Python 以线程及完成通知实现，不引入 asyncio。JS 使用事件循环。

TaskOutcome 包含 `task` 引用与 `status`（succeeded、failed、cancelled）。成功时有 `outputs`；失败时有带来源位置的结构化 `error`，不传原始异常对象。StopAck 包含 `task` 与 `state`。重复引用按首次出现顺序去重；先结束后等待、重复等待仍能取得相同最终结果。连续处理任一结果时，应生成排除已处理引用的新数组。

```ts
const refs = ['main', 'io', 'control'].map(key => context.tasks.start(key, {}));
const first = await context.tasks.waitAny(refs);
if (first?.status === 'failed') {
  context.tasks.requestStop(refs.filter(ref => ref.task_id !== first.task.task_id));
}
const results = await context.tasks.waitAllExited(refs);
```

管理 Node 可在自身 `if`、循环中决策，或把结果传给现有 Decision。失败不会自动停止兄弟任务。显式等待的失败可作为业务数据处理；未消费失败在 workflow 最终收尾时报错。

请求停止与实际退出是两个状态。管理 Node 可请求停止后直接返回，但 workflow 正常结束、异常或外部取消都必须停止并等待所属实际执行、Node 的异步 `finally`、SDK 操作及受管后代收尾。不能取消的操作仍属于 workflow，并保持 stopping，直到真实完成；超时不能冒充退出。收尾等待不会被同一取消信号提前截断；收尾期间禁止新启动。

普通 Node 应等待自身工作，或在 `finally` 释放资源。原生计时器、监听器检查按真实接口绑定及拥有／释放方式进行，用户自定义同名方法不会仅因名称被拒绝。规则不尝试证明任意业务的全部清理路径；丢弃 Promise、遗留原生计时器或监听器仍不合法。

任务退出后自动回收活跃执行及控制资源，结果保留至本次 workflow 结束，无需手工关闭遥控器。常驻 workflow 累计启动大量短任务时，结果缓存占用随累计任务数及输出大小增长；选择合理的 workflow 运行边界。

Workflow ABI 为 v6。旧 `async`、`result_key`、`detached` 调用入口与停止等待超时选项必须迁移，没有自动转换层。将旧启动点改为管理 Node 的声明目标，把引用通过数据连边传到显式等待点；独立后台任务也须归属于本次 workflow。迁移后重新生成 Architecture，再执行 validate、quality 和实际运行／构建。
