# 运行日志与状态接口

每次 Python 执行和 Node.js AOT 工作流调用都生成两个日志文件和一个状态文件，供开发者排查问题或自动化程序监控运行。

| 文件 | 内容 |
| --- | --- |
| `vibeflow.log` | 内核诊断、所选级别的运行事件、状态变化和错误 |
| `business.log` | 本次运行的业务 stdout 与 stderr，合并保存；终端继续显示 |
| `status.json` | 当前运行状态、错误、更新时间和业务信息 |

Python 文件默认位于 `runs/<run_id>/`。Node.js AOT 每次调用在当前工作目录的 `runs/` 下创建独立运行目录，也可以通过 `runDir` 指定位置。嵌套 Nodeset、Loop 和框架管理的异步任务共用本次运行的日志与状态。

## 外部监控读取的 JSON

```json
{
  "state": "running",
  "error": null,
  "updated_at": "2026-10-04T13:00:00Z",
  "info": [
    {"id": "training", "value": "epoch 10", "message": "正在训练第10轮"},
    {"loss": 0.125, "accuracy": 0.93}
  ]
}
```

`state`、`error`、`updated_at` 由内核填写。`state` 为 `starting`、`running`、`stopping`、`succeeded` 或 `failed`；`error` 无错误时为 `null`，失败时为字符串。通知判断使用 `state`。`updated_at` 是带 UTC 时区的 ISO 8601 时间。

默认每 60 秒更新一次。启动、进入执行和结束时立即写入；配置或实现加载失败也写入失败状态。每次新运行重新生成状态，清空旧 `info`。结束后保留最终文件。写入通过同目录临时文件原子替换完成，监控程序可以反复读取完整 JSON。

## 业务 Node 更新什么

业务只提交 `info`：一个 JSON 对象数组，对象字段自由定义，`id` 可省略。例如，一个对象写训练轮次，另一个对象写指标。`state/error/updated_at` 继续由内核维护；业务异常按原有执行机制上报，内核据此写入失败状态。

每次更新**替换整个数组**。先提交训练轮次，再单独提交指标，最终缓存就只剩指标；要同时显示两者，须在同一次调用中一起提交。`id` 是业务字段，不触发按 ID 合并。传入 `[]` 清空信息。多个 Node 共用同一缓存，以最后一次完成的更新为准，需持续保留的各项信息由业务统一整理后提交。

更新时框架复制数据到缓存。随后修改原数组或对象不会改变已提交内容；新的进度需要再次调用更新接口。下一次定时刷新、状态变化或结束时写入最新缓存。因此，短于刷新间隔的工作流也会在最终文件中保留最后一次业务更新，定时刷新之间的中间值则可能被下一次更新替换。

对象内可嵌套数组和对象，值使用字符串、有限数值、布尔或 `null`。Python 使用原生 `list/dict/int/float` 等 JSON 类型；训练中的 Tensor 或 NumPy 标量先转换成对应的原生标量，例如标量的 `.item()`。JS/TS 使用普通对象和数组。`NaN`、无穷值、循环引用、函数和其他非 JSON 对象不能作为监控资料。

此接口在实际运行的 Node 内使用。Node 照常返回契约规定的业务输出；监控信息通过缓存另行发布。Python 使用示例和插件登记见[Python SDK](python-development.md#在业务-node-中更新进度)，JS/TS 见[JS/TS SDK](javascript-development.md#在业务-node-中更新进度)。

## Python

```bash
python run.py run --config python_project/configs/main.jsonc \
  --status-file monitoring/status.json --status-interval 60
```

`delegate-cli` 支持相同选项。非零业务退出码写为 `failed`。`--status-file` 为监控提供固定读取位置；相对路径以启动工作目录为基准。多个并发运行应使用不同状态路径。

以下示例展示训练进度 Node 的方法体：声明 `training.metrics` 输入和 `metrics` 输出后，把该 Node 放入选中的插件。输入对象包含本轮的 `epoch/loss/accuracy`，每次被工作流调用时更新监控，并照常传递指标：

```python
from vibeflow.targets.python.sdk import update_run_info

class ReportTrainingProgress:
    def run_pure(self, inputs, params):
        metrics = inputs["training.metrics"]["value"]
        epoch = int(metrics["epoch"])
        update_run_info([
            {"id": "training", "epoch": epoch,
             "message": f"正在训练第{epoch}轮"},
            {"id": "metrics", "loss": float(metrics["loss"]),
             "accuracy": float(metrics["accuracy"])},
        ])
        return {"metrics": metrics}
```

也可在已有训练 Node 的每轮循环结束时直接调用 `update_run_info`，使用该轮真实指标。调用放在 `run_pure` 的执行路径中，保留原方法签名和 Ruleset；模块顶层或仅加载声明的检查阶段没有活动运行上下文。控制台 `print` 由业务日志保存，监控更新使用上述独立接口。

`RuntimeOptions(status_interval=60, status_file="monitoring/status.json")` 提供相同程序接口。项目 `vibeflow_project.jsonc` 的 `runtime` 可设置 `status_interval` 和 `status_file`；命令行选项覆盖项目设置。

Python 的 POSIX/Linux CLI 捕获 Python 输出、原生扩展和子进程写到 stdout/stderr 的内容，包括普通线程的控制台输出。其他平台使用上下文标准流适配。嵌入式 `PipelineRuntime` 按运行上下文捕获 Python 标准流，框架管理的异步任务保留此上下文。自行创建线程时，可以用 `contextvars.copy_context()` 传递上下文，以使用状态更新接口；嵌入式调用的原生文件描述符和子进程输出由宿主负责接入。

## JavaScript / TypeScript

```js
const result = runWorkflow(inputs, {
  runDir: "runs/training",
  statusFile: "monitoring/status.json",
  statusIntervalMs: 60000
});
```

异步入口 `runWorkflowAsync` 使用相同选项。每次 workflow 调用独立记录 `starting`、`running` 和真实终态，信息缓存不跨调用共享。宿主将普通 Capability API 和取消信号传入调用；建立监听、接收消息和关闭资源由图中的显式 Node 完成。

SDK Node 的 `run(inputs, params, context)` 使用运行器提供的第三个参数；把下面的方法放入声明了相同输入输出的 `defineNode` 对象：

```js
run(inputs, params, context) {
  const metrics = inputs["training.metrics"].value;
  context.updateInfo([
    {id: "training", epoch: metrics.epoch,
     message: `正在训练第${metrics.epoch}轮`},
    {id: "metrics", loss: metrics.loss, accuracy: metrics.accuracy},
  ]);
  return {metrics};
}
```

Node.js 构建自动写入文件，并通过独立线程维持文件更新时间，包含主事件循环被同步业务计算占用的阶段。`console` 和 `process.stdout/stderr.write` 进入业务日志，并继续输出到终端。直接继承操作系统文件描述符的子进程输出由调用方接回标准流后保存。

浏览器和底层纯源码生成接口通过 `onStatus(status)` 提供相同快照，由宿主接入存储或外部监控；浏览器定时回调按其事件循环调度。浏览器构建不包含 Node 文件系统适配器。`onTrace` 继续提供原有运行事件。

## 监控判读

独立工作流正常结束写为 `succeeded`；执行异常、取消或非零委托退出写为 `failed`。Node、Plugin 或显式清理抛出的异常按本次 workflow 的实际结果记录。`info` 只描述业务进度，不改变内核状态。进程被强制终止、机器断电或存储不可写时，最后文件可能仍是 `running`；监控程序可结合更新时间和自身进程检查判断是否失联。

普通节点的并发分发、显式汇合、取消与实际收尾合同见[普通图并发](graph-concurrency.md)。

`stopping` 表示停止已请求但所属执行或资源仍在收尾。并发分支、节点清理、插件释放和执行锁均以实际收尾完成为结束边界；取消对等待的关注不会冒充退出。
