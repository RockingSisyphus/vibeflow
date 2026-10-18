# 普通图并发沙箱（Python）

通过公开 CLI 和 SDK 验证 12 个普通 worker，经独立 `join_policy: all` 收集节点连接结束节点。启用标准 `vibeflow.workflow` 规则，无独立任务图或管理器。

`run_all.py` 固定执行以下案例，任何断言失败都会使入口失败：

| 案例 | 通过条件 |
| --- | --- |
| 正常分发 | 显式 `max_concurrency: 12`，12 个 worker 通过屏障并全部清理，按声明顺序交付结果，收集节点只执行一次 |
| 容量 4 | 12 个调用、峰值恰好 4；首批最后一个调用完成清理后补入下一项，此时其余三个仍未结束 |
| 默认容量 | 不设置 `max_concurrency`，12 个调用、峰值恰好 8，同样验证即时补位 |
| 回收兼分发 | 同一普通节点以 `all` 汇合后再次分叉；`validate` 和 `build` 都必须退出 1，并报告 `GRAPH.JOIN.FORK_CONFLICT`，不得发布构建产物 |
| 断路 | 删除一个 worker 到收集节点的边；两个 CLI 入口都必须退出 1，并报告 `GRAPH.FLOW.CANNOT_REACH_END`，不得发布构建产物 |

三个正常案例覆盖 `plan`、`block`、`compiled`，以及同一 AOT bundle 的连续两次执行。队列案例使用条件变量：除指定先完成的调用外，首批调用等待下一项启动。若实现等待整批结束才补位，将超时失败；仅进程存在或最终输出正确不能算通过。trace 还检查每个 worker 恰好启动、清理一次，且收集发生在全部清理之后。

运行：

```bash
python sandbox/python/graph_concurrency/run_all.py --work-dir /tmp/vibeflow-python-concurrency --renderer-root /path/to/renderer
```

使用新的工作目录；配置变体由受版本控制的共享案例生成器写入该目录，避免维护重复全图。目录内保留 `report.json`、各反例 CLI 原始输出、各模式运行 trace 和 AOT trace。两 Target 的 integration 入口及根目录 `--full` 均包含此入口；取消、失败与更复杂嵌套场景另见 conformance 和生命周期回归。
